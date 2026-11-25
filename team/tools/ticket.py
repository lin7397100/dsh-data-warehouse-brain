# -*- coding: utf-8 -*-
"""ticket.py —— 工单状态机（借鉴 dsh-superagent 的 Ticket / Mandate / Assignment / Subscription）

存在理由（证据）：
  `trace` 是**任务级**（一次问答一个 trace），而 5S 维度建模要跨天做 11 步
  （M1 业务指标 → M2 维度模型 → M3 事实明细 → M4 原子 → M5 派生 → M6 生成
   → M7 汇总 → ME 物化 → MU 上线 → MM 编排 → MI 血缘）。
  第 2 天用户说「继续第 3 步」，专家团认不出来——因为没有工单级持久化状态。

  本模块提供工单级状态机，三条硬规则照搬 superagent：
    ① Ticket 定义自己的状态，不跟 Executor 走（换专家/重启都不影响）
    ② 只有最终报告（ready）能结束工单，中间 progress 不算完
    ③ Subscription 续接：同一线程的后续消息自动路由回同一工单

用法：
    python tools/ticket.py init --kind 5s-modeling --title "钢铁料耗指标建模" \\
        --scope "三明闽光·炼钢·钢铁料耗" --intent-strength explicit --rules R-5S-MODELING
    python tools/ticket.py step --ticket MT-20261120-001 --id M3 --status running
    python tools/ticket.py step --ticket MT-20261120-001 --id M3 --status ready --artifact "BEDF52 截图"
    python tools/ticket.py show --ticket MT-20261120-001
    python tools/ticket.py open                      # 列出所有未结束工单
    python tools/ticket.py resume --thread thread-x   # 按订阅续接

退出码：0 成功 ｜ 1 门禁拒绝（跳步/非法状态） ｜ 2 输入错误
"""
import argparse
import datetime as _dt
import io
import json
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKET_DIR = os.path.join(PKG, "observed", "tickets")

# 5S 维度建模十一模型（顺序即门禁顺序，不可跳步）
FLOWS = {
    "5s-modeling": [
        ("M1", "业务指标", True),
        ("M2", "维度模型（物化）", True),
        ("M3", "事实明细模型（关联维度+物化）", True),
        ("M4", "原子指标（事实明细+数据域+SUM(重量)）", True),
        ("M5", "派生指标（原子+业务指标+统计维度+通用限定）", True),
        ("M6", "派生指标生成（BEDK02）", True),
        ("M7", "自动汇总指标（BEDK03 生成 DWS 并物化）", True),
        ("ME", "生成步骤（ODS→DWD/DWS 加工）", True),
        ("MU", "任务编排（BEDD00）", True),
        ("MM", "上线", True),
        ("MI", "指标血缘（ODS→DWD→DWS→ADS→IND）", True),
    ],
    "indicator-system": [
        ("L1", "业务指标", True),
        ("L2", "原子指标", True),
        ("L3", "派生指标", True),
        ("L4", "复合指标", True),
        ("LX", "血缘定义（四级穿透）", True),
    ],
}

STEP_STATUS = {"pending", "running", "ready", "blocked", "failed", "skipped"}
REPORT_STATUS = {"progress", "waiting", "ready", "blocked", "failed", "dropped"}


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _path(tid):
    return os.path.join(TICKET_DIR, "%s.json" % tid)


def _load(tid):
    p = _path(tid)
    if not os.path.isfile(p):
        raise SystemExit("FAIL: 工单不存在 %s" % tid)
    with io.open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def _save(tk):
    os.makedirs(TICKET_DIR, exist_ok=True)
    tk["updated_at"] = _now()
    with io.open(_path(tk["ticket_id"]), "w", encoding="utf-8") as f:
        json.dump(tk, f, ensure_ascii=False, indent=2)


def _next_id():
    day = _dt.date.today().strftime("%Y%m%d")
    os.makedirs(TICKET_DIR, exist_ok=True)
    n = 0
    for fn in os.listdir(TICKET_DIR):
        if fn.startswith("MT-%s-" % day) and fn.endswith(".json"):
            try:
                n = max(n, int(fn.split("-")[2].split(".")[0]))
            except Exception:
                pass
    return "MT-%s-%03d" % (day, n + 1)


