# -*- coding: utf-8 -*-
"""
企业微信(私有化) 智能表格 smartsheet 读取客户端
================================================
关键事实(已实测确认):
  * get_records 对 FIELD_TYPE_FORMULA(公式字段) 恒返回 null —— 服务端在 API 读取路径不做公式计算。
  * get_fields 的 property_formula 为空 {} —— 公式定义文本不通过 API 暴露。
  * 因此: 公式字段的"内容"无法经由 REST API 直接取得。
  * 解决路径: 用腾讯文档智能表格「脚本/自动化」把公式结果镜像到普通字段, 再用本客户端读取普通字段。

本模块职责:
  1. 取 token / 列子表 / 列字段 / 列记录(分页)
  2. 把各种字段类型的原始值标准化为 Python 原生类型
  3. 把"公式字段"与普通字段分开标记, 公式字段显式标注为 API 不可读
"""

import os
import urllib.request
import urllib.error
import json
import ssl

# ------------------------- 配置 -------------------------
BASE = "https://wecom.fjsg.com.cn"
CORPID = os.environ.get("CORPID", "")
CORPSECRET = os.environ.get("CORPSECRET", "")  # G5-SEC: 凭据不随包分发
DOCID = "s3_AMAA4RTkAAACdU08iSJSdO5DFEI6X_a"

# 私有化部署常见自签证书: 关闭主机名/证书校验以联通。
# 正式受信环境可改为 True (或传入自定义 CA)。
_VERIFY_SSL = False

# 周报汇总 子表
SHEET_ID_REPORT = "th3EVw"

_FORMULA_TYPE = "FIELD_TYPE_FORMULA"


def _ctx():
    if _VERIFY_SSL:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _post(path, payload):
    url = BASE + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, context=_ctx(), timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"errcode": e.code, "errmsg": "HTTPError", "_raw": e.read().decode("utf-8", "replace")}
    except Exception as e:  # noqa
        return None, {"errcode": -1, "errmsg": "EXCEPTION", "_exc": str(e)}


def require_credentials():
    """G5-SEC：凭据不随包分发。未注入时给出可操作报错，禁止空值直送企微 API。"""
    missing = [k for k, v in (("CORPID", CORPID), ("CORPSECRET", CORPSECRET)) if not v]
    if missing:
        raise RuntimeError(
            "G5-SEC 凭据未注入：缺少环境变量 %s。"
            "请从企微智能表格「数仓智脑凭据管理」读取后注入环境变量，或改用 DB2 MCP 主通道；"
            "切勿把凭据写回专家包文件。若仍沿用 2026-11-05 前随包分发的凭据，"
            "请先在企微后台轮换该 CORPSECRET。" % " / ".join(missing)
        )


def get_token():
    require_credentials()
    url = BASE + "/cgi-bin/gettoken?corpid=%s&corpsecret=%s" % (CORPID, CORPSECRET)
    with urllib.request.urlopen(urllib.request.Request(url, method="GET"), context=_ctx(), timeout=30) as r:
        obj = json.loads(r.read().decode("utf-8"))
    if obj.get("errcode") != 0:
        raise RuntimeError("gettoken 失败: %s" % json.dumps(obj, ensure_ascii=False))
    return obj["access_token"]


# ------------------------- 业务接口 -------------------------
def get_sheets(at, docid=DOCID):
    st, body = _post("/cgi-bin/wedoc/smartsheet/get_sheet?access_token=" + at, {"docid": docid})
    if body.get("errcode") != 0:
        raise RuntimeError("get_sheet 失败: %s" % json.dumps(body, ensure_ascii=False))
    return body.get("sheet_list", [])


def get_fields(at, docid=DOCID, sheet_id=None, limit=1000):
    st, body = _post("/cgi-bin/wedoc/smartsheet/get_fields?access_token=" + at,
                     {"docid": docid, "sheet_id": sheet_id, "limit": limit})
    if body.get("errcode") != 0:
        raise RuntimeError("get_fields 失败: %s" % json.dumps(body, ensure_ascii=False))
    return body.get("fields", [])


