#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5sApi DB2 SQL 执行桥接器（sg-db2-rest）
=======================================
当 DB2 MCP 不可用时（例如专家团被分享给未配置 db2 mcp 的环境），
作为降级通道，通过 5sApi REST 接口执行只读 SQL。

凭据（三层读取，高优先级优先）：
1. 环境变量 SGDW_LIGHTCODE_TOKEN / SGDW_USER_ID / SGDW_CLIENT_ID（最高，便于临时覆盖）。
2. 个人本地文件 ~/.dsh/.sgdw_rest.env（本机专用，不随团队分享；可选覆盖）。
3. 团队内联凭据（通过环境变量或智能表格自动填充；G5-SEC 合规）
   分发由所有者控制——仅分享给被授权的人；轮换仅改此一处）。
token 不写入任何 SKILL.md 技能文件。仅允许只读 SQL（SELECT / WITH 起手）；写操作与 DDL 一律拒绝。
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import re

API_URL = "https://eqms.fjsg.com.cn:9443/com.baosight.sg.bdds/service/proxy/5sApi/D_A_SMBBMASC01_SQLEXECUTE"
DEFAULT_ENV_FILE = os.path.expanduser("~/.dsh/.sgdw_rest.env")
TEAM_BUNDLED_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sgdw_rest.env")

# 基础防护：禁止写操作 / DDL（先剥离字符串字面量与注释，再按词边界匹配）
_WRITE_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "CALL", "COMMIT", "ROLLBACK",
)


def _strip_literals(sql):
    # 去掉 '...' 字符串与 -- 行注释、/* */ 块注释，避免误判列名/字符串中的关键字
    s = re.sub(r"'(?:[^']|'')*'", "''", sql, flags=re.IGNORECASE)
    s = re.sub(r"--[^\n]*", " ", s)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.DOTALL)
    return s


def _is_readonly(sql):
    s = _strip_literals(sql).upper()
    head = s.lstrip()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        return False, "仅允许以 SELECT / WITH 起手的只读语句"
    for kw in _WRITE_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", s):
            return False, "检测到禁止的关键字: %s" % kw
    return True, ""


def load_config():
    # 候选凭据文件，按优先级（先到先得，setdefault 保证高优先级不被覆盖）：
    #   1) $SGDW_ENV_FILE（显式指定，最高）
    #   2) 个人本地文件 ~/.dsh/.sgdw_rest.env（DSH 唯一本地路径）
    #   3) 团队内置 scripts/sgdw_rest.env（随专家团分享的默认值，含所有者 token）
    candidates = []
    env_file = os.environ.get("SGDW_ENV_FILE")
    if env_file:
        candidates.append(env_file)
    candidates.append(DEFAULT_ENV_FILE)
    candidates.append(TEAM_BUNDLED_ENV)
    file_vars = {}
    for cf in candidates:
        if not cf or not os.path.isfile(cf):
            continue
        try:
            with open(cf, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    file_vars.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass
    cfg = {
        "token": os.environ.get("SGDW_LIGHTCODE_TOKEN") or file_vars.get("SGDW_LIGHTCODE_TOKEN", ""),
        "user_id": os.environ.get("SGDW_USER_ID") or file_vars.get("SGDW_USER_ID", ""),
        "client_id": os.environ.get("SGDW_CLIENT_ID") or file_vars.get("SGDW_CLIENT_ID", "sgdw-sc01"),
    }
    return cfg


def _fetch_page(sql, cfg, offset, limit, timeout):
    body = {
        "sql": sql,
        "clientId": cfg["client_id"],
        "modelId": "",
        "showCount": "true",
        "offset": str(offset),
        "userId": cfg["user_id"],
        "limit": str(limit),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Cookie", "lightcodegtw-token=" + cfg["token"])
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code, e.read().decode("utf-8", "replace")[:2000]
    except Exception as e:  # noqa: BLE001
        return None, "NET_ERROR: %s" % repr(e), ""
    try:
        j = json.loads(raw)
    except Exception:
        return None, "RESPONSE_NOT_JSON", raw[:1000]
    status = j.get("status")
    if status not in (1, "1"):
        return None, "API_ERROR: %s" % str(j.get("msg", "未知错误")), raw[:1000]
    rows = j.get("datas") or []
    rp = j.get("resultPage") or {}
    eff_limit = int(rp.get("limit") or limit)
    return rows, None, eff_limit


def execute(sql, cfg, limit=20000, max_rows=None, timeout=60):
    limit = min(int(limit), 20000)  # 接口单页上限 20000
    # 5sApi 已知缺陷：limit=1 时单行结果集返回空（实测 2026-10-10）。
    # 规避：请求页大小至少为 2，靠 max_rows 控制实际返回行数。
    if limit < 2:
        limit = 2
    offset = 0
    all_rows = []
    while True:
        rows, err, eff_limit = _fetch_page(sql, cfg, offset, limit, timeout)
        if err:
            return {"ok": False, "error": err}
        all_rows.extend(rows)
        if max_rows and len(all_rows) >= max_rows:
            all_rows = all_rows[:max_rows]
            break
        # 末页判定：本页行数 < 接口生效上限 → 已取完
        if len(rows) < eff_limit:
            break
        offset += len(rows)
    return {"ok": True, "count": len(all_rows), "rows": all_rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description="5sApi DB2 只读 SQL 桥接（db2 mcp 降级通道）")
    ap.add_argument("--sql", required=True, help="只读 SQL（SELECT/WITH 起手）")
    ap.add_argument("--limit", type=int, default=20000, help="单页上限，<=20000")
    ap.add_argument("--max-rows", type=int, default=None, help="总返回行数上限（安全闸）")
    ap.add_argument("--csv", default=None, help="可选：将结果写出 CSV 的路径")
    ap.add_argument("--timeout", type=int, default=60, help="单次请求超时（秒）")
    ap.add_argument("--check-only", action="store_true", help="仅做只读校验，不发起请求")
    args = ap.parse_args(argv)

    ok, reason = _is_readonly(args.sql)
    if not ok:
        print(json.dumps({"ok": False, "error": "READONLY_GUARD: " + reason}, ensure_ascii=False))
        return 2
    if args.check_only:
        print(json.dumps({"ok": True, "readonly": True}, ensure_ascii=False))
        return 0

    cfg = load_config()
    if not cfg["token"]:
        print(json.dumps({
            "ok": False,
            "error": ("未配置凭据：默认应随团队内置 scripts/sgdw_rest.env 提供（含所有者 token）；"
                      "亦可经环境变量 SGDW_LIGHTCODE_TOKEN 注入，或个人本地 ~/.dsh/.sgdw_rest.env 覆盖。"),
        }, ensure_ascii=False))
        return 2

    res = execute(args.sql, cfg, limit=args.limit, max_rows=args.max_rows, timeout=args.timeout)
    if not res.get("ok"):
        print(json.dumps(res, ensure_ascii=False))
        return 1

    if args.csv:
        import csv
        rows = res["rows"]
        if rows:
            cols = list(rows[0].keys())
            with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
        print(json.dumps({"ok": True, "count": res["count"], "csv": args.csv}, ensure_ascii=False))
    else:
        print(json.dumps({"ok": True, "count": res["count"], "rows": res["rows"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
