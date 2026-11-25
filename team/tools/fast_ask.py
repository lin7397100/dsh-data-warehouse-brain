#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fast_ask.py —— 快车道物化直查（确定性 · 零 LLM 调用 · 零全量加载）
==================================================================

做五件事，全部在 Python 侧完成，只把 KB 级结果回给 LLM：
  1) 判车道      : 调 route_intent.build()，不是快车道就直接拒（不硬抄近路）
  2) 定指标码    : 调源包自带 skills/sg-indicator-system/engine/lookup_indicator.py --json
                   （离线匹配器，已内置 D4 伪零值防护 effective_has_sql）
  3) 加载守卫    : 调 scripts/materialized_sql_guard.py 的 load_guarded（R-04/R-05 代码级强制）
  4) 参数替换    : 按 `skills/sg-materialized-sql/SKILL.md` 的占位符表，只替换该 SQL 声明的 PARAMS
  5) 可选过网关  : `scripts/sg_db2_gateway.py exec` 三层门禁（G1 身份/G2 治理/G3 只读语法）
     注意：网关只放行，不执行（源包原文）。真执行必须由会话里的 mcp__db2__execute_sql 完成。

不做什么：
  - 不加载 indicator_registry.json（6.27 MB）到上下文，只在需要时按 zb_code 读单个 SQL 文件
  - 不改写 SQL 表达式（比率型/复合型指标不做 SUM 改写）
  - 不猜指标：候选不唯一或未物化 -> 输出 needs_slow_lane，交慢车道

用法：
  python tools/fast_ask.py --text "圆棒产量是多少" --date 20261117
  python tools/fast_ask.py --text "6#高炉月矿耗" --date 20261117 --gate
  python tools/fast_ask.py --text "为什么这个月成本涨了"        # 会被拒，走慢车道

