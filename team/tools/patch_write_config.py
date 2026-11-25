#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_write_config.py — 数仓专家团面板 · B 档安全标量回写（行级替换，不全量 round-trip）

设计约束（见 docs/panel-config-view-writeback.md）：
  * 只改白名单叶子标量，按「preset 内层 id + 插件 id + 键名」定位唯一一行；
  * 不做 PyYAML 全量 dump，保留 `!!js` 表达式、注释与其余字节；
  * 写前备份，写后用容错 SafeLoader 解析整份 patch；解析失败或 preset 数变化/重复 id 则自动回滚；
  * url 只替换 `!!js process.env.X ?? '...'` 里的兜底默认地址，保留环境变量覆盖外壳。

白名单（B 档，仅 MCP 插件）：
  serverName          string   服务名
  toolCallTimeoutMs   number   调用超时(ms)
  url                 url      兜底默认地址（保留 env 表达式外壳）
"""

import argparse
import io
import os
import re
import shutil
import sys
import datetime

# 优先使用随工具自带的 vendored PyYAML（tools/_vendor/pyyaml），避免依赖 TEMP 下的临时库
_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_vendor", "pyyaml")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


ALLOWED = {
    "serverName": "string",
    "toolCallTimeoutMs": "number",
    "url": "url",
}

PRESET_ID_RE = re.compile(r"^\s+id:\s*([A-Za-z0-9_-]+)\s*$")
PLUGIN_RE = re.compile(r"^(\s*)- id:\s*([A-Za-z0-9_-]+)\s*$")
KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_]+):\s*(.*)$")


def tolerant_loader():
    if yaml is None:
        return None

    class L(yaml.SafeLoader):
        pass

    def _unknown(loader, suffix, node):
        return node.value

    L.add_multi_constructor("tag:yaml.org,2002:js", _unknown)
    L.add_multi_constructor("!", _unknown)
    return L


def load_preset_ids(text, Loader):
    """容错解析，返回 (preset_id 列表, 解析是否成功)。"""
    if yaml is None or Loader is None:
        return None, False
    try:
        data = yaml.load(text, Loader=Loader)
    except Exception:
        return None, False
    ids = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        for pl in entry.get("insert") or []:
            if isinstance(pl, dict) and pl.get("name") == "@deepseek-ai/dsh-agent-preset":
                pid = (pl.get("config") or {}).get("id")
                if pid:
                    ids.append(pid)
    return ids, True


def validate_value(key, kind, raw):
    if kind == "number":
        try:
            n = int(str(raw))
        except (TypeError, ValueError):
            raise ValueError("toolCallTimeoutMs 必须是整数毫秒")
        if n <= 0 or n > 300000:
            raise ValueError("toolCallTimeoutMs 需在 1..300000 之间")
        return str(n)
    if kind == "string":
        v = str(raw).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", v):
            raise ValueError("serverName 仅限字母/数字/下划线/连字符，1..48 位")
        return v
    if kind == "url":
        v = str(raw).strip()
        if not re.match(r"^https?://[^\s'\"]+$", v):
            raise ValueError("url 需为 http(s):// 开头的合法地址")
        return v
    raise ValueError("未知值类型")


def quote_string(v):
    return "'" + v.replace("'", "''") + "'"


def replace_url_fallback(line, new_url):
    """保留 `!!js "process.env.X ?? '...'"` 外壳，仅替换最后一对单引号内兜底地址。"""
    if "??" not in line:
        raise ValueError("url 行不是环境变量兜底表达式，拒绝改写")
    matches = list(re.finditer(r"'([^']*)'", line))
    if not matches:
        raise ValueError("url 表达式中未找到兜底地址")
    m = matches[-1]
    safe = new_url.replace("'", "''")
    return line[:m.start()] + "'" + safe + "'" + line[m.end():]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", required=True)
    ap.add_argument("--preset", required=True)
    ap.add_argument("--plugin", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = args.key
    if key not in ALLOWED:
        print('{"ok": false, "error": "白名单外的键：%s"}' % key)
        return 2
    kind = ALLOWED[key]

    if not os.path.exists(args.patch):
        print('{"ok": false, "error": "patch 文件不存在：%s"}' % __import__("json").dumps(args.patch))
        return 2

    text = io.open(args.patch, encoding="utf-8").read()
    lines = text.splitlines(keepends=True)
    Loader = tolerant_loader()

    # 定位 preset 内层 id 锚点（不以 - 开头的 id 行）
    preset_idx = None
    for i, ln in enumerate(lines):
        m = PRESET_ID_RE.match(ln)
        if m and m.group(1) == args.preset:
            preset_idx = i
            break
    if preset_idx is None:
        print('{"ok": false, "error": "未找到 preset：%s"}' % args.preset)
        return 2

    # preset 块边界：向上找 preset- 列表项，向下找下一个 preset- 列表项
    list_item_re = re.compile(r"^(\s*)- id:\s*preset-")
    block_start = preset_idx
    for j in range(preset_idx, -1, -1):
        if list_item_re.match(lines[j]):
            block_start = j
            break
    block_end = len(lines)
    for j in range(preset_idx + 1, len(lines)):
        if list_item_re.match(lines[j]):
            block_end = j
            break

    # 在块内定位插件条目
    plugin_idx = None
    plugin_indent = None
    for j in range(block_start, block_end):
        m = PLUGIN_RE.match(lines[j])
        if m and m.group(2) == args.plugin:
            plugin_idx = j
            plugin_indent = len(m.group(1))
            break
    if plugin_idx is None:
        print('{"ok": false, "error": "preset 内未找到插件：%s"}' % args.plugin)
        return 2

    # 插件块边界：下一个同缩进 - id: 或缩进回退
    plugin_end = len(lines)
    for j in range(plugin_idx + 1, block_end):
        m = PLUGIN_RE.match(lines[j])
        if m and len(m.group(1)) <= plugin_indent:
            plugin_end = j
            break
        km = KEY_RE.match(lines[j])
        if km and len(km.group(1)) <= plugin_indent and not lines[j].lstrip().startswith("-"):
            plugin_end = j
            break

    # 在插件块内定位目标键
    key_idx = None
    key_indent = None
    for j in range(plugin_idx, plugin_end):
        m = KEY_RE.match(lines[j])
        if m and m.group(2) == key:
            key_idx = j
            key_indent = len(m.group(1))
            break
    if key_idx is None:
        print('{"ok": false, "error": "插件 %s 内未找到键：%s"}' % (args.plugin, key))
        return 2

    try:
        new_value = validate_value(key, kind, args.value)
    except ValueError as e:
        print('{"ok": false, "error": "%s"}' % e)
        return 2

    old_line = lines[key_idx]
    if kind == "number":
        new_line = " " * key_indent + "%s: %s\n" % (key, new_value)
    elif kind == "string":
        new_line = " " * key_indent + "%s: %s\n" % (key, quote_string(new_value))
    else:  # url
        new_line = replace_url_fallback(old_line.rstrip("\r\n"), new_value) + "\n"

    if new_line == old_line:
        print('{"ok": true, "changed": false, "message": "值未变化"}')
        return 0

    new_lines = lines[:]
    new_lines[key_idx] = new_line
    new_text = "".join(new_lines)

    # 写后校验：容错解析 + preset 数/重复 id 不变
    new_ids, ok = load_preset_ids(new_text, Loader)
    old_ids, old_ok = load_preset_ids(text, Loader)
    if not ok or not old_ok:
        print('{"ok": false, "error": "YAML 解析校验不可用（缺 PyYAML），已中止，未写盘"}')
        return 2
    if len(new_ids) != len(old_ids) or set(new_ids) != set(old_ids):
        print('{"ok": false, "error": "写后 preset 集合变化，已中止，未写盘"}')
        return 2
    if len(new_ids) != len(set(new_ids)):
        print('{"ok": false, "error": "出现重复 preset id，已中止，未写盘"}')
        return 2

    if args.dry_run:
        print('{"ok": true, "dry_run": true, "line": %d, "old": %s, "new": %s}' % (
            key_idx + 1,
            __import__("json").dumps(old_line.rstrip()),
            __import__("json").dumps(new_line.rstrip())))
        return 0

    backup = args.patch + ".bak-panel-write-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(args.patch, backup)
    io.open(args.patch, "w", encoding="utf-8", newline="").write(new_text)

    # 落盘后再解析一次，失败则回滚
    check_text = io.open(args.patch, encoding="utf-8").read()
    check_ids, check_ok = load_preset_ids(check_text, Loader)
    if not check_ok or set(check_ids) != set(old_ids) or len(check_ids) != len(set(check_ids)):
        shutil.copy2(backup, args.patch)
        print('{"ok": false, "error": "落盘后校验失败，已回滚备份", "backup": %s}' % __import__("json").dumps(backup))
        return 2

    print('{"ok": true, "changed": true, "line": %d, "backup": %s, "old": %s, "new": %s}' % (
        key_idx + 1, __import__("json").dumps(backup),
        __import__("json").dumps(old_line.rstrip()),
        __import__("json").dumps(new_line.rstrip())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
