---
name: sg-data-lineage
description: "三钢数仓智脑：全链路血缘引擎（反向追溯主引擎）。追踪 T_ODS→T_DWD/T_DWS(+tmp临时表)→T_ADS 三层链路，支持 KPI 单指标单日下钻（找源头）与源表上卷（找影响面），支持「无ADS层直接用CDM」合法终点，输出标准血缘 JSON 供下钻/趋势/报表/根因统一消费，为根因分析提供可核验的物理证据。"
version: 1.1.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, metadata, lineage]
owner: sg-metadata
---

# sg-data-lineage · 物理血缘分析

## 定位

表与表之间的**物理链路图**（区别于本体专家的业务语义血缘）。

| 维度 | 本体血缘（本体专家） | 物理血缘（本技能） |
|---|---|---|
| 内容 | 指标 → 业务计算逻辑 → 实体关系 | 表 → 表 → 表 |
| 数据来源 | ODS 表 + 存储过程解析 | DDL + 存储过程输入输出 |
| 用途 | 语义解析、业务根因定位 | 表定位、数据延迟判定、影响面评估 |

两者必须交叉验证，冲突时以 DB2 实数据核验为准。

## 链路模型

```
ODS (55 源系统)  →  DWD (存储过程加工)  →  DWS (19 Schema)  →  ADS (22 Schema)
SMBB_M_O_XXX        GZPROD/CBPROD 过程     SMBB_M_S_XXX        SMBB_M_A_XXX
                          ↓ 过程内
                    tmp*/GTT 临时表链（TMP1_1…TMP1_39）★链路合法一环，必须解析纳入

【三层下钻视角（2026-11-02 · 用户权威分层）】
  第一层  T_ADS  应用展示层   （可缺失 → 合法降级，见下）
  第二层  T_DWD / T_DWS  CDM 层（+ tmp 临时表，承载业务计算逻辑）
  第三层  T_ODS  贴源数据层   （最源头，须实查全明细行）

【无 ADS 层 = 合法终点】只要 T_ODS → T_DWD/T_DWS 链路连续，
  直接用 CDM 层展示即可，标记 has_ads=false，不得判为断链。
```

**成本域**：`ODS → CBPROD 十步链 → SMBB_M_S_CB00 成本底表 → 成本 KPI`

## 双向分析

### 方向一 · 下钻（KPI/表 → 源头）

```
起点：SMBB_M_A_GZ01.T_ADS_DIM_GZ01（指标配置）
 ↓ 指标 SQL1 指向
SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_ZG01
 ↓ 由过程写入
P_DWS_FACT_ZZGZ_ZG01（GZPROD）
 ↓ 读取
SMBB_M_O_SGP2Z1.T_ODS_TMMBW19B3（轧机实绩）
```

### 方向二 · 上卷（源表 → 影响面）

```
起点：T_ODS_TMMBW19B3 结构变更 / 数据延迟
 ↓ 影响
P_DWS_FACT_ZZGZ_ZG01 → T_DWS_FACT_ZZGZ_ZG01
 ↓ 影响 KPI
质量_圆棒当日合格量 / 圆棒日作业率 / …（按使用频度排序）
```

## 工作流（七步 · 2026-11-02 升级为通用反向追溯引擎）

> 原四步仅覆盖「表→表」粗粒度。本七步为**任意 (ZB_CODE, 日期)** 的通用反向追溯引擎，
> 完整 SQL 模板见 `agents/references/traceability_sql.md`「通用三层血缘下钻模板」；
> 断链时转 `agents/references/lineage_fallback.md`（正向建模由 `sg-metric-builder` 主责）。

### Step 1 · 定位起点

表名 / 指标名 → 在 DDL 与过程目录中定位（`sg-metadata-core` 辅助）。

### Step 2 · 逐层展开（按需）

默认展开到 DWS + PROC；根因核验场景再展开到 ODS。

### Step 3 · 物理证据采集（根因分析场景必做）

| 证据 | 获取方式 | 用途 |
|---|---|---|
| 表结构与字段 | DDL 检索 | 判断是否字段级问题 |
| 数据量 | `SELECT COUNT(*)`（DB2 MCP） | 判断是否缺数 |
| 最后更新时间 | `SELECT MAX(更新时间)`（DB2 MCP） | 判断**数据延迟** |
| 分区分布 | 按分区统计 | 判断是否部分分区缺失 |

### Step 4 · 完整性校验与输出

- 链路断裂 → 标注断裂点，交本体专家补解析
- 与本体血缘不一致 → 上报，由质量专家实数据核验