def get_records(at, docid=DOCID, sheet_id=None, offset=0, limit=100):
    """分页拉取记录, 自动翻页合并。"""
    all_recs = []
    while True:
        st, body = _post("/cgi-bin/wedoc/smartsheet/get_records?access_token=" + at,
                         {"docid": docid, "sheet_id": sheet_id, "offset": offset, "limit": limit})
        if body.get("errcode") != 0:
            raise RuntimeError("get_records 失败: %s" % json.dumps(body, ensure_ascii=False))
        recs = body.get("records", [])
        all_recs.extend(recs)
        if not body.get("has_more") or not recs:
            break
        offset = body.get("next", offset + len(recs))
    return all_recs


# ------------------------- 值标准化 -------------------------
def normalize_value(field_type, raw):
    """把智能表格各字段类型的原始值(raw)转成干净的 Python 类型。"""
    if raw is None:
        return None

    # 文本类: 形如 [{"type":"text","text":"xxx"}]
    if field_type in ("FIELD_TYPE_TEXT", "FIELD_TYPE_SINGLE_SELECT", "FIELD_TYPE_URL",
                      "FIELD_TYPE_PHONE_NUMBER", "FIELD_TYPE_EMAIL", "FIELD_TYPE_BARCODE"):
        if isinstance(raw, list):
            return " ".join(x.get("text", "") for x in raw if isinstance(x, dict))
        return raw

    # 成员类: [{"user_id":"..."}]
    if field_type in ("FIELD_TYPE_USER", "FIELD_TYPE_CREATED_USER", "FIELD_TYPE_MODIFIED_USER"):
        if isinstance(raw, list):
            return [x.get("user_id") for x in raw if isinstance(x, dict)]
        return raw

    # 多选: [{"id":..,"text":..}]
    if field_type == "FIELD_TYPE_SELECT":
        if isinstance(raw, list):
            return [x.get("text") for x in raw if isinstance(x, dict)]
        return raw

    # 关联/双向关联: ["record_id", ...]
    if field_type in ("FIELD_TYPE_TWOWAYLINKRECORDS", "FIELD_TYPE_REFERENCE"):
        return raw if isinstance(raw, list) else [raw]

    # 自动编号: {"seq":"1","text":"1"}
    if field_type == "FIELD_TYPE_AUTONUMBER":
        if isinstance(raw, dict):
            return raw.get("text") or raw.get("seq")
        return raw

    # 其余(数字/货币/百分数/进度/复选框/日期时间戳/公式/查找): 原样返回
    return raw


# ------------------------- 高层封装 -------------------------
def dump_sheet(at, docid=DOCID, sheet_id=None, limit=100):
    """
    读取一个子表, 返回结构化结果。
    公式字段会被单列到 formula_fields 并标注 'API不可读', 普通字段进入 rows。
    """
    fields = get_fields(at, docid, sheet_id)
    records = get_records(at, docid, sheet_id, limit=limit)

    formula_fields = [f for f in fields if f["field_type"] == _FORMULA_TYPE]
    plain_fields = [f for f in fields if f["field_type"] != _FORMULA_TYPE]

    rows = []
    for rec in records:
        values = rec.get("values", {})
        row = {"record_id": rec.get("record_id")}
        for f in fields:
            row[f["field_title"]] = normalize_value(f["field_type"], values.get(f["field_title"]))
        rows.append(row)

    return {
        "sheet_id": sheet_id,
        "total_fields": len(fields),
        "formula_fields": [f["field_title"] for f in formula_fields],
        "plain_fields": [f["field_title"] for f in plain_fields],
        "rows": rows,
        "note": ("公式字段(FIELD_TYPE_FORMULA)经实测在 get_records 中恒为 null, "
                 "需通过腾讯文档脚本/自动化把结果镜像到普通字段后再读取。"),
    }


# ------------------------- 演示 -------------------------
if __name__ == "__main__":
    at = get_token()
    print("token OK")

    sheets = get_sheets(at)
    print("\n子表清单:")
    for s in sheets:
        print("  %s  %s  (%s)" % (s["sheet_id"], s["title"], s["type"]))

    print("\n===== 周报汇总(th3EVw) dump =====")
    result = dump_sheet(at, DOCID, SHEET_ID_REPORT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
