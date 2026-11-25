#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_gz01.py — 将真实资产《T_ADS_DIM_GZ01》(6205 指标配置) 与 DDL/存储过程目录
固化为「完整指标体系 + 逐层物化 SQL + 数据血缘」。

输入（包内固化副本，优先 DB2_ASSETS_HOME 覆盖）：
  - <包>/knowledge/design/indicator/source/csv/T_ADS_DIM_GZ01.csv      指标配置表（SQL1=数值计算逻辑, SQL2=字符格式逻辑）
  - <包>/knowledge/design/indicator/source/ddl/                   表结构（96 张，命名含层：SMBB_M_O=ODS, SMBB_M_S=DWD/DWS, SMBB_M_A=ADS）
  - <包>/knowledge/design/indicator/source/procs  业务存储过程（P_DWD_* 构建 DWD/DWS）

输出（团队知识引擎层）：
  - knowledge/design/indicator/indicator_registry.json   全量指标注册表（机读，DSL 编译器直查）
  - knowledge/design/indicator/materialized_sql/<ZB_CODE>.sql  每个指标的物化 SQL
  - knowledge/design/indicator/materialized_sql/all_indicators.sql  合并版
  - knowledge/design/indicator/indicator_registry_report.md  人类可读摘要

设计要点：
  - 每个指标的 SQL1 即为「数值计算逻辑」，直接固化为可执行的物化语句（保留 $TD$/$D4$ 等时间占位符）。
  - 智能问数时 DSL 编译器命中 ZB_CODE 后「直接调用」该物化 SQL（参数替换后执行），免实时编译 → 秒级响应。
  - 血缘：从 SQL1 抽取源表，按命名约定判定层（ODS/DWD/DWS/ADS）；未解指标（SQL1 为空/“无”）标 unresolved，交由即席构建技能补全。
