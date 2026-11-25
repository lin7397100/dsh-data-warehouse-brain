#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jev_pick.py —— 指标候选消歧器（多候选择一，可弃权）
================================================================================

它解决的问题：`fast_ask.py` 有时返回 `ambiguous=true` 或 `needs_slow_lane`，
候选 2~8 个、名字都很像（「6#高炉月矿耗」「5#高炉月矿耗」「炼铁1#高炉月均矿耗」…）。
以前只有两条路：要么主理人硬选一个（**等于编造**），要么整个退回慢车道（82 min）。

第三条路：把候选列表交给 4.3B 小模型做一次 choice，**带两个阈值**——
  · confidence ≥ 0.90（默认）
  · top1 − top2 ≥ 0.50（默认）
任一不满足就**弃权**，把 top2 抛给用户选。宁可弃权，不可改答。

编号守卫（比模型更硬的规则，先于模型执行）：
  问题里出现 `6#` / `6号` 时，只保留名字含 `6#`/`6号` 的候选；
  一个都没有 → 直接弃权（`number_mismatch`），**连模型都不问**。
  依据：`lookup_indicator.py` 的分词会把 `6#` 剥掉，而 has_sql 加 15 分会把 `1#` 顶上来。

实测（2026-11-18）：
  · 「帮我查一下 6#高炉的月矿耗」8 候选（真实长名）→ 选 `6#高炉月矿耗`，conf 0.9975 ✅
  · 「帮我查一下高炉矿耗」（无编号）        → 选 `3#高炉矿耗`，conf 0.5871 → **弃权** ✅

用法：
  python tools/jev_pick.py --text "<原话>" --from-fastask fastask.json
  python tools/jev_pick.py --text "<原话>" --candidates '[{"zb_code":"8000287","name":"…"}]'
  python tools/jev_pick.py --text "<原话>" --candidates @cands.json --threshold 0.85
  python tools/jev_pick.py --text "<原话>" --from-fastask fastask.json --no-model   # 只跑守卫

退出码：0 采纳（有唯一候选）；1 有候选但无模型结论（--no-model）；3 弃权（含编号不符/置信不足）；4 jev 不可达。
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import jev_query  # noqa: E402

MAX_CANDIDATES = 8  # 实测 8 候选（长中文名）稳定；再多会稀释概率
NUM_RE = re.compile(r"(\d+)\s*[#号]")
INSTRUCTIONS = ("用户要查的数据来自这些指标中的一个。只选名字最贴近用户所指的那一个；"
               "如果没有任何一个明确对应，也必须挑一个最接近的。")


def load_candidates(text, from_fastask=None, inline=None):
    cands = []
    if from_fastask:
        with open(from_fastask, "r", encoding="utf-8") as f:
            d = json.load(f)
        src = (((d.get("lookup") or {}).get("candidates")) or d.get("candidates") or [])
        best = d.get("best") or {}
        if best and best.get("name") and not any(c.get("name") == best["name"] for c in src):
            src = [best] + list(src)
        for c in src:
            cands.append({"zb_code": c.get("zb_code"), "name": c.get("name"),
                          "has_sql": c.get("has_sql"), "score": c.get("score")})
    elif inline:
        raw = inline
        if raw.startswith("@"):
            with open(raw[1:], "r", encoding="utf-8-sig") as f:
                raw = f.read()
        try:
            parsed = json.loads(raw)
        except ValueError as e:
            raise SystemExit("候选 JSON 解析失败：%s（提示：Windows PowerShell 5.1 直接传内联 JSON 会剥掉双引号，"
                             "请改用 --candidates @<文件路径>）" % e)
        if isinstance(parsed, dict):
            parsed = parsed.get("candidates") or []
        for x in parsed:
            if isinstance(x, str):
                cands.append({"zb_code": None, "name": x})
            else:
                cands.append({"zb_code": x.get("zb_code"), "name": x.get("name"),
                              "has_sql": x.get("has_sql"), "score": x.get("score")})
    # 去重（按名称）
    seen, uniq = set(), []
    for c in cands:
        n = (c.get("name") or "").strip()
        if not n or n in seen:
            continue
        seen.add(n)
        uniq.append(c)
    return uniq


def numbering_guard(text, cands):
    """返回 (保留列表, 信息dict)。问题含编号时只留同编号候选；全无则保留空列表。"""
    nums = NUM_RE.findall(text or "")
    if not nums:
        return cands, {"asked": []}
    keep = [c for c in cands
            if any((n + "#") in (c.get("name") or "") or (n + "号") in (c.get("name") or "")
                   for n in nums)]
    info = {"asked": nums, "kept": [c["name"] for c in keep],
            "dropped": [c["name"] for c in cands if c not in keep]}
    return keep, info


