# -*- coding: utf-8 -*-
"""批量物化 26 个高炉燃料比指标（LT01 表，PROD_ITEM_CODE='燃料比'）。

BF 映射（实查 2026-11-17）：
  BF10=1#高炉(508)  BF11=2#高炉(0停)  BF12=3#高炉(509)
  BF14=4#高炉(0停)  BF15=5#高炉(0停)  BF16=6#高炉(507)
"""
import os, json, sys

ROOT = os.path.expanduser(r"~\Documents\deepseek-harness\data-warehouse-brain-team")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mcp_db2  # noqa: E402

# 高炉编号 → BF code
BF_MAP = {
    "1#": "BF10", "2#": "BF11", "3#": "BF12",
    "4#": "BF14", "5#": "BF15", "6#": "BF16",
}

# 待物化的孤儿指标（zb_code → zb_name）
TARGETS = [
    # 1100xxx 系列：4#/5#/6# 日/月/年
    ("1100024", "4#高炉日燃料比", "日"),
    ("1100025", "5#高炉日燃料比", "日"),
    ("1100026", "6#高炉日燃料比", "日"),
    ("1100027", "4#高炉月燃料比", "月"),
    ("1100028", "5#高炉月燃料比", "月"),
    ("1100029", "6#高炉月燃料比", "月"),
    ("1100030", "4#高炉年燃料比", "年"),
    ("1100031", "5#高炉年燃料比", "年"),
    ("1100032", "6#高炉年燃料比", "年"),
    # 500xxx 系列：1#/2#
    ("5001028", "炼铁1#高炉日燃料比", "日"),
    ("5001029", "炼铁1#高炉月均燃料比", "月"),
    ("5001030", "炼铁1#高炉年均燃料比", "年"),
    ("5001031", "炼铁2#高炉日燃料比", "日"),
    # 604xxx 系列：1#/2#/3#
    ("6047810", "1#高炉燃料比-月", "月"),
    ("6047900", "2#高炉燃料比", "月"),
    ("6048010", "3#高炉燃料比-月", "月"),
    ("6047820", "1#高炉燃料比-年", "年"),
]

# 时间粒度 → WORK_DATE 过滤（日=当天，月=当月平均，年=当年平均）
# LT01 表本身是日粒度，月/年需要 AVG
def build_sql(bf_code, grain):
    table = "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LT01"
    base = f"PROD_ITEM_CODE='燃料比' AND PROD_UNIT_CODE='{bf_code}'"
    if grain == "日":
        return f"SELECT PROD_ITEM_VALUE FROM {table} WHERE {base} AND WORK_DATE='$TD$'"
    elif grain == "月":
        # 月平均：当月 AVG
        return f"SELECT AVG(PROD_ITEM_VALUE) FROM {table} WHERE {base} AND WORK_DATE LIKE SUBSTR('$TD$',1,4)||SUBSTR('$TD$',5,2)||'%'"
    else:  # 年
        return f"SELECT AVG(PROD_ITEM_VALUE) FROM {table} WHERE {base} AND WORK_DATE LIKE SUBSTR('$TD$',1,4)||'%'"


def main():
    mat_dir = os.path.join(ROOT, "knowledge", "design", "indicator", "materialized_sql")
    reg_path = os.path.join(ROOT, "knowledge", "design", "indicator", "indicator_registry.json")
    reg = json.load(open(reg_path, encoding="utf-8"))
    inds = reg["indicators"]["indicators"]
    idx = {str(v.get("zb_code", "")): v for v in inds}

    ok = skip = 0
    for zb, name, grain in TARGETS:
        # 找高炉编号
        bf = None
        for k, v in BF_MAP.items():
            if k in name:
                bf = v; break
        if not bf:
            print(f"  [跳过] {zb} {name}: 无法识别高炉编号"); skip += 1; continue

        sql = build_sql(bf, grain)
        # 真取验证（用 20261117）
        test_sql = sql.replace("$TD$", "20261117")
        r = mcp_db2.execute(test_sql, limit=1)
        val = r["rows"][0][0] if r.get("ok") and r.get("rows") else "无数据"
        if not r.get("ok"):
            print(f"  [跳过] {zb} {name}: {r.get('error','')[:60]}"); skip += 1; continue

        # 写 .sql
        with open(os.path.join(mat_dir, f"{zb}.sql"), "w", encoding="utf-8") as f:
            f.write(f"-- ZB_CODE: {zb}\n-- ZB_NAME: {name}\n-- DOMAIN: 生产管制\n-- LEVEL: atomic\n")
            f.write(f"-- SOURCE_TABLES: SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LT01\n-- PARAMS: $TD$\n")
            f.write(f"-- ORIGIN: 高炉燃料比专项物化（{bf}，{grain}粒度）\n")
            f.write(f"-- 真取验证 20261117: {val}\n")
            f.write(sql + "\n")

        # 更新 registry
        if zb in idx:
            idx[zb]["level"] = "atomic"
            idx[zb]["status_note"] = f"高炉燃料比专项物化（{bf}，{grain}）"
            idx[zb]["source_tables"] = ["SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LT01"]
            idx[zb]["materialized_sql_file"] = f"materialized_sql/{zb}.sql"
            idx[zb]["maturity"] = "production"
        print(f"  [OK] {zb} {name:25s} -> {bf} = {val}")
        ok += 1

    json.dump(reg, open(reg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n=== 完成: {ok} 成功, {skip} 跳过 ===")


if __name__ == "__main__":
    main()
