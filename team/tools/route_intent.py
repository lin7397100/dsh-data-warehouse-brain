#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
route_intent.py —— 车道路由判定器（确定性 · 零 LLM 调用）
=========================================================

存在理由（证据）：
  源包主理人 SOP 明确规定「快车道不豁免 GATE-Q」（`agents/data-warehouse-brain-team-lead.md` L55），
  导致单指标裸查也要先派 sg-query-router 编译 IntentContract —— 这是 L0 裸查「基线 ≈82 min、
  目标 ≤30 s」（同文件 L629-631）的结构性成因。
  判定本该是确定性的（正则 + 词典），不需要一次 LLM 子会话。本脚本把判定搬出 LLM。

判定依据（逐条对齐源包）：
  ① 快车道正则 —— 逐字取自 `skills/sg-orchestrator/assets/fast_lane.js`（SINGLE / LIGHT_LOOKUP / HEAVY）
  ② T2a 准入四条件 —— `agents/data-warehouse-brain-team-lead.md` L666-667
  ③ T2b/根因信号 —— 同上 L664 判型映射、L677 专家配置
  ④ 硬超时档位 —— 同上 L643-649（T1 5min / T2a 10min / T2b·T3 60min / T4 90min / T5 120min）
  ⑤ 重任务词 —— fast_lane.js 的 HEAVY，另补 报告/驾驶舱/看板/全链路 等 L671 明令禁止项

输出：单个 JSON（默认）或人读文本（--format text）。不读取任何 DB，不访问网络。

用法：
  python tools/route_intent.py --text "圆棒产量是多少"
  python tools/route_intent.py --text "近7日三基地钢铁料耗趋势" --format text
  python tools/route_intent.py --text "为什么这个月成本涨了" --format json

