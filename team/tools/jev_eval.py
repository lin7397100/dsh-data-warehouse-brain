#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""jev_eval.py · jev 判定层精度评测器（quality / rootcause）

用法：
    python jev_eval.py --task quality
    python jev_eval.py --task rootcause --json-out out.json
    python jev_eval.py --task quality --set 我的集.jsonl --task-name fixed_quality

评测集格式（JSONL，每行一条）：
    {"id":"q-01","text":"……","gold":"完整性","kind":"definition","note":"……"}
    - kind=definition：有唯一金标，计入准确率
    - kind=ambiguous：无唯一金标（实际双解），只用于测“过信率”，不计入准确率
    gold=null 时必须是 kind=ambiguous。

输出：
    1) 定义集准确率（总体 / 各阈值下覆盖后的准确率）
    2) 每类召回率 + 混淆对
    3) 歧义集过信率（conf ≥ 阈值 的占比）——这个数字决定“能不能给 HARD 路由”
退出码：0 正常；2 评测集格式问题；3 端点不可用；4 无定义集样本

设计原则（为什么不直接拿历史工单当真值）：
  源包 observed/ 下的 100+ 治理产物是工程流程问题（trace_log、上下文压缩、token 预算），
  不是数据质量五维问题，没有单一类别字段，硬套就是编造。故采用**受控构造**：
  每条定义集样本只含一个五维/五类判别信号，金标由构造方式唯一确定（不依赖标注者口味），
  并通过歧义集单独量化“模型会不会自信地给双解题贴单标签”。
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

JEV_URL = os.environ.get("JEV_URL", "http://10.233.2.32:11434/v1/systemone")
JEV_MODEL = os.environ.get("JEV_MODEL", "tev1:4b-32k")

THRESHOLDS = [0.60, 0.70, 0.75, 0.80, 0.85, 0.90]


def load_items(path):
    items = []
    with io.open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                o = json.loads(line)
            except Exception as e:
                raise SystemExit("评测集第 %d 行不是合法 JSON：%s" % (ln, e))
            if "text" not in o:
                raise SystemExit("评测集第 %d 行缺 text" % ln)
            kind = o.get("kind", "definition")
            if kind not in ("definition", "ambiguous"):
                raise SystemExit("评测集第 %d 行 kind 只能是 definition/ambiguous" % ln)
            if kind == "definition" and not o.get("gold"):
                raise SystemExit("评测集第 %d 行是 definition 但缺 gold" % ln)
            if kind == "ambiguous" and o.get("gold"):
                raise SystemExit("评测集第 %d 行标注为 ambiguous 却给了 gold（自相矛盾）" % ln)
            o["kind"] = kind
            items.append(o)
    return items