def pick(text, cands, threshold=0.90, margin=0.50, use_model=True,
         url=None, model=None, timeout=30.0):
    out = {"text": (text or "").strip(), "adopted": False, "zb_code": None, "name": None,
           "confidence": 0.0, "margin": 0.0, "reason": "", "candidates": cands,
           "threshold": threshold, "margin_threshold": margin}

    keep, guard = numbering_guard(text or "", cands)
    out["numbering_guard"] = guard
    if guard["asked"] and not keep:
        out["reason"] = "number_mismatch：问题指定了编号 %s，但候选中没有任何同编号指标（不得改答别的编号）" % (
            ",".join(n + "#" for n in guard["asked"]))
        return out, 3
    cands = keep

    # 编号对称守卫（实测教训）：问「高炉矿耗」没指定几号炉时，jev 会以 conf 0.928
    # 自信地选「1#高炉矿耗」——**阈值挡不住**。规则：问题未指定编号而候选全部带编号，
    # 说明粒度未定，必须弃权让用户点名；有「无编号」候选时只在这些里面选。
    if not guard["asked"]:
        numbered = [c for c in cands if NUM_RE.search(c.get("name") or "")]
        plain = [c for c in cands if not NUM_RE.search(c.get("name") or "")]
        if numbered and not plain:
            out["unnamed_numbering"] = {"numbered_candidates": [c["name"] for c in numbered][:6]}
            out["reason"] = ("unnamed_numbering：问题没有指定编号，而候选全部按编号细分（%s…）→ "
                             "粒度未定，必须请用户点名，不得替用户选一个炉子"
                             % "、".join(c["name"] for c in numbered[:4]))
            return out, 3
        if plain:
            out["dropped_numbered"] = [c["name"] for c in numbered][:6]
            cands = plain

    if not cands:
        out["reason"] = "empty_candidates：没有候选可判"
        return out, 3

    if len(cands) == 1:
        c = cands[0]
        out.update({"adopted": True, "zb_code": c.get("zb_code"), "name": c.get("name"),
                    "confidence": 1.0, "margin": 1.0, "reason": "only_one：唯一候选，无需模型"})
        out["has_sql"] = c.get("has_sql")
        if c.get("has_sql") is False:
            out["note"] = "身份已定（唯一候选），但该指标**未物化** → 交 sg-adhoc-indicator / 物化流程，不得直查"
        return out, 0

    if not use_model:
        out["reason"] = "no_model：未启用模型，候选 %d 个仍需人工选择" % len(cands)
        return out, 1

    cands = cands[:MAX_CANDIDATES]
    labels = {c["name"]: c["name"] for c in cands}
    try:
        label, conf, probs, raw = jev_query.classify(
            text, labels, question="指标", instructions=INSTRUCTIONS,
            url=url, model=model, timeout=timeout)
    except jev_query.JevError as e:
        out["reason"] = "jev_unreachable：%s" % e
        return out, 4

    ranked = sorted((probs or {}).items(), key=lambda kv: -float(kv[1]))
    top1 = ranked[0][1] if ranked else 0.0
    top2 = ranked[1][1] if len(ranked) > 1 else 0.0
    out["jev"] = {"choice": label, "confidence": round(conf, 4),
                  "probabilities": {k: round(float(v), 4) for k, v in (probs or {}).items()},
                  "latency_ms": (raw or {}).get("_latency_ms"),
                  "top2": ({"name": ranked[1][0], "p": round(float(top2), 4)} if len(ranked) > 1 else None)}
    out["confidence"] = round(conf, 4)
    out["margin"] = round(float(top1) - float(top2), 4)

    if conf < threshold:
        out["reason"] = ("abstain_low_conf：conf=%.3f < %.2f（jev 倾向「%s」，但不足以定案）"
                         % (conf, threshold, label))
        return out, 3
    if out["margin"] < margin:
        out["reason"] = ("abstain_low_margin：top1−top2=%.3f < %.2f（前两名几乎平分）"
                         % (out["margin"], margin))
        return out, 3

    hit = next((c for c in cands if c["name"] == label), None)
    out.update({"adopted": True, "name": label, "zb_code": (hit or {}).get("zb_code"),
                "has_sql": (hit or {}).get("has_sql"),
                "reason": "adopted：conf=%.3f ≥ %.2f 且 margin=%.3f ≥ %.2f" % (conf, threshold, out["margin"], margin)})
    if (hit or {}).get("has_sql") is False:
        out["note"] = "身份已定，但该指标**未物化** → 交 sg-adhoc-indicator / 物化流程，不得直查"
    return out, 0


def main():
    ap = argparse.ArgumentParser(description="指标候选消歧（可弃权）")
    ap.add_argument("--text", required=True)
    ap.add_argument("--from-fastask", default="", help="fast_ask.py 的 JSON 输出文件")
    ap.add_argument("--candidates", default="", help="候选 JSON 内联或 @文件")
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--margin", type=float, default=0.50)
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--url", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--format", choices=["json", "text"], default="json")
    args = ap.parse_args()

    if not args.from_fastask and not args.candidates:
        print("需要 --from-fastask 或 --candidates", file=sys.stderr)
        return 2
    if not args.text.strip():
        print("--text 不能为空", file=sys.stderr)
        return 2

    cands = load_candidates(args.text, args.from_fastask or None, args.candidates or None)
    r, code = pick(args.text, cands, threshold=args.threshold, margin=args.margin,
                   use_model=not args.no_model, url=args.url or None,
                   model=args.model or None, timeout=args.timeout)
    r["code"] = code

    if args.format == "text":
        print("问题     : %s" % r["text"])
        print("采纳     : %s" % ("是" if r["adopted"] else "否（弃权）"))
        if r["adopted"]:
            print("指标     : %s（%s）| has_sql=%s" % (r["name"], r["zb_code"], r.get("has_sql")))
        print("置信/差  : %.4f / %.4f" % (r["confidence"], r["margin"]))
        print("原因     : %s" % r["reason"])
        if r.get("note"):
            print("注意     : %s" % r["note"])
        j = r.get("jev") or {}
        if j.get("top2"):
            print("次优     : %s (%.4f)" % (j["top2"]["name"], j["top2"]["p"]))
        print("编号守卫 : %s" % json.dumps(r.get("numbering_guard") or {}, ensure_ascii=False))
    else:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
