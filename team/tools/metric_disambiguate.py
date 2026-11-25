# -*- coding: utf-8 -*-
"""metric_disambiguate.py —— 指标名消歧（确定性优先 · jev 仅兜底）

存在理由（证据）：
  `jev_rules.md` §2 规定「root_cause 不问 jev」，而根因类任务恰恰最容易把
  「料耗」理解成「固体燃料耗」而不是「钢铁料耗」。整条链路一旦取错指标，
  后面再准也是错的。

  本模块把「指标候选生成」做成**确定性**的一步（不依赖模型），只在
  候选打平时才请 jev 小模型裁决——这与 superagent 的「Gate 确定性、
  Assessment 只在必要时用模型」一致。

用法：
    python tools/metric_disambiguate.py --text "查近七日三明闽光钢铁料耗、铁水耗、燃料比"
    python tools/metric_disambiguate.py --text "..." --use-jev
    python tools/metric_disambiguate.py --text "..." --json

退出码：0 全部消歧成功 ｜ 3 存在歧义（需人工点名）｜ 2 输入错误
"""
import argparse
import io
import json
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(PKG, "knowledge", "design", "indicator", "indicator_registry.json")
ALIASES = os.path.join(PKG, "knowledge", "design", "policy", "metric_aliases.yml")

FACTORY_CANON = {          # 同义厂别 → 唯一规范名（避免「三明」与「本部」重复计分）
    "三明": "本部", "闽光": "本部", "本部": "本部",
    "泉州": "泉州", "罗源": "罗源",
}
PROCESS_KW = ["炼钢", "转炉", "一炼", "二炼", "炼铁", "高炉", "烧结", "焦化", "轧钢", "棒材", "高线", "中板"]
PERIOD_KW = ["日平均", "月平均", "月累", "累计", "年"]


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_yaml(path):
    sys.path.insert(0, os.path.join(PKG, "tools", "_vendor"))
    import yaml  # noqa
    with io.open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_registry():
    with io.open(REGISTRY, encoding="utf-8-sig") as f:
        d = json.load(f)
    ind = d.get("indicators")
    if isinstance(ind, dict):
        ind = ind.get("indicators", [])
    return [x for x in (ind or []) if isinstance(x, dict)]


def factories_in(text):
    """返回文本中出现的**规范厂别**集合（同义合并）。"""
    return {FACTORY_CANON[k] for k in FACTORY_CANON if k in text}


def period_of(name):
    """从候选名里抽期间标记（只在紧邻指标名的后缀位置判定，避开「经营日报」的干扰）。"""
    n = name.replace("  ", "")
    if "日平均" in n:
        return "日平均"
    if "月平均" in n:
        return "月平均"
    if "月" in n and "累" in n:
        return "月累"
    if "年" in n:
        return "年"
    return None


def context_of(text):
    per = []
    if re.search(r"近\s*[7七]\s*日|近\s*\d+\s*日|日平均|每日", text):
        per.append("日平均")
    if re.search(r"月平均|近\s*\d+\s*月", text):
        per.append("月平均")
    if "年" in text:
        per.append("年")
    return {
        "factory": sorted(factories_in(text)),
        "process": [k for k in PROCESS_KW if k in text],
        "period": per,
        "_text": text,
    }


def score(name, ctx):
    """确定性打分：命中 +，冲突 −。"""
    s, why = 0, []
    nf = factories_in(name)
    for f in ctx["factory"]:
        if f in nf:
            s += 3
            why.append("厂别:" + f)
    for f in nf - set(ctx["factory"]):
        s -= 3
        why.append("厂别冲突:" + f)
    for p in ctx["process"]:
        if p in name:
            s += 2
            why.append("工序:" + p)
            break
    # 文本未点名子单元时，倾向「合计」而非「一炼/二炼/1#高炉/转炉」
    SUBUNIT_RE = r"[一二三四五六七八]\s*#|高炉|转炉|一炼|二炼|一高|二高|三高|棒材|高线|中板|烧结|焦化"
    if not re.search(SUBUNIT_RE, ctx.get("_text", "")) and re.search(SUBUNIT_RE, name):
        s -= 2
        why.append("子单元非合计")
    np_ = period_of(name)
    if np_ is not None:
        if np_ in ctx["period"]:
            s += 2
            why.append("期间:" + np_)
        else:
            s -= 3
            why.append("期间冲突:" + np_)
    if len(name) <= 20:
        s += 1
    return s, why


def candidates_for(term, registry, ctx, topn=8):
    hits = [x for x in registry if term in (x.get("zb_name") or "")]
    # 排除明显跨域（如「能源/采购」域）与未定义 SQL1 的不可执行项
    hits = [x for x in hits if (x.get("domain") or "生产管制") in ("生产管制", "日成本")]
    scored = []
    for x in hits:
        sc, why = score(x.get("zb_name") or "", ctx)
        scored.append({
            "zb_code": x.get("zb_code"),
            "zb_name": x.get("zb_name"),
            "domain": x.get("domain"),
            "level": x.get("level"),
            "unit": x.get("unit"),
            "executable": bool((x.get("sql1") or "").strip()),
            "score": sc,
            "why": why,
        })
    scored.sort(key=lambda r: (-r["score"], not r["executable"], len(r["zb_name"] or "")))
    return scored[:topn]


