#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""adhoc_discover.py —— 即席构建 Step 0/1 的素材发现工具。

给 sg-development / sg-metric-builder / sg-ontology-modeler 用：
  - 零 SQL1 指标要从 ODS 建 SQL 时，先拿真 DDL，不编表名。
  - 本地语料（K1 表结构 / K2 存储过程目录 / procedure_catalog.json）做二次佐证。

用法：
  python tools/adhoc_discover.py --search "ZZ00"              # 列 schema 下含 ZZ00 的表
  python tools/adhoc_discover.py --describe SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_0002
  python tools/adhoc_discover.py --corpus "圆棒产量"           # 本地语料搜表/过程
  python tools/adhoc_discover.py --procedure "圆棒"            # 存储过程目录搜
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mcp_db2  # noqa: E402

CORPUS_DIR = os.path.join(ROOT, "knowledge", "corpus")
PROC_CAT = os.path.join(ROOT, "knowledge", "corpus", "ontology", "procedure_catalog.json")


def search_tables(pattern):
    """在已知业务 schema 里搜表。"""
    schemas = ["SMBB_M_S_ZZ00", "SMBB_M_S_NY00", "SMBB_M_S_CG00", "SMBB_M_S_YX00",
               "SMBB_M_A_GZ01", "SMBB_M_S_CB00", "SMBB_M_O_SGM1M1"]
    out = []
    for sch in schemas:
        r = mcp_db2.call_tool("list_tables", {"schema": sch, "pattern": "%" + pattern + "%"})
        if r.get("ok"):
            for row in r["rows"]:
                out.append({"schema": sch, "table": row[0] if row else "", "extra": row[1:] if len(row) > 1 else []})
        else:
            out.append({"schema": sch, "error": r.get("error", "")[:120]})
    return out


def describe_table(fq):
    """fq = SCHEMA.TABLE"""
    parts = fq.split(".")
    if len(parts) != 2:
        return {"error": "格式应为 SCHEMA.TABLE"}
    sch, tab = parts
    r = mcp_db2.call_tool("describe_table", {"schema": sch, "table": tab})
    return r


def search_corpus(keyword):
    """在 K1/K2 语料里 grep。"""
    hits = []
    for root, _, files in os.walk(CORPUS_DIR):
        for f in files:
            if not f.endswith((".md", ".json", ".txt")):
                continue
            p = os.path.join(root, f)
            try:
                txt = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for i, line in enumerate(txt.splitlines(), 1):
                if keyword in line:
                    hits.append({"file": os.path.relpath(p, ROOT), "line": i, "text": line.strip()[:200]})
                    if len(hits) >= 30:
                        return hits
    return hits


def search_procedure(keyword):
    if not os.path.exists(PROC_CAT):
        return {"error": "procedure_catalog.json 不存在", "hits": []}
    cat = json.load(open(PROC_CAT, encoding="utf-8"))
    items = cat if isinstance(cat, list) else cat.get("procedures", cat.get("items", []))
    hits = []
    for it in items:
        s = json.dumps(it, ensure_ascii=False)
        if keyword in s:
            hits.append(it)
            if len(hits) >= 20:
                break
    return {"total": len(items), "hits": hits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", help="表名片段（跨业务 schema 搜）")
    ap.add_argument("--describe", help="SCHEMA.TABLE")
    ap.add_argument("--corpus", help="本地语料关键词")
    ap.add_argument("--procedure", help="存储过程目录关键词")
    args = ap.parse_args()

    if args.search:
        print(json.dumps(search_tables(args.search), ensure_ascii=False, indent=2))
    elif args.describe:
        print(json.dumps(describe_table(args.describe), ensure_ascii=False, indent=2))
    elif args.corpus:
        print(json.dumps(search_corpus(args.corpus), ensure_ascii=False, indent=2))
    elif args.procedure:
        print(json.dumps(search_procedure(args.procedure), ensure_ascii=False, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
