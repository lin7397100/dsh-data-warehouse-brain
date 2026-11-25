# -*- coding: utf-8 -*-
"""sql_cross_source.py —— SQL 第三阶：换源对拍（确定性 · 零模型调用）

来源：借鉴 dsh-superagent「独立信源 + 诚实交付」的思路。

v2.2 修正（2026-11-20 业务澄清 · **最重要的一次**）：
     用户指出：**ODS 是活数据**——每日 07:30 早会后会反复重抽多次；DWS 是
     07:35 那一刻的快照。**拿「当前 ODS」判「DWS 快照」错，是时间不可比，不是数据错。**
     故 v2.2 引入：
       ① `snapshot_time` 快照对齐（不同则判 NOT_COMPARABLE，不算漂移）
       ② ODS/RECOMPUTE 层**默认 advisory**（参考位，不计入独立层数）
       ③ 报告必须声明数据时点
     详见 `knowledge/design/policy/data_freshness_rules.md`

v2.1 修正：按显示精度定容差 + 三源多数票 + 权威序（2 源无法定责）

用法：
    python tools/sql_cross_source.py --spec knowledge/design/policy/recon_<TR>.json
    python tools/sql_cross_source.py --spec <json> --json
    python tools/sql_cross_source.py --spec <json> --require-layers 2

裁定（优先级从上到下）：
    VERIFIED         全部**可比且独立**的信源在容差内一致
    SOURCE_CONFLICT  多数层一致，存在离群信源 → 点名离群源（exit 5）
    DRIFT            无法形成多数（2 源各执一词）→ 禁止交付（exit 1）
    INSUFFICIENT     可比独立信源 < 要求层数 → 不得声称已核验（exit 3）
    NOT_COMPARABLE   存在快照时点不同的信源 → **时间不可比**，不算漂移（exit 6）

退出码：0 VERIFIED ｜ 5 SOURCE_CONFLICT ｜ 1 DRIFT ｜ 3 INSUFFICIENT ｜ 6 NOT_COMPARABLE ｜ 2 输入错误
"""
import argparse
import io
import json
import os
import sys

EPS = 1e-12
LAYER_AUTHORITY = {"REPORT": 1, "ADS": 1, "GOLDEN": 1, "DWS": 2, "DWD": 2, "ODS": 3, "RECOMPUTE": 3}
# 活数据层：默认只作参考位，除非显式给 snapshot_time 且与基准对齐
VOLATILE_LAYERS = {"ODS", "RECOMPUTE"}
EXIT = {"VERIFIED": 0, "DRIFT": 1, "INSUFFICIENT": 3, "SOURCE_CONFLICT": 5, "NOT_COMPARABLE": 6}


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def q_of(src, default):
    q = src.get("quantum")
    return float(q) if isinstance(q, (int, float)) and q > 0 else default


def agree(a, qa, b, qb):
    """两值是否在「各自显示精度」容差内一致。

    容差 = (qa + qb) / 2：两个 2 位小数（各 0.005）→ 0.005；报表 1 位（0.1）对 DWS 2 位 → 0.0525。
    不叠加“舍入后相等”判断 —— 会引入浮点脆弱性；容差本身已能拦住跨档。
    """
    if a is None or b is None:
        return None
    return abs(a - b) <= (qa + qb) / 2.0 + 1e-9


def pick_reference(sources, default_q):
    """选基准快照：取权威最高且带 snapshot_key/snapshot_time 的源。"""
    def key(s):
        return s.get("snapshot_key") or s.get("snapshot_time")
    cands = [s for s in sources if key(s)]
    if not cands:
        return None, None
    cands.sort(key=lambda s: LAYER_AUTHORITY.get((s.get("layer") or "?").upper(), 9))
    return key(cands[0]), cands[0].get("snapshot_time")