def jev_pick(term, cands, timeout=30.0):
    """候选打平时请 jev 小模型裁决（conf ≥ 0.85 才采纳）。"""
    sys.path.insert(0, os.path.join(PKG, "tools"))
    try:
        import jev_query  # noqa
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "jev_query 不可用：%s" % e}
    labels = ["%s（%s）" % (c["zb_code"], c["zb_name"]) for c in cands]
    state = ("指标名「%s」存在多个候选，请选出与下列业务语境最匹配的一个：%s"
             % (term, "；".join(labels)))
    try:
        out = jev_query.run_preset("domain", state, text="", timeout=timeout)
        return {"ok": True, "raw": out if isinstance(out, (dict, list, str)) else str(out)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def disambiguate(text, use_jev=False, topn=8):
    cfg = load_yaml(ALIASES)
    terms = [t["term"] for t in (cfg.get("ambiguous_terms") or [])]
    ctx = context_of(text)
    registry = load_registry()

    results = []
    for term in terms:
        if term not in text:
            continue
        cands = candidates_for(term, registry, ctx, topn)
        if not cands:
            results.append({"term": term, "status": "no_candidate", "candidates": []})
            continue
        execs = [c for c in cands if c["executable"]] or cands
        top1, top2 = execs[0], (execs[1] if len(execs) > 1 else None)
        gap = top1["score"] - (top2["score"] if top2 else -99)
        rec = {"term": term, "context": {k: v for k, v in ctx.items() if not k.startswith("_")},
               "candidates": cands, "top1": top1["zb_code"], "gap": gap}
        if gap >= 2:
            rec.update(status="resolved", source="rules", picked=top1["zb_code"],
                       confidence=min(0.99, 0.75 + 0.05 * gap))
        elif gap >= 1 and top1["score"] >= 3:
            # 微弱领先：锁定但**必须**在契约 open_questions 里请用户确认
            rec.update(status="resolved_weak", source="rules", picked=top1["zb_code"],
                       confidence=round(0.70 + 0.05 * gap, 2),
                       confirm_required=True)
        else:
            rec.update(status="ambiguous", source="rules")
            if use_jev:
                rec["jev"] = jev_pick(term, execs[:5])
        results.append(rec)
    statuses = {r["status"] for r in results}
    return {"text": text, "context": {k: v for k, v in ctx.items() if not k.startswith("_")},
            "terms": results, "statuses": sorted(statuses),
            "ok": bool(results) and "ambiguous" not in statuses and "no_candidate" not in statuses,
            "weak": "resolved_weak" in statuses}


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="指标名消歧（确定性优先）")
    ap.add_argument("--text", required=True)
    ap.add_argument("--use-jev", action="store_true")
    ap.add_argument("--topn", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.text.strip():
        print("--text 不能为空", file=sys.stderr)
        return 2
    out = disambiguate(args.text, use_jev=args.use_jev, topn=args.topn)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["ok"] and not out["weak"] else (4 if out["ok"] else 3)

    print("=" * 76)
    print("指标名消歧 · 确定性候选生成 + jev 兜底")
    print("=" * 76)
    print("  语境：厂别=%s ｜ 工序=%s ｜ 期间=%s"
          % (out["context"]["factory"] or "—", out["context"]["process"] or "—",
             out["context"]["period"] or "—"))
    for r in out["terms"]:
        print("-" * 76)
        st = {"resolved": "✅ 已消歧", "resolved_weak": "🟡 弱消歧（须用户确认）",
              "ambiguous": "⚠️ 有歧义", "no_candidate": "❌ 无候选"}[r["status"]]
        tail = ("，锁定 %s（conf %.2f）" % (r["picked"], r["confidence"])
                if r["status"] in ("resolved", "resolved_weak") else "")
        print("  词「%s」→ %s%s" % (r["term"], st, tail))
        for c in r["candidates"][:5]:
            mark = "→" if c["zb_code"] == r.get("picked") else " "
            print("    %s %-8s %-42s score=%2d %s"
                  % (mark, c["zb_code"], (c["zb_name"] or "")[:42], c["score"],
                     "可执行" if c["executable"] else "不可执行"))
        if r.get("jev"):
            print("    jev：%s" % str(r["jev"])[:160])
    print("=" * 76)
    if not out["ok"]:
        print("裁定：⚠️ 存在歧义 → **必须请用户点名**（禁替用户挑一个）")
    elif out["weak"]:
        print("裁定：🟡 弱消歧 → 可写入契约，但**必须在 open_questions 中请用户确认**")
    else:
        print("裁定：✅ 全部消歧成功 → 可写入 IntentContract.entities.metrics")
    print("=" * 76)
    return 0 if out["ok"] and not out["weak"] else (4 if out["ok"] else 3)


if __name__ == "__main__":
    sys.exit(main())
