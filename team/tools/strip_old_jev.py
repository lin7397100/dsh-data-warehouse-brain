#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""strip_old_jev.py —— 清理 cordis.patch.yml 里**任意历史版本**的 jev 判定块（幂等）

背景：enable_jev.py 的 strip_blocks 只认得「当前版本」的 LEAD_BEGIN/FAST_BEGIN 字面量，
升级版本号（v1.5 → v1.6）后，旧块不会被识别，直接 apply 会得到 END=4 的双份块。
本脚本按**模式**（不是字面量）识别 1.x 任意版本的 jev 块并整段删除，供升级时先清场。

用法：
    python strip_old_jev.py --file cordis.patch.yml            # 清场（只删 jev 块）
    python strip_old_jev.py --file cordis.patch.yml --dry-run  # 只报告会删几段
"""
import argparse
import io
import re
import sys

# 块首行模式（覆盖 v1.x 各版本措辞差异）
BEGIN_PAT = r"(?:^[ \t]*\*\*⏩ v1\.\d+ jev 判定闸.*?$|^[ \t]*## jev 判定闸（第 1\.5 步.*?$)"
END_PAT = r"^[ \t]*<!-- <<< DWB-JEV v\d+ <<< -->[ \t]*$"

PATTERN = re.compile(BEGIN_PAT + r"\r?\n(?:.*?\r?\n)*?" + END_PAT + r"\r?\n", re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = io.open(args.file, encoding="utf-8").read()
    hits = list(PATTERN.finditer(raw))
    print("识别到 jev 块：%d 段" % len(hits))
    for i, m in enumerate(hits, 1):
        first = m.group(0).strip().splitlines()[0][:90]
        print("  #%d 起始行字符偏移 %d ｜ %s" % (i, m.start(), first))
    if args.dry_run:
        return 0

    cleaned = PATTERN.sub("", raw)
    # 收缩连续空行（最多留两行）
    cleaned = re.sub(r"(?:\r?\n){4,}", lambda mm: "\n" * 3 if "\r\n" not in raw else "\r\n" * 3, cleaned)
    io.open(args.file, "w", encoding="utf-8", newline="").write(cleaned)
    print("已删除 %d 段，文件 %d → %d 字符" % (len(hits), len(raw), len(cleaned)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
