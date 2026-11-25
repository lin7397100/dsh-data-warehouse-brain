# -*- coding: utf-8 -*-
"""policy_check.py —— 策略版本化与在跑工单通知（借鉴 dsh-superagent 的 Policy version）

存在理由（证据）：
  superagent 的每条 Mandate 都记 `policy_version`；规则一变，**在跑工单会收到
  policy-changed 输入**，而不是被无声按新规则验收。本团此前改了 `rules.yml` /
  `iron_rules.md` / 专家 prompt，在跑工单完全不知道。

用法：
    python tools/policy_check.py show
    python tools/policy_check.py check                 # 在跑工单是否落后于当前策略
    python tools/policy_check.py bump --version 2026.11.21-1 \\
        --rule R-ROOT-CAUSE --from "jev 跳过" --to "指标候选强制消歧"
    python tools/policy_check.py notify               # 向落后工单写 policy-changed

退出码：0 一致 ｜ 4 存在落后工单（需 notify） ｜ 2 输入错误
"""
import argparse
import datetime as _dt
import io
import json
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join(PKG, "knowledge", "design", "policy", "policy_version.json")
TICKET_DIR = os.path.join(PKG, "observed", "tickets")


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def load_policy():
    if not os.path.isfile(POLICY):
        return {"version": "0.0.0", "history": []}
    with io.open(POLICY, encoding="utf-8-sig") as f:
        return json.load(f)


def save_policy(p):
    os.makedirs(os.path.dirname(POLICY), exist_ok=True)
    with io.open(POLICY, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def open_tickets():
    out = []
    if not os.path.isdir(TICKET_DIR):
        return out
    for fn in sorted(os.listdir(TICKET_DIR)):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        try:
            with io.open(os.path.join(TICKET_DIR, fn), encoding="utf-8-sig") as f:
                tk = json.load(f)
        except Exception:
            continue
        steps = tk.get("steps") or []
        if not steps or all(s.get("status") in ("ready", "skipped") for s in steps):
            continue
        out.append(tk)
    return out


def cmd_show(a):
    p = load_policy()
    print("=" * 78)
    print("当前策略版本 · %s" % p.get("version", "<none>"))
    print("=" * 78)
    print("  生效时间 : %s" % p.get("effective_at", "—"))
    print("  变更人   : %s" % p.get("changed_by", "—"))
    print("  变更条数 : %d" % len(p.get("diff") or []))
    for d in (p.get("diff") or []):
        print("    · %-16s %s → %s" % (d.get("rule", "?"), d.get("from", ""), d.get("to", "")))
    print("  历史版本 : %s" % (", ".join(h.get("version", "?") for h in (p.get("history") or [])) or "—"))
    print("=" * 78)
    return 0


def cmd_check(a):
    p = load_policy()
    cur = p.get("version", "0.0.0")
    tks = open_tickets()
    stale = [t for t in tks if (t.get("mandate") or {}).get("policy_version") != cur]
    print("=" * 78)
    print("策略一致性检查 · 当前 %s" % cur)
    print("=" * 78)
    print("  在跑工单 %d 个，落后 %d 个" % (len(tks), len(stale)))
    for t in stale:
        m = t.get("mandate") or {}
        print("    ⚠️ %s（%s）｜工单策略 %s ≠ 当前 %s"
              % (t["ticket_id"], (t.get("title") or "")[:24],
                 m.get("policy_version"), cur))
    print("=" * 78)
    if stale:
        print("裁定：⚠️ 存在落后工单 → 跑 `policy_check.py notify` 投递 policy-changed")
        return 4
    print("裁定：✅ 全部一致")
    return 0


def cmd_bump(a):
    p = load_policy()
    old = p.get("version", "0.0.0")
    if a.version == old:
        print("FAIL: 新版本号与当前相同 %s" % old)
        return 2
    p.setdefault("history", []).append({
        "version": old,
        "superseded_at": _now(),
        "diff": p.get("diff") or [],
    })
    p["version"] = a.version
    p["effective_at"] = _now()
    p["changed_by"] = a.by
    p["diff"] = [{"rule": a.rule, "from": a.old, "to": a.new, "at": _now()}]
    save_policy(p)
    tks = open_tickets()
    print("✅ 策略版本 %s → %s" % (old, a.version))
    print("   受影响在跑工单 %d 个：%s" % (len(tks), ", ".join(t["ticket_id"] for t in tks) or "—"))
    print("   下一步：python tools/policy_check.py notify")
    return 0


def cmd_notify(a):
    p = load_policy()
    cur = p.get("version", "0.0.0")
    tks = open_tickets()
    n = 0
    for t in tks:
        m = t.get("mandate") or {}
        if m.get("policy_version") == cur:
            continue
        t.setdefault("inputs", []).append({
            "kind": "policy-changed",
            "at": _now(),
            "from_version": m.get("policy_version"),
            "to_version": cur,
            "diff": p.get("diff") or [],
            "note": "规则已变更，请复核本工单的 matched_rules 与 scope 是否仍成立",
        })
        t.setdefault("history", []).append({"at": _now(), "event": "policy-changed"})
        old_ver = m.get("policy_version")
        m["policy_version"] = cur
        t["updated_at"] = _now()
        with io.open(os.path.join(TICKET_DIR, "%s.json" % t["ticket_id"]), "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=2)
        n += 1
        print("  📨 %s 已投递 policy-changed（%s → %s）" % (t["ticket_id"], old_ver, cur))
    print("✅ 已通知 %d 个工单" % n)
    return 0


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="策略版本化与在跑工单通知")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show").set_defaults(fn=cmd_show)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("notify").set_defaults(fn=cmd_notify)
    p = sub.add_parser("bump")
    p.add_argument("--version", required=True)
    p.add_argument("--rule", required=True)
    p.add_argument("--from", dest="old", default="")
    p.add_argument("--to", dest="new", default="")
    p.add_argument("--by", default="lead")
    p.set_defaults(fn=cmd_bump)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