def stage_of(tk):
    """七阶段判定（从上往下第一个匹配生效，照搬 superagent）。"""
    steps = tk["steps"]
    if tk.get("attention"):
        return "person/answer"
    latest = tk.get("report")
    if latest == "ready":
        return "person/review"
    if latest in ("blocked", "failed"):
        return "person/blocked" if latest == "blocked" else "person/failed"
    if any(s["status"] == "running" for s in steps):
        return "working"
    if tk.get("office_hours") is False:
        return "idle"
    if all(s["status"] in ("ready", "skipped") for s in steps):
        return "idle"
    return "working/queued"


def cmd_init(a):
    if a.kind not in FLOWS:
        print("FAIL: 未知工单类型 %s（可选 %s）" % (a.kind, "/".join(FLOWS)))
        return 2
    tk = {
        "ticket_id": _next_id(),
        "kind": a.kind,
        "title": a.title,
        "created_at": _now(),
        "updated_at": _now(),
        "mandate": {
            "policy_version": a.policy_version,
            "intent_strength": a.intent_strength,
            "accept_mode": a.accept_mode,
            "matched_rules": [r for r in (a.rules or "").split(",") if r],
            "scope": a.scope,
        },
        "report": "progress",
        "attention": None,
        "steps": [{"id": sid, "name": nm, "status": "pending",
                   "artifact": None, "started_at": None, "ready_at": None,
                   "attempts": 0} for sid, nm, _ in FLOWS[a.kind]],
        "assignments": [],
        "subscriptions": [s for s in (a.thread or "").split(",") if s],
        "history": [{"at": _now(), "event": "created"}],
    }
    _save(tk)
    print("✅ 已建工单 %s（%s，%d 步）" % (tk["ticket_id"], tk["kind"], len(tk["steps"])))
    print("   阶段：%s ｜ 授权：%s ｜ 规则：%s"
          % (stage_of(tk), tk["mandate"]["intent_strength"],
             ",".join(tk["mandate"]["matched_rules"]) or "—"))
    return 0


def cmd_step(a):
    tk = _load(a.ticket)
    steps = tk["steps"]
    idx = next((i for i, s in enumerate(steps) if s["id"] == a.id), None)
    if idx is None:
        print("FAIL: 工单无此步骤 %s（可选 %s）" % (a.id, ",".join(s["id"] for s in steps)))
        return 2
    if a.status not in STEP_STATUS:
        print("FAIL: 非法状态 %s（可选 %s）" % (a.status, "/".join(sorted(STEP_STATUS))))
        return 2

    # 门禁：前置步骤必须 ready/skipped，禁止跳步
    if a.status in ("running", "ready"):
        blocked = [s["id"] for s in steps[:idx] if s["status"] not in ("ready", "skipped")]
        if blocked:
            print("❌ 门禁拒绝：%s 之前还有未完成步骤 %s（不可跳步）" % (a.id, ",".join(blocked)))
            return 1

    s = steps[idx]
    s["status"] = a.status
    s["attempts"] += 1
    if a.status == "running" and not s["started_at"]:
        s["started_at"] = _now()
    if a.status == "ready":
        s["ready_at"] = _now()
        s["artifact"] = a.artifact or s["artifact"]
    if a.status == "blocked" and a.reason:
        s["reason"] = a.reason

    tk["history"].append({"at": _now(), "event": "step:%s=%s" % (a.id, a.status),
                          "artifact": s["artifact"], "reason": a.reason})

    # 报告状态与阶段同步
    if any(x["status"] == "failed" for x in steps):
        tk["report"] = "failed"
    elif a.status == "blocked":
        tk["report"] = "blocked"
    elif all(x["status"] in ("ready", "skipped") for x in steps):
        tk["report"] = "ready"
    else:
        tk["report"] = "progress"

    if a.executor:
        cur = next((x for x in tk["assignments"] if x.get("to") is None), None)
        if cur:
            cur["to"] = _now()
            cur["outcome"] = "ended"
        tk["assignments"].append({"executor": a.executor, "from": _now(), "to": None})

    _save(tk)
    done = sum(1 for x in steps if x["status"] in ("ready", "skipped"))
    print("✅ %s：%s → %s（%d/%d 完成）｜阶段 %s ｜报告 %s"
          % (tk["ticket_id"], a.id, a.status, done, len(steps), stage_of(tk), tk["report"]))
    if tk["report"] == "ready":
        print("   🎉 全部步骤就绪 → 工单可结束（等待评审）")
    return 0


