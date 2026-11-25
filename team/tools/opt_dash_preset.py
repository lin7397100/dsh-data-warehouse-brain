# -*- coding: utf-8 -*-
"""优化 sg-zhishu-dashboard-designer preset：瘦身 prefix + 关闭 tool-web。

安全策略：
  1. 只改目标 preset 块内的内容（按块边界切片，绝不全局替换）
  2. 改前校验锚点行，锚点不符直接退出（不写盘）
  3. 写盘前用 yaml 解析验证
用法：
  python tools/opt_dash_preset.py --dry-run
  python tools/opt_dash_preset.py
"""
import argparse
import io
import os
import sys

PATCH = os.path.join(os.path.expanduser("~"), ".dsh", "profiles", "desktop", "cordis.patch.yml")
PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(PKG, "agents", "sg-zhishu-dashboard-designer.md")
PRESET_ID = "preset-sg-zhishu-dashboard-designer"
LANG_RULE = (
    "**语言铁律（最高优先级）**：面向用户的一切自然语言输出**始终使用简体中文**；"
    "代码、SQL、字段名、表名、文件路径保持原文不翻译。用户用中文提问时，"
    "禁止用英文整句作答，也不要用英文开头再补中文。"
)
IND = " " * 16


def build_prefix_lines():
    """由 .md 生成 prefix 块内容行（不含 'prefix: |' 行本身）。"""
    md = io.open(MD, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    while md and md[0].strip() == "":
        md.pop(0)
    if not md or not md[0].startswith("# "):
        raise SystemExit("FAIL: %s 首行不是 '# 标题'" % MD)
    out = [""]                      # 块标量首空行（与原格式一致）
    out.append(md[0])               # 标题
    out.append("")
    out.append(LANG_RULE)           # 渲染器注入的语言铁律（源 .md 不带）
    out.append("")
    body = md[1:]
    while body and body[0].strip() == "":
        body.pop(0)
    out.extend(body)
    while out and out[-1].strip() == "":
        out.pop()
    return [IND + l if l.strip() else "" for l in out]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    raw = io.open(PATCH, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)

    # --- 1. 定位 preset 块 ---
    try:
        p_start = next(i for i, l in enumerate(lines) if l.strip() == "- id: " + PRESET_ID)
    except StopIteration:
        raise SystemExit("FAIL: 找不到 %s" % PRESET_ID)
    p_end = p_start + 1
    while p_end < len(lines) and not lines[p_end].startswith("    - id: "):
        p_end += 1
    if p_end >= len(lines):
        raise SystemExit("FAIL: 找不到 preset 块结尾")

    # --- 2. 定位 prefix 块 ---
    try:
        pre = next(i for i in range(p_start, p_end) if lines[i].strip() == "prefix: |")
    except StopIteration:
        raise SystemExit("FAIL: preset 块内找不到 'prefix: |'")
    if not lines[pre].startswith(" " * 14):
        raise SystemExit("FAIL: prefix 行缩进异常: %r" % lines[pre][:30])
    pre_end = pre + 1
    while pre_end < p_end and (lines[pre_end].strip() == "" or lines[pre_end].startswith(IND)):
        pre_end += 1
    while pre_end > pre + 1 and lines[pre_end - 1].strip() == "":
        pre_end -= 1

    old_len = sum(len(l) for l in lines[pre + 1:pre_end])
    new_block = build_prefix_lines()
    new_len = sum(len(l) for l in new_block)

    # --- 3. 关掉 tool-web ---
    block = lines[p_start:p_end]
    hits = [i for i, l in enumerate(block) if l.strip() == "name: '@deepseek-ai/dsh-tool-web'"]
    if len(hits) == 1:
        j = p_start + hits[0]
        if not any("disabled:" in x for x in block[hits[0]:hits[0] + 6]):
            block.insert(hits[0] + 1, " " * 12 + "disabled: true")
    elif len(hits) == 0:
        print("WARN: preset 块内没有 tool-web，跳过")
    else:
        raise SystemExit("FAIL: preset 块内 tool-web 出现 %d 次" % len(hits))

    # --- 4. 写回 ---
    new_lines = lines[:p_start] + block + lines[p_end:]
    # 重新定位 prefix（因为前面插入了 disabled 行，位置可能后移）
    p2 = next(i for i in range(p_start, p_start + len(block)) if new_lines[i].strip() == "prefix: |")
    e2 = p2 + 1
    while e2 < p_start + len(block) and (new_lines[e2].strip() == "" or new_lines[e2].startswith(IND)):
        e2 += 1
    while e2 > p2 + 1 and new_lines[e2 - 1].strip() == "":
        e2 -= 1
    new_lines = new_lines[:p2 + 1] + new_block + new_lines[e2:]
    out = nl.join(new_lines)

    # --- 5. YAML 校验 ---
    sys.path.insert(0, os.path.join(PKG, "tools", "_vendor"))
    try:
        import yaml
    except Exception:
        yaml = None
    if yaml is not None:
        class L(yaml.SafeLoader):
            pass
        L.add_multi_constructor("!", lambda loader, suffix, node: None)
        L.add_multi_constructor("tag:yaml.org,2002:js", lambda loader, suffix, node: None)
        yaml.load(out, Loader=L)
        ok = "YAML OK"
    else:
        ok = "YAML SKIP(no pyyaml)"

    print("prefix:  %d → %d chars  (-%d, -%.1f%%)"
          % (old_len, new_len, old_len - new_len, 100.0 * (old_len - new_len) / old_len))
    print("block:   %d → %d lines" % (p_end - p_start, len(block) + len(new_block) - (e2 - p2 - 1)))
    print("tool-web disabled: %s" % ("yes" if len(hits) == 1 else "n/a"))
    print("validate: %s" % ok)

    if args.dry_run:
        print("DRY-RUN: 未写盘")
        return 0
    io.open(PATCH, "w", encoding="utf-8", newline="").write(out)
    print("WROTE %s" % PATCH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
