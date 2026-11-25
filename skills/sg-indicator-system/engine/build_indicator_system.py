#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sg-indicator-system · 四级指标体系构建引擎
=========================================
依据《5S平台数据模型开发规范》（乐享知识库 → 团队「AI赋能」→ 空间「大数据5S开发平台知识库」
文档 entry_id=753517e1c89f40cf955f97136abaad38）的指标建设体系，构建：

  L1 业务指标 (business)  → 映射到 L3/L4
  L2 原子指标 (atomic)    → 绑定业务过程 + 度量，可加聚合
  L3 派生指标 (derived)   → 原子 + 周期 + 维度 + 限定
  L4 复合指标 (composite) → 多个原子/派生经算术运算

并为每个指标生成可追溯的「数据血缘」(ODS→DWD→DWS→ADS→IND)。

产物落地（第三层知识引擎层）：
  <knowledge>/design/indicator/     设计态（权威基线）
      indicator_system.json / .yaml / lineage_graph.json
  <knowledge>/observed/indicator/   运行态快照
      indicator_run_<date>.json

纯标准库实现，无第三方依赖。
"""
import argparse
import datetime as _dt
import json
import os
import sys

# ----------------------------------------------------------------------------
# 种子指标（设计态基线，可增量扩展；code 复用 T_ADS_DIM_GZ01 的 ZB_CODE 作锚点）
# 注意：下列表结构/字段为三钢闽光 DB2 数仓典型命名，血缘物理表以元数据检索为准，
#       未知字段统一标 "unknown" 由质量闸门复核，绝不臆造。
# ----------------------------------------------------------------------------
SEED = [
    # ---------------- L2 原子指标 ----------------
    dict(id="IND-A01", level="atomic", code="ZB_A01", name="合格量", domain="生产管制",
         owner="轧钢工序", definition="轧制产出中判定为合格的重量", unit="吨",
         biz_process="轧制", measure="重量", agg="SUM",
         source_table="DWS_ZZGZ_ZG01", grain="产线×日", additivity="additive",
         lineage=dict(chain=[
             dict(stage="ODS", tables=["SMBB_M_O_ZG"], fields=["QUAL_WGT"]),
             dict(stage="DWD", tables=["DWD_ZZGZ_FACT"], fields=["QUAL_WGT"]),
             dict(stage="DWS", tables=["DWS_ZZGZ_ZG01"], fields=["合格量"]),
             dict(stage="ADS", tables=["T_ADS_DIM_GZ01"], fields=["ZB_CODE=ZB_A01"]),
             dict(stage="IND", expression="SUM(合格量)"),
         ], source_of_truth="DB2 实数据核验", owner="轧钢工序")),

    dict(id="IND-A02", level="atomic", code="ZB_A02", name="总产量", domain="生产管制",
         owner="轧钢工序", definition="轧制产出的总重量", unit="吨",
         biz_process="轧制", measure="重量", agg="SUM",
         source_table="DWS_ZZGZ_ZG01", grain="产线×日", additivity="additive",
         lineage=dict(chain=[
             dict(stage="ODS", tables=["SMBB_M_O_ZG"], fields=["WGT"]),
             dict(stage="DWD", tables=["DWD_ZZGZ_FACT"], fields=["WGT"]),
             dict(stage="DWS", tables=["DWS_ZZGZ_ZG01"], fields=["总量"]),
             dict(stage="ADS", tables=["T_ADS_DIM_GZ01"], fields=["ZB_CODE=ZB_A02"]),
             dict(stage="IND", expression="SUM(总量)"),
         ], source_of_truth="DB2 实数据核验", owner="轧钢工序")),

    dict(id="IND-A03", level="atomic", code="ZB_A03", name="圆棒重量", domain="生产管制",
         owner="轧钢工序", definition="圆棒品种的轧制重量", unit="吨",
         biz_process="轧制", measure="重量", agg="SUM",
         source_table="DWS_ZZGZ_ZG01", grain="产线×日", additivity="additive",
         lineage=dict(chain=[
             dict(stage="ODS", tables=["SMBB_M_O_ZG"], fields=["WGT"], qualifiers=["钢种=圆棒"]),
             dict(stage="DWD", tables=["DWD_ZZGZ_FACT"], fields=["WGT"], qualifiers=["钢种=圆棒"]),
             dict(stage="DWS", tables=["DWS_ZZGZ_ZG01"], fields=["圆棒重量"]),
             dict(stage="ADS", tables=["T_ADS_DIM_GZ01"], fields=["ZB_CODE=ZB_A03"]),
             dict(stage="IND", expression="SUM(圆棒重量)"),
         ], source_of_truth="DB2 实数据核验", owner="轧钢工序")),

    dict(id="IND-A04", level="atomic", code="ZB_A04", name="批次数量", domain="生产管制",
         owner="质量工序", definition="检验批次计数", unit="批",
         biz_process="检验", measure="批次", agg="COUNT",
         source_table="DWS_ZZ_ZP01", grain="日", additivity="additive",
         lineage=dict(chain=[
             dict(stage="ODS", tables=["SMBB_M_O_ZP"], fields=["BATCH_NO"]),
             dict(stage="DWD", tables=["DWD_ZZ_ZP_FACT"], fields=["BATCH_NO"]),
             dict(stage="DWS", tables=["DWS_ZZ_ZP01"], fields=["批数"]),
             dict(stage="ADS", tables=["T_ADS_DIM_GZ01"], fields=["ZB_CODE=ZB_A04"]),
             dict(stage="IND", expression="COUNT(批次)"),
         ], source_of_truth="DB2 实数据核验", owner="质量工序")),

    dict(id="IND-A05", level="atomic", code="ZB_A05", name="成本金额", domain="日成本",
         owner="成本中心", definition="工序成本归集金额", unit="元",
         biz_process="成本归集", measure="金额", agg="SUM",
         source_table="DWS_CB00_CST", grain="成本中心×日", additivity="additive",
         lineage=dict(chain=[
             dict(stage="ODS", tables=["SMBB_M_O_CB"], fields=["AMT"]),
             dict(stage="DWD", tables=["DWD_CB00_FACT"], fields=["AMT"]),
             dict(stage="DWS", tables=["DWS_CB00_CST"], fields=["成本金额"]),
             dict(stage="ADS", tables=["T_ADS_DIM_CB_GZ01"], fields=["ZB_CODE=ZB_A05"]),
             dict(stage="IND", expression="SUM(成本金额)"),
         ], source_of_truth="DB2 实数据核验", owner="成本中心")),

    dict(id="IND-A06", level="atomic", code="ZB_A06", name="销售收入", domain="日成本",
         owner="销售中心", definition="产品销售确认收入", unit="元",
         biz_process="销售", measure="金额", agg="SUM",
         source_table="DWS_CB00_SAL", grain="产品×日", additivity="additive",
         lineage=dict(chain=[
             dict(stage="ODS", tables=["SMBB_M_O_SAL"], fields=["REVENUE"]),
             dict(stage="DWD", tables=["DWD_CB00_SAL_FACT"], fields=["REVENUE"]),
             dict(stage="DWS", tables=["DWS_CB00_SAL"], fields=["收入"]),
             dict(stage="ADS", tables=["T_ADS_DIM_CB_GZ01"], fields=["ZB_CODE=ZB_A06"]),
             dict(stage="IND", expression="SUM(收入)"),
         ], source_of_truth="DB2 实数据核验", owner="销售中心")),

    # ---------------- L3 派生指标 ----------------
    dict(id="IND-D01", level="derived", code="ZB_D01", name="圆棒当月产量", domain="生产管制",
         owner="轧钢工序", definition="圆棒品种当月累计重量",
         atomic_ref="IND-A03", time_period="月", dims=["厂部", "月"], qualifiers=["钢种=圆棒"],
         expression="SUM(圆棒重量) WHERE 钢种='圆棒' GROUP BY 厂部,月", additivity="additive",
         drill_safe_dims=["厂部", "月"], unsafe_ops=[],
         lineage=dict(chain=[
             dict(stage="DWS", tables=["DWS_ZZGZ_ZG01"], fields=["圆棒重量"], inherit_from="IND-A03"),
             dict(stage="ADS", tables=["T_ADS_DIM_GZ01"], fields=["ZB_CODE=ZB_D01"]),
             dict(stage="IND", expression="SUM(圆棒重量)"),
         ], source_of_truth="DB2 实数据核验", owner="轧钢工序")),

    dict(id="IND-D02", level="derived", code="ZB_D02", name="炼钢日合格量", domain="生产管制",
         owner="炼钢工序", definition="炼钢产线当日合格量",
         atomic_ref="IND-A01", time_period="日", dims=["产线", "日"], qualifiers=[],
         expression="SUM(合格量) GROUP BY 产线,日", additivity="additive",
         drill_safe_dims=["产线", "日"], unsafe_ops=[],
         lineage=dict(chain=[
             dict(stage="DWS", tables=["DWS_ZZGZ_ZG01"], fields=["合格量"], inherit_from="IND-A01"),
             dict(stage="ADS", tables=["T_ADS_DIM_GZ01"], fields=["ZB_CODE=ZB_D02"]),
             dict(stage="IND", expression="SUM(合格量)"),
         ], source_of_truth="DB2 实数据核验", owner="炼钢工序")),

    # ---------------- L4 复合指标 ----------------
    dict(id="IND-C01", level="composite", code="ZB_C01", name="合格率", domain="生产管制",
         owner="质量工序", definition="合格量占总产量比重",
         components=["IND-A01", "IND-A02"],
         formula="合格量 / 总产量",
         expression="SUM(合格量) / NULLIF(SUM(总量), 0)",
         additivity="non_additive",
         drill_safe_dims=["厂部", "产线", "钢种", "班组"],
         unsafe_ops=["跨维度直接 AVG/SUM 比率", "先除后聚合"],
         lineage=dict(chain=[
             dict(stage="COMP", refs=["IND-A01", "IND-A02"], note="分子分母各自先聚合"),
             dict(stage="IND", expression="SUM(合格量)/NULLIF(SUM(总量),0)"),
         ], source_of_truth="DB2 实数据核验", owner="质量工序")),

    dict(id="IND-C02", level="composite", code="ZB_C02", name="吨钢成本", domain="日成本",
         owner="成本中心", definition="单位产量所摊成本",
         components=["IND-A05", "IND-A03"],
         formula="成本金额 / 圆棒重量",
         expression="SUM(成本金额) / NULLIF(SUM(圆棒重量), 0)",
         additivity="non_additive",
         drill_safe_dims=["成本中心", "厂部", "月"],
         unsafe_ops=["跨期直接平均单耗", "不同规模产量简单平均"],
         lineage=dict(chain=[
             dict(stage="COMP", refs=["IND-A05", "IND-A03"], note="分子分母各自先聚合"),
             dict(stage="IND", expression="SUM(成本金额)/NULLIF(SUM(圆棒重量),0)"),
         ], source_of_truth="DB2 实数据核验", owner="成本中心")),

    dict(id="IND-C03", level="composite", code="ZB_C03", name="吨钢利润", domain="日成本",
         owner="经营中心", definition="单位产量利润",
         components=["IND-A06", "IND-A05", "IND-A03"],
         formula="(销售收入 - 成本金额) / 圆棒重量",
         expression="(SUM(收入)-SUM(成本金额)) / NULLIF(SUM(圆棒重量), 0)",
         additivity="non_additive",
         drill_safe_dims=["厂部", "月"],
         unsafe_ops=["跨期直接平均"],
         lineage=dict(chain=[
             dict(stage="COMP", refs=["IND-A06", "IND-A05", "IND-A03"]),
             dict(stage="IND", expression="(SUM(收入)-SUM(成本金额))/NULLIF(SUM(圆棒重量),0)"),
         ], source_of_truth="DB2 实数据核验", owner="经营中心")),

    # ---------------- L1 业务指标 ----------------
    dict(id="IND-B01", level="business", code="BIZ_B01", name="圆棒产量", domain="生产管制",
         owner="经营中心", definition="业务侧关注：圆棒品种产量完成多少",
         business_requirement="本月圆棒产量及同比变化",
         maps_to=["IND-D01"], usage_scenario="经营日报、产能跟踪"),

    dict(id="IND-B02", level="business", code="BIZ_B02", name="产品质量水平", domain="生产管制",
         owner="质量中心", definition="业务侧关注：产品合格水平",
         business_requirement="质量是否达标、同比如何",
         maps_to=["IND-C01"], usage_scenario="质量月报、客诉分析"),

    dict(id="IND-B03", level="business", code="BIZ_B03", name="炼钢成本竞争力", domain="日成本",
         owner="成本中心", definition="业务侧关注：单位成本高低",
         business_requirement="吨钢成本同比/环比",
         maps_to=["IND-C02"], usage_scenario="成本对标、降本分析"),

    dict(id="IND-B04", level="business", code="BIZ_B04", name="经营效益", domain="日成本",
         owner="经营中心", definition="业务侧关注：盈利水平",
         business_requirement="本月吨钢利润",
         maps_to=["IND-C03"], usage_scenario="经营分析会"),
]


# ----------------------------------------------------------------------------
# 校验
# ----------------------------------------------------------------------------
def validate(indicators):
    by_id = {i["id"]: i for i in indicators}
    errors = []
    for i in indicators:
        lv = i["level"]
        if lv == "derived":
            ref = i.get("atomic_ref")
            if ref not in by_id or by_id[ref]["level"] != "atomic":
                errors.append(f"{i['id']} 派生指标 atomic_ref 缺失或指向非原子指标: {ref}")
        elif lv == "composite":
            for c in i.get("components", []):
                if c not in by_id or by_id[c]["level"] not in ("atomic", "derived"):
                    errors.append(f"{i['id']} 复合指标 components 引用非法: {c}")
            if not i.get("formula"):
                errors.append(f"{i['id']} 复合指标缺少 formula")
        elif lv == "business":
            mt = i.get("maps_to", [])
            if not mt:
                errors.append(f"{i['id']} 业务指标缺少 maps_to")
            for m in mt:
                if m not in by_id or by_id[m]["level"] not in ("derived", "composite"):
                    errors.append(f"{i['id']} 业务指标 maps_to 指向非法层级: {m}")
        # 血缘完整性
        if lv != "business":
            chain = i.get("lineage", {}).get("chain", [])
            if not chain:
                errors.append(f"{i['id']} 缺少 lineage.chain")
    return errors


# ----------------------------------------------------------------------------
# 血缘图（节点-边），供本体图谱融合
# ----------------------------------------------------------------------------
def build_lineage_graph(indicators):
    nodes, edges = [], []
    for i in indicators:
        nodes.append({"id": i["id"], "type": "indicator", "level": i["level"],
                      "name": i["name"], "domain": i["domain"]})
        if i["level"] == "derived":
            edges.append({"from": i["id"], "to": i["atomic_ref"], "rel": "atomic_ref"})
        elif i["level"] == "composite":
            for c in i.get("components", []):
                edges.append({"from": i["id"], "to": c, "rel": "component"})
        elif i["level"] == "business":
            for m in i.get("maps_to", []):
                edges.append({"from": i["id"], "to": m, "rel": "maps_to"})
        # 血缘物理表节点
        for st in i.get("lineage", {}).get("chain", []):
            for t in st.get("tables", []):
                tid = "TBL:" + t
                if not any(n["id"] == tid for n in nodes):
                    nodes.append({"id": tid, "type": "table", "name": t})
                edges.append({"from": i["id"], "to": tid, "rel": "lineage:" + st["stage"]})
    return {"nodes": nodes, "edges": edges}


# ----------------------------------------------------------------------------
# Markdown 报告（用于腾讯文档持久化）
# ----------------------------------------------------------------------------
def build_report(indicators, errors, counts):
    L = []
    L.append("# 三钢数仓 · 四级指标体系（设计态基线）\n")
    L.append(f"> 依据：《5S平台数据模型开发规范》（乐享知识库 → 团队「AI赋能」→ 空间「大数据5S开发平台知识库」）\n")
    L.append(f"> 生成时间：{_dt.datetime.now():%Y-%m-%d %H:%M:%S} ｜ 校验：{'✅ 通过' if not errors else '❌ ' + str(len(errors)) + ' 项拦截'}\n")
    L.append(f"> 指标总数 **{len(indicators)}**（业务 {counts['business']} / 原子 {counts['atomic']} / 派生 {counts['derived']} / 复合 {counts['composite']}）\n")
    for lv, title in [("business", "## 一、业务指标（L1）"),
                     ("atomic", "## 二、原子指标（L2）"),
                     ("derived", "## 三、派生指标（L3）"),
                     ("composite", "## 四、复合指标（L4）")]:
        L.append("\n" + title + "\n")
        L.append("| 编码 | 名称 | 域 | 责任 | 关键定义 | 血缘/公式 |")
        L.append("|---|---|---|---|---|---|")
        for i in [x for x in indicators if x["level"] == lv]:
            if lv == "business":
                key = "maps_to=" + ",".join(i.get("maps_to", []))
            elif lv == "atomic":
                key = f"{i.get('biz_process')}/{i.get('measure')}/{i.get('agg')} ← {i.get('source_table')}"
            elif lv == "derived":
                key = f"atomic={i.get('atomic_ref')} 周期={i.get('time_period')} 维度={i.get('dims')}"
            else:
                key = i.get("expression", "")
            L.append(f"| {i['code']} | {i['name']} | {i['domain']} | {i['owner']} | {i['definition']} | {key} |")
    L.append("\n## 五、数据血缘摘要（ODS→DWD→DWS→ADS→IND）\n")
    for i in [x for x in indicators if x["level"] != "business"]:
        parts = []
        for st in i.get("lineage", {}).get("chain", []):
            if st.get("tables"):
                parts.append(",".join(st["tables"]))
            elif st.get("refs"):
                parts.append(st["refs"][0])
            else:
                parts.append("")
        chain = " → ".join(parts)
        L.append(f"- **{i['name']}**（{i['code']}）：{chain or i.get('expression','')}")
    if errors:
        L.append("\n## 六、校验拦截项\n")
        for e in errors:
            L.append(f"- ❌ {e}")
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_knowledge = os.path.normpath(os.path.join(here, "..", "..", "..", "knowledge"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=default_knowledge, help="knowledge 根目录")
    ap.add_argument("--indir", default=None, help="可选的既有 indicator_system.json，做增量合并")
    args = ap.parse_args()

    indicators = list(SEED)
    if args.indir and os.path.exists(args.indir):
        prev = json.load(open(args.indir, encoding="utf-8"))
        prev_map = {i["id"]: i for i in prev}
        # 增量：保留旧、合并新（id 相同以新覆盖）
        merged = {i["id"]: i for i in prev}
        for i in SEED:
            merged[i["id"]] = i
        indicators = list(merged.values())

    errors = validate(indicators)
    counts = {lv: sum(1 for i in indicators if i["level"] == lv)
              for lv in ("business", "atomic", "derived", "composite")}

    design = os.path.join(args.out, "design", "indicator")
    observed = os.path.join(args.out, "observed", "indicator")
    os.makedirs(design, exist_ok=True)
    os.makedirs(observed, exist_ok=True)

    date = _dt.date.today().isoformat()
    # JSON
    model = dict(meta=dict(
        spec="5S平台数据模型开发规范", source_kb="大数据5S开发平台知识库",
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
        levels=["business", "atomic", "derived", "composite"],
        ref_anchor="ZB_CODE(T_ADS_DIM_GZ01)"), indicators=indicators, validation=errors)
    with open(os.path.join(design, "indicator_system.json"), "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    # YAML（手写，避免第三方依赖）
    yaml_text = _to_yaml(model)
    with open(os.path.join(design, "indicator_system.yaml"), "w", encoding="utf-8") as f:
        f.write(yaml_text)
    # 血缘图
    graph = build_lineage_graph(indicators)
    with open(os.path.join(design, "lineage_graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    # 运行态快照
    with open(os.path.join(observed, f"indicator_run_{date}.json"), "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    # 报告
    report = build_report(indicators, errors, counts)
    with open(os.path.join(design, "indicator_report.md"), "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[OK] 指标总数={len(indicators)} 业务={counts['business']} 原子={counts['atomic']} "
          f"派生={counts['derived']} 复合={counts['composite']}")
    print(f"[OK] 校验：{'通过' if not errors else str(len(errors)) + ' 项拦截'}")
    if errors:
        for e in errors:
            print("  ❌ " + e)
    print(f"[OK] 设计态 -> {design}")
    print(f"[OK] 运行态 -> {observed}")
    print(f"[OK] 血缘节点={len(graph['nodes'])} 边={len(graph['edges'])}")
    # 退出码：校验失败返回 1（可接 CI / 每日回归）
    sys.exit(1 if errors else 0)


def _to_yaml(model):
    out = []
    out.append("meta:")
    for k, v in model["meta"].items():
        out.append(f"  {k}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}")
    out.append("indicators:")
    for i in model["indicators"]:
        out.append(f"  - id: {i['id']}")
        out.append(f"    level: {i['level']}")
        out.append(f"    code: {i['code']}")
        out.append(f"    name: {i['name']}")
        out.append(f"    domain: {i['domain']}")
        out.append(f"    owner: {i['owner']}")
        out.append(f"    definition: {i['definition']}")
        if i["level"] == "atomic":
            out.append(f"    biz_process: {i.get('biz_process')}")
            out.append(f"    measure: {i.get('measure')}")
            out.append(f"    agg: {i.get('agg')}")
            out.append(f"    source_table: {i.get('source_table')}")
            out.append(f"    grain: {i.get('grain')}")
        elif i["level"] == "derived":
            out.append(f"    atomic_ref: {i.get('atomic_ref')}")
            out.append(f"    time_period: {i.get('time_period')}")
            out.append(f"    dims: {json.dumps(i.get('dims', []), ensure_ascii=False)}")
        elif i["level"] == "composite":
            out.append(f"    components: {json.dumps(i.get('components', []), ensure_ascii=False)}")
            out.append(f"    formula: {i.get('formula')}")
        elif i["level"] == "business":
            out.append(f"    maps_to: {json.dumps(i.get('maps_to', []), ensure_ascii=False)}")
        out.append(f"    lineage_chain: {json.dumps(i.get('lineage', {}).get('chain', []), ensure_ascii=False)}")
    out.append("validation: " + json.dumps(model["validation"], ensure_ascii=False))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