def cmd_show(a):
    tk = _load(a.ticket)
    steps = tk["steps"]
    done = sum(1 for x in steps if x["status"] in ("ready", "skipped"))
    print("=" * 78)
    print("工单 %s · %s" % (tk["ticket_id"], tk["title"]))
    print("=" * 78)
    print("  类型   : %s" % tk["kind"])
    print("  阶段   : %s ｜ 报告：%s" % (stage_of(tk), tk.get("report")))
    m = tk["mandate"]
    print("  授权   : %s（%s 模式）｜策略版本 %s"
          % (m["intent_strength"], m["accept_mode"], m["policy_version"]))
    print("  规则   : %s" % (",".join(m["matched_rules"]) or "—"))
    print("  范围   : %s" % m["scope"])
    print("  订阅   : %s" % (",".join(tk["subscriptions"]) or "—"))
    print("  进度   : %d/%d" % (done, len(steps)))
    print("-" * 78)
    icon = {"pending": "○", "running": "▶", "ready": "●", "blocked": "■",
            "failed": "✕", "skipped": "—"}
    for s in steps:
        art = ("  ← %s" % s["artifact"]) if s.get("artifact") else ""
        rsn = ("  ! %s" % s.get("reason")) if s.get("reason") else ""
        print("  %s %-3s %-46s%s%s" % (icon.get(s["status"], "?"), s["id"], s["name"][:46], art, rsn))
    print("-" * 78)
    print("  执行器 : %s" % (", ".join(x["executor"] for x in tk["assignments"]) or "—"))
    print("=" * 78)
    return 0


def cmd_open(a):
    if not os.path.isdir(TICKET_DIR):
        print("（无工单）")
        return 0
    rows = []
    for fn in sorted(os.listdir(TICKET_DIR)):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        try:
            tk = _load(fn[:-5])
        except SystemExit:
            continue
        if tk.get("report") == "ready" and stage_of(tk) == "person/review":
            continue
        done = sum(1 for x in tk["steps"] if x["status"] in ("ready", "skipped"))
        rows.append((tk["ticket_id"], tk["title"][:28], stage_of(tk), tk["report"],
                     "%d/%d" % (done, len(tk["steps"]))))
    if not rows:
        print("✅ 无未结束工单")
        return 0
    print("%-20s %-30s %-16s %-10s %s" % ("工单", "标题", "阶段", "报告", "进度"))
    print("-" * 92)
    for r in rows:
        print("%-20s %-30s %-16s %-10s %s" % r)
    return 0


def cmd_resume(a):
    """按订阅续接：找到订阅了该线程的未结束工单。"""
    if not os.path.isdir(TICKET_DIR):
        print("（无工单）")
        return 1
    for fn in sorted(os.listdir(TICKET_DIR), reverse=True):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        tk = _load(fn[:-5])
        if a.thread in (tk.get("subscriptions") or []):
            print("↩️ 续接到工单 %s（%s）｜阶段 %s"
                  % (tk["ticket_id"], tk["title"], stage_of(tk)))
            nxt = next((s for s in tk["steps"] if s["status"] in ("pending", "blocked", "failed")), None)
            if nxt:
                print("   下一步：%s %s" % (nxt["id"], nxt["name"]))
            return 0
    print("（该线程无关联工单，需新建）")
    return 1


