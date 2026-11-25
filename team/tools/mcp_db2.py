#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""mcp_db2.py —— DSH mcp-db2 的纯标准库客户端（streamable HTTP，零 pip 依赖）。

用途：
  - 给快车道（fast_ask.py --live）用：确定性取数后，直接在本机把真数跑回来，
    不再要求"在 DSH 会话里再调一次 mcp__db2__execute_sql"。
  - 给 doctor 用：一条 SQL 探活，非致命。

用法：
  python tools/mcp_db2.py --sql "SELECT ZB_NAME,YMD,ZB_VALUE FROM ... WHERE ZB_NAME='...' ORDER BY YMD DESC" --limit 5
  python tools/mcp_db2.py --probe     # 冒烟：探圆棒产量最新分区

环境变量：
  SG_DB2_MCP_URL  默认 http://10.18.136.38:8765/mcp
  SG_DB2_MCP === 'off'  时本机禁用（与 cordis.patch.yml 的 disabled 表达式一致）

已知服务器行为（2026-11-18 实测，不要重犯）：
  1. 服务端会在 SQL 末尾自动拼 `fetch first 3000 rows only` —— SQL 文本里**自己写 FETCH FIRST
     必撞 SQLCODE=-104**（重复 FETCH）。要限量走 --limit 参数。
  2. 只读强制：非 SELECT/WITH/VALUES 直接拒。
  3. 响应有两段 content：markdown 表格 + ```json 机器块；本脚本解析 JSON 块。
  4. 首条连接要先 initialize（拿 Mcp-Session-Id），再 notifications/initialized，再调工具。

退出码：0 成功；3 MCP 不可达；4 服务端报错（isError）；5 响应无法解析。
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

# SQL 尾部自带的限行子句必须剥离：服务端会自动再拼一段，重复限行 → SQLCODE=-104。
_LIMIT_RE = re.compile(
    r'\s*(?:fetch\s+first\s+\d+\s+rows\s+only|limit\s+\d+)\s*;?\s*$',
    re.IGNORECASE)


def _strip_limit(sql):
    if not sql:
        return sql
    prev = None
    while prev != sql:
        prev = sql
        sql = _LIMIT_RE.sub('', sql).rstrip()
    return sql

URL = os.environ.get("SG_DB2_MCP_URL", "http://10.18.136.38:8765/mcp")
_session = {"id": None}


def _post(payload, timeout=60):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _session["id"]:
        headers["Mcp-Session-Id"] = _session["id"]
    req = urllib.request.Request(URL, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            _session["id"] = sid
        return r.status, r.read().decode("utf-8", "ignore")


def _parse(body):
    body = (body or "").strip()
    if body.startswith("event:") or "data:" in body:
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return None
    return json.loads(body) if body else None


def _handshake():
    _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
           "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                      "clientInfo": {"name": "dwb-mcp-db2", "version": "1.0"}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})


def execute(sql, limit=3000, timeout=60):
    """返回 dict：{ok, columns, rows, row_count, markdown, error}。"""
    sql = _strip_limit(sql)
    last = None
    for attempt in (1, 2):
        try:
            if not _session["id"]:
                _handshake()
            code, body = _post({
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "execute_sql",
                           "arguments": {"sql": sql, "limit": int(limit), "showCount": True}},
            }, timeout=timeout)
        except urllib.error.HTTPError as e:
            last = {"ok": False, "error": "HTTP %d：%s" % (e.code, e.read().decode("utf-8", "ignore")[:300]), "code": 4}
            _session["id"] = None  # 会话可能已失效，下轮重握
            continue
        except Exception as e:
            return {"ok": False, "error": "调用失败：%s" % e, "code": 3}

        msg = _parse(body) or {}
        result = msg.get("result") or {}
        content = result.get("content") or []
        md = ""
        js = None
        for c in content:
            if not isinstance(c, dict):
                continue
            txt = c.get("text") or ""
            if txt.startswith("```json"):
                block = txt.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                try:
                    js = json.loads(block)
                except Exception:
                    js = None
            else:
                md += txt
        if result.get("isError"):
            first = (content[0].get("text")[:300] if content else body[:300])
            return {"ok": False, "error": first, "code": 4}
        if js is None:
            return {"ok": False, "error": "响应里没有 JSON 块：%s" % md[:200], "code": 5}
        out = {
            "ok": True,
            "columns": js.get("columns") or [],
            "rows": js.get("rows") or [],
            "row_count": len(js.get("rows") or []),
            "markdown": md,
        }
        if attempt == 2 and last:
            out["recovered_after_retry"] = True
        return out
    return last or {"ok": False, "error": "未知错误", "code": 4}


def call_tool(name, arguments=None, timeout=30):
    """通用 MCP 工具调用（list_schemas / list_tables / describe_table）。
    返回 {ok, columns, rows, markdown, error}。"""
    arguments = arguments or {}
    last = None
    for attempt in (1, 2):
        try:
            if not _session["id"]:
                _handshake()
            code, body = _post({
                "jsonrpc": "2.0", "id": 50, "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }, timeout=timeout)
        except urllib.error.HTTPError as e:
            last = {"ok": False, "error": "HTTP %d：%s" % (e.code, e.read().decode("utf-8", "ignore")[:300]), "code": 4}
            _session["id"] = None
            continue
        except Exception as e:
            return {"ok": False, "error": "调用失败：%s" % e, "code": 3}
        msg = _parse(body) or {}
        result = msg.get("result") or {}
        content = result.get("content") or []
        md = ""
        js = None
        for c in content:
            if not isinstance(c, dict):
                continue
            txt = c.get("text") or ""
            if txt.startswith("```json"):
                block = txt.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                try:
                    js = json.loads(block)
                except Exception:
                    js = None
            else:
                md += txt
        if result.get("isError"):
            first = (content[0].get("text")[:300] if content else body[:300])
            return {"ok": False, "error": first, "code": 4}
        return {
            "ok": True,
            "columns": js.get("columns") if js else [],
            "rows": js.get("rows") if js else [],
            "row_count": len(js.get("rows") or []),
            "markdown": md,
        }
    return last or {"ok": False, "error": "未知错误", "code": 4}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", help="只读 SELECT")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--probe", action="store_true", help="冒烟：探圆棒产量最新分区")
    ap.add_argument("--out", help="把 JSON 结果写到文件")
    args = ap.parse_args()

    if os.environ.get("SG_DB2_MCP") == "off":
        print("SG_DB2_MCP=off，按约定禁用 MCP")
        return 3

    if args.probe:
        args.sql = ("SELECT MAX(YMD) AS MAX_YMD, COUNT(*) AS CNT "
                    "FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_0002 "
                    "WHERE ZB_NAME='三钢闽光能源-圆棒产量t-日统计'")

    if not args.sql:
        print("缺 --sql 或 --probe")
        return 2

    res = execute(args.sql, limit=args.limit)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    return 0 if res.get("ok") else res.get("code") or 4


if __name__ == "__main__":
    sys.exit(main())