"""
import os, re, csv, json, sys, datetime

# 资产根：优先环境变量 DB2_ASSETS_HOME（指向含 csv/ddl/procs 的资产根），
# 否则回退到本包内置固化副本 knowledge/design/indicator/source（分享/导出后他人可用）。
def find_team_root(start):
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, ".codebuddy-plugin")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
        cur = parent
TEAM_ROOT = find_team_root(os.path.abspath(__file__))
OUT_ROOT = os.path.join(TEAM_ROOT, "knowledge", "design", "indicator")
ROOT = os.environ.get("DB2_ASSETS_HOME", os.path.join(TEAM_ROOT, "knowledge", "design", "indicator", "source"))
CSV_PATH = os.path.join(ROOT, "csv", "T_ADS_DIM_GZ01.csv")
DDL_DIR = os.path.join(ROOT, "ddl")

# ---- 工具函数 ----
TOKEN_RE = re.compile(r"\$[A-Za-z0-9_]+\$")
TABLE_RE = re.compile(r"(?:from|join)\s+([A-Za-z0-9_\.]+)", re.IGNORECASE)
SCHEMA_TABLE_RE = re.compile(r"(SMBB_M_[AOS]_\w+)(?:\.(T_[A-Za-z0-9_]+))?")

def table_layer(name: str):
    """按命名约定判定表所在层：O=ODS, S=DWD/DWS, A=ADS。"""
    n = name.upper()
    if ".T_" in n or n.startswith("T_"):
        # 带 T_ 的具体表：再看 schema
        pass
    if "SMBB_M_O_" in n:
        return "ODS"
    if "SMBB_M_A_" in n:
        return "ADS"
    if "SMBB_M_S_" in n:
        return "DWS"  # 含 DWD/DWS 汇总层
    if n.startswith("T_DWD"):
        return "DWD"
    if n.startswith("T_DWS"):
        return "DWS"
    if n.startswith("T_ADS") or "DIM" in n:
        return "ADS"
    return "UNKNOWN"

def domain_of(factory_div: str, sql1: str):
    f = (factory_div or "")
    s = (sql1 or "").upper()
    if ("成本" in f) or ("CB" in s) or ("SMBB_M_S_CB00" in s) or ("SMBB_M_A_CB" in s):
        return "日成本"
    if ("能源" in f) or ("采购" in f) or ("原采" in f):
        return "能源/采购"
    return "生产管制"

def classify_level(sql1: str):
    """原子=直接取预计算值(无聚合)；派生=含聚合/分组；unresolved=空或'无'。"""
    s = (sql1 or "").strip().strip("'").strip()
    if s == "" or s == "无" or s.upper() == "NULL":
        return "unresolved", "SQL1 为空或未定义，需即席构建"
    agg = re.search(r"\b(SUM|AVG|COUNT|MAX|MIN|GROUP\s+BY)\b", sql1, re.IGNORECASE)
    fetch = re.search(r"ZB_VALUE", sql1, re.IGNORECASE)
    if agg:
        return "derived", ""
    if fetch:
        return "atomic", ""
    return "derived", ""

def extract_tables(sql1: str):
    tables = []
    for m in TABLE_RE.finditer(sql1):
        t = m.group(1)
        # 规范化：取 schema.table
        mm = SCHEMA_TABLE_RE.search(t)
        if mm:
            tables.append(mm.group(1) + (("." + mm.group(2)) if mm.group(2) else ""))
        else:
            tables.append(t)
    # 去重保序
    seen, out = set(), []
    for t in tables:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

def main():
    os.makedirs(os.path.join(OUT_ROOT, "materialized_sql"), exist_ok=True)
    # 加载 DDL 表清单（用于血缘存在性校验）
    ddl_tables = set()
    if os.path.isdir(DDL_DIR):
        for fn in os.listdir(DDL_DIR):
            base = fn.upper()
            ddl_tables.add(base.split(".")[0])

    rows = []
    with open(CSV_PATH, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    print(f"[import] read {len(rows)} KPI rows from T_ADS_DIM_GZ01")

    registry = []
    level_counter = {"atomic":0, "derived":0, "unresolved":0}
    domain_counter = {}
    sql_files = 0
    all_sql_parts = []
    for r in rows:
        zb_code = (r.get("ZB_CODE") or "").strip()
        zb_name = (r.get("ZB_NAME") or "").strip()
        factory = (r.get("FACTORY_DIV") or "").strip()
        zb_type = (r.get("ZB_TYPE") or "").strip()
        unit = (r.get("UNIT") or "").strip()
        sql1 = (r.get("SQL1") or "").strip()
        sql2 = (r.get("SQL2") or "").strip()
        if not zb_code:
            continue
        domain = domain_of(factory, sql1)
        level, note = classify_level(sql1)
        level_counter[level] = level_counter.get(level, 0) + 1
        domain_counter[domain] = domain_counter.get(domain, 0) + 1
        tables = extract_tables(sql1)
        layers = {}
        for t in tables:
            layers[t] = table_layer(t)
        params = sorted(set(TOKEN_RE.findall(sql1))) if sql1 else []
        entry = {
            "zb_code": zb_code,
            "zb_name": zb_name,
            "factory_div": factory,
            "zb_type": zb_type,
            "unit": unit,
            "domain": domain,
            "level": level,
            "status_note": note,
            "sql1": sql1,
            "sql2": sql2,
            "params": params,
            "source_tables": tables,
            "source_layers": layers,
            "lineage_chain": build_lineage(tables, layers),
            "materialized_sql_file": None,
        }
        # 物化 SQL 文件（仅对可计算指标）
        if level in ("atomic", "derived") and sql1:
            rel = f"materialized_sql/{zb_code}.sql"
            fpath = os.path.join(OUT_ROOT, rel)
            header = (
                f"-- ZB_CODE: {zb_code}\n"
                f"-- ZB_NAME: {zb_name}\n"
                f"-- DOMAIN: {domain}\n"
                f"-- LEVEL: {level}\n"
                f"-- FACTORY: {factory}\n"
                f"-- UNIT: {unit}\n"
                f"-- SOURCE_TABLES: {', '.join(tables) if tables else '(none)'}\n"
                f"-- PARAMS: {', '.join(params) if params else '(none)'}\n"
                f"-- ORIGIN: T_ADS_DIM_GZ01.SQL1 (数值计算逻辑)\n"
                f"-- 执行时由 DSL 编译器替换 $TD$/$D4$ 等时间占位符后直投 DB2 MCP，免实时编译。\n"
            )
            with open(fpath, "w", encoding="utf-8") as sf:
                sf.write(header + sql1 + "\n")
            entry["materialized_sql_file"] = rel
            sql_files += 1
            all_sql_parts.append(f"-- ===== {zb_code} {zb_name} =====\n{sql1};\n")
        registry.append(entry)

    # 写注册表
    reg_path = os.path.join(OUT_ROOT, "indicator_registry.json")
    reg_doc = {
        "meta": {
            "spec": "T_ADS_DIM_GZ01 全量指标 + 物化 SQL 注册表",
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "source_csv": CSV_PATH,
            "total": len(registry),
            "level_counter": level_counter,
            "domain_counter": domain_counter,
            "materialized_sql_files": sql_files,
            "ref_anchor": "ZB_CODE(T_ADS_DIM_GZ01)",
            "invocation": "DSL 编译器按 zb_code 查本表 → 取 materialized_sql_file → 替换时间参数 → DB2 MCP 直执行",
        },
        "indicators": registry,
    }
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(reg_doc, f, ensure_ascii=False, indent=1)

    # 合并版
    all_path = os.path.join(OUT_ROOT, "materialized_sql", "all_indicators.sql")
    with open(all_path, "w", encoding="utf-8") as f:
        f.write(f"-- 全量物化指标 SQL（共 {sql_files} 条可计算指标）\n")
        f.write(f"-- 生成时间：{reg_doc['meta']['generated_at']}\n")
        f.write(f"-- 执行时替换 $TD$/$D4$/$D30$/$YM$ 等时间占位符。\n\n")
        f.write("\n".join(all_sql_parts))

    # 摘要报告
    rep_path = os.path.join(OUT_ROOT, "indicator_registry_report.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("# 指标注册表摘要（T_ADS_DIM_GZ01 全量固化）\n\n")
        f.write(f"- 生成时间：{reg_doc['meta']['generated_at']}\n")
        f.write(f"- 指标总数：**{len(registry)}**\n")
        f.write(f"- 层级分布：{level_counter}\n")
        f.write(f"- 物化 SQL 文件数：**{sql_files}**（位于 `materialized_sql/`）\n")
        f.write(f"- 域分布：{domain_counter}\n\n")
        f.write("## 血缘覆盖（源表层级）\n")
        layer_cnt = {}
        for e in registry:
            for t, l in e["source_layers"].items():
                layer_cnt[l] = layer_cnt.get(l, 0) + 1
        f.write(f"- {layer_cnt}\n\n")
        f.write("## 未解指标（unresolved，需即席构建补齐）\n")
        unres = [e for e in registry if e["level"] == "unresolved"]
        f.write(f"- 共 {len(unres)} 条；示例前 10：\n")
        for e in unres[:10]:
            f.write(f"  - `{e['zb_code']}` {e['zb_name']}（{e['factory_div']}）\n")
        f.write("\n## 调用方式\n")
        f.write("智能问数命中 `zb_code` 时，DSL 编译器直接读取 `materialized_sql/<zb_code>.sql`，"
                "替换 `$TD$` 等时间参数后投 DB2 MCP 执行，免实时编译，秒级（≤5 分钟）响应。\n")

    print(f"[import] done. total={len(registry)} materialized_sql_files={sql_files}")
    print(f"[import] level={level_counter}")
    print(f"[import] domain={domain_counter}")
    print(f"[import] wrote: {reg_path}")
    print(f"[import] wrote: {all_path}")
    print(f"[import] wrote: {rep_path}")

def build_lineage(tables, layers):
    """构造可读血缘链：ODS→DWD→DWS→ADS→IND（按实际抽取到的源表层归集）。"""
    chain = []
    order = ["ODS", "DWD", "DWS", "ADS", "UNKNOWN"]
    by_layer = {}
    for t, l in layers.items():
        by_layer.setdefault(l, []).append(t)
    for l in order:
        if l in by_layer:
            chain.append({"stage": l, "tables": by_layer[l]})
    chain.append({"stage": "IND", "note": "由 SQL1 计算"})
    return chain

if __name__ == "__main__":
    main()
