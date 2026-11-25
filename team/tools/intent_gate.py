# -*- coding: utf-8 -*-
"""intent_gate.py —— IntentContract v2.0 意图门禁校验器（确定性 · 零模型调用）

来源：借鉴 dsh-superagent 原型「三事实 + 证据锚 + 规则全覆盖 + 决策枚举」机制。
职责：在任何取数/派发之前，校验意图契约是否**真的理解了用户**。
      不通过 → 禁止进入取数链路（exit 1）。

用法：
    python tools/intent_gate.py --contract observed/intents/<TR>.json
    python tools/intent_gate.py --contract <path> --json     # 机器可读
    python tools/intent_gate.py --rules <rules.yml> --contract <path>

退出码：
    0  通过（可派发）
    1  不通过（禁止派发）
    2  输入/环境错误

六道门禁（任一失败即拦）：
    G1 direction_settled=false  → decision 只能是 ignore / stop
    G2 intent_strength=not_admitted → 禁止取数
    G3 decision=accept 但无一条 matched=true 规则 → 驳回（无规则依据不得接单）
    G4 rule_assessments 未覆盖全部启用规则 / 含未知 id / 重复 id → 驳回
    G5 三条 evidence_quote 未能在 raw_query 原文命中 → 驳回（防编造证据）
    G6 conflicts 非空 → decision 只能是 ignore
"""
import argparse
import io
import json
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RULES = os.path.join(PKG, "knowledge", "design", "policy", "rules.yml")

DECISIONS = {"accept", "stop", "ignore", "unavailable"}
STRENGTHS = {"explicit", "inferred", "not_admitted"}
FACTS = ("targets_project", "implementation_requested", "direction_settled")


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_yaml(path):
    sys.path.insert(0, os.path.join(PKG, "tools", "_vendor"))
    try:
        import yaml  # noqa
    except Exception:
        try:
            import yaml  # noqa
        except Exception:
            raise SystemExit("FAIL: 缺少 pyyaml（tools/_vendor/pyyaml）")
    with io.open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def norm(s):
    """归一化：去空白与全半角标点差异，仅保留中日韩文字与字母数字。"""
    return re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", s or "")


def check(contract, rules_doc):
    errs, warns, oks = [], [], []

    enabled = [r for r in (rules_doc.get("rules") or []) if r.get("enabled", True)]
    enabled_ids = [r["id"] for r in enabled]
    global_mode = rules_doc.get("accept_mode", "observe")

    a = contract.get("assessment")
    if not isinstance(a, dict):
        return ["缺少 assessment 块（IntentContract v2.0 必填）"], warns, oks

    decision = a.get("decision")
    strength = a.get("intent_strength")
    mode = a.get("accept_mode", global_mode)
    facts = a.get("facts") or {}
    ra = a.get("rule_assessments")
    conflicts = a.get("conflicts") or []
    raw = contract.get("raw_query") or ""

    # --- 枚举合法性 ---
    if decision not in DECISIONS:
        errs.append("G0 decision=%r 非法，必须 ∈ %s" % (decision, sorted(DECISIONS)))
    if strength not in STRENGTHS:
        errs.append("G0 intent_strength=%r 非法，必须 ∈ %s" % (strength, sorted(STRENGTHS)))
    if mode not in ("off", "observe", "auto"):
        errs.append("G0 accept_mode=%r 非法，必须 ∈ off/observe/auto" % (mode,))

    # --- 三事实齐全 ---
    for f in FACTS:
        v = facts.get(f)
        if not isinstance(v, dict):
            errs.append("G0 facts.%s 缺失（必须为 {value, evidence_quote}）" % f)
            continue
        if not isinstance(v.get("value"), bool):
            errs.append("G0 facts.%s.value 必须为布尔" % f)
        if not (v.get("evidence_quote") or "").strip():
            errs.append("G0 facts.%s.evidence_quote 为空（禁止无证据判定）" % f)
    if errs:
        return errs, warns, oks

    # --- G1 方向未定 → 只能 ignore/stop ---
    if facts["direction_settled"]["value"] is False:
        if decision not in ("ignore", "stop"):
            errs.append("G1 方向未确定（direction_settled=false），decision 必须为 ignore/stop，实际=%r" % decision)
        else:
            oks.append("G1 方向未定 → 正确降为 %s（不派发）" % decision)
    else:
        oks.append("G1 方向已确定")

    # --- G2 不受理 → 禁止取数 ---
    if strength == "not_admitted":
        if decision == "accept":
            errs.append("G2 intent_strength=not_admitted 时禁止 decision=accept（三态授权铁律）")
        else:
            oks.append("G2 不受理 → 未接单（%s）" % decision)
    else:
        oks.append("G2 授权强度=%s" % strength)

    # --- G2b observe 模式：推断候选不得真接单 ---
    if mode == "observe" and strength == "inferred" and decision == "accept":
        errs.append("G2b accept_mode=observe 时推断候选只能记为 would-accept（decision 应为 ignore），实际 accept")
    elif mode == "off" and strength == "inferred":
        if decision == "accept":
            errs.append("G2b accept_mode=off 时推断候选一律不受理")
    else:
        oks.append("G2b 放权档位=%s 与强度=%s 相容" % (mode, strength))

    # --- G3 接单必须有规则依据 ---
    if not isinstance(ra, list) or not ra:
        errs.append("G3 rule_assessments 必须为非空数组（每条启用规则一条）")
        ra = []
    matched = [x for x in ra if isinstance(x, dict) and x.get("matched") is True]
    if decision == "accept" and not matched:
        errs.append("G3 decision=accept 但 matched=true 的规则数为 0（无规则依据不得接单）")
    if decision == "accept":
        oks.append("G3 依据规则：%s" % ", ".join(x.get("rule_id", "?") for x in matched))

    # --- G4 规则全覆盖 ---
    got, dup = [], []
    for x in ra:
        if not isinstance(x, dict):
            errs.append("G4 rule_assessments 含非对象元素")
            continue
        rid = x.get("rule_id")
        if rid in got:
            dup.append(rid)
        got.append(rid)
        if rid not in enabled_ids:
            errs.append("G4 未知/未启用的 rule_id=%r（禁止编造规则）" % (rid,))
        if not isinstance(x.get("matched"), bool):
            errs.append("G4 %r 的 matched 必须为布尔" % (rid,))
        if not (x.get("reason") or "").strip():
            errs.append("G4 %r 缺 reason（负判也必须写理由）" % (rid,))
    if dup:
        errs.append("G4 rule_id 重复：%s" % sorted(set(dup)))
    missing = [r for r in enabled_ids if r not in got]
    if missing:
        errs.append("G4 未覆盖启用规则 %d 条：%s" % (len(missing), ", ".join(missing)))
    else:
        oks.append("G4 规则全覆盖（%d/%d）" % (len(enabled_ids), len(enabled_ids)))

    # --- G5 证据锚必须原文命中 ---
    raw_n = norm(raw)
    for f in FACTS:
        q = facts[f]["evidence_quote"]
        if norm(q) and norm(q) in raw_n:
            continue
        errs.append("G5 facts.%s.evidence_quote 未在 raw_query 原文命中：%r" % (f, q[:40]))
    if not any(e.startswith("G5") for e in errs):
        oks.append("G5 三条证据锚全部原文命中")

    # --- G6 冲突 → 只能 ignore ---
    if conflicts:
        if decision != "ignore":
            errs.append("G6 存在规则冲突（%d 条），decision 必须为 ignore，实际=%r" % (len(conflicts), decision))
        else:
            oks.append("G6 规则冲突 → 安静忽略")
    else:
        oks.append("G6 无规则冲突")

    return errs, warns, oks


