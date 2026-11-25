#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jev_router.py —— 判型融合器：规则闸（route_intent.py）+ 小模型闸（jev）
================================================================================

为什么要融合而不是二选一：

  · 规则闸（route_intent.py）：0.13 s、零网络、100% 可复现，但只能认「字面」——
    用户说「麻烦你帮我确认一下咱们厂圆棒线上个月实际产出到底多少」这种 30 字口语，
    规则判 full（保守），其实就是一个单指标裸查。
  · 小模型闸（jev / tev1:4b-32k）：0.7–1.0 s、带概率，能读语义，但会错、会幻觉。
  · 融合原则：**规则优先、jev 只做兜底和升级；jev 永远无权越过 HEAVY 词**。

判定矩阵（施加顺序即优先级）：

  | 规则闸结论 | 是否问 jev | jev 能做什么 |
  |---|---|---|
  | fast / trend | 不问（规则已确定，别再花 1 s） | — |
  | root_cause | 不问（归因已是慢车道，路由正确） | — |
  | full 且**含 HEAVY 词** | 不问（对标/各工序/报告类，jev 无权降级） | — |
  | full 且**无 HEAVY 词**（兜底态） | **问** | 命中「单指标取数」→ 降级 fast；「趋势查询」→ 降级 trend；「归因诊断」→ 升 root_cause；其余保持 full |

采纳阈值：`confidence >= --min-conf`（默认 0.85），否则**弃权**（保持规则结论）。

实测（2026-11-18）：
  · 「帮我查一下 1#高炉这个月的矿耗」→ 单指标取数 conf 0.9885
  · 「这个数不对，帮我看看为什么」   → 归因诊断   conf 0.9340
  · 8 候选择一（真实长指标名）      → 0.9975
  · 「帮我查一下高炉矿耗」（无编号） → conf 0.5871 → **本器会弃权**（正确行为）

用法：
  python tools/jev_router.py --text "<用户原话>" [--format text]
  python tools/jev_router.py --text "…" --no-jev          # 只跑规则
  python tools/jev_router.py --text "…" --force-jev       # 规则已定也问一次（诊断用）
  python tools/jev_router.py --text "…" --min-conf 0.9

退出码：0 正常；4 jev 不可达（已降级为纯规则结论，并在输出标注 jev_unreachable=true）。
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import jev_query  # noqa: E402
import route_intent  # noqa: E402

INTENT_LABELS = {
    "单指标取数": "要某一个具体指标的数值（一个数，不要一段）",
    "趋势查询": "要一段时间内的变化、走势、对比",
    "归因诊断": "要原因、为什么、异常排查",
    "综合报告": "要报告、看板、驾驶舱、汇报材料",
    "开发变更": "要建表、改表、存储过程、ETL、建模",
}

LABEL_TO_LANE = {
    "单指标取数": ("fast", "T1"),
    "趋势查询": ("trend", "T2a"),
    "归因诊断": ("root_cause", "T2b"),
    "综合报告": ("full", "T3"),
    "开发变更": ("full", "T5"),
}

HEAVY_NOTE = "含 HEAVY 词（对标/本周/各工序/各基地/报告/汇总/分析…）→ jev 无权降级，维持规则结论"


