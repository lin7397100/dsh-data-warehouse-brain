# 数据分层 ODS→DWD→DWS→ADS 完整建模（2026-11-16 · v1.0）

> 来源：三钢数据中台真实分层架构 + 用户 2026-11-16 指示。
> 本文件为铨度（语义层）、构枢（本体）、淬锋（编译）、诠枢（向量建模）的共同分层规则源。

## 一、四层定义（必须逐字遵守）

| 层 | 表名前缀 | 语义 | SQL 特征 | 示例 |
|---|---|---|---|---|
| **ODS** | `T_ODS_*` | 贴源数据层·原始镜像 | SELECT * FROM 源表；无加工、无清洗、无口径 | `T_ODS_SAP_ORDER` → 100% SAP 原貌 |
| **DWD** | `T_DWD_*` | 明细事实层·清洗后原子指标 | 清洗（去空/去重/标准化）+ 统一口径（CODE→NAME 映射）+ 必要 JOIN（维度补全） | `T_DWD_FACT_CACB_CDT6` → 清洗后的成本中心事实明细 |
| **DWS** | `T_DWS_*` | 汇总服务层·派生指标宽表 | GROUP BY 维度 + 聚合函数（SUM/AVG/COUNT）+ 派生计算（加减乘除）；来自 DWD 或 DWS | `T_DWS_FACT_ZZGZ_0001` → 按厂别+日汇总的产量宽表 |
| **ADS** | `T_ADS_*` | 直接应用层·交付就绪 | 在 DWS 基础上最终加工：排序/TOP N/同比环比/格式化；**不准再聚合** | `T_ADS_SRV_CACA_DAY_COST` → 日成本单位成本交付表 |

**关键规则**：
- **ODS→DWD**：清洗转换（去空、去重、编码标准化、维度补全）
- **DWD→DWS**：汇总聚合（GROUP BY + SUM/AVG/COUNT），或在已有 DWS 上做派生计算（指标 A ÷ 指标 B）
- **DWS→ADS**：最终加工（排序、格式化、同比环比），**ADS 层禁止再新增 GROUP BY 聚合**——聚合必须在 DWS 完成

## 二、从零构建 SQL 的分层决策树

当目标指标「零物化 SQL、零存储过程、零现有计算链」时，专家团**必须**按以下顺序逐层构建：

```
Step 1: 定位 ODS 源表（data_source 字段、域知识库、SYSCAT.TABLES 模糊匹配）
    │
    ▼
Step 2: DWD 构建计划 → 用户确认
    │  ① 哪些 ODS 字段保留/丢弃
    │  ② 清洗规则（NULL→0? 去重? 编码标准化?）
    │  ③ 需要 JOIN 哪些维度表（如 CDT6 补 CODE→NAME）
    │  ④ 统一口径（如 FACTORY_CODE→厂别名称）
    │  产出：DWD SELECT 语句 + 字段说明
    │
    ▼
Step 3: DWS 构建计划 → 用户确认
    │  ① GROUP BY 维度（day/factory/heat/prod_unit）
    │  ② 度量聚合方式（SUM(CONSUME) / AVG(COST)）
    │  ③ 派生指标公式（A/B、A+B-C）
    │  ④ 必要过滤（IS_VALID、排除合计码 BF10/BF20）
    │  产出：DWS SELECT 语句 + 派生指标说明
    │
    ▼
Step 4: ADS 构建计划 → 用户确认
    │  ① 排序/TOP N
    │  ② 同比环比窗口函数
    │  ③ 格式化（ROUND/单位转换）
    │  产出：ADS SELECT 语句 + 交付说明
    │
    ▼
Step 5: 执行 ADS 查询 → 返回数据
    │
    ▼
Step 6: 用户确认可用 → 物化闭环（sg-sql-materialization 六步）
```

**每层产出必须经用户确认后才继续下一层**。（与三令牌护栏的「确认令牌」对齐）

## 三、分层表命名规范（从 SYSCAT.TABLES 自动识别）

```
T_{layer}_{domain}_{fact|dim}_{subject}[_{suffix}]
  │       │       │             │
  │       │       │             └─ 主题缩写（如 CACB=成本预算, ZZGZ=制造管控）
  │       │       └─ 表类型：FACT=事实, DIM=维度
  │       └─ 业务域：CBPROD→CB, GZPROD→GZ, ZZ→制造
  └─ 层前缀：ODS/DWD/DWS/ADS
```

**本团已注册的核心表**（来源：v1.4.0 语料 `semantic_corpus.json`）：

| 层 | 表 | 域 | 用途 |
|---|---|---|---|
| DWD | `SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_COST` | CBPROD | 分产品成本 |
| DWD | `SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_EARN` | CBPROD | 分产品挣得量 |
| DWD | `SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT6` | CBPROD | 成本中心字典 |
| DWS | `SMBB_M_S_ZZGZ.T_DWS_FACT_ZZGZ_0001` | GZPROD | 制造产量宽表 |
| DWS | `SMBB_M_S_CB00.T_DWS_FACT_CBZX_CACA_CENTER_COST` | CBPROD | 成本中心成本汇总 |
| ADS | `SMBB_M_A_CB01.T_ADS_SRV_CACA_DAY_COST` | CBPROD | 日成本交付表 |

## 四、分层 SQL 模板（确定性编译框架）

