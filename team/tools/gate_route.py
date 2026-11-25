#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_route.py —— GATE-0 确定性预检闸（规则闸 + jev 小模型融合 · 落盘路由 JSON）
=================================================================================

存在理由（证据）：
  2026-11-18 慢任务复盘：jev 脚本一次都没被调用，主理人靠自己反复 grep 判型，
  GATE-Q 又强制先派辨枢子会话，意图解析烧了近 9 分钟。jev_router.py 本已实现
  规则+小模型融合，但只写在 persona「建议位」里，LLM 临场想不起来跑。
  本脚本把它变成 GATE-0 的**必跑副作用**：一条命令出车道 + 置信度 + 下一步，
  结果落盘 observed/routes/，供主理人、监衡与专家团面板留痕。

判定链路（与 jev_router.py 一致，不另立体系）：
  ① route_intent 规则闸（0.13s、零网络、可复现）
  ② 仅当规则判 full 且无 HEAVY 词时，才问 jev（conf≥0.85 采纳，否则弃权）
  ③ HEAVY 词 / root_cause / fast / trend 不问 jev

输出：单个 JSON（默认）或人读文本（--format text）。

用法：
  python tools/gate_route.py --text "圆棒产量是多少"
  python tools/gate_route.py --text "近7日三基地钢铁料耗趋势" --date 20261117 --trace-id TR-...
  python tools/gate_route.py --text "为什么这个月成本涨了" --no-jev