# ---------------------------------------------------------------- 订阅续接（P2）
def _tokens(s):
    import re as _re
    return {t for t in _re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{2,}", s or "")}


def cmd_bind(a):
    """把线程/关键词绑定到工单（Subscription 的显式版本）。"""
    tk = _load(a.ticket)
    subs = tk.setdefault("subscriptions", [])
    if a.thread and a.thread not in subs:
        subs.append(a.thread)
    kw = tk.setdefault("keywords", [])
    for k in (a.keywords or "").split(","):
        k = k.strip()
        if k and k not in kw:
            kw.append(k)
    tk.setdefault("history", []).append({"at": _now(), "event": "bound",
                                         "thread": a.thread, "keywords": a.keywords})
    _save(tk)
    print("✅ 已绑定：%s ← 线程 %s ｜关键词 %s"
          % (tk["ticket_id"], a.thread or "—", ",".join(kw) or "—"))
    return 0


def cmd_route(a):
    """给定一条新消息，判断它是否续接某个未结束工单（跨会话续接）。"""
    if not os.path.isdir(TICKET_DIR):
        print("（无工单）")
        return 1
    toks = _tokens(a.text)
    best, best_score = None, 0
    for fn in sorted(os.listdir(TICKET_DIR)):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        try:
            tk = _load(fn[:-5])
        except SystemExit:
            continue
        steps = tk.get("steps") or []
        if not steps or all(s.get("status") in ("ready", "skipped") for s in steps):
            continue
        bag = _tokens(tk.get("title", "")) | _tokens((tk.get("mandate") or {}).get("scope", ""))
        bag |= {k for k in (tk.get("keywords") or [])}
        score = len(toks & bag)
        if score > best_score:
            best, best_score = tk, score

    print("=" * 78)
    print("跨会话续接 · 工单匹配")
    print("=" * 78)
    print("  消息：%s" % a.text[:70])
    if best is None or best_score < a.min_score:
        print("  判定：无匹配工单（最高分 %d < 阈值 %d）→ 走新任务" % (best_score, a.min_score))
        print("=" * 78)
        return 1
    nxt = next((s for s in best["steps"] if s["status"] in ("pending", "blocked", "failed")), None)
    print("  ✅ 命中工单 %s（%s）｜匹配 %d 个关键词 ｜阶段 %s"
          % (best["ticket_id"], best["title"], best_score, stage_of(best)))
    print("  授权：%s ｜范围：%s" % ((best["mandate"] or {}).get("intent_strength", "—"),
                                     (best["mandate"] or {}).get("scope", "—")))
    if nxt:
        print("  下一步：%s %s" % (nxt["id"], nxt["name"]))
    print("=" * 78)
    return 0



def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="工单状态机（Ticket / Mandate / Assignment / Subscription）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--kind", default="5s-modeling", choices=sorted(FLOWS))
    p.add_argument("--title", required=True)
    p.add_argument("--scope", default="")
    p.add_argument("--intent-strength", default="explicit",
                   choices=["explicit", "inferred", "not_admitted"])
    p.add_argument("--accept-mode", default="observe", choices=["off", "observe", "auto"])
    p.add_argument("--rules", default="")
    p.add_argument("--policy-version", default="2026.11.20-1")
    p.add_argument("--thread", default="")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("step")
    p.add_argument("--ticket", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--artifact", default="")
    p.add_argument("--reason", default="")
    p.add_argument("--executor", default="")
    p.set_defaults(fn=cmd_step)

    p = sub.add_parser("show")
    p.add_argument("--ticket", required=True)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("open")
    p.set_defaults(fn=cmd_open)

    p = sub.add_parser("resume")
    p.add_argument("--thread", required=True)
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("bind", help="把线程/关键词绑定到工单（订阅）")
    p.add_argument("--ticket", required=True)
    p.add_argument("--thread", default="")
    p.add_argument("--keywords", default="")
    p.set_defaults(fn=cmd_bind)

    p = sub.add_parser("route", help="给定新消息判断是否续接某未结束工单（跨会话）")
    p.add_argument("--text", required=True)
    p.add_argument("--min-score", type=int, default=2)
    p.set_defaults(fn=cmd_route)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
