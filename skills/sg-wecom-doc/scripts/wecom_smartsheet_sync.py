#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
 钢铁料耗 × 炼钢成本 跨域比对报告  →  企业微信「智能表格」全自动落地
==============================================================================
通过企业微信 wedoc 开放 API，把 HTML 报表的全部信息与功能在企微文档中重建：
  文档 → 子表 → 字段 → 记录 → 权限
全部经 API 完成，不使用人工界面操作。

零第三方依赖（仅标准库 urllib + ssl），适配私有化部署自签证书环境。

用法：
  python wecom_smartsheet_sync.py --dry-run      # 干跑：只构建并自检，不写接口
  python wecom_smartsheet_sync.py                # 正式落地（新建文档）
  python wecom_smartsheet_sync.py --docid <ID>   # 复用已有文档增量同步
  python wecom_smartsheet_sync.py --limit 5      # 每表只写 5 行，先验证字段/权限
==============================================================================
"""

import argparse
import json
import os
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# =============================================================================
# ===== 配置区 ================================================================
# =============================================================================

# 私有化部署域名（你的环境）。公有云请改为 https://qyapi.weixin.qq.com
BASE = "https://wecom.fjsg.com.cn"

CORPID = os.environ.get("CORPID", "")

# 应用 Secret：优先读环境变量 WECOM_CORPSECRET；否则回退复用随包分发的 scripts/wecom_smartsheet.py
CORPSECRET = os.environ.get("WECOM_CORPSECRET", "")
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LEGACY_SECRET_FILE = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "..", "scripts", "wecom_smartsheet.py"))

# 私有化部署常见自签证书：关闭主机名/证书校验以联通；受信环境可改 True
VERIFY_SSL = False

SPACE_ID = ""      # 选填：空间 spaceid；留空则创建到应用默认位置
FATHER_ID = ""     # 选填：父目录 fileid；根目录时填空间 spaceid

DOC_NAME = "钢铁料耗×成本跨域比对·全厂横向比对·同比环比·ODS下钻（2026-09）"

ADMIN_USERS = []   # 选填：文档管理员 userid 列表
MEMBER_USERS = []  # 选填：需授权成员 userid 列表
MEMBER_AUTH = 1    # 1=只读  2=读写  7=管理员

# 子表跳转链接：优先用 create_doc 返回的 url 做基址（最可靠）
SHEET_URL_TPL = "{base_url}?tab={sheet_id}"
DOC_URL_FALLBACK_TPL = "https://doc.weixin.qq.com/smartsheet/{docid}"  # 复用旧文档时的兜底
INCLUDE_FILTER_PARAM = False   # True 时追加 &f=<筛选键>

BATCH_SIZE = 100      # add_records 单批行数（单表上限 10 万行）
FIELD_BATCH = 20      # add_fields 单批列数（单表上限 150 列）
SLEEP_BETWEEN = 0.35  # 调用间隔（秒），规避限流
MAX_RETRY = 5

HERE = Path(__file__).resolve().parent
DATA_JSON = HERE / "report_data.json"
TOKEN_CACHE = HERE / ".wecom_token.json"


def _resolve_corpsecret():
    if CORPSECRET:
        return CORPSECRET
    try:
        txt = Path(LEGACY_SECRET_FILE).read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'^CORPSECRET\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def _ctx():
    if VERIFY_SSL:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# =============================================================================
# ===== 1. access_token：获取 / 缓存 / 刷新 ===================================
# =============================================================================

class WecomError(Exception):
    def __init__(self, errcode, errmsg, path, payload=None):
        self.errcode, self.errmsg, self.path = errcode, errmsg, path
        self.payload = payload
        super().__init__(f"[{path}] errcode={errcode} errmsg={errmsg}")


_TOKEN = {"value": None, "expire_at": 0}


def _http(url, body=None, timeout=30):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return json.loads(r.read().decode("utf-8"))


def get_token(force=False):
    """获取 access_token；进程内 + 文件双缓存，提前 5 分钟过期。"""
    now = time.time()
    if not force and _TOKEN["value"] and _TOKEN["expire_at"] > now:
        return _TOKEN["value"]

    if not force and TOKEN_CACHE.exists():
        try:
            c = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
            if c.get("expire_at", 0) > now:
                _TOKEN.update(value=c["access_token"], expire_at=c["expire_at"])
                return _TOKEN["value"]
        except Exception:
            pass

    secret = _resolve_corpsecret()
    if not secret:
        raise WecomError(-1, "未配置 CORPSECRET（设环境变量 WECOM_CORPSECRET 或填写脚本顶部）", "gettoken")

    # GET {BASE}/cgi-bin/gettoken?corpid=&corpsecret=
    q = urllib.parse.urlencode({"corpid": CORPID, "corpsecret": secret})
    r = _http(f"{BASE}/cgi-bin/gettoken?{q}")
    if r.get("errcode") != 0:
        raise WecomError(r.get("errcode"), r.get("errmsg"), "gettoken")
    # 返回 {errcode, errmsg, access_token, expires_in}
    _TOKEN.update(value=r["access_token"], expire_at=now + r.get("expires_in", 7200) - 300)
    try:
        TOKEN_CACHE.write_text(json.dumps(_TOKEN), encoding="utf-8")
    except Exception:
        pass
    return _TOKEN["value"]


_TOKEN_ERR = {40001, 42001, 41001}              # 凭证无效/过期/缺失 → 刷新重试
_BUSY_ERR = {45009, 45033, -1, 41050}           # 限流/系统繁忙 → 退避重试
RETRYABLE_PARAM_ERR = {301002, 301017, 40058, 41004}   # 无权限/参数错 → 不重试


def api(path, body=None, _attempt=0):
    """统一接口调用：自动带 token、刷新、限流退避。path 形如 'wedoc/create_doc'"""
    token = get_token()
    url = f"{BASE}/cgi-bin/{path}?access_token={urllib.parse.quote(token)}"
    try:
        r = _http(url, body)
    except Exception as e:
        if _attempt < MAX_RETRY:
            time.sleep(min(2 ** _attempt, 30) * (1 + random.random() * 0.3))
            return api(path, body, _attempt + 1)
        raise WecomError(-999, f"网络异常 {e}", path)

    ec = r.get("errcode", 0)
    if ec == 0:
        time.sleep(SLEEP_BETWEEN)
        return r

    if ec in _TOKEN_ERR and _attempt < MAX_RETRY:
        get_token(force=True)
        return api(path, body, _attempt + 1)

    if ec in _BUSY_ERR and _attempt < MAX_RETRY:
        wait = min(2 ** _attempt, 30) * (1 + random.random() * 0.3)
        log(f"   ! {path} errcode={ec} {r.get('errmsg')}，{wait:.1f}s 后重试 "
            f"({_attempt + 1}/{MAX_RETRY})")
        time.sleep(wait)
        return api(path, body, _attempt + 1)

    raise WecomError(ec, r.get("errmsg"), path, body)


# =============================================================================
# ===== 2. 文档 / 子表 / 字段 / 记录 / 权限 ===================================
# =============================================================================

def create_doc():
    """新建智能表格文档。doc_type: 3文档 4表格 10智能表格 11智能文档"""
    body = {"doc_type": 10, "doc_name": DOC_NAME}
    if SPACE_ID:
        body["spaceid"] = SPACE_ID
        body["fatherid"] = FATHER_ID or SPACE_ID
    if ADMIN_USERS:
        body["admin_users"] = ADMIN_USERS
    r = api("wedoc/create_doc", body)     # → {errcode, errmsg, url, docid}
    log(f"   文档已创建 docid={r['docid']}")
    log(f"   访问链接 {r.get('url')}")
    return r["docid"], r.get("url", "")


def list_sheets(docid):
    r = api("wedoc/smartsheet/get_sheet", {"docid": docid, "need_all_type_sheet": True})
    return r.get("sheet_list", [])


def add_sheet(docid, title, index=None):
    props = {"title": title}
    if index is not None:
        props["index"] = index
    r = api("wedoc/smartsheet/add_sheet", {"docid": docid, "properties": props})
    return r["properties"]["sheet_id"]


def rename_sheet(docid, sheet_id, title):
    api("wedoc/smartsheet/update_sheet",
        {"docid": docid, "properties": {"sheet_id": sheet_id, "title": title}})


def remove_default_column(docid, sheet_id):
    """删除新建子表自带的默认『智能表列』（通常 field_id=fabcde）。

    注意：必须在 add_fields 写入至少一个真实字段之后调用——否则该列是
    全表唯一列，平台会静默拒绝删除（返回 errcode=0 但列仍在）。
    按真实 field_id（而非标题）删除，是经实测可靠的写法。返回是否执行了删除。
    """
    flds = get_fields(docid, sheet_id)
    if len(flds) <= 1:
        return False  # 唯一列不可删，跳过
    zhil = next((f for f in flds if f.get("field_title") == "智能表列"), None)
    if not zhil:
        return False
    api("wedoc/smartsheet/delete_fields",
        {"docid": docid, "sheet_id": sheet_id, "field_ids": [zhil["field_id"]]})
    return True


def get_fields(docid, sheet_id, limit=100):
    out, offset = [], 0
    while True:
        r = api("wedoc/smartsheet/get_fields",
                {"docid": docid, "sheet_id": sheet_id, "offset": offset, "limit": limit})
        # 该私有化部署返回顶层 "fields"；公有云偶有 "field_list"，两者兼容
        fl = r.get("fields")
        if fl is None:
            fl = r.get("field_list", [])
        out.extend(fl)
        if len(fl) < limit:
            break
        offset += limit
    return out


def ensure_fields(docid, sheet_id, fields):
    """幂等建字段：同名标题跳过（新建子表自带一个默认字段，不影响写入）。
    FIELD_TYPE_URL 字段自动补必填属性 property_url={"type":"LINK_TYPE_PURE_TEXT"}，
    否则平台报 2022019 invalid url field。"""
    exist = {f.get("field_title") for f in get_fields(docid, sheet_id)}
    todo = [f for f in fields if f["field_title"] not in exist]
    if not todo:
        return 0
    def _norm(f):
        if f.get("field_type") == "FIELD_TYPE_URL" and not f.get("property_url"):
            return {**f, "property_url": {"type": "LINK_TYPE_PURE_TEXT"}}
        return f
    for i in range(0, len(todo), FIELD_BATCH):
        api("wedoc/smartsheet/add_fields",
            {"docid": docid, "sheet_id": sheet_id,
             "fields": [_norm(f) for f in todo[i:i + FIELD_BATCH]]})
    return len(todo)


def add_records(docid, sheet_id, records):
    ok = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i:i + BATCH_SIZE]
        r = api("wedoc/smartsheet/add_records", {
            "docid": docid, "sheet_id": sheet_id,
            "key_type": "CELL_VALUE_KEY_TYPE_FIELD_TITLE", "records": chunk})
        ok += len(r.get("records", chunk))
        log(f"      + 写入 {len(chunk)} 行（累计 {ok}）")
    return ok


def iter_records(docid, sheet_id, page=200, max_rows=None):
    """分页读取（大数据量同步/校验用）"""
    offset, got = 0, 0
    while True:
        r = api("wedoc/smartsheet/get_records",
                {"docid": docid, "sheet_id": sheet_id, "offset": offset, "limit": page})
        recs = r.get("records", [])
        for x in recs:
            yield x
        got += len(recs)
        if len(recs) < page or (max_rows and got >= max_rows):
            break
        offset += page


def grant_members(docid):
    if not MEMBER_USERS:
        return
    for i in range(0, len(MEMBER_USERS), 100):
        api("wedoc/mod_doc_member", {"docid": docid, "update_file_member_list": [
            {"type": 1, "auth": MEMBER_AUTH, "userid": u}
            for u in MEMBER_USERS[i:i + 100]]})
    log(f"   已授权 {len(MEMBER_USERS)} 名成员（auth={MEMBER_AUTH}）")


# =============================================================================
# ===== 3. 单元格值构造（严格匹配企微 CellValue 规范）=========================
# =============================================================================

def T(s):
    """文本 FIELD_TYPE_TEXT → Object[](CellTextValue)"""
    return [{"type": "text", "text": "" if s is None else str(s)}]


def U(text, link):
    """链接 FIELD_TYPE_URL → Object[](CellUrlValue)，目前只展示一个"""
    return [{"type": "url", "text": str(text), "link": link}]


def N(x):
    """数字 FIELD_TYPE_NUMBER → double"""
    return float(x)


# =============================================================================
# ===== 4. 子表结构定义（组织形式 / 字段与列设计 / 数据映射）=================
# =============================================================================

FACTORY_KEYS = ["benbu", "yilian", "erlian", "luoyuan", "quanzhou"]
METRIC_KEYS = ["steel", "cost"]
METRIC_NAME = {"steel": "钢铁料耗", "cost": "炼钢成本"}
METRIC_UNIT = {"steel": "kg/t", "cost": "元/吨"}

SHEETS = [
    ("S00", "00_说明与口径"),
    ("S01", "01_趋势明细_钢铁料耗"),
    ("S02", "02_趋势明细_炼钢成本"),
    ("S03", "03_同比环比"),
    ("S04", "04_血缘链路_按工厂(L2)"),
    ("S05", "05_指标血缘矩阵_13列"),
    ("S06", "06_指标体系注册"),
    ("S07", "07_工厂维度字典"),
    ("S08", "08_DWS逐日明细_202609"),
    ("S09", "09_DWD临时表_一炼钢11"),
    ("S10", "09_DWD临时表_二炼钢12"),
    ("S11", "09_DWD临时表_本部三明11+12"),
    ("S12", "09_DWD临时表_罗源14"),
    ("S13", "09_DWD临时表_泉州13"),
    ("S14", "10_ODS原始明细_一炼钢11"),
    ("S15", "10_ODS原始明细_二炼钢12"),
    ("S16", "10_ODS原始明细_本部三明11+12"),
    ("S17", "10_ODS原始明细_罗源14"),
    ("S18", "10_ODS原始明细_泉州13"),
    ("S19", "11_下钻链接索引"),
    ("S20", "12_最新月对标_202609"),
]

# 工厂 → (DWD子表key, ODS子表key)
F_DRILL = {
    "yilian":   ("S09", "S14"),
    "erlian":   ("S10", "S15"),
    "benbu":    ("S11", "S16"),
    "luoyuan":  ("S12", "S17"),
    "quanzhou": ("S13", "S18"),
}
ZB_TO_FACTORY = {"1600209": "yilian", "1600210": "erlian", "1600212": "erlian"}


def _key_col(t):
    """
    定位临时表的「工厂列」下标。
    注意：不能写死 0/1 —— TP003_TMP1_2_1 首列是 REC_CREATE_TIME，FACTORY_DIV 在第 2 列；
    TP003_TMP1_48 用 FACTORT_CODE。按列名定位最稳妥。
    """
    for name in ("FACTORY_DIV", "FACTORT_CODE"):
        if name in t["cols"]:
            return t["cols"].index(name)
    return 0


def build_all(data, sid, docid, doc_url=""):
    """返回 {sheet_key: (fields, records)}；依赖 sid 生成下钻超链接"""
    months = data["meta"]["months"]
    steel, cost = data["steel"], data["cost"]
    f_cname, f_div = data["f_cname"], data["f_div"]
    base_url = doc_url or DOC_URL_FALLBACK_TPL.format(docid=docid)

    def url(target_key, label, filter_key=None):
        link = SHEET_URL_TPL.format(base_url=base_url, sheet_id=sid[target_key])
        if INCLUDE_FILTER_PARAM and filter_key:
            link += "&f=" + urllib.parse.quote(str(filter_key))
        return U(label, link)

    out = {}

    # ---------- S00 说明与口径 ----------
    out["S00"] = (
        [("项目", "FIELD_TYPE_TEXT"), ("内容", "FIELD_TYPE_TEXT")],
        [{"项目": T(k), "内容": T(v)} for k, v in [
            ("报告名称", DOC_NAME),
            ("来源", "钢铁料耗成本跨域比对_全厂横向比对_可视化报告_20260922.html"),
            ("数据抽取时间", data["meta"]["extracted_at"]),
            ("DWD临时表批次", data["meta"]["tmp_batch"]),
            ("月份范围", f"{months[0]} ~ {months[-1]}（共 {len(months)} 期）"),
            ("指标①口径", "钢铁料耗(kg/t) = 钢铁料消耗(分子) ÷ 钢产量(分母)；比率不可加，先按基地聚合后相除"),
            ("指标②口径", "炼钢成本(元/吨)：成本中心日明细 LGYS 分项，CB01 仅含本部三厂"),
            ("工厂维度口径", "三明一炼钢=11；三明二炼钢=12；三明本部合计=11+12(1A)；罗源=14；泉州=13"),
            ("罗源/泉州口径", "不在本部 ZZGZ 临时表链路，走各自 MES → T_ADS_LY_SCRB(5000106) / T_ADS_QZ_SCRB(6012800)"),
            ("数据缺口", "泉州炼钢成本全空：SG_SIGN_COST_QZ 的 ACCOUNT_PERIOD 全空(37行)，留空待补"),
            ("已知原始层异常", "2024-12 一炼=1213.44、2024-09 二炼=1650.49、2024-12 二炼=1317.90（ADS/KPI 已清洗）"),
            ("数据一致性提示",
             f"源 steel.benbu 数组长度 {len(steel['benbu'])} ≠ 月份数 {len(months)}，"
             f"末尾未对应月份的值已忽略（与 monthsAll 对齐）"),
            ("下钻使用说明", "每行「下钻链接」为超链接字段(FIELD_TYPE_URL)，点击跳转目标子表；"
                          "「筛选键」用于在目标子表内二次筛选同一工厂/指标"),
            ("图表说明", "原 HTML 的 ECharts 图表在此落地为明细数据；"
                       "可在企微端基于本表插入「图表视图/仪表盘」还原可视化"),
        ]],
    )

    # ---------- S01/S02 趋势明细 ----------
    for key, metric in (("S01", "steel"), ("S02", "cost")):
        arrs = steel if metric == "steel" else cost
        fields = [("月份", "FIELD_TYPE_TEXT"), ("工厂", "FIELD_TYPE_TEXT"),
                  ("FACTORY_DIV", "FIELD_TYPE_TEXT"), ("指标", "FIELD_TYPE_TEXT"),
                  ("数值", "FIELD_TYPE_NUMBER"), ("单位", "FIELD_TYPE_TEXT"),
                  ("筛选键", "FIELD_TYPE_TEXT"), ("下钻链接", "FIELD_TYPE_URL")]
        recs = []
        for i, ym in enumerate(months):
            for f in FACTORY_KEYS:
                v = arrs[f][i] if i < len(arrs[f]) else None
                if v is None:
                    continue
                fk = f"{f}|{metric}"
                recs.append({"月份": T(ym), "工厂": T(f_cname[f]),
                             "FACTORY_DIV": T("/".join(f_div[f])),
                             "指标": T(METRIC_NAME[metric]), "数值": N(v),
                             "单位": T(METRIC_UNIT[metric]), "筛选键": T(fk),
                             "下钻链接": url("S04", f"▶ 下钻血缘链路 · {f_cname[f]}", fk)})
        out[key] = (fields, recs)

    # ---------- S03 同比环比 ----------
    fields = [("月份", "FIELD_TYPE_TEXT"), ("工厂", "FIELD_TYPE_TEXT"),
              ("FACTORY_DIV", "FIELD_TYPE_TEXT"), ("指标", "FIELD_TYPE_TEXT"),
              ("当期值", "FIELD_TYPE_NUMBER"), ("上期值", "FIELD_TYPE_NUMBER"),
              ("环比率%", "FIELD_TYPE_NUMBER"), ("去年同期值", "FIELD_TYPE_NUMBER"),
              ("同比率%", "FIELD_TYPE_NUMBER"), ("筛选键", "FIELD_TYPE_TEXT"),
              ("下钻链接", "FIELD_TYPE_URL")]
    recs = []
    for metric in METRIC_KEYS:
        arrs = steel if metric == "steel" else cost
        for i, ym in enumerate(months):
            for f in FACTORY_KEYS:
                cur = arrs[f][i] if i < len(arrs[f]) else None
                if cur is None:
                    continue
                row = {"月份": T(ym), "工厂": T(f_cname[f]),
                       "FACTORY_DIV": T("/".join(f_div[f])),
                       "指标": T(METRIC_NAME[metric]), "当期值": N(cur)}
                prev = arrs[f][i - 1] if i >= 1 and i - 1 < len(arrs[f]) else None
                if prev:
                    row["上期值"] = N(prev)
                    row["环比率%"] = N(round((cur - prev) / prev * 100, 4))
                ly = arrs[f][i - 12] if i >= 12 and i - 12 < len(arrs[f]) else None
                if ly:
                    row["去年同期值"] = N(ly)
                    row["同比率%"] = N(round((cur - ly) / ly * 100, 4))
                fk = f"{f}|{metric}"
                row["筛选键"] = T(fk)
                row["下钻链接"] = url("S04", f"▶ 下钻血缘链路 · {f_cname[f]}", fk)
                recs.append(row)
    out["S03"] = (fields, recs)

    # ---------- S04 血缘链路_按工厂 (L2) ----------
    fields = [("工厂", "FIELD_TYPE_TEXT"), ("FACTORY_DIV", "FIELD_TYPE_TEXT"),
              ("指标", "FIELD_TYPE_TEXT"), ("ODS源表", "FIELD_TYPE_TEXT"),
              ("DWD临时表", "FIELD_TYPE_TEXT"), ("DWS落地表", "FIELD_TYPE_TEXT"),
              ("ADS报表", "FIELD_TYPE_TEXT"), ("加工存储过程", "FIELD_TYPE_TEXT"),
              ("口径说明", "FIELD_TYPE_TEXT"), ("筛选键", "FIELD_TYPE_TEXT"),
              ("下钻链接", "FIELD_TYPE_URL")]
    ZZ = "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01"
    recs = []
    for f in FACTORY_KEYS:
        ods = data["ods_steel"].get(f, {})
        for metric in METRIC_KEYS:
            fk = f"{f}|{metric}"
            dwd_key = F_DRILL[f][0]
            if metric == "steel":
                if f in ("luoyuan", "quanzhou"):
                    row = dict(ODS源表=T(ods.get("tbl", [""])[0]),
                               DWD临时表=T("（不在本部 ZZGZ 临时表链路）"),
                               DWS落地表=T("自有 DWS"),
                               ADS报表=T("T_ADS_LY_SCRB(KPI 5000106)" if f == "luoyuan"
                                         else "T_ADS_QZ_SCRB(KPI 6012800)"),
                               加工存储过程=T("P_DWS_FACT_ZZGZ_0003（分支）" if f == "luoyuan" else "泉州分支"),
                               口径说明=T(ods.get("note", "")))
                else:
                    row = dict(ODS源表=T(" / ".join(ods.get("tbl", []))),
                               DWD临时表=T("TP003_TMP1_1→TMP1_2_1→TMP1_2→TMP1_3→TMP1_40→TMP1_48"),
                               DWS落地表=T(ZZ),
                               ADS报表=T("SMBB_M_A_GZ01.T_ADS_SM_SCRB (KPI "
                                         + "/".join(data["zb_of"].get(f, [])) + ")"),
                               加工存储过程=T("P_DWS_FACT_ZZGZ_0003"),
                               口径说明=T(ods.get("note", "")))
            else:
                if f == "quanzhou":
                    row = dict(ODS源表=T("（缺口）"), DWD临时表=T("（缺口）"),
                               DWS落地表=T("（缺口）"), ADS报表=T("（缺口）"),
                               加工存储过程=T("（缺口）"),
                               口径说明=T("SG_SIGN_COST_QZ ACCOUNT_PERIOD 全空；"
                                        "PRODUCT_COST_QZ 需科目/产量映射 → 留空待补"))
                elif f == "luoyuan":
                    row = dict(ODS源表=T("罗源 MES 成本"), DWD临时表=T("钢种成本存储过程"),
                               DWS落地表=T("钢种成本 DWS"), ADS报表=T("SG_SIGN_COST_LY"),
                               加工存储过程=T("钢种成本存储过程"),
                               口径说明=T("产量加权 SUM(COST)/SUM(EARN_N)，"
                                        "剔除铁前成本中心 10932x，自 2024-12 起"))
                else:
                    row = dict(ODS源表=T("成本原始凭证（MES/ERP 抛账）"),
                               DWD临时表=T("T_DWS_FACT_CBZX_CACA_CENTER_COST（REPORT_TYPE=5,LGYS）"),
                               DWS落地表=T("P_ADS_SRV_CACA_DAY_COST"),
                               ADS报表=T("CB01.T_ADS_SRV_CACA_DAY_COST"),
                               加工存储过程=T("CBPROD 50 个日成本存储过程（十步计算链）"),
                               口径说明=T("成本中心 " + ("100350101" if f == "yilian"
                                                     else "100350201" if f == "erlian" else "1003501xx")))
            row.update({"工厂": T(f_cname[f]), "FACTORY_DIV": T("/".join(f_div[f])),
                        "指标": T(METRIC_NAME[metric]), "筛选键": T(fk),
                        "下钻链接": url(dwd_key, f"▶ 下钻 DWD 临时表 · {f_cname[f]}", fk)})
            recs.append(row)
    out["S04"] = (fields, recs)

    # ---------- S05 指标血缘矩阵 ----------
    lm = data["lineage_matrix"]
    fields = [(c, "FIELD_TYPE_TEXT") for c in lm["columns"]] + [("下钻链接", "FIELD_TYPE_URL")]
    recs = []
    for row in lm["rows"]:
        v = {c: T(row[i]) for i, c in enumerate(lm["columns"])}
        v["下钻链接"] = url("S04", "▶ 下钻血缘链路")
        recs.append(v)
    out["S05"] = (fields, recs)

    # ---------- S06 指标体系注册 ----------
    fields = [("指标编码", "FIELD_TYPE_TEXT"), ("指标名称", "FIELD_TYPE_TEXT"),
              ("指标层级", "FIELD_TYPE_TEXT"), ("业务域", "FIELD_TYPE_TEXT"),
              ("归属/口径", "FIELD_TYPE_TEXT"), ("物化SQL", "FIELD_TYPE_TEXT"),
              ("体系", "FIELD_TYPE_TEXT")]
    recs = []
    for z, r in data["ind_reg"].items():
        recs.append({"指标编码": T(z), "指标名称": T(r["name"]), "指标层级": T(r["level"]),
                     "业务域": T(r["domain"]), "归属/口径": T(r["div"]),
                     "物化SQL": T(r["sql"]), "体系": T("生产管制·钢铁料耗")})
    for z, r in data["ind_reg_cost"].items():
        recs.append({"指标编码": T(z), "指标名称": T(r["name"]), "指标层级": T(r["level"]),
                     "业务域": T(r["domain"]), "归属/口径": T(r["div"]),
                     "物化SQL": T(r["sql"]), "体系": T("日成本·炼钢成本")})
    out["S06"] = (fields, recs)

    # ---------- S07 工厂维度字典 ----------
    fields = [("类型", "FIELD_TYPE_TEXT"), ("KEY", "FIELD_TYPE_TEXT"),
              ("工厂名称/FACTORY_CNAME", "FIELD_TYPE_TEXT"), ("FACTORY_DIV", "FIELD_TYPE_TEXT"),
              ("ZB_CODE", "FIELD_TYPE_TEXT"), ("说明", "FIELD_TYPE_TEXT"),
              ("下钻链接", "FIELD_TYPE_URL")]
    recs = []
    for f in FACTORY_KEYS:
        recs.append({"类型": T("工厂"), "KEY": T(f), "工厂名称/FACTORY_CNAME": T(f_cname[f]),
                     "FACTORY_DIV": T("/".join(f_div[f])),
                     "ZB_CODE": T("/".join(data["zb_of"].get(f, [])) or "—"),
                     "说明": T(data["ods_steel"].get(f, {}).get("note", "")),
                     "下钻链接": url(F_DRILL[f][0], f"▶ DWD临时表 · {f_cname[f]}")})
    for z, divs in data["zb_div"].items():
        recs.append({"类型": T("ZB_CODE→FACTORY_DIV"), "KEY": T(z),
                     "工厂名称/FACTORY_CNAME": T(data["ind_reg"].get(z, {}).get("name", z)),
                     "FACTORY_DIV": T("/".join(divs)), "ZB_CODE": T(z),
                     "说明": T("该指标下钻明细按此 FACTORY_DIV 过滤"),
                     "下钻链接": url(F_DRILL.get(ZB_TO_FACTORY.get(z, "benbu"))[0], "▶ DWD临时表")})
    out["S07"] = (fields, recs)

    # ---------- S08 DWS 逐日明细 ----------
    fields = [("月份", "FIELD_TYPE_TEXT"), ("日", "FIELD_TYPE_TEXT"),
              ("ZB_CODE", "FIELD_TYPE_TEXT"), ("指标名称", "FIELD_TYPE_TEXT"),
              ("FACTORY_DIV", "FIELD_TYPE_TEXT"), ("FACTORY_CNAME", "FIELD_TYPE_TEXT"),
              ("ZB_VALUE", "FIELD_TYPE_NUMBER"), ("筛选键", "FIELD_TYPE_TEXT"),
              ("下钻链接", "FIELD_TYPE_URL")]
    recs = []
    for ym, byzb in data["dws_daily"].items():
        for z, days in byzb.items():
            fac = ZB_TO_FACTORY.get(z, "benbu")
            for d in sorted(days):
                fk = f"{fac}|steel|{z}"
                recs.append({"月份": T(f"{ym[:4]}-{ym[4:]}"), "日": T(f"{ym[4:]}-{d}"),
                             "ZB_CODE": T(z),
                             "指标名称": T(data["ind_reg"].get(z, {}).get("name", z)),
                             "FACTORY_DIV": T("/".join(data["zb_div"].get(z, []))),
                             "FACTORY_CNAME": T(f_cname[fac]),
                             "ZB_VALUE": N(days[d]), "筛选键": T(fk),
                             "下钻链接": url(F_DRILL[fac][0],
                                        f"▶ 下钻 DWD/ODS · {f_cname[fac]}", fk)})
    out["S08"] = (fields, recs)

    # ---------- S09~S13 DWD 临时表（按工厂隔离）----------
    dwd_fields = [("临时表ID", "FIELD_TYPE_TEXT"), ("层级角色", "FIELD_TYPE_TEXT"),
                  ("行数", "FIELD_TYPE_TEXT"), ("数据来源ODS", "FIELD_TYPE_TEXT"),
                  ("清洗/聚合说明", "FIELD_TYPE_TEXT"), ("字段结构", "FIELD_TYPE_TEXT")]
    dwd_fields += [(f"列{i}", "FIELD_TYPE_TEXT") for i in range(1, 10)]
    dwd_fields += [("筛选键", "FIELD_TYPE_TEXT"), ("下钻链接", "FIELD_TYPE_URL")]

    for skey, fac in (("S09", "yilian"), ("S10", "erlian"), ("S11", "benbu"),
                      ("S12", "luoyuan"), ("S13", "quanzhou")):
        allow = f_div[fac]
        recs = []
        if fac in ("luoyuan", "quanzhou"):
            recs.append({
                "临时表ID": T("（不适用）"),
                "层级角色": T(f"{f_cname[fac]} 不在本部 ZZGZ 临时表链路"),
                "行数": T("0"), "数据来源ODS": T("自有 MES（非本部 ZZGZ 源表）"),
                "清洗/聚合说明": T(f"按 FACTORY_DIV={allow[0]} 与 FACTORY_CNAME={f_cname[fac]} "
                              f"与本部(三明11/12)区分；落地 "
                              + ("T_ADS_LY_SCRB(KPI 5000106)" if fac == "luoyuan"
                                 else "T_ADS_QZ_SCRB(KPI 6012800)")),
                "字段结构": T("—"),
                "列1": T("本部 ZZGZ 临时表仅含三明 FACTORY_DIV 11/12"),
                "筛选键": T(fac),
                "下钻链接": url(F_DRILL[fac][1], f"▶ ODS原始明细 · {f_cname[fac]}")})
        else:
            for t in data["tmp_tables"]:
                key_col = _key_col(t)
                rows = [r for r in t["rows"] if r[key_col] in allow]
                if not rows:
                    recs.append({"临时表ID": T(t["id"]), "层级角色": T(t["role"]),
                                 "行数": T(t["cnt"]), "数据来源ODS": T(t["src"]),
                                 "清洗/聚合说明": T(f"本工厂 {f_cname[fac]} 在此表无 "
                                              f"FACTORY_DIV={'/'.join(allow)} 的行"),
                                 "字段结构": T(" / ".join(t["cols"])), "筛选键": T(fac),
                                 "下钻链接": url(F_DRILL[fac][1],
                                            f"▶ ODS原始明细 · {f_cname[fac]}")})
                    continue
                for r in rows:
                    v = {"临时表ID": T(t["id"]), "层级角色": T(t["role"]),
                         "行数": T(t["cnt"]), "数据来源ODS": T(t["src"]),
                         "清洗/聚合说明": T(t["src"]),
                         "字段结构": T(" / ".join(t["cols"])), "筛选键": T(fac)}
                    for i, x in enumerate(r[:9], start=1):
                        v[f"列{i}"] = T(x)
                    v["下钻链接"] = url(F_DRILL[fac][1],
                                    f"▶ 下钻 ODS 原始明细 · {f_cname[fac]}", fac)
                    recs.append(v)
        out[skey] = (dwd_fields, recs)

    # ---------- S14~S18 ODS 原始明细（最底层）----------
    cols = data["ods_sample_cols"]
    ods_fields = [(c, "FIELD_TYPE_TEXT") for c in cols]
    ods_fields += [("ODS源表", "FIELD_TYPE_TEXT"), ("筛选SQL", "FIELD_TYPE_TEXT"),
                   ("筛选键", "FIELD_TYPE_TEXT"), ("血缘回溯链接", "FIELD_TYPE_URL")]

    for skey, fac in (("S14", "yilian"), ("S15", "erlian"), ("S16", "benbu"),
                      ("S17", "luoyuan"), ("S18", "quanzhou")):
        allow = (["11"] if fac == "yilian" else ["12"] if fac == "erlian"
                 else ["11", "12"] if fac == "benbu" else [])
        recs = []
        if not allow:
            recs.append({cols[0]: T("（不适用）"), cols[1]: T("14" if fac == "luoyuan" else "13"),
                         cols[2]: T(f"{f_cname[fac]} 自有 MES，不在本部 ODS ZZGZ 源表"),
                         cols[3]: T("按 FACTORY_DIV 与 FACTORY_CNAME 与本部(三明11/12)区分"),
                         cols[4]: T("落地 " + ("T_ADS_LY_SCRB(5000106)" if fac == "luoyuan"
                                              else "T_ADS_QZ_SCRB(6012800)")),
                         "ODS源表": T(data["ods_steel"].get(fac, {}).get("tbl", [""])[0]),
                         "筛选SQL": T("—"), "筛选键": T(fac),
                         "血缘回溯链接": url("S05", "◀ 返回指标血缘矩阵")})
        else:
            fp_sql = ("FACTORY_PROD IN ('11','12')" if fac == "benbu"
                      else f"FACTORY_PROD='{allow[0]}'")
            for r in data["ods_sample_rows"]:
                if r[1] not in allow:
                    continue
                v = {c: T(r[i]) for i, c in enumerate(cols)}
                v["ODS源表"] = T(data["ods_steel"].get(fac, {}).get("tbl", [""])[0])
                v["筛选SQL"] = T(f"SELECT ... WHERE {fp_sql} "
                                 f"AND COMPLEX_DECIDE_CODE NOT IN('2','4') "
                                 f"AND substr(REC_CREATE_TIME,1,6)='202609'")
                v["筛选键"] = T(fac)
                v["血缘回溯链接"] = url("S05", "◀ 返回指标血缘矩阵")
                recs.append(v)
        out[skey] = (ods_fields, recs)

    # ---------- S19 下钻链接索引 ----------
    fields = [("层级", "FIELD_TYPE_TEXT"), ("起点", "FIELD_TYPE_TEXT"),
              ("目标子表", "FIELD_TYPE_TEXT"), ("目标说明", "FIELD_TYPE_TEXT"),
              ("筛选键", "FIELD_TYPE_TEXT"), ("下钻链接", "FIELD_TYPE_URL")]
    recs = []
    titles = dict(SHEETS)
    for f in FACTORY_KEYS:
        dwd_key, ods_key = F_DRILL[f]
        for metric in METRIC_KEYS:
            recs.append({"层级": T("L1→L2"),
                         "起点": T(f"趋势明细 · {f_cname[f]} · {METRIC_NAME[metric]}"),
                         "目标子表": T(titles["S04"]),
                         "目标说明": T("ODS→DWD→DWS→ADS 全链路 + 加工存储过程"),
                         "筛选键": T(f"{f}|{metric}"),
                         "下钻链接": url("S04", "▶ 打开血缘链路", f"{f}|{metric}")})
        recs.append({"层级": T("L2→L3"), "起点": T(f"血缘链路 · {f_cname[f]}"),
                     "目标子表": T(titles[dwd_key]),
                     "目标说明": T("TP003_TMP1_* 临时表结构与明细（按 FACTORY_DIV 过滤）"),
                     "筛选键": T(f), "下钻链接": url(dwd_key, "▶ 打开 DWD 临时表", f)})
        recs.append({"层级": T("L3→L4"), "起点": T(f"DWD 临时表 · {f_cname[f]}"),
                     "目标子表": T(titles[ods_key]),
                     "目标说明": T("ODS 最底层原始字段明细（清洗前）"),
                     "筛选键": T(f), "下钻链接": url(ods_key, "▶ 打开 ODS 原始明细", f)})
        recs.append({"层级": T("L4→回溯"), "起点": T(f"ODS 原始明细 · {f_cname[f]}"),
                     "目标子表": T(titles["S05"]), "目标说明": T("回溯 13 列血缘矩阵"),
                     "筛选键": T(f), "下钻链接": url("S05", "◀ 返回血缘矩阵")})
    for z in data["dws_daily"].get("202609", {}):
        fac = ZB_TO_FACTORY.get(z, "benbu")
        recs.append({"层级": T("DWS→L3"), "起点": T(f"DWS 逐日明细 · ZB {z}"),
                     "目标子表": T(titles[F_DRILL[fac][0]]),
                     "目标说明": T(f"{f_cname[fac]} 的 DWD 临时表明细"),
                     "筛选键": T(f"{fac}|steel|{z}"),
                     "下钻链接": url(F_DRILL[fac][0], "▶ 打开 DWD 临时表", f"{fac}|steel|{z}")})
    out["S19"] = (fields, recs)

    # ---------- S20 最新月对标 ----------
    fields = [("工厂", "FIELD_TYPE_TEXT"), ("FACTORY_DIV", "FIELD_TYPE_TEXT"),
              ("钢铁料耗kg/t", "FIELD_TYPE_NUMBER"), ("炼钢成本元/吨", "FIELD_TYPE_NUMBER"),
              ("筛选键", "FIELD_TYPE_TEXT"), ("下钻链接", "FIELD_TYPE_URL")]
    last = len(months) - 1
    recs = []
    for f in FACTORY_KEYS:
        row = {"工厂": T(f_cname[f]), "FACTORY_DIV": T("/".join(f_div[f])),
               "筛选键": T(f"{f}|benchmark")}
        sv = steel[f][last] if last < len(steel[f]) else None
        cv = cost[f][last] if last < len(cost[f]) else None
        if sv is not None:
            row["钢铁料耗kg/t"] = N(sv)
        if cv is not None:
            row["炼钢成本元/吨"] = N(cv)
        row["下钻链接"] = url(F_DRILL[f][0], f"▶ 下钻 DWD 临时表 · {f_cname[f]}", f)
        recs.append(row)
    out["S20"] = (fields, recs)

    return out


# =============================================================================
# ===== 4b. 串厂自检 ==========================================================
# =============================================================================

def cell_text(v):
    if isinstance(v, list) and v:
        return str(v[0].get("text", ""))
    return "" if v is None else str(v)


def self_check(built, data):
    """返回问题列表；空列表 = 按工厂过滤正确。"""
    problems = []
    tt = {t["id"]: t for t in data["tmp_tables"]}
    titles = dict(SHEETS)

    for skey, fac in (("S09", "yilian"), ("S10", "erlian"), ("S11", "benbu"),
                      ("S12", "luoyuan"), ("S13", "quanzhou")):
        allow = set(data["f_div"][fac])
        for r in built[skey][1]:
            t = tt.get(cell_text(r.get("临时表ID")))
            if not t:
                continue
            val = cell_text(r.get(f"列{_key_col(t) + 1}"))
            if val not in allow:
                problems.append(f"{titles[skey]} 混入 {val}（允许 {sorted(allow)}），表 {t['id']}")

    cols = data["ods_sample_cols"]
    fpi = cols.index("FACTORY_PROD") if "FACTORY_PROD" in cols else 1
    for skey, fac in (("S14", "yilian"), ("S15", "erlian"), ("S16", "benbu")):
        allow = {"yilian": {"11"}, "erlian": {"12"}, "benbu": {"11", "12"}}[fac]
        for r in built[skey][1]:
            val = cell_text(r.get(cols[fpi]))
            if val and val not in allow:
                problems.append(f"{titles[skey]} ODS 混入 FACTORY_PROD={val}（允许 {sorted(allow)}）")
    return problems


# =============================================================================
# ===== 5. 主流程 =============================================================
# =============================================================================

def log(msg):
    print(msg, flush=True)


def main():
    ap = argparse.ArgumentParser(description="企微智能表格同步")
    ap.add_argument("--data", default=str(DATA_JSON))
    ap.add_argument("--docid", default="", help="复用已有智能表格 docid")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    log(f"数据载入完成：{len(data['meta']['months'])} 个月份，"
        f"血缘矩阵 {len(data['lineage_matrix']['rows'])} 行，"
        f"临时表 {len(data['tmp_tables'])} 张")

    if args.dry_run:
        built = build_all(data, {k: "SHEETID_" + k for k, _ in SHEETS},
                          "DOCID_PLACEHOLDER", "https://example/doc")
        total = 0
        log("\n[DRY-RUN] 子表结构预览：")
        for key, title in SHEETS:
            fields, recs = built[key]
            n = len(recs) if not args.limit else min(len(recs), args.limit)
            total += n
            log(f"  {title:<34} 字段 {len(fields):>3} 列   记录 {n:>5} 行")
        log(f"\n  合计记录 {total} 行 / {len(SHEETS)} 张子表（未调用任何写接口）")
        probs = self_check(built, data)
        if probs:
            log("\n  ！串厂自检发现问题：")
            for p in probs[:20]:
                log("    - " + p)
        else:
            log("  ✓ 串厂自检通过：一炼(11)/二炼(12)/罗源(14)/泉州(13) 互不混入")
        return

    if not _resolve_corpsecret():
        sys.exit("未配置 CORPSECRET：请设置环境变量 WECOM_CORPSECRET，或在脚本顶部填写。")

    # ---- 1) 文档 ----
    log("\n[1/5] 创建/复用智能表格文档")
    if args.docid:
        docid, doc_url = args.docid, ""
        log(f"   复用 docid={docid}")
    else:
        docid, doc_url = create_doc()

    # ---- 2) 子表 ----
    log("\n[2/5] 创建子表")
    existing = {s["title"]: s["sheet_id"] for s in list_sheets(docid)}
    log(f"   已有子表 {len(existing)} 张")
    sid, idx = {}, 0
    for key, title in SHEETS:
        if title in existing and args.docid:
            sid[key] = existing[title]
            log(f"   复用 {title}")
            continue
        if idx == 0 and existing:
            first = next(iter(existing.values()))
            rename_sheet(docid, first, title)
            sid[key] = first
            log(f"   重命名默认子表 → {title}")
        else:
            sid[key] = add_sheet(docid, title, idx)
            log(f"   + {title}")
        idx += 1

    # ---- 3) 字段 + 记录 ----
    built = build_all(data, sid, docid, doc_url)
    log("\n[3/5] 建字段并写入记录")
    grand = 0
    for key, title in SHEETS:
        fields, recs = built[key]
        if args.limit:
            recs = recs[:args.limit]
        fdefs = [{"field_title": n, "field_type": t} for n, t in fields]
        added = ensure_fields(docid, sid[key], fdefs)
        log(f"   ▸ {title}：字段 {len(fdefs)} 列（新增 {added}）")
        # 删掉 add_sheet 自带的默认『智能表列』（真实字段已存在，此时可安全删除）
        try:
            if remove_default_column(docid, sid[key]):
                log(f"      ✓ 已移除默认『智能表列』")
        except Exception:
            pass
        if recs:
            grand += add_records(docid, sid[key], recs)
        else:
            log("      （无记录）")

    # ---- 4) 权限 ----
    log("\n[4/5] 权限管理")
    grant_members(docid)

    # ---- 5) 回读校验 ----
    log("\n[5/5] 回读校验（分页抽样）")
    titles = dict(SHEETS)
    for key in ("S01", "S05", "S09", "S14", "S19"):
        n = sum(1 for _ in iter_records(docid, sid[key], page=200, max_rows=2000))
        log(f"   {titles[key]:<34} 回读 {n} 行")

    log(f"\n完成：共写入 {grand} 行记录")
    if doc_url:
        log(f"文档链接：{doc_url}")


if __name__ == "__main__":
    main()
