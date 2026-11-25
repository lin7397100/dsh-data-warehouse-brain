#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jev_query.py —— jev 结构化判定客户端（tev1:4b-32k · 零依赖 · 只用标准库）
================================================================================

jev 是什么：你自建服务器上的 Ollama 兼容端点 `POST /v1/systemone`，用 4.3B 的
`tev1:4b-32k`（capabilities: decision）对一个状态串 + 一组结构化问题做**判定**，
返回每一问的取值、概率分布与置信度。

它和专家团的关系：专家团（大模型）负责长链推理；jev 负责"判定"——
判型、消歧、紧急度、质量维度…这类**一问一答、要概率、要能弃权**的小决定，
放在 0.7–1.0 s 的本地小模型上，比派一次子会话快 2~3 个数量级，而且带 confidence
可以做**阈值弃权**——这是"不编造"的量化抓手。

实测语义（2026-11-18，本机 → 10.233.2.32:11434，5 次取样）：
  · type 仅三种：choice / score / noul（其他值 HTTP 400：questions.x: "type" must be one of …）
  · choice  → {choice, probabilities{label: p}, confidence}
  · score   → {score: 0..N-1 的期望值, legend{"0": 第一档…}, probabilities, confidence}
  · noul    → {noul} = **问句为真的概率**（实测：紧急 0.930 / 不紧急 0.008 / 立刻停线 0.986）
  · 延迟    → 单问 0.67–0.94 s；8 候选长名 1.7 s（首次冷启 7.5 s）；600 字长文 1.8 s
  · 精度    → 8 候选择一 0.9975；业务域 80%（20 条真值）；指标级别 atomic/derived **仅 40%**（禁用）

用法（CLI）：
  python tools/jev_query.py --state "客户消息：我被重复扣款了，赶紧退款！" --preset urgency
  python tools/jev_query.py --state "…" --preset emotion --text
  python tools/jev_query.py --state "…" --question '意图' --choices 退款,咨询,投诉
  python tools/jev_query.py --state "…" --questions @questions.json --json
  python tools/jev_query.py --preset urgency --dry-run        # 离线自测（不联网）

环境变量：
  JEV_URL   默认 http://10.233.2.32:11434/v1/systemone
  JEV_MODEL 默认 tev1:4b-32k

退出码：0 成功；2 参数错误；3 低于阈值（仅 --threshold 时）；4 不可达/传输失败；5 响应无法解析。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("JEV_URL") or "http://10.233.2.32:11434/v1/systemone"
DEFAULT_MODEL = os.environ.get("JEV_MODEL") or "tev1:4b-32k"

# ---------------------------------------------------------------- 预置问法（面向三块业务）
PRESETS = {
    # 问数·判型：与 route_intent.py 的五个车道一一对应，便于交叉验证
    "intent": {
        "q": "意图",
        "questions": {
            "意图": {
                "type": "choice",
                "instructions": "用户这句话想做什么？只选最贴近的一个。",
                "criteria": {
                    "单指标取数": "要某一个具体指标的数值（一个数，不要一段）",
                    "趋势查询": "要一段时间内的变化、走势、对比",
                    "归因诊断": "要原因、为什么、异常排查",
                    "综合报告": "要报告、看板、驾驶舱、汇报材料",
                    "开发变更": "要建表、改表、存储过程、ETL、建模",
                },
            }
        },
    },
    # 治数·工单优先级
    "urgency": {
        "q": "是否紧急",
        "questions": {"是否紧急": {"type": "noul", "instructions": "这条消息需要当天就处理吗？"}},
    },
    # 治数/舆情·情绪
    "emotion": {
        "q": "情绪等级",
        "questions": {
            "情绪等级": {
                "type": "score",
                "instructions": "发送者的情绪强度如何？",
                "criteria": ["平静", "轻微不满", "愤怒", "极度愤怒"],
            }
        },
    },
    # 治数·质量问题归类（**五维口径逐字对齐 `sg-quality-rule-gen` 的五维规则体系**：
    # 完整性/唯一性/有效性/一致性/及时性。注意源包用的是「有效性(值是否合法)」而非「准确性」）
    "quality": {
        "q": "质量问题类型",
        "questions": {
            "质量问题类型": {
                "type": "choice",
                "instructions": "这条数据问题最主要属于哪一维？（按 sg-quality-rule-gen 五维规则体系判定）",
                "criteria": {
                    "完整性": "该有的数据没有：关键字段空、分区/指标缺天",
                    "唯一性": "重复：主键重复、指标单表单日多值",
                    "有效性": "值不合法：超出合理区间/工艺边界、枚举非法、日期格式错",
                    "一致性": "对不上：跨表/父子表/双轮/同环比勾稽不平",
                    "及时性": "没按时到：抽取/加工/批处理延迟",
                },
            }
        },
    },
    # 治数·根因归类（**五类根因逐字对齐 `sg-root-cause-fullchain` 的「五类根因」**）
    "rootcause": {
        "q": "根因类型",
        "questions": {
            "根因类型": {
                "type": "choice",
                "instructions": "这个数据异常最可能的根因属于哪一类？（按 sg-root-cause-fullchain 五类根因判定）",
                "criteria": {
                    "口径歧义": "用户理解与指标定义不一致、近似指标混淆（源包标注为最常见）",
                    "数据延迟": "ODS 最后更新时间早于预期，该到的数没到",
                    "计算缺陷": "存储过程逻辑边界（跨月/跨班次/NULL/舍入）",
                    "源数据错误": "ODS 原始记录本身异常（业务系统录入错）",
                    "参数错误": "日期参数展开错、版本参数错用",
                },
            }
        },
    },
    # 沉淀·业务域预分类（实测 80%，只作建议）
    "domain": {
        "q": "业务域",
        "questions": {
            "业务域": {
                "type": "choice",
                "instructions": "这个指标属于哪个业务域？",
                "criteria": {
                    "生产管制": "产量、质量、设备、工序",
                    "日成本": "成本、消耗、费用",
                    "能源采购": "能源、采购、库存",
                },
            }
        },
    },
    # 沉淀·指标级别（**实测 40%，仅作反例留存，业务侧禁止使用**）
    "level": {
        "q": "指标级别",
        "questions": {
            "指标级别": {
                "type": "choice",
                "instructions": "这个指标是原子指标还是派生指标？",
                "criteria": {
                    "atomic": "单一字段直接取值，不可再拆",
                    "derived": "由计算、聚合或比率得到",
                },
            }
        },
    },
}

