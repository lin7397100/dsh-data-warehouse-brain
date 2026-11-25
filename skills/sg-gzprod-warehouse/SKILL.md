---
name: sg-gzprod-warehouse
description: "三钢数仓智脑：生产管制域（GZPROD）数仓全量知识。55 个存储过程、425 张表（ODS/DWD/DWS/ADS）、840 条表级血缘、76 条字段级血缘、373 条 JOIN 条件、3801 个注册指标及全链路。用于该域表结构检索、血缘穿透、加工逻辑还原与指标口径校验。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, gzprod, warehouse, lineage, indicator]
owner: sg-gzprod
---

<!-- SG-DOMAIN-KB-ARCHIVED v1 -->
> **owner 归位**：本技能为生产域知识载体，owner 为管枢 `sg-gzprod`（在册主责）。历史上一度迁至舆图，现已归位。

> **归属变更**：本技能原属「原管枢（`sg-gzprod`）」专家。该专家已退役，其知识已导出为知识库文档：
> `C:\Users\lin\WorkBuddy\2026-09-05-09-44-33\指标血缘报告\管枢_生产管制域GZPROD_知识库文档.md`。
> **本技能保留可用**，作为该域的程序化检索入口；人类可读的完整知识以知识库文档为准。

# sg-gzprod-warehouse · 生产管制域数仓全量知识

## 定位

生产管制域（GZPROD）的**物理事实底座**。所有关于该域的表结构、血缘、加工逻辑、JOIN 方式、
指标口径的问题，先查本技能的知识文件，再决定是否 DB2 实跑复核。

## 知识文件

| 文件 | 内容 | 规模 |
|---|---|---|
| `knowledge/domains/gzprod/gzprod_lineage.json` | 55 过程 + 425 表（含字段结构）+ 840 表级边 + 76 字段级边 + JOIN | 4.7 MB |
| `knowledge/domains/gzprod/gzprod_indicators.json` | 3801 指标（ZB_CODE/名称/单位/SQL1/CREATER/来源表/全链路） | 2.3 MB |

### JSON 结构速查

```
gzprod_lineage.json
  meta            {domain, cn_name, proc_count, table_count, layer_dist, edge_count, field_edge_count}
  tables          {SCHEMA.TABLE: {schema, table, cn, layer, ncols, pk, columns[], upstream[], downstream[], written_by[], read_by[]}}
  procs[]         {proc, file, params, targets[], sources[], joins[]{table,on,type}, comments_cn[]}
  edges[]         {src, tgt, proc, op}          # 表级血缘
  field_edges[]   {src_table, src_col, tgt_table, tgt_col, expr, proc}   # 字段级血缘

gzprod_indicators.json
  meta            {domain, count, with_chain, creater_distinct, layer_dist}
  indicators[]    {code, name, unit, factory, creater, sql1, sql2, src_tables[], chain[], chain_str, src_layer_top}
```

## 分层判定

表名前缀优先：`T_ODS_`→ODS、`T_DWD_`→DWD、`T_DWS_`→DWS、`T_ADS_`→ADS；
schema 兜底：`SMBB_M_O_*`→ODS、`SMBB_M_S_*`→DWS、`SMBB_M_A_*`→ADS。

本域分布：**ODS 199 / DWD 63 / DWS 149 / ADS 11**（共 425）。

## 标准操作

### 1. 表结构查询
在 `tables[SCHEMA.TABLE].columns[]` 取字段（name/cn/type/len/prec/null/def），主键看 `pk`。

### 2. 血缘下钻（找源头）
从目标表出发沿 `tables[].upstream[]` 递归至 `layer == 'ODS'`；输出链路
`ODS:xxx → DWD:xxx → DWS:xxx`。指标的 `chain_str` 字段已预计算，直接取用。

### 3. 血缘上卷（找影响面）
沿 `tables[].downstream[]` 递归，得到所有下游表与 `read_by` 过程。

### 4. 加工逻辑还原
查 `procs[]`：按 `targets` 定位写入过程 → 读 `sources`（输入表）+ `joins`（关联条件）
+ `comments_cn`（中文业务注释）→ 复述加工口径。

### 5. 字段级血缘
`field_edges[]` 给出 `源表.源字段 → 目标表.目标字段` 及计算表达式 `expr`。
> 覆盖率说明：受动态 SQL（`EXECUTE IMMEDIATE`）与多层 CTE 影响，字段级为**尽力解析**（76 条）；
> 未覆盖部分请以 `procs[].comments_cn` 与 DB2 实跑为准，不得凭空补全。

## 已验证事实（硬性约束）

- ZZGZ 报表对拍：SQL1 ↔ 导出 Excel（2026-09-04）**8/8 = 100%**。
- 三公司闭环：SQL1 ↔ T_PM_KPI 抽样 **45/48 = 93.8%**。
- `T_DWS_FACT_ZZGZ_*` **末次装载 2025-06-30**（数据源停更），指向该系列查当期为空须判为停更。
- 指标 8000618 SQL1 引用已废弃 ITEMNAME，正确同族为 **8001391**。

## 与其他技能边界

| 场景 | 用谁 |
|---|---|
| 生产管制域物理结构/血缘/加工 | **本技能** |
| **生产域异常自动识别与根因报告** | **`sg-gzprod-anomaly-detect`**（v1.0，砺真挂帅） |
| 跨域或通用血缘分析 | `sg-data-lineage` |
| 业务语义（指标业务含义/同义词） | `sg-semantic-layer` |
| 本体实体与关系建模 | `sg-ontology-modeling` |

### 与指标血缘知识库协同（强制）

<!-- SG-KB-COOP v1 -->

本技能（域知识检索入口）与知识库目录 `C:\Users\lin\WorkBuddy\2026-09-05-09-44-33\指标血缘报告` **协同使用**：

- `T_ADS_DIM_GZ01.csv`（DB2 `SMBB_M_A_GZ01.T_ADS_DIM_GZ01` 镜像）定指标与口径，其 `SQL1` 可直接执行；
- 三份指标血缘文档（`ZZGZ_指标血缘.md` / `ZZGZ_JD02_指标血缘.md` / `GZJD02LDY_指标血缘.md`）提供完整可执行 SQL 与上游链路；
- 域知识文档解释加工逻辑、定位根因所在层（ODS/DWD/DWS/ADS）。

**检索优先级**：① `T_ADS_DIM_GZ01` → ② 三份指标血缘文档 → ③ 域知识文档 → ④ DB2 实表查询（仅前三层缺失时）。

**协同铁律**：血缘文档 SQL 与 `SQL1` 的执行结果必须交叉对拍，相对误差 >1e-6 或单位不一致即触发复算/告警，**禁止裸数直出**。
