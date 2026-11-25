# -*- coding: utf-8 -*-
"""数据画像脚本 —— 对 CSV 做快速摸底。

用法：
    python data_profiler.py <csv_path> [--rows 100000] [--out report.md]

输出：字段级画像（类型/空值率/基数/数值分布/异常值提示）。
仅依赖标准库，无需安装第三方包。
"""
import argparse
import csv
import json
import math
import os
import sys
from collections import Counter


def infer_type(values):
    """推断字段类型：int / float / date / str"""
    sample = [v for v in values if v not in ("", None)][:1000]
    if not sample:
        return "empty"
    if all(_is_int(v) for v in sample):
        return "int"
    if all(_is_float(v) for v in sample):
        return "float"
    if all(_is_date(v) for v in sample):
        return "date"
    return "str"


def _is_int(v):
    try:
        int(v)
        return True
    except Exception:
        return False


def _is_float(v):
    try:
        float(v)
        return True
    except Exception:
        return False


def _is_date(v):
    s = str(v)
    return len(s) >= 8 and s[:4].isdigit() and s[4] in "-/." or (len(s) == 8 and s.isdigit())


def profile(path, max_rows=100000):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        cols = {c: [] for c in fields}
        n = 0
        for row in reader:
            n += 1
            if n > max_rows:
                break
            for c in fields:
                cols[c].append(row.get(c, ""))

    report = {"file": path, "rows_scanned": n, "fields": []}
    for c in fields:
        vals = cols[c]
        nonnull = [v for v in vals if v not in ("", None)]
        null_rate = 1 - len(nonnull) / len(vals) if vals else 1.0
        ftype = infer_type(vals)
        item = {"field": c, "type": ftype, "null_rate": round(null_rate, 4),
                "cardinality": len(set(nonnull))}
        if ftype in ("int", "float") and nonnull:
            nums = [float(v) for v in nonnull]
            nums_sorted = sorted(nums)
            q1 = nums_sorted[int(len(nums_sorted) * 0.25)]
            q3 = nums_sorted[int(len(nums_sorted) * 0.75)]
            iqr = q3 - q1
            mean = sum(nums) / len(nums)
            std = math.sqrt(sum((x - mean) ** 2 for x in nums) / len(nums)) if len(nums) > 1 else 0
            outliers = sum(1 for x in nums if x < q1 - 1.5 * iqr or x > q3 + 1.5 * iqr)
            item.update({"min": min(nums), "max": max(nums), "mean": round(mean, 4),
                         "std": round(std, 4), "p25": q1, "p50": nums_sorted[len(nums_sorted) // 2],
                         "p75": q3, "outliers_iqr": outliers})
        elif nonnull:
            top = Counter(nonnull).most_common(5)
            item["top_values"] = top
        report["fields"].append(item)
    return report


def to_markdown(report):
    lines = ["# 数据画像报告", ""]
    lines.append(f"- 文件：`{report['file']}`")
    lines.append(f"- 扫描行数：{report['rows_scanned']:,}")
    lines.append("")
    lines.append("| 字段 | 类型 | 空值率 | 基数 | 关键统计 |")
    lines.append("|---|---|---|---|---|")
    for f in report["fields"]:
        if f["type"] in ("int", "float") and "mean" in f:
            stat = f"min {f['min']} / p50 {f['p50']} / max {f['max']} / 均值 {f['mean']} / 异常点 {f['outliers_iqr']}"
        elif "top_values" in f:
            stat = "Top3: " + ", ".join(f"{k}({v})" for k, v in f["top_values"][:3])
        else:
            stat = "-"
        lines.append(f"| {f['field']} | {f['type']} | {f['null_rate']:.1%} | {f['cardinality']} | {stat} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--rows", type=int, default=100000)
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.csv_path):
        print(f"文件不存在：{args.csv_path}", file=sys.stderr)
        sys.exit(1)

    rep = profile(args.csv_path, args.rows)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        md = to_markdown(rep)
        print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(to_markdown(rep) if not args.json else json.dumps(rep, ensure_ascii=False, indent=2))
        print(f"\n已写入：{args.out}")


if __name__ == "__main__":
    main()
