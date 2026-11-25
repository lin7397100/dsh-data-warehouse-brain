# -*- coding: utf-8 -*-
"""verify_eplat_templates.py —— 把 sg-eplat-metadata-core 的 SQL 模板全部实跑一遍

为什么需要：
  `references/eplat_sql_templates.sql` 是 EPLAT 设计态取数的**唯一权威模板**。
  它一旦写错列名/别名/CLOB 截断长度，专家会在生产里反复撞 ORA 错误。
  本脚本按 `-- ----` 分隔符切块，逐条替换占位符后经 MCP 实跑，任何一条报错即 exit 1。

用法：
  python tools/verify_eplat_templates.py                 # 全量实跑
  python tools/verify_eplat_templates.py --only Q06,Q07  # 只跑指定模板
  python tools/verify_eplat_templates.py --url http://10.18.136.38:8770/mcp

退出码：0 全通过；1 有模板失败；2 文件/MCP 不可用

注：占位符必须替换成**真实字面量**——MCP 不支持绑定变量。
    默认值取自 2026-11-25 实测样本，可经 --sub 覆盖。
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TPL = os.path.join(ROOT, "skills", "sg-eplat-metadata-core",
                   "references", "eplat_sql_templates.sql")
DEFAULT_URL = os.environ.get("SG_EPLAT_MCP_URL", "http://10.18.136.38:8770/mcp")

SUB = {
    ":uuid": "DY_MO_FM_00_c0314be176764e2e8667ddb2f897ad4f",
    ":fact_field_uuid": "DY_MO_FM_00_c0314be176764e2e8667ddb2f897ad4f",
    ":dim_field_uuid": "DY_MO_DM_00_5f128d732ffd4b5b86b230e13aaba246",
    ":phys_field_uuid": "DY_TB_TF_00_a360d9f548314bcdbd4a76b378376d66",
    ":keyword": "合格率",
    ":term": "伸缩",
    ":table_name": "T_ADS_SRV_CGWL_CLKC08",
    ":column_name": "PUR_ORG_NAME",
    ":api_id": "M_DWD_FACT_CGJH_CLJH01_JX.D_A_CGJX_PSCS_BJK2_001",
}


class Mcp(object):
    def __init__(self, url):
        self.url = url
        self.sid = None
        self.hdr = {"Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"}

    def _post(self, payload, timeout=180):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.url, data=data, headers=dict(self.hdr), method="POST")
        if self.sid:
            req.add_header("Mcp-Session-Id", self.sid)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            sid = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
            if sid:
                self.sid = sid
            raw = r.read().decode("utf-8", "replace")
            ct = (r.headers.get("Content-Type") or "").lower()
        if "text/event-stream" in ct:
            chunks = [ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")]
            raw = chunks[-1] if chunks else raw
        return raw

    def start(self):
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "dwb-verify", "version": "1.1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def query(self, sql, max_rows=50):
        doc = json.loads(self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "oracle_query", "arguments": {"sql": sql, "max_rows": max_rows}}}))
        if "error" in doc:
            return False, "RPC-ERROR " + json.dumps(doc["error"], ensure_ascii=False)[:200]
        txt = "".join(b.get("text", "") for b in (doc.get("result") or dict()).get("content") or [])
        if "执行失败" in txt or "ORA-" in txt:
            return False, txt.replace("\n", " ")[:220]
        lo, hi = txt.find("{"), txt.rfind("}")
        try:
            obj = json.loads(txt[lo:hi + 1])
            return True, "rows=%s truncated=%s" % (obj.get("row_count"), obj.get("truncated"))
        except Exception:  # noqa
            return True, txt[:160].replace("\n", " ")


def blocks(path):
    """按 '-- ----' 分隔符切块，返回 [(Qnn, title, sql)]；SQL 块紧跟其标题块。"""
    raw = io.open(path, encoding="utf-8").read()
    out, cur = [], None
    for blk in re.split(r"(?m)^-- -{5,}\s*$", raw):
        m = re.search(r"(?m)^-- (Q\d\d)\s*(.*)$", blk)
        if m:
            cur = (m.group(1), m.group(2).strip())
            continue
        sql = "\n".join(ln for ln in blk.split("\n") if not ln.lstrip().startswith("--")).strip().rstrip(";")
        if sql and cur:
            out.append((cur[0], cur[1], sql))
            cur = None
    return out


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--tpl", default=TPL)
    ap.add_argument("--only", default="")
    ap.add_argument("--sub", action="append", default=[], help="额外替换 k=v，可多次")
    a = ap.parse_args(argv)

    if not os.path.isfile(a.tpl):
        print("FAIL: 找不到模板 %s" % a.tpl)
        return 2

    sub = dict(SUB)
    for kv in a.sub:
        k, _, v = kv.partition("=")
        sub[k] = v

    want = {x.strip().upper() for x in a.only.split(",") if x.strip()}
    cases = [c for c in blocks(a.tpl) if not want or c[0] in want]
    if not cases:
        print("FAIL: 没有可执行的模板块")
        return 2

    mcp = Mcp(a.url)
    try:
        mcp.start()
    except (urllib.error.URLError, OSError) as e:
        print("FAIL: EPLAT MCP 不可达 %s（%s）" % (a.url, e))
        return 2

    ok = bad = 0
    for qid, title, sql in cases:
        for k, v in sub.items():
            sql = sql.replace(k, v)
        good, msg = mcp.query(sql)
        ok += 1 if good else 0
        bad += 0 if good else 1
        print("%s %-5s %-34s %s" % ("OK  " if good else "ERR ", qid, title[:34], msg))
    print("\n合计：OK=%d ERR=%d（模板 %d 条）" % (ok, bad, len(cases)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
