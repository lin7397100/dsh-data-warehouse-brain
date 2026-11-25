#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_indicator_index.py — 从 indicator_registry.json 生成轻量级索引，供问数快车道 O(1) 命中，
避免每次问数把 4.68MB / 6155 指标全量注册表载入上下文（这正是 3 小时超时的根因）。

产出 knowledge/design/indicator/indicator_index.json：
  {
    "total": 6155,
    "by_code": { "<ZB_CODE>": {"name","level","domain","factory_div","materialized_sql_file","has_sql"} },
    "by_name": { "<zb_name 标准化>": "<ZB_CODE>" },
    "flat":    [ {"code","name","level","has_sql"} ... ]   # 供子串扫描
  }
"""
import os, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
TEAM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
REG = os.path.join(TEAM_ROOT, "knowledge", "design", "indicator", "indicator_registry.json")
OUT = os.path.join(TEAM_ROOT, "knowledge", "design", "indicator", "indicator_index.json")

_stop = set("的_之_与_及_and_生产_域_指标_值_量_t_月累计_年累计_日_周_本期_累计".split())

def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[\s\u3000]+", "", s)
    return s

# 与 lookup_indicator.strip_stop 对齐：查询侧会剥离厂部前缀与标点，
# 索引侧若不做同样归一化，含「三钢闽光能源-…」的名称就无法被子串命中。
_SQL_DIR = os.path.join(TEAM_ROOT, "knowledge", "design", "indicator", "materialized_sql")
_GUARD_PATH = os.path.join(TEAM_ROOT, "scripts", "materialized_sql_guard.py")
_GUARD_CACHE = {}


def _sql_blocked(code, mfile):
    """调用同包 guard 做加载断言；guard 缺失时保守判为拦截（不静默放行）。"""
    path = os.path.join(_SQL_DIR, os.path.basename(mfile))
    if not os.path.exists(path):
        return True
    if "mod" not in _GUARD_CACHE:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_sgdw_index_guard", _GUARD_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _GUARD_CACHE["mod"] = mod
    blocked, _reason = _GUARD_CACHE["mod"].is_blocked(path)
    return blocked


_PUNCT_RE = re.compile(r"[-_·、\s/\\（）()\[\]【】]+")
_FACTORY_TOKENS = ["三钢", "闽光", "公司", "钢厂"]

def main():
    with open(REG, encoding="utf-8") as f:
        reg = json.load(f)
    if isinstance(reg, dict):
        items = reg.get("indicators") or reg.get("items") or []
    else:
        items = reg

    by_code, by_name, flat = {}, {}, []
    for it in items:
        code = str(it.get("zb_code") or it.get("ZB_CODE") or "")
        if not code:
            continue
        name = it.get("zb_name") or it.get("ZB_NAME") or ""
        level = it.get("level") or it.get("LEVEL") or "unresolved"
        domain = it.get("domain") or it.get("DOMAIN") or ""
        fdiv = it.get("factory_div") or it.get("FACTORY_DIV") or ""
        mfile = it.get("materialized_sql_file") or ""
        has_sql = bool(mfile)
        # D4 / R-05 构建期强制：路径存在不等于 SQL 可用。
        # 「注释头 + 常量 0」的空壳必须标 has_sql=false，否则每次重建索引
        # 都会重新把伪零值注册成快车道资产。本脚本只改判定逻辑，不改现有数据。
        if has_sql and _sql_blocked(code, mfile):
            has_sql = False
            mfile = ""
        by_code[code] = {
            "name": name, "level": level, "domain": domain,
            "factory_div": fdiv, "materialized_sql_file": mfile, "has_sql": has_sql,
        }
        n = norm(name)
        if n:
            by_name[n] = code
            # 去掉常见后缀再存一份，提升子串命中
            short = re.sub(r"(月累计|年累计|日累计|周累计|本期|累计|实际|计划|-?\d+)$", "", n)
            # 单字别名会让 lookup 的 score() 中「name in query」+80 规则退化成误命中
            # （实测「日计划」→「日」抢走「压缩空气总产出」的第 1 名），故设长度下限。
            if short and short != n and len(short) >= 2:
                by_name.setdefault(short, code)
            # 去标点 + 去厂部前缀别名，对齐查询侧 strip_stop 口径后存一份，提升子串命中
            alias = _PUNCT_RE.sub("", n)
            for w in _FACTORY_TOKENS:
                alias = alias.replace(w, "")
            if len(alias) >= 2 and alias != n and alias != short:
                by_name.setdefault(alias, code)
        flat.append({"code": code, "name": name, "level": level, "has_sql": has_sql})

    out = {"total": len(by_code), "by_code": by_code, "by_name": by_name, "flat": flat}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT}")
    print(f"  total={len(by_code)} indexed_names={len(by_name)} with_sql={sum(1 for v in by_code.values() if v['has_sql'])}")

if __name__ == "__main__":
    main()
