#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回填 00~12 共 21 张空表（企微智能表格《钢铁料耗·炼钢成本 指标血缘与本体建模》）。

关键修正（相对 Phase-1 的失败根因）：
  1) 字段标题禁下划线 → 全部剥离 '_'（FACTORY_DIV→FACTORYDIV 等），否则 2022030 拒绝建字段。
  2) 本平台 NUMBER 字段经 API 静默丢值 → 所有数值以「文本字段」承载。
  3) URL 字段类型(FIELD_TYPE_URL)不可经 API 创建(2022019) → 下钻链接用「文本字段」承载完整 URL，
     企微文本单元格内 URL 会自动渲染为可点击链接。
  4) add_records 在本平台对「按字段标题建行」会产出空值行 → 改为 先建空壳行 → 按 record_id 回填。
  5) 跳转链接指向对应工厂的 DWD临时表(09_*)/ODS原始明细(10_*) 明细数据表。
  6) 新建子表会自带『智能表列』默认列 → add_fields 后用 remove_default_column 按 field_id 删除，
     保证每张表不再残留该列（平台要求表至少保留 1 列，故须在真实字段建好后再删）。

数据来源：report_data.json（由 DB2 MCP 抽取，已与实时库核对）。
"""
import sys, json, time, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wecom_smartsheet_sync as S

# 目标文档 docid：默认复用《钢铁料耗·炼钢成本 指标血缘与本体建模》；
# 换文档时设环境变量 WECOM_DOCID 覆盖，保持脚本可复用。
TARGET = os.environ.get("WECOM_DOCID", "s3_AMAA4RTkAAA0q7TKZxkTZ668rLE5Y_a")
DATA = json.load(open(S.HERE / "report_data.json", encoding="utf-8"))
# 文档访问基址（从 HTML 报告 grep 得到）；子表跳转拼 &sheetid=
BASE = "https://wecomdoc.fjsg.com.cn/smartsheet/s3_AMAA4RTkAAA0q7TKZxkTZ668rLE5Y_a?scode=AMAA4RTkAAA72uXFV1AMAA4RTkAAA"

# 缺口字段兜底（S00 说明用到）
DATA.setdefault("meta", {})
DATA["meta"].setdefault("extracted_at", "2026-09-22")
DATA["meta"].setdefault("tmp_batch", "TP003 (7,949 行 UNION ALL → 5 张临时表)")

# 让 build_all 用 &sheetid= 拼跳转链接
S.SHEET_URL_TPL = "{base_url}&sheetid={sheet_id}"

F_DRILL = {'yilian': ('S09', 'S14'), 'erlian': ('S10', 'S15'), 'benbu': ('S11', 'S16'),
           'luoyuan': ('S12', 'S17'), 'quanzhou': ('S13', 'S18')}
REV_F = {v: k for k, v in DATA["f_cname"].items()}


def Tt(s):
    return [{"type": "text", "text": "" if s is None else str(s)}]


def san(t):
    """字段标题剥离下划线（平台禁下划线），其余保留。"""
    return t.replace("_", "")


# ---------------------------------------------------------------------------
# 1) 删除并重建 21 张表（00~12 系列），拿到全新 sid，彻底清除 Phase-1 空壳/坏字段
# ---------------------------------------------------------------------------
print("== 1) 重建 21 张目标子表 ==")
existing = {s["title"]: s["sheet_id"] for s in S.list_sheets(TARGET)}
sid = {}
for key, title in S.SHEETS:
    if title in existing:
        try:
            S.api("wedoc/smartsheet/delete_sheet", {"docid": TARGET, "sheet_id": existing[title]})
        except Exception as e:
            print("   delete skip", title, e)
        time.sleep(0.3)
    sid[key] = S.add_sheet(TARGET, title)
    time.sleep(0.3)
    print(f"   + {title}  -> {sid[key]}")

# ---------------------------------------------------------------------------
# 2) build_all 产出结构 + 跳转链接（sid 已是真实新 sid，链接指向正确子表）
# ---------------------------------------------------------------------------
print("\n== 2) build_all 生成结构与跳转链接 ==")
built = S.build_all(DATA, sid, TARGET, BASE)

# ---------------------------------------------------------------------------
# 3) 后处理：标题去下划线 / 全部 TEXT / 单元格统一为文本 cell / 钢铁料耗直跳 DWD
# ---------------------------------------------------------------------------
LINK_TITLES = {"下钻链接"}   # 这些列用真链接字段(FIELD_TYPE_URL)，其余列用文本

print("== 3) 后处理（去下划线 + 链接列用URL字段/其余文本 + 钢铁料耗直跳明细表）==")
for key, (fields, recs) in built.items():
    # 字段标题去下划线并建立 旧→新 映射；链接列保持 URL 类型（须带 property_url）
    new_fields = [(san(t), "FIELD_TYPE_URL" if san(t) in LINK_TITLES else "FIELD_TYPE_TEXT")
                  for (t, _) in fields]
    keymap = {t: san(t) for (t, _) in fields}
    new_recs = []
    for r in recs:
        nr = {}
        for f, v in r.items():
            nf = keymap.get(f, san(f))
            if isinstance(v, list) and v:
                cell = v[0]
                if cell.get("type") == "url":
                    if nf in LINK_TITLES:      # 链接列：保留 url 单元格（可点击跳转）
                        lnk = cell.get("link") or cell.get("text")
                        nr[nf] = [{"type": "url", "text": cell.get("text") or lnk, "link": lnk}]
                    else:
                        nr[nf] = Tt(cell.get("link") or cell.get("text"))
                else:
                    nr[nf] = v                                          # 已是文本 cell
            else:
                nr[nf] = Tt(v)                                         # N() 浮点 / 普通值 → 文本
        new_recs.append(nr)
    # 钢铁料耗数据：下钻链接直跳对应工厂 DWD临时表（09_*）
    if key in ("S01", "S20") or key == "S03":
        for nr in new_recs:
            fac = REV_F.get((nr.get("工厂") or [{}])[0].get("text", "")) if nr.get("工厂") else None
            metric = (nr.get("指标") or [{}])[0].get("text", "") if nr.get("指标") else ""
            if fac and (key != "S03" or metric == "钢铁料耗"):
                dwd_key = F_DRILL[fac][0]
                nr["下钻链接"] = Tt(f"{BASE}&sheetid={sid[dwd_key]}")
    built[key] = (new_fields, new_recs)
    print(f"   {key}: 字段 {len(new_fields)}  记录 {len(new_recs)}")

# ---------------------------------------------------------------------------
# 4) 写入：建字段 → 建空壳行 → 按 record_id 回填 → 读回校验
# ---------------------------------------------------------------------------
print("\n== 4) 写入（建字段→空壳→按id回填）==")
summary = []
for key, title in S.SHEETS:
    fields, recs = built[key]
    # 建字段（URL 字段必须带 property_url，否则 2022019）
    fdefs = [{"field_title": t,
              "field_type": ty,
              **({"property_url": {"type": "LINK_TYPE_PURE_TEXT"}} if ty == "FIELD_TYPE_URL" else {})}
             for t, ty in fields]
    for i in range(0, len(fdefs), S.FIELD_BATCH):
        S.api("wedoc/smartsheet/add_fields",
              {"docid": TARGET, "sheet_id": sid[key], "fields": fdefs[i:i + S.FIELD_BATCH]})
    time.sleep(0.4)
    # 删掉新建子表自带的默认『智能表列』（add_fields 后该列已非唯一，可安全删除）
    try:
        if S.remove_default_column(TARGET, sid[key]):
            print(f"   {title}: ✓ 已移除默认『智能表列』")
    except Exception as e:
        print(f"   {title}: ! 移除默认列失败 {e}")
    if not recs:
        print(f"   {title}: 无记录（仅字段）")
        summary.append((title, 0, 0))
        continue
    # 建空壳行（拿 record_id）
    resp = S.api("wedoc/smartsheet/add_records",
                 {"docid": TARGET, "sheet_id": sid[key],
                  "key_type": "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
                  "records": [{} for _ in recs]})
    ids = [r["record_id"] for r in resp.get("records", [])]
    # 按 id 回填
    upd = [{"record_id": ids[i], "values": recs[i]} for i in range(len(recs))]
    for i in range(0, len(upd), 100):
        S.api("wedoc/smartsheet/update_records",
              {"docid": TARGET, "sheet_id": sid[key], "records": upd[i:i + 100]})
        time.sleep(0.3)
    # 读回校验非空行数
    n = sum(1 for r in S.iter_records(TARGET, sid[key], page=200) if r.get("values"))
    summary.append((title, len(recs), n))
    print(f"   {title}: 计划 {len(recs)} 行 -> 非空回读 {n} 行")

# ---------------------------------------------------------------------------
# 5) 汇总
# ---------------------------------------------------------------------------
print("\n== 5) 回填汇总 ==")
ok = sum(1 for _, p, n in summary if n == p)
for title, p, n in summary:
    flag = "OK" if n == p else "!!不符"
    print(f"   {title:<32} 计划{p:>4} 非空回读{n:>4}  {flag}")
print(f"\n   全部一致: {ok}/{len(summary)} 张子表")