### Step 5 · 解析 tmp 临时表链（2026-11-02 必做）

```sql
SELECT BSCHEMA, BNAME, BTYPE FROM SYSCAT.ROUTINEDEP
WHERE ROUTINESCHEMA='<PROC_SCHEMA>' AND ROUTINENAME='<CREATER>';
```
正文侧 Grep `TMP|tmp|GTT|SESSION\.|DECLARE GLOBAL TEMPORARY` 提取中间层。
**tmp 是链路合法一环，必须纳入血缘 JSON 的 `layers.CDM.tmp_chain`**；静态依赖残缺须如实标注，**不得补造**。

### Step 6 · 实查 ODS 全明细（溯源铁律）

对 `T_ODS_*` 按当日**全条件**实查，列出**所有**明细行（禁抽样、禁只给聚合值），让用户逐行复核到原始凭证。记录 `detail_rows_n`。

### Step 7 · 逐层对账 + 三闸门

`ODS 之和 = CDM = ADS`（无 ADS 时 `ODS 之和 = CDM`）；对不平 → 标 `[对账差异]`。

**血缘三闸门**（任一不过即标存疑，不得作确定值交付）：

| 闸门 | 校验 | 不过处置 |
|---|---|---|
| ① 结构完整 | 三层齐全，或合法降终点到 CDM | 标 `[结构缺失]` |
| ② 链路连续 | 无断点、无臆断映射 | 标 `[链路断裂@<层>]` → 转断链兜底 |
| ③ 设计态≡数据态 | 对照 weknora K7 5S 规范核验 | 标 `[设计态/数据态不一致]` |

## 延迟判定规则

| 现象 | 判定 |
|---|---|
| ODS 最后更新时间 < 预期抽取时点 | **上游未抽取**（数据延迟） |
| ODS 有数但 DWS 无 | 存储过程未执行或执行失败 |
| DWS 有数但 ADS 无 | 指标配置缺失或 SQL1 无结果 |
| 各层都有但值不符 | 计算逻辑问题（转本体 / 质量专家） |

## 输出规范

- 链路图：层级 / 对象 / 角色 / 数据量 / 最后更新时间
- 影响面清单（上卷时）：受影响表 + KPI（按频度排序）
- 断裂与异常标注

### 标准血缘 JSON（2026-11-02 · 全团唯一交换格式 · 所有消费层无差别消费）

```json
{
  "zb_code": "<ZB_CODE>", "indicator_name": "<名称>", "date": "<YYYYMMDD>",
  "level": "L4业务|L3复合|L2派生|L1原子",
  "layers": {
    "ADS": {"table": "<T_ADS_xxx 或 null>", "source": "T_ADS_DIM_GZ01.SQL1", "has_ads": true},
    "CDM": {"tables": ["T_DWD_*","T_DWS_*"], "tmp_chain": ["TMP1_1","TMP1_2"], "procedure": "<CREATER>"},
    "ODS": {"tables": ["T_ODS_*"], "schema": "SMBB_M_O_SGP1Z1", "detail_rows_n": 71}
  },
  "lineage_mode": "reverse",
  "gates": {"structure":"pass", "continuity":"pass", "design_vs_data":"pass"},
  "reconcile": {"ods_sum":0, "cdm_sum":0, "ads_sum":0, "diff":0},
  "confidence": 0.95,
  "annotation": ""
}
```

**标注纪律**：gates 不全 pass → `annotation` 必含 `[血缘不完整·数据存疑]`；断链转正向 → 标 `[正向建模·待实据核验]` 且 `confidence ≤ 0.60`。

**消费纪律**：`sg-insight` 渲染**四层抽屉**（L1 构成 / L2 序列 / L3 tmp / L4 ODS）、**只能**消费本 JSON；
> 📎 下钻规则唯一权威源：`knowledge/kb/数据下钻规则_权威手册.md`
**禁止**任何消费层（含编排器）手搓近似血缘。T2a 快线同样适用：趋势可快，**点开任意数据点必须走本引擎**。

**⚠ 5S 规范校验**：判「无 ADS」「tmp 是否该纳入」等分层问题有疑时，查 weknora **K7 大数据5S平台知识库**（`d12f3c32-bf50-41cc-8be8-77af4c45bb35`，`match_count ≤3`，返回可达 97–186KB 防溢出）。

## 注意事项

1. **物理证据必须来自 DB2 实数据**，不用经验推断。
2. 上卷影响面可能很大，输出按频度排序并限制条数（默认 ≤20 条）。
3. 延迟判定必须给出"预期时点"的依据（调度时间 / 历史基线）。