def ask(questions, state, timeout=25):
    """调 /v1/systemone，返回 answers 字典。单问项。"""
    body = {"model": JEV_MODEL, "state": state, "questions": questions}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(JEV_URL, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return payload.get("answers") or {}, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["quality", "rootcause", "anomaly"], required=True,
                    help="quality=五维质量问题；rootcause=五类根因（anomaly 为旧别名）")
    ap.add_argument("--set", default=None, help="自定义评测集路径；默认 docs/jev-eval/<task>.jsonl")
    ap.add_argument("--json-out", default=None, help="把全部指标写成 JSON")
    ap.add_argument("--dry-run", action="store_true", help="只校验评测集，不打端点")
    args = ap.parse_args()

    task = "rootcause" if args.task == "anomaly" else args.task
    setpath = args.set or os.path.join(HERE, "..", "docs", "jev-eval", task + ".jsonl")
    if not os.path.exists(setpath):
        raise SystemExit("评测集不存在：%s" % setpath)
    items = load_items(setpath)

    import jev_query
    questions = jev_query.preset_questions(task)
    qname = list(questions.keys())[0]

    n_def = sum(1 for it in items if it["kind"] == "definition")
    n_amb = sum(1 for it in items if it["kind"] == "ambiguous")
    print("评测集：%s" % setpath)
    print("样本：定义集 %d 条 / 歧义集 %d 条 ｜ 问项「%s」" % (n_def, n_amb, qname))
    if args.dry_run:
        classes = sorted({it["gold"] for it in items if it["kind"] == "definition"})
        print("金标类别：%s" % ", ".join(classes))
        print("dry-run OK（未调端点）")
        return
    if n_def == 0:
        raise SystemExit(4)

    rows = []
    fails = 0
    for it in items:
        try:
            answers, el = ask(questions, it["text"])
            a = answers.get(qname) or {}
            pred = a.get("choice")
            conf = float(a.get("confidence") or 0.0)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:200]
            print("HTTP %d：%s" % (e.code, body))
            raise SystemExit(3)
        except Exception as e:
            print("端点不可用：%s" % e)
            raise SystemExit(3)
        rows.append({"id": it.get("id"), "text": it["text"], "kind": it["kind"],
                     "gold": it.get("gold"), "pred": pred, "conf": round(conf, 4),
                     "correct": (pred == it.get("gold")) if it["kind"] == "definition" else None,
                     "sec": round(el, 2)})
        if it["kind"] == "definition" and pred != it.get("gold"):
            fails += 1
        print("  %-6s %-10s pred=%-8s conf=%.3f  %s  %.2fs"
              % (it.get("id"), it["kind"][:4], pred, conf,
                 "OK" if rows[-1]["correct"] else ("--" if rows[-1]["correct"] is None else "XX"),
                 el))

    # ---- 定义集指标 ----
    defs = [r for r in rows if r["kind"] == "definition"]
    acc = sum(1 for r in defs if r["correct"]) / len(defs)

    classes = sorted({r["gold"] for r in defs})
    per_class = {}
    for c in classes:
        sub = [r for r in defs if r["gold"] == c]
        per_class[c] = {"support": len(sub),
                        "recall": round(sum(1 for r in sub if r["correct"]) / len(sub), 4)}

    conf_pairs = {}
    for r in defs:
        if not r["correct"]:
            k = "%s→%s" % (r["gold"], r["pred"])
            conf_pairs[k] = conf_pairs.get(k, 0) + 1

    sweep = []
    for T in THRESHOLDS:
        cov = [r for r in defs if r["conf"] >= T]
        sweep.append({"T": T,
                      "coverage": round(len(cov) / len(defs), 4),
                      "acc_covered": round((sum(1 for r in cov if r["correct"]) / len(cov)), 4) if cov else None,
                      "abstained": len(defs) - len(cov)})

    # ---- 歧义集：过信率 ----
    ambs = [r for r in rows if r["kind"] == "ambiguous"]
    over = {str(T): (round(sum(1 for r in ambs if r["conf"] >= T) / len(ambs), 4) if ambs else None)
            for T in THRESHOLDS}

    print("\n==== 定义集（%d 条）====" % len(defs))
    print("总体准确率：%.1f%%（错 %d 条）" % (acc * 100, fails))
    print("每类召回：")
    for c in classes:
        print("  %-6s 支持 %2d  召回 %.1f%%" % (c, per_class[c]["support"], per_class[c]["recall"] * 100))
    if conf_pairs:
        print("混淆对：")
        for k, v in sorted(conf_pairs.items(), key=lambda x: -x[1]):
            print("  %-22s %d" % (k, v))
    print("\n阈值扫描（覆盖=conf≥T 的占比；覆盖后准确率=敢路由的那部分有多准）：")
    print("  %-5s %-8s %-10s %-8s" % ("T", "覆盖", "覆盖后准确率", "弃权"))
    for s in sweep:
        a = "--" if s["acc_covered"] is None else "%.1f%%" % (s["acc_covered"] * 100)
        print("  %-5.2f %-8.1f%% %-10s %-8d" % (s["T"], s["coverage"] * 100, a, s["abstained"]))

    if ambs:
        print("\n==== 歧义集（%d 条，无唯一金标）====" % len(ambs))
        print("过信率（模型仍给 conf≥T 的比例）：")
        for T in (0.80, 0.85, 0.90):
            print("  T=%.2f  %s" % (T, "%.0f%%" % (over[str(T)] * 100)))
        print("  说明：过信率高 → 该阈值不能用于 HARD 路由，只能作建议位。")

    best = max([s for s in sweep if s["acc_covered"] is not None],
               key=lambda s: (s["acc_covered"], s["coverage"]), default=None)
    print("\n建议：")
    if best:
        print("  阈值 %.2f 时覆盖 %.0f%%、覆盖后准确率 %.1f%%"
              % (best["T"], best["coverage"] * 100, best["acc_covered"] * 100))
    print("  HARD 路由需同时满足：覆盖后准确率 ≥ 90%% 且 歧义集过信率 ≤ 30%%；否则只作建议位并披露。")

    if args.json_out:
        out = {"task": task, "set": os.path.abspath(setpath), "model": JEV_MODEL,
               "n_definition": len(defs), "n_ambiguous": len(ambs),
               "accuracy": round(acc, 4), "per_class": per_class,
               "confusion_pairs": conf_pairs, "threshold_sweep": sweep,
               "ambiguous_overconfidence": over, "rows": rows,
               "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with io.open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("JSON 已写：%s" % args.json_out)


if __name__ == "__main__":
    main()