### 4.1 ODS→DWD 模板
```sql
-- DWD: {主题}_{清洗规则}_{日期}
SELECT
  -- ① 保留字段（显式列出，禁止 SELECT *）
  t.COL1,
  -- ② 清洗转换
  COALESCE(t.COL2, 0) AS COL2_CLEANED,          -- NULL→0
  CASE WHEN t.CODE='01' THEN '本部' END AS NAME, -- 编码标准化
  -- ③ 维度补全（JOIN 字典表）
  d.DICT_NAME AS DIM_NAME
FROM {ODS_TABLE} t
LEFT JOIN {DICT_TABLE} d ON t.CODE = d.CODE
WHERE t.YMD BETWEEN '{START}' AND '{END}'       -- 分区过滤
  AND t.IS_VALID = '1'                          -- 有效数据
```

### 4.2 DWD→DWS 模板
```sql
-- DWS: {派生指标}_{维度}_{日期范围}
SELECT
  {DIM1}, {DIM2},                               -- GROUP BY 维度
  SUM({METRIC1}) AS SUM_M1,                      -- 可加度量
  AVG({METRIC2}) AS AVG_M2,                      -- 半累加度量
  SUM(CASE WHEN {COND} THEN {VALUE} END) AS COND_M, -- 条件聚合
  -- 派生指标（加减乘除）
  SUM(A) / NULLIF(SUM(B), 0) AS DERIVED_1       -- 加权比值
FROM {DWD_TABLE}
WHERE {FILTERS}
GROUP BY {DIM1}, {DIM2}
```

### 4.3 DWS→ADS 模板
```sql
-- ADS: {最终交付}_{日期}
SELECT
  *,                                             -- DWS 字段原样保留
  ROUND(DERIVED_1, 4) AS FORMATTED,             -- 格式化
  LAG(DERIVED_1, 1) OVER (ORDER BY YMD) AS PREV, -- 环比/同比
  ROW_NUMBER() OVER (ORDER BY METRIC DESC) AS RN -- 排名
FROM {DWS_TABLE}
WHERE YMD = '{DATE}'                             -- 单日/单期
-- 禁止新增 GROUP BY
```

## 五、分层构建的六道质量闸门

| 闸门 | 检查点 | 负责专家 |
|---|---|---|
| G1 源表识别 | ODS 表是否存在、字段是否完整、分区列是 YMD 还是 WORK_DATE | 舆图 sg-metadata + 矩衡 |
| G2 清洗规则 | NULL 处理是否正确、编码映射是否查字典表、去重是否必要 | 铨度 + 砺真 |
| G3 聚合方向 | SUM 是否对可加度量、AVG 是否先按粒度去重、COUNT 是否 DISTINCT | 砺真 sg-quality |
| G4 派生公式 | 分子分母口径是否一致、除法 NULLIF 防御、加减法单位统一 | 矩衡 sg-metric-builder |
| G5 基数检查 | fan-out 是否由 JOIN 引入、GROUP BY 后的行数是否可解释 | 守钧 sg-governance |
| G6 值与 ADS 闭合 | 若已有 ADS 同指标，新构建的结果是否与 ADS 一致（Q5/Q6 模式） | 淬锋 + 铨度 |

## 六、与 DSL→MQL→SQL 的关系

```
用户 NL
   │
   ▼
[辨枢] IntentContract JSON（业务语义稿）
   │
   ▼
[铨度] MQL DSL（纯业务语义，无物理表名/字段名）← 新增分层信息
   │  metric: {name, grain, aggregation, formula}
   │  dimensions: [{name, hierarchy, code_column}]
   │  layer_hint: "可以直接查 ADS" | "需要从 DWS 聚合" | "需要从 ODS 构建"  ← 新增
   │
   ▼
[淬锋 + 构枢] 确定性翻译
   │  layer_hint='ADS' → 直接编译 DWS→ADS SQL（最快）
   │  layer_hint='DWS' → 在已有 DWS 上聚合编译
   │  layer_hint='ODS' → **触发分层构建决策树**（本文件第二节）
   │
   ▼
SQL → [只读执行器] → 数据
```

**分层构建入口**：当 `IntentContract.layer_hint = 'ODS'` 或铨度 MQL 中找不到可用的 DWD/DWS/ADS 表时，淬锋**必须**按本文件第二节的决策树逐层构建，不能跳过中间的确认门禁。

## 七、DWS 派生指标的两种来源（用户指定）

| 类型 | 来源 | 示例 |
|---|---|---|
| **DWD→DWS** | 对 DWD 明细事实聚合 | 按日+厂汇总 `SUM(CONSUME)` → `T_DWS_FACT_ZZGZ_0001` |
| **DWS→DWS** | 两个已有 DWS 指标加减乘除 | 铁水耗 = `铁水消耗量(来自 DWSA) ÷ 钢产量(来自 DWSB)` |

**DWS 派生指标构建规则**：
- 若分子分母来自同一 DWS 表 → 单表计算（最快）
- 若来自不同 DWS 表 → 须确认两张表 **维度对齐**（同 grain）后才 JOIN，否则报"跨粒度不可直接运算"

## 八、落地到专家团分工

| 分层步骤 | 主责 | 协同 |
|---|---|---|
| ODS 表发现 | 舆图 sg-metadata（查 SYSCAT.TABLES）+ 矩衡（ddl） | 铨度裁决选哪张 |
| DWD 清洗计划 | 铨度 sg-semantic（口径标准）+ 砺真（数据质量规则） | 成枢 sg-cbprod 确认域规则 |
| DWS 聚合方案 | 矩衡 sg-metric-builder（派生公式）+ 构枢 sg-ontology-modeler（JOIN 键） | 淬锋校对 JOIN |
| ADS 最终加工 | 淬锋 sg-development（编译 SQL） | 守钧审查 |
| 全链物化 | 衍薪 sg-skill-evolution + sg-sql-materialization | K8 记忆库写结果 |