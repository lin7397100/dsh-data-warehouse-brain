#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 16 张表的文本型「下钻链接」列换成真正的 FIELD_TYPE_URL 链接字段。
流程（每张表）：新建链接列(临时名) → 搬 URL 数据 → 校验行数一致 → 删旧文本列 → 改名「下钻链接」。
"""
import sys, time, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wecom_smartsheet_sync as S

# 目标文档 docid：默认复用《钢铁料耗·炼钢成本 指标血缘与本体建模》；
# 换文档时设环境变量 WECOM_DOCID 覆盖，保持脚本可复用。
TARGET = os.environ.get("WECOM_DOCID", "s3_AMAA4RTkAAA0q7TKZxkTZ668rLE5Y_a")
TMP = "下钻链接_新"
URL_PROP = {"type": "LINK_TYPE_PURE_TEXT"}

# 16 张含 TEXT 链接列的表（S01/S20/S14 已是 URL 类型，跳过）
TABLES = ["02_趋势明细_炼钢成本", "03_同比环比", "04_血缘链路_按工厂(L2)",
          "05_指标血缘矩阵_13列", "07_工厂维度字典", "08_DWS逐日明细_202609",
          "09_DWD临时表_一炼钢11", "09_DWD临时表_二炼钢12", "09_DWD临时表_本部三明11+12",
          "09_DWD临时表_罗源14", "09_DWD临时表_泉州13",
          "10_ODS原始明细_二炼钢12", "10_ODS原始明细_本部三明11+12",
          "10_ODS原始明细_罗源14", "10_ODS原始明细_泉州13",
          "11_下钻链接索引"]

sheets = {s["title"]: s["sheet_id"] for s in S.list_sheets(TARGET)}
ok, fail, skip = [], [], []

def cell_link(v):
    """从旧单元格取 (text, link)。"""
    if not v:
        return None
    c = v[0]
    text = c.get("text", "")
    link = c.get("link") or text
    if not link:
        return None
    return (text or link, link)

for title in TABLES:
    sid = sheets.get(title)
    if not sid:
        fail.append((title, "表不存在")); continue
    try:
        flds = S.get_fields(TARGET, sid)
        col_old = next((f for f in flds if f["field_title"] == "下钻链接"), None)
        if not col_old:
            skip.append((title, "无下钻链接列")); continue
        if col_old["field_type"] == "FIELD_TYPE_URL":
            skip.append((title, "已是链接字段")); continue

        # 1) 新建链接列
        S.api("wedoc/smartsheet/add_fields", {"docid": TARGET, "sheet_id": sid,
             "fields": [{"field_title": TMP, "field_type": "FIELD_TYPE_URL",
                         "property_url": URL_PROP}]})
        time.sleep(0.4)

        # 2) 搬数据
        recs = list(S.iter_records(TARGET, sid, page=200))
        upd, old_n = [], 0
        for r in recs:
            cl = cell_link(r.get("values", {}).get("下钻链接"))
            if cl:
                old_n += 1
                upd.append({"record_id": r["record_id"],
                            "values": {TMP: [{"type": "url", "text": cl[0], "link": cl[1]}]}})
        for i in range(0, len(upd), 100):
            S.api("wedoc/smartsheet/update_records",
                  {"docid": TARGET, "sheet_id": sid, "records": upd[i:i + 100]})
            time.sleep(0.3)

        # 3) 校验搬齐
        new_n = sum(1 for r in S.iter_records(TARGET, sid, page=200)
                    if r.get("values", {}).get(TMP))
        if new_n != old_n:
            fail.append((title, f"搬迁不全 旧{old_n} 新{new_n}，保留旧列未删")); continue

        # 4) 删旧文本列 + 改名
        S.api("wedoc/smartsheet/delete_fields",
              {"docid": TARGET, "sheet_id": sid, "field_ids": [col_old["field_id"]]})
        time.sleep(0.5)
        flds2 = S.get_fields(TARGET, sid)
        col_new = next(f for f in flds2 if f["field_title"] == TMP)
        S.api("wedoc/smartsheet/update_fields", {"docid": TARGET, "sheet_id": sid,
             "fields": [{"field_id": col_new["field_id"], "field_title": "下钻链接",
                         "field_type": "FIELD_TYPE_URL"}]})
        time.sleep(0.5)

        # 5) 终验
        flds3 = S.get_fields(TARGET, sid)
        final = next(f for f in flds3 if f["field_title"] == "下钻链接")
        is_url = final["field_type"] == "FIELD_TYPE_URL"
        fin_n = sum(1 for r in S.iter_records(TARGET, sid, page=200)
                    if r.get("values", {}).get("下钻链接"))
        if is_url and fin_n == old_n:
            ok.append((title, f"{old_n} 行链接全部迁移，字段类型=URL"))
        else:
            fail.append((title, f"终验异常 is_url={is_url} 行数{fin_n}/{old_n}"))
    except Exception as e:
        fail.append((title, f"异常 {e}"))

print("== 成功 ==")
for t, m in ok:
    print(f"  ✓ {t}  ({m})")
print("\n== 跳过 ==")
for t, m in skip:
    print(f"  - {t}  ({m})")
print("\n== 失败 ==")
for t, m in fail:
    print(f"  ! {t}  ({m})")
print(f"\n汇总：成功 {len(ok)}，跳过 {len(skip)}，失败 {len(fail)}")
