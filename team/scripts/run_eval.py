#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_eval.py · 黄金问题集评测执行器（P1-1 · 2026-11-05）
两模式共用同一套评分：baseline（内置规则，确定性，不依赖 LLM/DB2）/ team（对专家团预测结果打分）。

用法：
  python scripts/run_eval.py --mode baseline                          # 基线模式
  python scripts/run_eval.py --mode team --pred predictions.json       # 团队模式
  python scripts/run_eval.py --mode baseline --output eval/基线报告   # 指定输出前缀

退出码 0 = 通过 / 1 = 团队准确率较历史基线降 >2pp（仅 team 模式） / 2 = 参数错误
说明：baseline 模式为确定性规则「对照标尺」，不含语义/SQL/治理引擎，低分属预期，
      产出报告即 exit 0，不参与回归阻断；回归阻断只在 team 模式（对专家团预测打分）执行。
"""
import argparse, csv, json, os, sys, time, collections

# ── 路径常量 ──
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV = os.path.join(ROOT, "knowledge", "design", "eval", "黄金问题集-v1.0.csv")
EVAL_DIR = os.path.join(ROOT, "knowledge", "design", "eval")

# 域代码映射
DOMAINS = {"LT01": "铁前", "ZG01": "轧钢", "LG01": "炼钢", "CB01": "成本",
           "YL01": "原料", "CG01": "采购", "NY01": "能源"}
STAGES = {"route": "域路由", "intent": "意图识别", "semantic": "语义匹配",
          "guard": "口径护栏", "sql": "SQL编译", "govern": "治理审查", "refuse": "拒答"}

def load_questions(path):
    """加载黄金问题集 CSV → [{qid,layer,...,_row},...]"""
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_row"] = int(r.get("qid","R00")[1:]) if r.get("qid","")[1:].isdigit() else 0
    return rows

# ── 判分函数 ──
def score_exact(got: str, want: str) -> float:
    return 1.0 if str(got).strip().split("|") == str(want).strip().split("|") else 0.0

def score_numeric(got: float, want: float, tol: float = 0.01) -> float:
    if want == 0: return 1.0 if abs(got) < tol else 0.0
    return 1.0 if abs(got - want) / abs(want) <= tol else 0.0

def score_set(got: str, want: str) -> float:
    gs = set(str(got).strip().split("|"))
    ws = set(str(want).strip().split("|"))
    return len(gs & ws) / len(ws) if ws else 0.0

def score_token(actual_sql: str, must: str, forbid: str) -> float:
    """检查 SQL 必含/禁含令牌（大小写不敏感）"""
    s = (actual_sql or "").lower()
    ok = True
    if must:
        for t in must.split("|"):
            if t.strip().lower() not in s:
                ok = False; break
    if forbid:
        for t in forbid.split("|"):
            if t.strip().lower() in s:
                ok = False; break
    return 1.0 if ok else 0.0

# ── 基线模式（内置规则，不依赖 LLM/DB2） ──
def baseline_score(q):
    """基线：用 deterministic rules 推断答案。局限性：只能覆盖部分层，
    返回值会在 CSV 中作为 'baseline' 字段引用。"""
    qid = q.get("qid", "?")
    layer = q.get("layer", "")
    score = 0.0
    detail = ""
    # 基线规则（可扩展）
    if layer == "route":
        kw = q.get("question", "").lower()
        domain_hints = {"高炉": "LT01", "铁": "LT01", "轧": "ZG01", "线": "ZG01",
                        "炼钢": "LG01", "炉": "LG01", "成本": "CB01", "库": "YL01",
                        "港": "YL01", "采购": "CG01", "能源": "NY01"}
        for k, v in domain_hints.items():
            if k in kw:
                got = v
                want = q.get("expected_domain", "")
                score = score_exact(got, want)
                detail = f"keyword '{k}' → domain {got} (want {want})"
                break
        if not detail:
            score, detail = 0.0, f"no domain keyword match for '{kw[:40]}'"
    elif layer == "refuse":
        score = 1.0 if q.get("expect_refuse", "0") == "1" else 0.5
        detail = "refuse baseline"
    elif layer == "govern":
        score = 1.0 if q.get("expect_gate", "0") == "1" else 0.5
        detail = "gate baseline"
    else:
        score, detail = 0.5, "baseline limited (needs semantic/sql engine)"
    return score, detail

# ── 主入口 ──
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["baseline", "team"])
    ap.add_argument("--pred", help="predictions JSON file (team mode)")
    ap.add_argument("--output", default=os.path.join(EVAL_DIR, "基线报告"))
    a = ap.parse_args()

    if not os.path.exists(CSV):
        print(f"❌ 黄金问题集不存在: {CSV}")
        sys.exit(2)

    questions = load_questions(CSV)
    print(f"📋 加载 {len(questions)} 题（{CSV}）")

    if a.mode == "baseline":
        run_baseline(questions, a.output)
    elif a.mode == "team":
        if not a.pred or not os.path.exists(a.pred):
            print(f"❌ team mode requires --pred <file>")
            sys.exit(2)
        with open(a.pred, encoding="utf-8") as f:
            preds = json.load(f)
        run_team(questions, preds, a.output)

def run_baseline(questions, out_prefix):
    t0 = time.time()
    results = []
    by_layer = collections.defaultdict(lambda: {"correct": 0, "total": 0})
    by_domain = collections.defaultdict(lambda: {"correct": 0, "total": 0})

    for q in questions:
        score, detail = baseline_score(q)
        qid = q["qid"]
        layer = q["layer"]
        domain = q["expected_domain"]
        results.append({"qid": qid, "layer": layer, "score": score, "detail": detail,
                        "question": q["question"][:60]})
        by_layer[layer]["total"] += 1
        if score >= 0.99: by_layer[layer]["correct"] += 1
        by_domain[domain]["total"] += 1
        if score >= 0.99: by_domain[domain]["correct"] += 1

    total = sum(1 for r in results if r["score"] >= 0.99)
    accuracy = total / len(results) if results else 0
    elapsed = time.time() - t0

    # ── 写报告 ──
    report = f"""# 黄金问题集基线报告 · {time.strftime('%Y-%m-%d')}