退出码：0 = 产出可用 SQL 或明确的降级结论；1 = 未命中可用物化 SQL；2 = 环境错误。
"""

import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                     # 团队根目录（安装后 = TeamRoot）
LOOKUP = os.path.join(ROOT, "skills", "sg-indicator-system", "engine", "lookup_indicator.py")
GUARD = os.path.join(ROOT, "scripts", "materialized_sql_guard.py")
GATEWAY = os.path.join(ROOT, "scripts", "sg_db2_gateway.py")
SQL_DIR = os.path.join(ROOT, "knowledge", "design", "indicator", "materialized_sql")


def _load_router():
    sys.path.insert(0, HERE)
    import route_intent  # noqa: E402
    return route_intent


def _load_guard():
    spec = importlib.util.spec_from_file_location("_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lookup_candidates(text, top):
    if not os.path.exists(LOOKUP):
        return {"error": "lookup_indicator.py 不存在：%s" % LOOKUP, "candidates": []}
    p = subprocess.run(
        [sys.executable, LOOKUP, "--query", text, "--top", str(top), "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if p.returncode != 0:
        return {"error": (p.stdout or p.stderr or "")[:400], "candidates": []}
    try:
        return json.loads(p.stdout)
    except Exception as e:
        return {"error": "lookup 输出非 JSON: %s" % e, "candidates": []}


def _parse_header(raw):
    """解析物化 SQL 头部注释：ZB_CODE / ZB_NAME / DOMAIN / LEVEL / FACTORY / UNIT /
    SOURCE_TABLES / PARAMS / MATURITY / CALIBER_SOURCE / CONFIDENCE（缺者不臆造）。"""
    meta = {}
    for line in raw.splitlines():
        s = line.strip()
        if not s.startswith("--"):
            continue
        m = re.match(r"--\s*([A-Z_]+)\s*:\s*(.*)$", s)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def _subst(sql, params, ymd):
    """只替换该 SQL 声明的 PARAMS 中的时间占位符；未声明的令牌原样保留。"""
    declared = [p.strip() for p in re.split(r"[,\s]+", params or "") if p.strip()]
    d = _dt.datetime.strptime(ymd, "%Y%m%d")
    subs, left = {}, []
    for tok in declared:
        if tok == "$TD$":
            subs[tok] = ymd
        elif re.match(r"^\$D(\d+)\$", tok):
            n = int(re.match(r"^\$D(\d+)\$", tok).group(1))
            subs[tok] = (d - _dt.timedelta(days=n)).strftime("%Y%m%d")
        else:
            left.append(tok)
    out = sql
    for k, v in subs.items():
        out = out.replace(k, v)
    return out, subs, left


def _need_aggregation(text):
    """区间/对比意图：本月·今年·同比·环比。按 SKILL 规则需改谓词为 BETWEEN，属慢车道改写。"""
    return bool(re.search(r"(本月|当月|这个月|今年|本年|同比|环比|去年同期|累计)", text or ""))


def main():
    ap = argparse.ArgumentParser(description="快车道物化直查（确定性）")
    ap.add_argument("--text", required=True, help="用户原始问题")
    ap.add_argument("--date", default=_dt.date.today().strftime("%Y%m%d"), help="取数日 YYYYMMDD")
    ap.add_argument("--top", type=int, default=5, help="候选数")
    ap.add_argument("--gate", action="store_true", help="额外过 sg_db2_gateway.py 三层门禁")
    ap.add_argument("--live", action="store_true",
                    help="直连 mcp-db2 真取：先探最新分区，再执行（今日无分区时自动改取最新）")
    ap.add_argument("--sql-only", action="store_true", help="只打印最终 SQL")
    args = ap.parse_args()

    router = _load_router()
    route = router.build(args.text)

    out = {"route": {k: route[k] for k in ("lane", "task_type", "fast_lane", "reasons")}}
    out["date"] = args.date

    # ① 车道闸：不是快车道就明说，交回 SOP
    if not route["fast_lane"]:
        out["mode"] = "lane_rejected"
        out["reason"] = "判型为 %s，不走快车道；按 SOP 派辨枢出契约或走 T2a/T2b 链路。" % route["lane"]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    # ② 定码
    lk = _lookup_candidates(args.text, args.top)
    cands = lk.get("candidates") or []
    out["lookup"] = {
        "matched": lk.get("matched"),
        "query_core": lk.get("query_core"),
        "candidates": [
            {k: c.get(k) for k in ("zb_code", "name", "level", "domain", "factory_div",
                                   "has_sql", "blocked_reason", "score", "match_mode")}
            for c in cands
        ],
    }
    if lk.get("error"):
        out["mode"] = "env_error"
        out["reason"] = lk["error"]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2

    ready = [c for c in cands if c.get("fast_lane_ready")]

    # 编号守卫（最容易答错的一类）：问「6#高炉矿耗」不能答「1#高炉矿耗」。
    # 依据：lookup 的 _STOP 会剥掉厂部/时间词，但不会保留「6#」这种编号强判别；
    # 且打分对 has_sql 加 15 分，会把未物化的 6# 挤到后面、把 1# 顶上来。
    nums = re.findall(r"(\d+)\s*[#号]", args.text)
    if nums and ready:
        keep = [c for c in ready if any((n + "#") in (c["name"] or "") or (n + "号") in (c["name"] or "") for n in nums)]
        if not keep:
            all_cands = [c for c in cands if not c.get("has_sql")]
            out["mode"] = "needs_slow_lane"
            out["reason"] = "问题指定了编号 %s，但该编号下没有可用物化 SQL（不得改答别的编号）" % ",".join(n + "#" for n in nums)
            out["blocked"] = [
                {"zb_code": c["zb_code"], "name": c["name"], "why": c.get("blocked_reason") or "未物化"}
                for c in all_cands
            ][:5]
            out["numbering_guard"] = {"asked": nums, "rejected_candidates": [
                {"zb_code": c["zb_code"], "name": c["name"]} for c in ready if c not in keep][:5]}
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 1
        ready = keep
        out["numbering_guard"] = {"asked": nums, "kept": [c["zb_code"] for c in keep]}

    if not ready:
        out["mode"] = "needs_slow_lane"
        blocked = [c for c in cands if c.get("blocked_reason")]
        out["reason"] = (
            "无可用物化 SQL（空壳/缺文件/未解析指标）→ 转 sg-adhoc-indicator 或 sg-dsl-compiler"
        )
        out["blocked"] = [{"zb_code": c["zb_code"], "why": c["blocked_reason"]} for c in blocked][:5]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    best = ready[0]
    # 歧义保护：只有"分数几乎并列、且第一名并未真正包含用户说法"才算歧义。
    # 依据：lookup_indicator.py 对 effective_has_sql 与 atomic/derived 分别加 15/8 分，
    # 分数接近是加权结果而非语义并列；若查询核心词命中第一名名称，则视为已定位。
    second = ready[1] if len(ready) > 1 else None

    def _core_hit(name):
        core = re.sub(r"(是多少|什么意思|是什么|多少|是|的|呢|吗|？|\?)$", "", (lk.get("query_core") or "").strip())
        toks = [t for t in re.findall(r"[\u4e00-\u9fff]{2,}", core)]
        if not toks:
            return False
        return any(t in (name or "") for t in toks) or (core and core in (name or ""))

    ambiguous = bool(second) and second["name"] != best["name"] and (
        float(best.get("score") or 0) - float(second.get("score") or 0) < 3
    ) and not (_core_hit(best["name"]) and not _core_hit(second["name"]))
    out["chosen"] = {k: best[k] for k in ("zb_code", "name", "level", "domain", "factory_div", "score", "match_mode")}
    out["ambiguous"] = ambiguous
    if ambiguous:
        out["ambiguous_with"] = {"zb_code": second["zb_code"], "name": second["name"]}

    # ③ 守卫 + ④ 参数替换
    path = os.path.join(SQL_DIR, "%s.sql" % best["zb_code"])
    if not os.path.exists(path):
        out["mode"] = "needs_slow_lane"
        out["reason"] = "SQL 文件不存在：%s" % path
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1
    try:
        body = _load_guard().load_guarded(path)
    except Exception as e:
        out["mode"] = "needs_slow_lane"
        out["reason"] = "guard 拦截：%s" % e
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    raw = open(path, encoding="utf-8", errors="replace").read()
    meta = _parse_header(raw)
    sql, subs, unsupported = _subst(body, meta.get("PARAMS", "$TD$"), args.date)

    out["source"] = {"file": "materialized_sql/%s.sql" % best["zb_code"], "size_bytes": os.path.getsize(path)}
    out["meta"] = meta
    out["params_substituted"] = subs
    out["sql_executed"] = sql
    out["mode"] = "materialized"
    # maturity 三档原样透传（不写死 certified）
    out["maturity"] = {
        "maturity": meta.get("MATURITY") or "draft",
        "caliber_source": meta.get("CALIBER_SOURCE") or ("materialized_sql/%s.sql 头部注释" % best["zb_code"]),
        "confidence": meta.get("CONFIDENCE") or "0.70",
        "disclosure": None if (meta.get("MATURITY") in ("certified", "indexed")) else "[未经人工校准]",
    }
    warnings = []
    if unsupported:
        warnings.append("未替换的声明参数（需人工按口径处理）：%s" % ",".join(unsupported))
    if _need_aggregation(args.text):
        warnings.append("问题含区间/对比意图（本月/今年/同比/环比）：按 SKILL 需改谓词为 BETWEEN 区间聚合，本脚本不改写表达式，请走慢车道或用两期分别取数")
    if ambiguous:
        warnings.append("候选不唯一（%s 分数接近），请先与用户确认口径再取数" % second["name"])
    out["warnings"] = warnings

    # ⑤ 可选：过网关门禁（只放行，不执行）
    if args.gate:
        p = subprocess.run([sys.executable, GATEWAY, "exec", sql], capture_output=True, text=True, encoding="utf-8")
        out["gate"] = {"exit": p.returncode, "stdout": (p.stdout or "")[-600:].strip()}
        if p.returncode != 0:
            out["warnings"].append("网关未放行（exit=%d）：%s" % (p.returncode, (p.stdout or "").strip()[:200]))

    # ⑥ 可选：--live 直连 mcp-db2 真取（先探最新分区，今日空分区自动改取最新）
    if args.live:
        try:
            import mcp_db2  # noqa: E402
        except Exception as e:
            out["live"] = {"ok": False, "error": "mcp_db2.py 不可用：%s" % e}
        else:
            table = (meta.get("SOURCE_TABLES") or "").split(",")[0].strip()
            name = meta.get("ZB_NAME") or best["name"]
            probe = ("SELECT MAX(YMD) AS MAX_YMD FROM %s WHERE ZB_NAME='%s'" % (table, name))
            pr = mcp_db2.execute(probe, limit=10)
            live = {"probe": pr.get("ok"), "table": table, "name": name}
            if pr.get("ok") and pr.get("rows"):
                live["latest_ymd"] = pr["rows"][0][0]
                live["probe_rows"] = pr["rows"]
                if live["latest_ymd"] and live["latest_ymd"] != args.date:
                    sql = sql.replace("YMD='%s'" % args.date, "YMD='%s'" % live["latest_ymd"])
                    out["sql_executed"] = sql
                    live["date_adjusted"] = True
                    live["date_adjust_note"] = "用户取数日 %s 无分区，自动改取最新分区 %s" % (args.date, live["latest_ymd"])
                    out["warnings"].append(live["date_adjust_note"])
            else:
                live["probe_error"] = pr.get("error")
            if pr.get("ok"):
                fin = mcp_db2.execute(sql, limit=20)
                live["execute"] = {
                    "ok": fin.get("ok"), "row_count": fin.get("row_count"),
                    "columns": fin.get("columns"), "rows": fin.get("rows"),
                }
                if not fin.get("ok"):
                    live["execute"]["error"] = fin.get("error")
            out["live"] = live

    out["next_action"] = (
        "若需真实数字：在会话内调 mcp__db2__execute_sql 执行 sql_executed（只读单语句；"
        "SQL 里不要自己写 FETCH FIRST，服务端会自动拼，用 limit 参数）；"
        "本机已开 --live 时见 out.live 真数结果；无 MCP 时按 sg-db2-executor 的 REST 通道处理，禁止手改表达式"
    )

    if args.sql_only:
        print(sql)
        return 0
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
