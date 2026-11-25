# -*- coding: utf-8 -*-
"""add_eplat_mcp.py —— 给指定 preset 注入 mcp-eplat（EPLAT 5S 元数据 MCP 通道）

为什么需要：
  专家要读 5S 设计态元数据（业务术语/数据要素/四级指标/血缘/质量/安全/API），
  唯一合法通道是 MCP 服务 `eplat`（oracle-mcp，streamable-http）。
  DSH 的 preset 是自包含组合：**没挂 mcp-client 就没有这份工具**，
  所以「谁该有 EPLAT」必须显式写进 profile patch，而不是写在提示词里许愿。

纪律（与 doc 的 toolPolicy 一致）：
  - 主理人（data-warehouse-brain-team-lead）**不挂** eplat：只调度不取数。
  - 只挂 7 个 EPLAT 主责专家；其余专家按 owner 转派，禁止自行猜设计态。

用法：
  python tools/add_eplat_mcp.py --dry-run      # 只打印计划
  python tools/add_eplat_mcp.py                # 写盘（幂等，已存在自动跳过）
  python tools/add_eplat_mcp.py --check        # 只校验谁有谁没有

退出码：0 成功/一致；1 --check 发现缺口；2 环境错误
"""
import argparse
import io
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH = os.path.join(os.path.expanduser("~"), ".dsh", "profiles", "desktop", "cordis.patch.yml")

# EPLAT 主责 7 专家（owner=职责域，与 SKILL.md §8 交接表一致）
TARGETS = [
    "sg-metadata",        # 舆图：字段解析 / 表字段血缘 / API（技能 owner）
    "sg-metric-builder",  # 矩衡：指标查重 / 四级链 / 落地清单
    "sg-semantic",        # 铨度：术语 / 数据元 / 口径消歧
    "sg-ontology",        # 鼎元：域 / 对象 / 过程 / ER 入图
    "sg-governance",      # 守钧：质量规则 / 安全分级
    "sg-5s-dev",          # 规枢：平台落地查重 / 建模步骤
    "sg-5s-qa",           # 解枢：设计态对拍 / 排障
]

BLOCK = """          - id: mcp-eplat
            name: '@deepseek-ai/dsh-mcp-client'
            config:
              serverName: eplat
              transport: streamable-http
              url: !!js "process.env.SG_EPLAT_MCP_URL ?? 'http://10.18.136.38:8770/mcp'"
              toolCallTimeoutMs: 120000
            disabled: !!js "process.env.SG_MCP === 'off'"
"""


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def parse_yaml(text):
    sys.path.insert(0, os.path.join(PKG, "tools", "_vendor"))
    import yaml  # noqa

    class L(yaml.SafeLoader):
        pass

    L.add_multi_constructor("!", lambda l, s, n: None)
    L.add_multi_constructor("tag:yaml.org,2002:js", lambda l, s, n: None)
    yaml.load(text, Loader=L)


def preset_span(lines, pid):
    """返回 preset 块的行区间 [start, end)，找不到返回 None。"""
    needle = "    - id: preset-" + pid
    try:
        start = next(i for i, l in enumerate(lines) if l.rstrip() == needle)
    except StopIteration:
        return None
    end = start + 1
    while end < len(lines):
        l = lines[end]
        if l.startswith("    - id: ") or l.startswith("    # ==== DWB-TEAM-END"):
            break
        end += 1
    return start, end


def has_eplat(lines, start, end):
    return any(l.strip() == "- id: mcp-eplat" for l in lines[start:end])


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", default=PATCH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)

    if not os.path.isfile(a.patch):
        print("FAIL: 找不到 patch %s" % a.patch)
        return 2

    raw = io.open(a.patch, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)

    missing, present, notfound = [], [], []
    for pid in TARGETS:
        span = preset_span(lines, pid)
        if span is None:
            notfound.append(pid)
            continue
        (present if has_eplat(lines, *span) else missing).append(pid)

    print("目标 preset：%d 个" % len(TARGETS))
    print("  已挂 eplat：%s" % (", ".join(present) if present else "（无）"))
    print("  待挂       ：%s" % (", ".join(missing) if missing else "（无）"))
    if notfound:
        print("  ⚠ 找不到 preset：%s" % ", ".join(notfound))

    if a.check:
        return 0 if not missing else 1

    if not missing:
        print("无需改动（幂等）")
        return 0

    # 从后往前插入，避免行号偏移
    for pid in sorted(missing, key=lambda p: preset_span(lines, p)[0], reverse=True):
        start, end = preset_span(lines, pid)
        # 去掉块尾空行后再插
        ins = end
        while ins > start + 1 and lines[ins - 1].strip() == "":
            ins -= 1
        lines[ins:ins] = BLOCK.rstrip("\n").split("\n") + [""]
        print("  + %-20s 插入 mcp-eplat（第 %d 行）" % (pid, ins + 1))

    out = nl.join(lines)
    try:
        parse_yaml(out)
    except Exception as e:  # noqa
        print("FAIL: 改后 YAML 解析失败，未写盘：%s" % e)
        return 2

    if a.dry_run:
        print("DRY-RUN 未写盘（YAML 校验通过）")
        return 0
    import datetime
    bak = a.patch + ".bak-eplat-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    io.open(bak, "w", encoding="utf-8", newline="").write(raw)
    print("已备份：%s" % bak)
    io.open(a.patch, "w", encoding="utf-8", newline="").write(out)
    print("已写盘：%s（YAML 校验通过）" % a.patch)
    print("⚠ 需重启 DSH 或新建会话才会加载 mcp-eplat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
