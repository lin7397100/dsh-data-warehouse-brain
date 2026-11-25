#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""audit_unresolved.py —— 2123 个 unresolved 指标普查与分批。

不编造：只做三件事
  1) 从 indicator_registry.json 按 level 计数
  2) unresolved 按 zb_code 反查 kpi_bindings（kpi_id == zb_code），看能拿到 ds_name 多少
  3) unresolved 按 zb_code 反查 materialized_sql/ 目录，看有没有漏登的 .sql 文件

输出：
  - 控制台汇总
  - docs/materialize-backlog.csv 三列：zb_code, zb_name, factory_div, domain, recoverable(ds_name/empty), action
  - 按 action 分批：
      have_sql_file    = 磁盘上已有 .sql 但 registry 没登记（补登记即可，0 成本）
      has_ds_name      = kpi_bindings 里能查到数据集名（需人工/慢车道把 ds_name 落成 DWS 表）
      fully_orphan     = 既无 .sql 也无 kpi_bindings（业务方补 SQL1，技术侧无法凭空生成）
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "knowledge", "design", "indicator", "indicator_registry.json")
FORM = os.path.join(ROOT, "knowledge", "kb", "indicator_formula_registry.json")
SQL_DIR = os.path.join(ROOT, "knowledge", "design", "indicator", "materialized_sql")
OUT_CSV = os.path.join(ROOT, "docs", "materialize-backlog.csv")


def main():
    reg = json.load(open(REG, encoding="utf-8"))
    inds = reg["indicators"]["indicators"] if "indicators" in reg["indicators"] else reg["indicators"]
    form = json.load(open(FORM, encoding="utf-8"))
    kb = {x.get("kpi_id"): x for x in form.get("kpi_bindings", [])}

    by_level = {}
    for it in inds:
        by_level[it.get("level", "?")] = by_level.get(it.get("level", "?"), 0) + 1
    print("== registry 按 level ==")
    for k, v in sorted(by_level.items(), key=lambda x: -x[1]):
        print("  %-12s %d" % (k, v))

    sql_files = {os.path.splitext(f)[0] for f in os.listdir(SQL_DIR) if f.endswith(".sql")}
    print("磁盘 .sql 文件数：", len(sql_files))

    rows = []
    buckets = {"have_sql_file": 0, "has_ds_name": 0, "fully_orphan": 0}
    for it in inds:
        if it.get("level") != "unresolved":
            continue
        code = str(it.get("zb_code", "")).strip()
        name = it.get("zb_name", "")
        fac = it.get("factory_div", "")
        dom = it.get("domain", "")
        if code in sql_files:
            action = "have_sql_file"
            ds = "(磁盘已有 .sql)"
        elif code in kb:
            action = "has_ds_name"
            ds = kb[code].get("ds_name", "")
        else:
            action = "fully_orphan"
            ds = ""
        buckets[action] += 1
        rows.append([code, name, fac, dom, ds, action])

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zb_code", "zb_name", "factory_div", "domain", "source_ds", "action"])
        w.writerows(rows)

    print("\n== 2123 unresolved 分批 ==")
    for k, v in buckets.items():
        print("  %-16s %d" % (k, v))
    print("\nbacklog CSV：", OUT_CSV)

    # 样例
    print("\n样例（have_sql_file 前 3）：")
    for r in [x for x in rows if x[5] == "have_sql_file"][:3]:
        print("  ", r[:5])
    print("样例（fully_orphan 前 3）：")
    for r in [x for x in rows if x[5] == "fully_orphan"][:3]:
        print("  ", r[:5])


if __name__ == "__main__":
    main()