# 离线自测夹具（doctor / 无网络环境用；不参与任何真实判定）
DRY_FIXTURES = {
    "intent": {"意图": {"type": "choice", "choice": "单指标取数", "confidence": 0.98,
                       "probabilities": {"单指标取数": 0.98, "趋势查询": 0.01, "归因诊断": 0.005,
                                         "综合报告": 0.003, "开发变更": 0.002}}},
    "urgency": {"是否紧急": {"type": "noul", "noul": 0.93}},
    "emotion": {"情绪等级": {"type": "score", "score": 2.43, "confidence": 0.52,
                            "legend": {"0": "平静", "1": "轻微不满", "2": "愤怒", "3": "极度愤怒"},
                            "probabilities": {"0": 0.03, "1": 0.18, "2": 0.57, "3": 0.21}}},
    "quality": {"质量问题类型": {"type": "choice", "choice": "一致性", "confidence": 0.91,
                                "probabilities": {"一致性": 0.91, "完整性": 0.05, "唯一性": 0.02,
                                                  "有效性": 0.015, "及时性": 0.005}}},
    "rootcause": {"根因类型": {"type": "choice", "choice": "口径歧义", "confidence": 0.88,
                              "probabilities": {"口径歧义": 0.88, "数据延迟": 0.06,
                                                "计算缺陷": 0.04, "源数据错误": 0.015,
                                                "参数错误": 0.005}}},
    "domain": {"业务域": {"type": "choice", "choice": "生产管制", "confidence": 0.86,
                         "probabilities": {"生产管制": 0.86, "日成本": 0.09, "能源采购": 0.05}}},
    "level": {"指标级别": {"type": "choice", "choice": "atomic", "confidence": 0.53,
                          "probabilities": {"atomic": 0.53, "derived": 0.47}}},
}

# 兼容别名（旧文档/旧会话里可能写 --preset anomaly）
ALIASES = {"anomaly": "rootcause"}


class JevError(Exception):
    def __init__(self, code, msg):
        Exception.__init__(self, msg)
        self.code = code


def _post(url, model, state, questions, timeout=30.0, retries=2):
    payload = {"model": model, "state": state, "questions": questions}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except ValueError:
                raise JevError(5, "响应非 JSON：%s" % raw[:200])
            if "answers" not in data:
                raise JevError(5, "响应缺 answers 字段：%s" % raw[:200])
            data["_latency_ms"] = int((time.time() - t0) * 1000)
            return data
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            if e.code == 400 or e.code == 422:
                raise JevError(2, "请求被拒（HTTP %d）：%s" % (e.code, detail))
            last = "HTTP %d：%s" % (e.code, detail)
        except urllib.error.URLError as e:
            last = "连接失败：%s" % e.reason
        except JevError:
            raise
        except Exception as e:
            last = "异常：%s" % e
        if attempt < retries:
            time.sleep(0.6 * (attempt + 1))
    raise JevError(4, "jev 不可达：%s（url=%s）" % (last, url))


def ask(state, questions, url=None, model=None, timeout=30.0, retries=2, dry_run=False):
    """最底层：一问一答。返回 {"answers": {...}, "latency_ms": int, ...}"""
    if dry_run:
        preset = None
        for name, qs in PRESETS.items():
            if qs["questions"] == questions:
                preset = name
        answers = DRY_FIXTURES.get(preset)
        if answers is None:
            answers = {k: {"type": v.get("type"), "choice": "DRY", "confidence": 0.0}
                       for k, v in questions.items()}
        return {"model": model or DEFAULT_MODEL, "answers": answers, "_latency_ms": 0,
                "_dry_run": True}
    return _post(url or DEFAULT_URL, model or DEFAULT_MODEL, state, questions,
                 timeout=timeout, retries=retries)