def render(contract, errs, warns, oks, as_json):
    a = contract.get("assessment") or {}
    if as_json:
        print(json.dumps({
            "ok": not errs,
            "trace_id": contract.get("trace_id"),
            "decision": a.get("decision"),
            "intent_strength": a.get("intent_strength"),
            "accept_mode": a.get("accept_mode"),
            "errors": errs,
            "warnings": warns,
            "checks": oks,
        }, ensure_ascii=False, indent=2))
        return 0 if not errs else 1

    print("=" * 66)
    print("意图门禁 · IntentContract v2.0 校验")
    print("=" * 66)
    print("  trace_id      : %s" % contract.get("trace_id", "<none>"))
    print("  decision      : %s" % a.get("decision", "<none>"))
    print("  intent_strength: %s" % a.get("intent_strength", "<none>"))
    print("  accept_mode   : %s" % a.get("accept_mode", "<none>"))
    print("-" * 66)
    for o in oks:
        print("  [PASS] %s" % o)
    for w in warns:
        print("  [WARN] %s" % w)
    for e in errs:
        print("  [FAIL] %s" % e)
    print("-" * 66)
    if errs:
        print("裁定: ❌ 不通过（%d 项）→ **禁止进入取数链路**，退回 sg-query-router 重出契约" % len(errs))
    else:
        print("裁定: ✅ 通过 → 可进入 GATE-Q 后续阶段")
    print("=" * 66)
    return 0 if not errs else 1


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="IntentContract v2.0 意图门禁校验")
    ap.add_argument("--contract", required=True, help="IntentContract JSON 路径")
    ap.add_argument("--rules", default=DEFAULT_RULES, help="规则清单 YAML（默认 knowledge/design/policy/rules.yml）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = ap.parse_args(argv)

    for p in (args.contract, args.rules):
        if not os.path.isfile(p):
            print("FAIL: 找不到 %s" % p)
            return 2
    with io.open(args.contract, encoding="utf-8") as f:
        contract = json.load(f)
    rules_doc = load_yaml(args.rules)
    errs, warns, oks = check(contract, rules_doc)
    return render(contract, errs, warns, oks, args.json)


if __name__ == "__main__":
    sys.exit(main())
