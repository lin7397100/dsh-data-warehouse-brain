#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""batch_materialize_energy.py —— 批量补 QZ/LY 能源类物化 SQL。

只做已被真库验证过的模板（2026-11-18 实测两表可取数）：
  表：SMBB_M_A_GZ01.T_ADS_QZ_ENERGY（泉州）/ T_ADS_LY_ENERGY（罗源）
  列：KPI_ID, KPI_VAL, KPI_TIME
  模板：SELECT KPI_ID, KPI_VAL FROM <表> WHERE KPI_ID=<code> AND TO_CHAR(KPI_TIME,'YYYYMMDD')='$TD$'

不做什么：
  - 不猜周期：只生成日粒度（表数据就是日粒度）；月累计/年均类留给慢车道
  - 不改 registry：只落 .sql 文件，lookup_indicator 按 zb_code 自动发现
  - 不覆盖已有 .sql

用法：
  python tools/batch_materialize_energy.py            # 干跑（只报告）
  python tools/batch_materialize_energy.py --write   # 真正写文件
"""
import argparse, csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKLOG = os.path.join(ROOT, "docs", "materialize-backlog.csv")
SQL_DIR = os.path.join(ROOT, "knowledge", "design", "indicator", "materialized_sql")

TPL = """-- ZB_CODE: {code}
-- ZB_NAME: {name}
-- DOMAIN: 能源采购
-- LEVEL: derived
-- FACTORY: {factory}
-- UNIT: 
-- SOURCE_TABLES: {table}
-- PARAMS: TD
-- ORIGIN: DB2 溯源补登（v1.7 批量：cpot 报表 KPI_ID 命中 {ds}，日粒度，周期待业务方确认）
-- 执行时由 DSL 编译器替换 $TD$/$D4$ 等时间占位符后直投 DB2 MCP，免实时编译。
-- 注意：SQL 文本不要写 FETCH FIRST，服务端自动拼；限量走 limit 参数。
SELECT KPI_ID, KPI_VAL FROM {table} WHERE KPI_ID={code} AND TO_CHAR(KPI_TIME,'YYYYMMDD')='$TD$'
"""

TABLE_MAP = {
    "QZ_ENERGY": ("SMBB_M_A_GZ01.T_ADS_QZ_ENERGY", "泉州闽光"),
    "LY_ENERGY": ("SMBB_M_A_GZ01.T_ADS_LY_ENERGY", "罗源闽光"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(BACKLOG, encoding="utf-8-sig")))
    targets = [r for r in rows if r["action"] == "has_ds_name" and r["source_ds"] in TABLE_MAP]

    existing = {os.path.splitext(f)[0] for f in os.listdir(SQL_DIR) if f.endswith(".sql")}
    written, skipped = 0, 0
    for r in targets:
        code = r["zb_code"].strip()
        if code in existing:
            skipped += 1
            continue
        table, factory = TABLE_MAP[r["source_ds"]]
        body = TPL.format(code=code, name=r["zb_name"], factory=factory, table=table, ds=r["source_ds"])
        path = os.path.join(SQL_DIR, "%s.sql" % code)
        if args.write:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
        written += 1

    print("目标：%d 条（QZ %d + LY %d）" % (
        len(targets),
        sum(1 for r in targets if r["source_ds"] == "QZ_ENERGY"),
        sum(1 for r in targets if r["source_ds"] == "LY_ENERGY")))
    print("已有跳过：%d" % skipped)
    print("将写/已写：%d  %s" % (written, "(DRY RUN，加 --write 落盘)" if not args.write else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
