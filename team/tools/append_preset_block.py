# -*- coding: utf-8 -*-
"""append_preset_block.py —— 在指定 preset 的 persona prefix **末尾**追加一块内容（幂等）

为什么需要：agents/*.md 是「详细知识库」，patch prefix 是「浓缩手册」，两者体积差 2~3 倍，
直接 sync_persona 会撑爆上下文。本脚本只做**定点追加**，不动已有内容。

用法：
    python tools/append_preset_block.py --agent sg-gzprod --marker "## 生产管制报表导出" --block-file blk.md
"""
import argparse
import io
import os
import sys

PATCH = os.path.join(os.path.expanduser("~"), ".dsh", "profiles", "desktop", "cordis.patch.yml")
IND = " " * 16


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--marker", required=True, help="幂等标记（块首行应包含它）")
    ap.add_argument("--block-file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    raw = io.open(PATCH, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    if a.marker in raw:
        print("SKIP: 「%s」已存在" % a.marker)
        return 0
    block_txt = io.open(a.block_file, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")

    lines = raw.split(nl)
    i = next((k for k, l in enumerate(lines) if l.strip() == "- id: preset-" + a.agent), None)
    if i is None:
        print("FAIL: 找不到 preset-%s" % a.agent)
        return 2
    j = i + 1
    while j < len(lines) and not lines[j].startswith("    - id: "):
        j += 1
    pre = next((k for k in range(i, j) if lines[k].strip() == "prefix: |"), None)
    if pre is None:
        print("FAIL: preset 内无 'prefix: |'")
        return 2
    e = pre + 1
    while e < j and (lines[e].strip() == "" or lines[e].startswith(IND)):
        e += 1
    while e > pre + 1 and lines[e - 1].strip() == "":
        e -= 1

    block = [""] + [IND + l if l.strip() else "" for l in block_txt.split("\n")]
    new_lines = lines[:e] + block + lines[e:]
    new = nl.join(new_lines)

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "tools", "_vendor"))
    import yaml

    class L(yaml.SafeLoader):
        pass

    L.add_multi_constructor("!", lambda l, s, n: None)
    L.add_multi_constructor("tag:yaml.org,2002:js", lambda l, s, n: None)
    yaml.load(new, Loader=L)

    old = sum(len(x) for x in lines[pre + 1:e])
    newc = sum(len(x) for x in block)
    print("%s: %d → %d 字符（+%d）%s" % (a.agent, old, old + newc, newc,
                                          "｜DRY" if a.dry_run else "｜已写盘"))
    if not a.dry_run:
        io.open(PATCH, "w", encoding="utf-8", newline="").write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