def snapkey(s):
    return s.get("snapshot_key") or s.get("snapshot_time")


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="换源对拍（第三阶 v2.2 · 快照对齐）")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--quantum", type=float, default=None, help="缺省显示精度，默认取 spec.quantum 或 0.005")
    ap.add_argument("--require-layers", type=int, default=2)
    ap.add_argument("--allow-advisory", action="store_true",
                    help="把 advisory（活数据）源也计入层数（不推荐，除非已对齐快照）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.spec):
        print("FAIL: 找不到 %s" % args.spec)
        return 2
    with io.open(args.spec, encoding="utf-8-sig") as f:
        spec = json.load(f)

    dq = args.quantum if args.quantum is not None else spec.get("quantum", 0.005)
    req = args.require_layers
    metrics_out, flags, min_layers = [], set(), 99

    for m in spec.get("metrics") or []:
        all_src = m.get("sources") or []
        with_vals = [s for s in all_src if s.get("values")]
        skipped = [s for s in all_src if not s.get("values")]
        ref_key, ref_ts = pick_reference(with_vals, dq)

        comparable, not_comparable, advisory = [], [], []
        for s in with_vals:
            lay = (s.get("layer") or "?").upper()
            k = snapkey(s)
            is_volatile = lay in VOLATILE_LAYERS
            explicit_adv = s.get("advisory")
            # 活数据层未给快照标识 → 降为 advisory（不计入独立层）
            if explicit_adv is True or (is_volatile and k is None and not args.allow_advisory):
                advisory.append({"source_id": s.get("source_id"), "layer": lay,
                                 "reason": "活数据层未提供 snapshot_key/time，降为参考位（不计入独立层）"})
                continue
            # 快照标识不同 → 时间不可比
            if ref_key is not None and k is not None and k != ref_key:
                not_comparable.append({"source_id": s.get("source_id"), "layer": lay,
                                       "snapshot_key": k, "reference_key": ref_key,
                                       "reason": "快照时点不同，时间不可比"})
                continue
            comparable.append(s)

        # 同一快照内每层取权威最高的一个代表
        by_layer = {}
        for s in comparable:
            lay = (s.get("layer") or "?").upper()
            auth = s.get("authority") or LAYER_AUTHORITY.get(lay, 5)
            if lay not in by_layer or auth < by_layer[lay]["_auth"]:
                by_layer[lay] = {"src": s, "_auth": auth}
        reps = sorted([(lay, d["src"], d["_auth"]) for lay, d in by_layer.items()], key=lambda x: x[2])
        layers = [r[0] for r in reps]
        min_layers = min(min_layers, len(layers))

        pairs = []
        for i in range(len(reps)):
            for j in range(i + 1, len(reps)):
                la, a, _ = reps[i]
                lb, b, _ = reps[j]
                keys = sorted(set(a["values"]) & set(b["values"]))
                qa, qb = q_of(a, dq), q_of(b, dq)
                bad, worst = 0, 0.0
                for k in keys:
                    va, vb = num(a["values"][k]), num(b["values"][k])
                    if agree(va, qa, vb, qb) is False:
                        bad += 1
                        worst = max(worst, abs((va or 0) - (vb or 0)))
                pairs.append({"a": a.get("source_id"), "a_layer": la, "a_q": qa,
                              "b": b.get("source_id"), "b_layer": lb, "b_q": qb,
                              "n": len(keys), "bad": bad, "worst": worst, "ok": bad == 0})

        verdict, outlier, consensus = "INSUFFICIENT", None, []
        if len(reps) >= 2:
            votes = {}
            for lay, _s, _a in reps:
                votes[lay] = sum(1 for p in pairs if p["ok"] and lay in (p["a_layer"], p["b_layer"]))
            best = max(votes.values())
            top = sorted([l for l, v in votes.items() if v == best], key=lambda l: LAYER_AUTHORITY.get(l, 5))
            winner = top[0]
            if best == len(reps) - 1:
                verdict, consensus = "VERIFIED", layers
            elif len(reps) == 2:
                verdict = "DRIFT"
            else:
                agree_layers = [winner] + [
                    p["b_layer"] if p["a_layer"] == winner else p["a_layer"]
                    for p in pairs if p["ok"] and winner in (p["a_layer"], p["b_layer"])]
                others = [l for l in layers if l not in agree_layers]
                if others and len(agree_layers) > len(others):
                    verdict, outlier, consensus = "SOURCE_CONFLICT", others[0], agree_layers
                else:
                    verdict = "DRIFT"

        if verdict == "INSUFFICIENT" and not_comparable and not reps:
            conflicting = True
        else:
            conflicting = bool(not_comparable)

        flags.add(verdict)
        if conflicting:
            flags.add("NOT_COMPARABLE")

        metrics_out.append({
            "zb_code": m.get("zb_code"), "name": m.get("name", ""), "unit": m.get("unit", ""),
            "layers": layers, "n_sources": len(with_vals), "verdict": verdict,
            "consensus_layers": sorted(set(consensus)), "outlier_layer": outlier,
            "reference_time": ref_ts,
            "not_comparable": not_comparable, "advisory": advisory,
            "skipped": [{"source_id": s.get("source_id"), "layer": s.get("layer"),
                         "reason": s.get("reason", "未取数")} for s in skipped],
            "pairs": pairs,
        })

    if "DRIFT" in flags:
        overall = "DRIFT"
    elif "SOURCE_CONFLICT" in flags:
        overall = "SOURCE_CONFLICT"
    elif "NOT_COMPARABLE" in flags and "VERIFIED" not in flags:
        overall = "NOT_COMPARABLE"
    elif min_layers >= req:
        overall = "VERIFIED"
    else:
        overall = "INSUFFICIENT"

    if args.json:
        print(json.dumps({"overall": overall, "trace_id": spec.get("trace_id"),
                          "quantum": dq, "required_layers": req, "min_layers": min_layers,
                          "metrics": metrics_out}, ensure_ascii=False, indent=2))
        return EXIT.get(overall, 3)

    print("=" * 84)
    print("换源对拍 · 第三阶 v2.2（快照对齐 · 精度感知 · 多数票）")
    print("=" * 84)
    print("  trace_id : %s" % spec.get("trace_id", "<none>"))
    print("  缺省精度 : %g（各源可自带 quantum；报表常为 0.1）" % dq)
    print("  独立层要求: ≥ %d" % req)
    print("  ⚠ 活数据层（ODS/RECOMPUTE）无 snapshot_time 时降为 advisory，不计入层数")
    for m in metrics_out:
        print("-" * 84)
        print("  %s %s（%s）｜%d 源 ｜可比独立层 %s → **%s**%s"
              % (m["zb_code"], m["name"], m["unit"], m["n_sources"],
                 "/".join(m["layers"]) or "—", m["verdict"],
                 "  离群=%s" % m["outlier_layer"] if m["outlier_layer"] else ""))
        if m["reference_time"]:
            print("     基准快照时点：%s" % m["reference_time"])
        for x in m["advisory"]:
            print("     ⊘ 参考位 %s [%s]：%s" % (x["source_id"], x["layer"], x["reason"]))
        for x in m["not_comparable"]:
            print("     ⏳ 不可比 %s [%s, key=%s ≠ 基准 %s]：%s"
                  % (x["source_id"], x["layer"], x["snapshot_key"], x["reference_key"], x["reason"]))
        for s in m["skipped"]:
            print("     ⊘ 跳过 %s [%s]：%s" % (s["source_id"], s["layer"], s["reason"]))
        for p in m["pairs"]:
            print("     %s %s[%s,q=%g] vs %s[%s,q=%g]：%s n=%d bad=%d max|Δ|=%.6g"
                  % ("✅" if p["ok"] else "❌", p["a"], p["a_layer"], p["a_q"],
                     p["b"], p["b_layer"], p["b_q"],
                     "ROUNDING" if p["ok"] else "DIFF", p["n"], p["bad"], p["worst"]))
    print("=" * 84)
    if overall == "VERIFIED":
        print("裁定：✅ VERIFIED（≥%d 个可比独立层，全部一致）→ 可交付" % req)
    elif overall == "SOURCE_CONFLICT":
        print("裁定：⚠️ SOURCE_CONFLICT（多数层一致，存在离群信源）→ 保留多数结论，离群源单独复核")
    elif overall == "DRIFT":
        print("裁定：❌ DRIFT（无法形成多数，两源各执一词）→ **禁止交付**")
    elif overall == "NOT_COMPARABLE":
        print("裁定：⏳ NOT_COMPARABLE（存在快照时点不同的信源）→ **时间不可比，不算漂移**；"
              "如需比对应先重跑 DWS 对齐快照")
    else:
        print("裁定：⚠️ INSUFFICIENT（可比独立层 %d < %d）→ **不得声称已核验**" % (min_layers, req))
    print("=" * 84)
    return EXIT.get(overall, 3)


if __name__ == "__main__":
    sys.exit(main())