退出码：0 正常；2 参数错误。
"""

import argparse
import json
import re
import sys

# ---------------------------------------------------------------- 词表（对齐源包）
# ① fast_lane.js 三段正则，逐字复制，不增不改
RE_SINGLE = re.compile(r"(单指标|单个指标|单一指标|某指标|某科目|一个指标|一个科目)")
RE_LIGHT_LOOKUP = re.compile(r"(是多少|定义|口径|怎么算|如何计算|来源表|取数SQL|sql|来源|说明|什么意思)")
RE_HEAVY = re.compile(r"(对标|本周|上周|各工序|各基地|报告|降本建议|降本|全链路|分析|全部|汇总|三公司|三钢)")

# ② 根因/归因（T2a 的排除项，L667 条件②）
RE_ROOT_CAUSE = re.compile(
    r"(为什么|为啥|原因|异常|归因|波动分析|波动|排查|诊断|根因|溯源|下钻|偏差|不对|对不上|飙|暴跌|暴增)"
)
# ③ 趋势（T2a 的必备项，L667 条件①）
RE_TREND = re.compile(r"(趋势|走势|近\s*\d+\s*[日天]|连日|曲线|同比|环比|逐日|变化情况)")
# ④ 报告/大盘类（重任务，禁走快车道，L671）
RE_REPORT = re.compile(r"(驾驶舱|看板|仪表盘|大盘|dashboard|cockpit|日报|周报|月报|综合报告|报告)")
# ⑤ 多基地/多工序（L667 条件③ 指标≤5 且基地≤4）
RE_MULTI_FACTORY = re.compile(r"(三基地|各基地|各厂|三公司|三钢闽光|泉州闽光|罗源闽光|多基地|各工序|各产线)")
# ⑥ 开发类（T5）
RE_DEV = re.compile(r"(建表|存储过程|ETL|Kettle|DolphinScheduler|建模|改表|新增字段|上线)")

# 硬超时档位 —— L643-649 原值
TIMEOUT_BY_TASK = {
    "T1": 5,      # 单指标查数 / 快车道
    "T2a": 10,    # 趋势速览
    "T2b": 60,    # 根因分析
    "T3": 60,
    "T4": 90,     # 双轮管控
    "T5": 120,    # 开发任务
}
# SLA 目标 —— L629-635 原值（秒）
SLA_TARGET_BY_LANE = {
    "fast": 30,       # L0 单指标裸查 ≤30 s
    "trend": 180,     # L1 T2a ≤3 min
    "full": 720,      # L2 ≤12 min（20→12 收敛后）
    "root_cause": 2100,  # L3 ≤35 min
}

LANE_TO_TASK = {"fast": "T1", "trend": "T2a", "full": "T2b", "root_cause": "T2b"}


def signals(text):
    t = text or ""
    return {
        "single": bool(RE_SINGLE.search(t)),
        "light_lookup": bool(RE_LIGHT_LOOKUP.search(t)),
        "heavy": bool(RE_HEAVY.search(t)),
        "root_cause": bool(RE_ROOT_CAUSE.search(t)),
        "trend": bool(RE_TREND.search(t)),
        "report": bool(RE_REPORT.search(t)),
        "multi_factory": bool(RE_MULTI_FACTORY.search(t)),
        "dev": bool(RE_DEV.search(t)),
        "has_sql_word": bool(re.search(r"sql", t, re.I)),
        "length": len(t.strip()),
    }


def decide(text):
    """返回 (lane, reasons)。判定顺序即优先级，与源包的分层一致。"""
    s = signals(text)
    reasons = []

    # T5 开发任务：最高优先，绝不进快车道
    if s["dev"]:
        reasons.append("命中开发类词（建表/存储过程/ETL/建模…）→ T5 开发任务")
        return "full", "T5", reasons

    # 根因/归因：T2a 条件② 明确排除，必须升 T2b
    if s["root_cause"]:
        reasons.append("命中根因/归因词（为什么/原因/异常/归因/波动/排查/诊断/下钻）→ 违反 T2a 准入②，升 T2b")
        return "root_cause", "T2b", reasons

    # 报告/大盘：全链路重任务，禁快车道（L671 明令禁止项）
    if s["report"]:
        reasons.append("命中报告/驾驶舱/看板词 → 走完整链路，不进快车道")
        return "full", "T3", reasons

    # T2a 趋势速览：条件①通过 + 非根因 + 非报告
    if s["trend"]:
        reasons.append("命中趋势词（趋势/走势/近N日/同比/环比）且无归因词 → T2a 趋势速览（1 条区间 SQL）")
        if s["multi_factory"]:
            reasons.append("含多基地词：T2a 仍需满足基地≤4 —— 超过则升 T2b")
        return "trend", "T2a", reasons

    # 快车道：逐条抄 fast_lane.js 的短路顺序
    if s["single"]:
        reasons.append("命中 SINGLE（单指标/某指标/一个指标）→ fast_lane.js 首条短路成立")
        return "fast", "T1", reasons
    if s["light_lookup"] and not s["heavy"]:
        reasons.append("命中 LIGHT_LOOKUP 且不含 HEAVY → fast_lane.js 第二条短路成立")
        return "fast", "T1", reasons
    # fast_lane.js 第三条 `intent.metric && !HEAVY` 的确定性近似：短查询 + 无重任务词 = 裸指标名
    if (not s["heavy"]) and 0 < s["length"] <= 16 and re.search(r"[\u4e00-\u9fff0-9#]", text or ""):
        reasons.append("短查询（≤16 字）且无重任务词 → 按裸指标名处理（等价 fast_lane.js 第三条 intent.metric && !HEAVY）")
        return "fast", "T1", reasons
    if s["heavy"]:
        reasons.append("命中 HEAVY（对标/各基地/报告/汇总/分析…）→ 快车道被否决")
    else:
        reasons.append("未命中任何快车道短路条件 → 保守走完整链路")
    return "full", "T3", reasons


def build(text):
    lane, task, reasons = decide(text)
    s = signals(text)
    byp = lane == "fast"
    return {
        "text": (text or "").strip(),
        "lane": lane,
        "task_type": task,
        "fast_lane": byp,
        "bypass_gate_q": byp,
        "timeout_minutes": TIMEOUT_BY_TASK.get(task, 60),
        "sla_target_seconds": SLA_TARGET_BY_LANE[lane],
        "signals": s,
        "reasons": reasons,
        "next": (
            "物化直查：python tools/fast_ask.py --text \"<原问题>\" --date <YYYYMMDD>"
            if byp
            else "按 SOP 派发：辨枢出 IntentContract → 淬锋编译 SQL → 砺真核验"
        ),
    }


def main():
    ap = argparse.ArgumentParser(description="车道路由判定器（确定性，零 LLM 调用）")
    ap.add_argument("--text", required=True, help="用户原始问题")
    ap.add_argument("--format", choices=["json", "text"], default="json")
    args = ap.parse_args()
    if not args.text.strip():
        print("--text 不能为空", file=sys.stderr)
        return 2
    r = build(args.text)
    if args.format == "json":
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("问题    : %s" % r["text"])
        print("车道    : %s（task_type=%s）" % (r["lane"], r["task_type"]))
        print("绕 GATE-Q: %s" % ("是（快车道）" if r["bypass_gate_q"] else "否"))
        print("SLA     : ≤%d s ｜ 硬超时 %d min" % (r["sla_target_seconds"], r["timeout_minutes"]))
        print("依据    :")
        for x in r["reasons"]:
            print("  - %s" % x)
        print("下一步  : %s" % r["next"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
