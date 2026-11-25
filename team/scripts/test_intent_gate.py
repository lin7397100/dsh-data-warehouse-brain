# -*- coding: utf-8 -*-
"""意图门禁回归测试：1 正例 + 6 反例。任一用例判定不符 → exit 1。"""
import copy
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(HERE, "tools", "intent_gate.py")
BASE = os.path.join(HERE, "observed", "intents", "TR-20261120-1046-9C1F.intent.json")
TMP = os.path.join(HERE, "observed", "intents", "_selftest")

with io.open(BASE, encoding="utf-8") as f:
    base = json.load(f)

cases = []


def add(name, mutate, expect_exit, expect_kw):
    c = copy.deepcopy(base)
    mutate(c)
    cases.append((name, c, expect_exit, expect_kw))


def drop_rule(c):
    c["assessment"]["rule_assessments"] = [
        x for x in c["assessment"]["rule_assessments"] if x["rule_id"] != "R-CROSS-FACTORY"
    ]


def fake_evidence(c):
    c["assessment"]["facts"]["targets_project"]["evidence_quote"] = "用户说要建采购管控领域模型"


def unsettled_accept(c):
    c["assessment"]["facts"]["direction_settled"]["value"] = False


def not_admitted_accept(c):
    c["assessment"]["intent_strength"] = "not_admitted"


def no_match_accept(c):
    for x in c["assessment"]["rule_assessments"]:
        x["matched"] = False


def unknown_rule(c):
    c["assessment"]["rule_assessments"].append(
        {"rule_id": "R-MADE-UP", "matched": True, "reason": "编造规则"}
    )


def observe_inferred_accept(c):
    c["assessment"]["intent_strength"] = "inferred"
    c["assessment"]["accept_mode"] = "observe"


add("正例 · 真实契约", lambda c: None, 0, '"ok": true')
add("反例1 · 漏一条规则未判", drop_rule, 1, "未覆盖启用规则")
add("反例2 · 编造证据（原文不含）", fake_evidence, 1, "未在 raw_query 原文命中")
add("反例3 · 方向未定却接单", unsettled_accept, 1, "direction_settled=false")
add("反例4 · 不受理却接单", not_admitted_accept, 1, "禁止 decision=accept")
add("反例5 · 无规则依据接单", no_match_accept, 1, "matched=true 的规则数为 0")
add("反例6 · 编造规则ID", unknown_rule, 1, "未知/未启用的 rule_id")
add("反例7 · observe模式推断项直接", observe_inferred_accept, 1, "observe 时推断候选")

os.makedirs(TMP, exist_ok=True)
fails = []
for i, (name, c, expect, kw) in enumerate(cases):
    p = os.path.join(TMP, "case%02d.json" % i)
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    r = subprocess.run([sys.executable, GATE, "--contract", p, "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    ok = (r.returncode == expect) and (kw in (r.stdout or ""))
    print(("  [OK  ] " if ok else "  [FAIL] ") + "%-30s exit=%d(期望%d) 关键词=「%s」"
          % (name, r.returncode, expect, kw))
    if not ok:
        fails.append((name, r.returncode, expect, (r.stdout or "")[:400], (r.stderr or "")[:200]))

print()
if fails:
    print("❌ %d/%d 用例失败" % (len(fails), len(cases)))
    for f in fails:
        print("   %s | exit=%s 期望=%s\n     out=%s\n     err=%s" % f)
    sys.exit(1)
print("✅ 全部 %d 个用例通过（1 正例 + %d 反例）" % (len(cases), len(cases) - 1))
sys.exit(0)
