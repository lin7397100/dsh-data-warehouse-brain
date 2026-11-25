#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lookup_indicator.py —— 物化直查快车道「离线匹配器」
====================================================

设计意图（性能关键）：
  indicator_index.json 约 2.18 MB（6155 条），indicator_registry.json 约 4.68 MB。
  二者都**绝不能**载入 LLM 上下文（自托管 Qwen3-32B 上限 32768 token，载入即 400 错误 → 重试 → 数小时卡死）。
  本脚本在 Python 侧完成匹配，只把「命中结果（KB 级以下）」回传给 LLM。

能力：
  1. 精确匹配：归一化名称 → by_name → zb_code。
  2. 模糊匹配：自然语言「圆棒产量」无精确键时，按 子串 / 词素 / SequenceMatcher 打分，
     只返回高分候选（默认 Top5），优先 has_sql=True 且与业务词强相关的记录。
  3. 返回结构化 JSON，含 materialized_sql_file 与 source 信息，供 sg-materialized-sql 物化直查。

用法：
  python lookup_indicator.py --query "圆棒产量"
  python lookup_indicator.py --query "圆棒产量" --top 3
  python lookup_indicator.py --query "圆棒产量" --json
"""
import argparse
import json
import os
import re
import sys
import importlib.util
from difflib import SequenceMatcher
from functools import lru_cache

# ---- 路径解析：本脚本位于 skills/sg-indicator-system/engine/ ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_INDEX_PATH = os.path.normpath(
    os.path.join(_HERE, "..", "..", "..", "knowledge", "design", "indicator", "indicator_index.json")
)


def _resolve_index():
    """定位 indicator_index.json：优先相对路径，失败则向上回溯查找（兼容不同 CWD）。"""
    if os.path.exists(_INDEX_PATH):
        return _INDEX_PATH
    cur = _HERE
    for _ in range(8):
        cur = os.path.dirname(cur)
        cand = os.path.join(cur, "knowledge", "design", "indicator", "indicator_index.json")
        if os.path.exists(cand):
            return cand
    return _INDEX_PATH

# ---- D4 / R-04 防护：运行期代码级强制，空壳物化 SQL 不得进入快车道候选 ----
# 索引里的 has_sql=true 只代表「文件名存在」，不代表正文是可执行 SELECT。
# 此处在候选返回前强制调用同包 scripts/materialized_sql_guard.py 做加载断言，
# 绕过 SKILL.md 的文字描述也不会把「注释头 + 常量 0」的伪零值当可用 SQL 交出去。
_PKG_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
_SQL_DIR = os.path.join(_PKG_ROOT, "knowledge", "design", "indicator", "materialized_sql")
_GUARD_PATH = os.path.join(_PKG_ROOT, "scripts", "materialized_sql_guard.py")


@lru_cache(maxsize=1)
def _guard():
    """动态加载同包 guard，不污染 sys.path；marketplace / cache 双副本均适用。"""
    spec = importlib.util.spec_from_file_location("_sgdw_materialized_sql_guard", _GUARD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=8192)
def blocked_reason(code, mfile):
    """返回拦截原因；空字符串表示可进快车道。结果按 (code, 文件) 缓存。"""
    if not mfile:
        return "NO_SQL_FILE"
    path = os.path.join(_SQL_DIR, os.path.basename(mfile))
    if not os.path.exists(path):
        return "SQL_FILE_MISSING"
    try:
        blocked, reason = _guard().is_blocked(path)
    except Exception as e:
        return "GUARD_UNAVAILABLE:%s" % type(e).__name__
    return reason if blocked else ""


def effective_has_sql(code, rec):
    """索引 has_sql 只是路径存在；必须再过 guard 才算真有可用 SQL。"""
    if not rec.get("has_sql"):
        return False
    return not blocked_reason(str(code), rec.get("materialized_sql_file") or "")


# 匹配时剥离的「非业务词」（时间/对比/语气/厂部前缀等），避免污染子串匹配。
_STOP = [
    # 时间 / 对比词（业务无关，必须与指标名剥离才能命中「圆棒产量」而非「圆棒」）
    "本月", "当月", "这个月", "这月", "今年", "本年", "上月", "去年同期", "去年",
    "同比", "环比", "同比变化", "变化", "增幅", "增长", "下降",
    # 语气 / 动词 / 连接词
    "及", "和", "与", "查询", "查一下", "查", "帮我", "多少", "数据", "统计",
    "一下", "的", "了", "请问", "我想", "看下", "看",
    # 厂部前缀（指标名常带「三钢闽光能源-」前缀，剥离后子串更易命中）
    "三钢", "闽光", "公司", "钢厂",
]
_CJK = re.compile(r"[一-鿿]")

try:
    from rapidfuzz import fuzz  # 可选加速
    _HAS_RAPID = True
except Exception:
    _HAS_RAPID = False


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def strip_stop(q: str) -> str:
    q = q
    for w in sorted(_STOP, key=len, reverse=True):
        q = q.replace(w, "")
    return q.strip()


def score(name_norm: str, q_norm: str) -> float:
    if not q_norm:
        return 0.0
    s = 0.0
    if q_norm in name_norm:
        s += 100 + len(q_norm)
    if name_norm in q_norm:
        s += 80
    if _HAS_RAPID:
        s += fuzz.partial_ratio(q_norm, name_norm) * 0.3
    else:
        s += SequenceMatcher(None, q_norm, name_norm).ratio() * 30
    # 强相关：双方都含核心业务词（如「圆棒」）
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="自然语言指标词，如 圆棒产量")
    ap.add_argument("--top", type=int, default=5, help="返回候选数")
    ap.add_argument("--json", action="store_true", help="仅输出 JSON")
    args = ap.parse_args()

    if not os.path.exists(_INDEX_PATH):
        print(json.dumps({"error": f"index not found: {_resolve_index()}"}, ensure_ascii=False))
        return 1

    idx = json.load(open(_resolve_index(), encoding="utf-8"))
    by_name = idx.get("by_name", {})
    by_code = idx.get("by_code", {})

    raw_q = args.query.strip()
    q_norm = norm(raw_q)
    q_core = norm(strip_stop(raw_q))

    # 1) 精确匹配
    exact_code = by_name.get(q_norm) or by_name.get(q_core)
    results = []
    if exact_code:
        rec = by_code.get(exact_code)
        if rec:
            results.append(_fmt(exact_code, rec, 999.0, "exact"))

    # 2) 模糊匹配（遍历 by_name，离线完成，不进 LLM 上下文）
    scored = []
    seen = {r["zb_code"] for r in results}
    for nm, code in by_name.items():
        if code in seen:
            continue
        sc = score(norm(nm), q_core if q_core else q_norm)
        rec = by_code.get(code)
        if not rec:
            continue
        # 优先有「通过 guard 的」物化 SQL（空壳不加分，R-04/R-05）
        if effective_has_sql(code, rec):
            sc += 15
        # 原子/派生优先于业务汇总（更贴近「指标」语义）
        lvl = rec.get("level", "")
        if lvl in ("atomic", "derived"):
            sc += 8
        if sc > 0:
            scored.append((sc, code, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    for sc, code, rec in scored[: args.top]:
        results.append(_fmt(code, rec, round(sc, 2), "fuzzy"))

    out = {
        "query": raw_q,
        "query_core": q_core,
        "total_index": idx.get("total"),
        "matched": len(results),
        "best": results[0] if results else None,
        "candidates": results,
        "fast_lane_blocked": [r["zb_code"] for r in results if r.get("blocked_reason")],
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False))
    return 0


def _fmt(code, rec, sc, mode):
    reason = ""
    if rec.get("has_sql"):
        reason = blocked_reason(str(code), rec.get("materialized_sql_file") or "")
    ready = bool(rec.get("has_sql")) and not reason
    return {
        "zb_code": code,
        "name": rec.get("name"),
        "level": rec.get("level"),
        "domain": rec.get("domain"),
        "factory_div": rec.get("factory_div"),
        "materialized_sql_file": rec.get("materialized_sql_file") if ready else None,
        "has_sql": ready,
        "fast_lane_ready": ready,
        "blocked_reason": reason or None,
        "score": sc,
        "match_mode": mode,
    }


if __name__ == "__main__":
    sys.exit(main())