def build(text, use_jev=True, min_conf=0.85, force_jev=False,
          url=None, model=None, timeout=30.0):
    rule = route_intent.build(text)
    out = dict(rule)
    out["source"] = "rules"
    out["rule_lane"] = rule["lane"]
    out["rule_task_type"] = rule["task_type"]
    out["jev"] = None
    out["agreement"] = None
    out["jev_unreachable"] = False

    if not use_jev:
        out["next"] = _next_for(out["lane"])
        return out

    heavy = bool((rule.get("signals") or {}).get("heavy"))
    askable = force_jev or (rule["lane"] == "full" and not heavy)
    if not askable:
        if rule["lane"] == "full" and heavy:
            out["reasons"] = list(rule["reasons"]) + [HEAVY_NOTE]
        out["next"] = _next_for(out["lane"])
        return out

    try:
        label, conf, probs, raw = jev_query.classify(
            text, INTENT_LABELS, question="意图",
            instructions="用户这句话想做什么？只选最贴近的一个。",
            url=url, model=model, timeout=timeout)
    except jev_query.JevError as e:
        out["jev_unreachable"] = True
        out["jev"] = {"error": str(e), "code": e.code}
        out["reasons"] = list(rule["reasons"]) + [
            "jev 不可达（%s）→ 直接退回规则结论，禁止凭印象判型" % getattr(e, "code", "?")]
        out["next"] = _next_for(out["lane"])
        return out

    out["jev"] = {
        "choice": label,
        "confidence": round(conf, 4),
        "probabilities": {k: round(float(v), 4) for k, v in (probs or {}).items()},
        "latency_ms": raw.get("_latency_ms") if isinstance(raw, dict) else None,
        "model": (raw or {}).get("model") if isinstance(raw, dict) else None,
        "dry_run": bool((raw or {}).get("_dry_run")),
    }

    if conf < min_conf:
        out["reasons"] = list(rule["reasons"]) + [
            "jev 判定 %s 但 confidence=%.3f < %.2f → 弃权，维持规则结论（%s）"
            % (label, conf, min_conf, rule["lane"])]
        out["agreement"] = "abstain"
        out["next"] = _next_for(out["lane"])
        return out

    lane, task = LABEL_TO_LANE.get(label, (rule["lane"], rule["task_type"]))
    if heavy and lane != rule["lane"]:
        out["reasons"] = list(rule["reasons"]) + [HEAVY_NOTE]
        out["agreement"] = "jev_vetoed"
        out["next"] = _next_for(out["lane"])
        return out

    out["lane"] = lane
    out["task_type"] = task
    out["fast_lane"] = lane == "fast"
    out["bypass_gate_q"] = lane == "fast"
    out["timeout_minutes"] = route_intent.TIMEOUT_BY_TASK.get(task, 60)
    out["sla_target_seconds"] = route_intent.SLA_TARGET_BY_LANE[lane]
    out["source"] = "jev"
    out["agreement"] = "agree" if lane == rule["lane"] else ("downgrade" if lane in ("fast", "trend") else "route_change")

    if lane == rule["lane"]:
        note = "jev 与规则一致（%s，conf %.3f）→ 结论不变" % (lane, conf)
    elif out["agreement"] == "downgrade":
        note = "jev 判 %s（conf %.3f）且无 HEAVY 词 → **降级到 %s 快车道**（规则原判 %s）" % (
            label, conf, lane, rule["lane"])
    else:
        note = "jev 判 %s（conf %.3f）→ 改路由到 %s（规则原判 %s）" % (label, conf, lane, rule["lane"])
    out["reasons"] = list(rule["reasons"]) + [note]
    out["next"] = _next_for(lane)
    return out


def _next_for(lane):
    if lane == "fast":
        return "快车道：python tools/fast_ask.py --text \"<原问题>\" --date <YYYYMMDD>"
    if lane == "trend":
        return "T2a 趋势快线：sg-trend-quick（1 条区间 SQL，≤3 min）"
    if lane == "root_cause":
        return "T2b 根因：sg-root-cause-fullchain（五维取证，≤60 min 硬超时）"
    return "按 SOP 派发：辨枢出 IntentContract → 淬锋编译 SQL → 砺真核验"


def main():
    ap = argparse.ArgumentParser(description="判型融合器：规则 + jev 小模型闸")
    ap.add_argument("--text", required=True)
    ap.add_argument("--format", choices=["json", "text"], default="json")
    ap.add_argument("--no-jev", action="store_true", help="只跑规则，不问 jev")
    ap.add_argument("--force-jev", action="store_true", help="规则已定也问 jev（诊断用，不会改结论以外的行为）")
    ap.add_argument("--min-conf", type=float, default=0.85)
    ap.add_argument("--url", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()
    if not args.text.strip():
        print("--text 不能为空", file=sys.stderr)
        return 2

    r = build(args.text, use_jev=not args.no_jev, min_conf=args.min_conf,
              force_jev=args.force_jev, url=args.url or None, model=args.model or None,
              timeout=args.timeout)

    if args.format == "text":
        print("问题       : %s" % r["text"])
        print("最终车道   : %s（task_type=%s，source=%s）" % (r["lane"], r["task_type"], r["source"]))
        print("规则闸原判 : %s / %s" % (r["rule_lane"], r["rule_task_type"]))
        j = r.get("jev")
        if j and j.get("choice"):
            print("jev 判定   : %s（conf %.4f，%s ms）" % (
                j["choice"], j.get("confidence", 0), j.get("latency_ms") or 0))
        elif j:
            print("jev        : 未采纳（%s）" % (j.get("error") or "弃权/无需"))
        else:
            print("jev        : 未调用（规则已确定或含 HEAVY）")
        print("一致性     : %s" % (r.get("agreement") or "—"))
        print("SLA        : ≤%d s ｜ 硬超时 %d min" % (r["sla_target_seconds"], r["timeout_minutes"]))
        for x in r["reasons"]:
            print("  - %s" % x)
        print("下一步     : %s" % r["next"])
    else:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