**模式**: baseline（确定性规则，不依赖 LLM/DB2）｜**题目数**: {len(results)} ｜**总准确率**: {total}/{len(results)} = {accuracy:.1%}｜**耗时**: {elapsed:.1f}s

## 分层准确率
| 环节 | 正确数 | 总数 | 准确率 |
|---|---|---|---|"""
    for layer in ["route","intent","semantic","guard","sql","govern","refuse"]:
        d = by_layer[layer]
        if d["total"]:
            report += f"\n| {STAGES.get(layer,layer)} | {d['correct']} | {d['total']} | {d['correct']/d['total']:.1%} |"

    report += "\n\n## 分域准确率\n| 域 | 正确数 | 总数 | 准确率 |\n|---|---|---|---|"
    for domain, d in sorted(by_domain.items()):
        report += f"\n| {DOMAINS.get(domain,domain)} | {d['correct']} | {d['total']} | {d['correct']/d['total']:.1%} |"

    # 写文件
    md_path = f"{out_prefix}-{time.strftime('%Y-%m-%d')}.md"
    csv_path = f"{out_prefix}明细-{time.strftime('%Y-%m-%d')}.csv"
    json_path = f"{out_prefix}预测-{time.strftime('%Y-%m-%d')}.json"

    with open(md_path, "w", encoding="utf-8") as f: f.write(report)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["qid","layer","score","detail","question"])
        w.writeheader(); w.writerows(results)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": "baseline",
                   "total": len(results), "accuracy": accuracy, "results": results,
                   "by_layer": {k: dict(v) for k, v in by_layer.items()}},
                  f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}\n✅ 基线报告\n{'='*60}")
    print(f"总准确率: {total}/{len(results)} = {accuracy:.1%}")
    print(f"报告: {md_path}\n明细: {csv_path}\n预测: {json_path}")
    print(f"分层: " + " | ".join(f"{STAGES.get(k,k)}:{v['correct']}/{v['total']}"
          for k, v in by_layer.items() if v['total']))

    # baseline 是对照标尺，低分属预期，不参与回归阻断（回归判定见 run_team）。
    print(f"\nℹ️  baseline 为对照基线（总准确率 {accuracy:.1%}），不代表专家团准确率，不触发回归阻断")
    print("   回归阻断判定请执行: python scripts/run_eval.py --mode team --pred <predictions.json>")
    sys.exit(0)

def run_team(questions, preds, out_prefix):
    """团队模式：对专家团预测结果打分"""
    pred_map = {p.get("qid"): p for p in preds}
    results = []
    for q in questions:
        qid = q["qid"]
        p = pred_map.get(qid, {})
        score = 0.0
        detail = "no prediction"

        if "predicted_zb_codes" in p:
            score = score_set(str(p["predicted_zb_codes"]), q.get("expected_zb_codes", ""))
            detail = f"zb_code set_match={score:.2f}"
        if "predicted_sql" in p and (q.get("must_tokens") or q.get("forbid_tokens")):
            s = score_token(p.get("predicted_sql", ""), q.get("must_tokens", ""), q.get("forbid_tokens", ""))
            score = min(score, s)

        results.append({"qid": qid, "layer": q["layer"], "score": score,
                        "detail": detail, "question": q["question"][:60]})

    total = sum(1 for r in results if r["score"] >= 0.99)
    accuracy = total / len(results) if results else 0
    json_path = f"{out_prefix}-{time.strftime('%Y-%m-%d')}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": "team",
                   "total": len(results), "accuracy": accuracy, "results": results},
                  f, ensure_ascii=False, indent=2)

    print(f"\n✅ 团队评测: {total}/{len(results)} = {accuracy:.1%}")
    print(f"结果: {json_path}")

    # 回归阻断：仅 team 模式与历史基线 80.3% 对比，降 >2pp → exit 1
    HIST_BASELINE = 0.803
    if accuracy < HIST_BASELINE - 0.02:
        print(f"\n⚠️ 团队准确率 {accuracy:.1%} < 历史基线 {HIST_BASELINE:.1%} - 2pp，回归阻断")
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()