def classify(state, labels, question="意图", instructions="", **kw):
    """choice 判定 → (label, confidence, probabilities)"""
    crit = dict(labels) if isinstance(labels, dict) else {x: x for x in labels}
    qs = {question: {"type": "choice", "criteria": crit}}
    if instructions:
        qs[question]["instructions"] = instructions
    r = ask(state, qs, **kw)
    a = (r.get("answers") or {}).get(question) or {}
    return a.get("choice"), float(a.get("confidence") or 0.0), a.get("probabilities") or {}, r


def yes_no(state, question="是否紧急？", key="是否紧急", **kw):
    """noul 判定 → P(是)"""
    r = ask(state, {key: {"type": "noul", "instructions": question}}, **kw)
    a = (r.get("answers") or {}).get(key) or {}
    return float(a.get("noul") or 0.0), r


def score(state, criteria, key="分数", question="", **kw):
    """score 判定 → 0..N-1 期望值 + legend"""
    r = ask(state, {key: {"type": "score", "criteria": list(criteria),
                          "instructions": question or "强度如何？"}}, **kw)
    a = (r.get("answers") or {}).get(key) or {}
    return float(a.get("score") or 0.0), a.get("legend") or {}, float(a.get("confidence") or 0.0), r


def preset_questions(preset):
    key = ALIASES.get(preset, preset)
    if key not in PRESETS:
        raise KeyError("未知 --preset：%s（可用：%s；别名：%s）"
                       % (preset, ", ".join(sorted(PRESETS)), ", ".join(sorted(ALIASES))))
    return PRESETS[key]["questions"]


def parse_questions(spec):
    """--questions 支持 '@文件路径' 或直接 JSON 字符串"""
    if spec.startswith("@"):
        with open(spec[1:], "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(spec)


def _fmt_text(result):
    lines = ["model : %s" % result.get("model", DEFAULT_MODEL),
             "latency: %d ms" % result.get("_latency_ms", 0)]
    for k, a in (result.get("answers") or {}).items():
        t = a.get("type")
        if t == "choice":
            lines.append("  %s = %s（conf %.3f）" % (k, a.get("choice"), a.get("confidence") or 0.0))
            lines.append("     概率：" + ", ".join(
                "%s %.3f" % (kk, vv) for kk, vv in (a.get("probabilities") or {}).items()))
        elif t == "noul":
            lines.append("  %s = %.4f（P(是)）" % (k, a.get("noul") or 0.0))
        elif t == "score":
            lines.append("  %s = %.3f（conf %.3f）档位：%s" % (
                k, a.get("score") or 0.0, a.get("confidence") or 0.0,
                json.dumps(a.get("legend") or {}, ensure_ascii=False)))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="jev 结构化判定客户端（tev1:4b-32k）")
    ap.add_argument("--state", default="", help="待判定的文本（客户消息/指标名/工单内容）")
    ap.add_argument("--preset", choices=sorted(PRESETS) + sorted(ALIASES), help="预置问法")
    ap.add_argument("--question", default="意图", help="自定义 choice 的问项名")
    ap.add_argument("--choices", default="", help="自定义 choice 标签：逗号分隔，或 '标签=说明,标签=说明'")
    ap.add_argument("--questions", default="", help="完整 questions JSON，或 @文件")
    ap.add_argument("--url", default="", help="覆盖 JEV_URL")
    ap.add_argument("--model", default="", help="覆盖 JEV_MODEL")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=None,
                    help="choice 置信度下限；低于则 exit=3")
    ap.add_argument("--json", action="store_true", help="输出 JSON（默认）")
    ap.add_argument("--text", action="store_true", help="输出人读文本")
    ap.add_argument("--dry-run", action="store_true", help="离线夹具自测，不联网")
    args = ap.parse_args()

    if not args.state and not args.dry_run:
        print("--state 不能为空", file=sys.stderr)
        return 2

    if args.questions:
        try:
            qs = parse_questions(args.questions)
        except Exception as e:
            print("questions 解析失败：%s" % e, file=sys.stderr)
            return 2
    elif args.preset:
        qs = preset_questions(args.preset)
    elif args.choices:
        labels = {}
        for part in args.choices.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k.strip()] = v.strip()
            else:
                labels[part] = part
        qs = {args.question: {"type": "choice", "criteria": labels}}
    else:
        print("需要 --preset / --choices / --questions 之一", file=sys.stderr)
        return 2

    try:
        result = ask(args.state, qs, url=args.url or None, model=args.model or None,
                     timeout=args.timeout, retries=args.retries, dry_run=args.dry_run)
    except JevError as e:
        print(json.dumps({"ok": False, "code": e.code, "error": str(e)}, ensure_ascii=False))
        return e.code

    ok = True
    if args.threshold is not None:
        for _, a in (result.get("answers") or {}).items():
            if a.get("type") == "choice" and float(a.get("confidence") or 0.0) < args.threshold:
                ok = False

    if args.text:
        print(_fmt_text(result))
    else:
        print(json.dumps({"ok": ok, "code": 0, "result": result}, ensure_ascii=False, indent=2))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