退出码：0 正常（含 jev 不可达降级为规则结论）；2 参数错误。
"""

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROUTE_DIR = os.path.join(ROOT, "observed", "routes")
TRACE_LOG = os.path.join(ROOT, "scripts", "trace_log.py")

# 慢车道预期派发步骤（与 subagent_dispatch.md 执行者映射表一致）
FULL_EXPECTED = "0.5a,0.5b,2,3,4,5,6,7,8"

# T2a 趋势快线精简集：口径核查（Step2 口径卡）与 DSL（Step3）合并进 0.5b 语义探针，
# 不单独落口径卡 / DSL JSON（analysis_model_driven.md §六：1 条区间 SQL + 7 条断言，
# 不强制统计模型；caliber_freeze.md §五：T2a 只跑 A1–A4 + C1–C3）。
TREND_EXPECTED = "0.5a,0.5b,4,5,6,7,8"

# 按车道裁剪预期步骤：fast 无派发（豁免考核）；trend/T2a 用精简集；其余（full/root_cause…）全量
EXPECTED_BY_LANE = {
    "fast": "",
    "trend": TREND_EXPECTED,
    "T2a": TREND_EXPECTED,
}

if HERE not in sys.path:
    sys.path.insert(0, HERE)

import jev_router  # noqa: E402


def _gen_trace_id():
    return "TR-" + _dt.datetime.now().strftime("%Y%m%d-%H%M") + "-" + os.urandom(2).hex().upper()


def next_action(lane):
    if lane == "fast":
        return "快车道：python tools/fast_ask.py --text \"<原话>\" --date <YYYYMMDD>（命中物化 SQL 且 ambiguous=false 才出数）"
    if lane == "trend":
        return "T2a 趋势快线：sg-trend-quick（1 条区间 SQL，≤3 min；下钻另走完整血缘）"
    if lane == "root_cause":
        return "T2b 根因：Workflow B 五维并行取证（砺真+舆图+矩衡+鼎元+铨度+域专家+监衡）"
    return "完整链路：GATE-Q 派辨枢出 IntentContract → 淬锋编译 SQL → 守钧审查 → 砺真核验"


def build(text, date=None, trace_id=None, use_jev=True, min_conf=0.85,
          url=None, model=None, timeout=30.0):
    route = jev_router.build(
        text, use_jev=use_jev, min_conf=min_conf,
        url=url, model=model, timeout=timeout,
    )
    route["date"] = date or _dt.date.today().strftime("%Y%m%d")
    route["trace_id"] = trace_id or _gen_trace_id()
    route["at"] = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    route["next"] = next_action(route["lane"])
    return route


def persist(route):
    os.makedirs(ROUTE_DIR, exist_ok=True)
    path = os.path.join(ROUTE_DIR, "%s.json" % route["trace_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(route, f, ensure_ascii=False, indent=2)
    # 混合落库：路由判定同时写入 SQLite（权威），JSON 为快照兜底
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import trace_db
        conn = trace_db.connect()
        trace_db.upsert_route(conn, route, now_ts=route.get("at"))
        conn.commit()
        conn.close()
    except Exception as e:  # noqa: BLE001
        route["route_db_error"] = str(e)[:200]
    return path


def init_trace(route):
    """GATE-0 联动：用同一 trace_id 初始化派发台账 observed/traces/<tid>.json。

    快车道无专家派发，expected 留空（trace_log report 对 fast_lane 豁免覆盖率考核）；
    trend/T2a 走精简步骤集；其余慢车道按六阶段 SOP 登记全量预期步骤。
    台账初始化失败不阻断路由，仅在 route 标注。
    """
    if not os.path.exists(TRACE_LOG):
        route["trace_init"] = "skipped: trace_log.py 不存在"
        return
    ttype = route["task_type"]
    expected = EXPECTED_BY_LANE.get(route["lane"], FULL_EXPECTED)
    cmd = [
        sys.executable, TRACE_LOG, "init",
        "--task-type", ttype,
        "--lane", route["lane"],
        "--expected", expected,
        "--trace-id", route["trace_id"],
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            route["trace_init"] = "ok"
        else:
            route["trace_init"] = "failed"
            route["trace_init_error"] = (proc.stderr or proc.stdout or "").strip()[:300]
    except Exception as e:  # noqa: BLE001
        route["trace_init"] = "error"
        route["trace_init_error"] = str(e)[:300]


def main():
    ap = argparse.ArgumentParser(description="GATE-0 确定性预检闸（规则 + jev 融合，落盘路由 JSON）")
    ap.add_argument("--text", required=True, help="用户原始问题")
    ap.add_argument("--date", default="", help="取数日 YYYYMMDD，默认今天")
    ap.add_argument("--trace-id", default="", help="trace_id，缺省自动生成")
    ap.add_argument("--no-jev", action="store_true", help="只跑规则，不问 jev")
    ap.add_argument("--min-conf", type=float, default=0.85)
    ap.add_argument("--url", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--format", choices=["json", "text"], default="json")
    ap.add_argument("--no-trace-init", action="store_true", help="只落路由 JSON，不初始化 traces 台账")
    args = ap.parse_args()

    if not args.text.strip():
        print("--text 不能为空", file=sys.stderr)
        return 2

    route = build(
        args.text,
        date=args.date or None,
        trace_id=args.trace_id or None,
        use_jev=not args.no_jev,
        min_conf=args.min_conf,
        url=args.url or None,
        model=args.model or None,
        timeout=args.timeout,
    )
    path = persist(route)
    route["route_file"] = path

    if not args.no_trace_init:
        init_trace(route)

    if args.format == "text":
        print("问题       : %s" % route["text"])
        print("最终车道   : %s（task_type=%s，source=%s）" % (route["lane"], route["task_type"], route["source"]))
        j = route.get("jev")
        if j and j.get("choice"):
            print("jev 判定   : %s（conf %.4f，%s ms）" % (j["choice"], j.get("confidence", 0), j.get("latency_ms") or 0))
        elif j and j.get("error"):
            print("jev        : 不可达/未采纳（%s）" % j.get("error"))
        else:
            print("jev        : 未调用（规则已确定或含 HEAVY）")
        print("一致性     : %s" % (route.get("agreement") or "—"))
        print("SLA        : ≤%d s ｜ 硬超时 %d min" % (route["sla_target_seconds"], route["timeout_minutes"]))
        for x in route["reasons"]:
            print("  - %s" % x)
        print("路由落盘   : %s" % path)
        print("下一步     : %s" % route["next"])
    else:
        print(json.dumps(route, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
