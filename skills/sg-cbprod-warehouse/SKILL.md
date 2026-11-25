---
name: sg-cbprod-warehouse
description: "三钢数仓智脑：成本域与利润域智能问数全量知识。基于DB2实测的权威口径手册：6铁律、9版口径体系(V1-V9)、10表清单+全字段、5类SQL模板、3级校验体系、34坑清单、FAQ速配表、口径决策树、链路自证清单。适用于一切成本/利润/边际贡献/科目构成/保本线类自然语言问数。"
version: 2.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, cbprod, cost, lineage, indicator, caliber, profit, margin, breakeven]
owner: sg-cbprod
---

<!-- SG-DOMAIN-KB-COST-V2 -->
> **版本升级 v1→v2**：全文基于《三钢成本域与利润域·数据口径与计算链路权威手册》（DB2 SGPROD1 实测，基准账期 20261013V1，81KB）重写，替代旧版 CBPROD 知识库。旧版仍可查阅 `knowledge/domains/cbprod/` 下的 lineage/indicators JSON。

> **owner 归位**：本技能为成本域权威载体，owner 为成枢 `sg-cbprod`（在册主责）。历史上一度迁至舆图，现已归位。

# sg-cbprod-warehouse v2 · 成本域与利润域智能问数权威知识

## 定位

成本域/利润域智能问数的**唯一权威知识源**。当用户问及以下任何问题时，必须优先加载本技能：

- 单位成本、分钢种成本、日成本、月累成本
- 边际贡献、利润、保本线、该不该保
- 成本科目构成、差异归因、为什么贵
- 标准成本 vs 实际成本 vs 即时成本
- 当天成本出了没有、为什么某个科目没进成本
- 吨材成本、轧制费、成材率、工序成本

---

## 0. 铁律（违反必错）

| # | 铁律 | 违反后症状 |
|---|---|---|
| **1** | **必须显式指定版本**：`ACCOUNT_PERIOD='YYYYMMDDVn'`，永远不要只按月份过滤 | 同一天返回多版本多行，数值被平均 |
| **2** | **主表 `DAY_COST` 的 `MON_VAL` 不是月累实际成本，是 V4 标准成本** | 把"月累"答成标准成本，差 40 元/吨以上 |
| **3** | **单位成本必须用 `ΣCOST ÷ ΣEARN_N`**，禁止 AVG 已有单位成本字段 | 小批量品种偏差数百元/吨 |
| **4** | **科目必须映射中文名，且 `COMPANY_CODE='100'`** | 交付 6 位编码或把"软水（北区）"错成"纯水" |
| **5** | **默认口径不反问但要标注**：成本=V1+DS3(当天)，利润=V1+DT4+RC2(月累市场价) | 用户每次都要等一轮澄清 |
| **6** | **任何 SQL 写 `schema.表名` 全称**，默认 schema 是 `SGJYSU` 不是 `SMBB_M_S_CB00` | `SQLCODE=-204` 误判为"表不存在" |

---

## 1. 数据库与连接

- 库：**SGPROD1**（DB2，生产只读）
- 规模：9167 表 / 96 Schema / 105 存储过程（成本域相关 185 Routine）
- 只读通道：DB2 MCP（优先）或 5sApi REST（需自备 token）

### Schema 分工与表命名速查

| Schema | 层 | 放了什么 |
|---|---|---|
| `SMBB_M_S_CB00` | DWD | 成本明细事实、成本字典(CDT系列)、维表 |
| `SMBB_M_A_CB01` | ADS | 日成本主表、边际贡献表、分钢种效益表 |
| `SMBB_M_S_ZZ00`/`_YX00` | DWD | 轧钢/原修（一般不直接用） |
| `SMBB_M_A_WL01`/`_MC00` | ADS | 物流成本/煤化工成本 |

> ⚠️ **高频错点**：`T_ADS_SRV_CACA_DAY_COST` 和 `T_ADS_SRV_CACA_SIDE_COST` 在 **`SMBB_M_A_CB01`**，不在 `SMBB_M_S_CB00`。

---

## 2. 版本口径体系（最容易出错）

### 2.1 ACCOUNT_PERIOD 结构

`ACCOUNT_PERIOD = 'YYYYMMDD' + 'V' + 版本号`，如 `20261013V1`

### 2.2 成本域：V1 + DATA_SOURCE 二维口径

| 版本 | DS | 语义 | 取法 |
|---|---|---|---|
| **V1** | `3` | **当天实际成本** ★默认 | `PRODUCT_COST / PRODUCT_EARN` 现算 ΣCOST/ΣEARN_N |
| **V1** | `4` | **月累实际成本** | 同上（DS=4） |
| **V4** | `3` | **标准成本** | `SG_SIGN_COST` 物化表直取，自带 UNIT_COST |
| V3 | `3` | 日即时成本 | 偏低估约 86 元/吨，**不当实际成本** |
| V7/V8/V9 | `4`/`4`/`3` | 内部测算变体 | 偏低 12%–29%，**禁止用于完整报表** |

**V1 与 V4 是唯二可交付口径**。`DATA_SOURCE` 取值：`1`=核算 `2`=预算 `3`=日成本 `4`=累计。

### 2.3 利润/边际贡献域：两维正交

落点表：`SMBB_M_A_CB01.T_ADS_SRV_CACA_SIDE_COST`

`DATA_TYPE` × `RC_TYPE` 两维正交：
- **DT=4, RC=2** → 月累-市场价 ★默认
- DT=4, RC=3 → 月累-结算价
- DT=3, RC=1 → 当日即时-市场价 (V3)
- DT=3, RC=3 → 日成本-市场价 (V1)

`DATA_TYPE`：`3`=当日 / `4`=月累。`RC_TYPE`：`1`=库存价 / `2`=市场价 / `3`=结算价。

### 2.4 默认口径

| 对象 | 默认 | 切换条件 |
|---|---|---|
| 成本 | **V1 + DS='3'（当天）** | 用户强调"月累/累计"→DS='4'；"标准/计划"→V4 |
| 利润/边际贡献 | **V1 + DT='4' + RC='2'（月累-市场价）** | "当日"→DT='3'；"结算价"→RC='3'；"即时"→V3 |

### 2.5 版本数值指纹（反向识别）

以 20261013 中板为例，单位成本落点范围判断版本：
- 3,283.63 → V1+DS3（当天实际）★
- 3,302.41 → V1+DS4（月累实际）
- 3,274.39 → V4（标准成本）
- 3,197.64 → V3（日即时，偏低估 86）
- 2,890 / 3,038 / 2,344 → V7/V8/V9（测算变体，不可对外）

---

## 3. 核心表清单（物理落点 · SQL必须写全称）

| 简称 | SQL 全称 | 行数 | 用途 |
|---|---|---|---|
| `PRODUCT_COST` | `SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_COST` | DS3≈3千/天 | ★主力：分产品科目级成本 |
| `PRODUCT_EARN` | `SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_EARN` | DS3≈2.5千/天 | 分产品产量(挣得量) |
| `SG_SIGN_COST` | `SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_SG_SIGN_COST` | 33–61行/天 | V4分钢种成本(物化) |
| `CDT8` | `SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT8` | **28,072** | 产品→钢种映射 |
| `CDT7` | `SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT7` | 661(账套100) | 科目字典(编码→中文名) |
| `FIX_TITLE` | `SMBB_M_S_CB00.T_DWD_DIM_ZBCB_FIX_TITLE` | 12 | 固定费用界定 |
| `DAY_COST` | `SMBB_M_A_CB01.T_ADS_SRV_CACA_DAY_COST` | 76行/天 | 日成本主表(对账基准) |
| `SIDE_COST` | `SMBB_M_A_CB01.T_ADS_SRV_CACA_SIDE_COST` | V1 861行/天 | 边际贡献 |
| `GRADE_BENEFIT` | `SMBB_M_A_CB01.T_ADS_SRV_CACA_GRADE_BENEFIT` | 175–232行/月 | 月度分钢种效益(滞后1月) |
| `CACC_LOGS` | `SMBB_M_S_CB00.T_DWD_FACT_CACC_LOGS` | **132.5万** | 实际成本过程日志 |

### 关键字段速查

**PRODUCT_COST**：`COMPANY_CODE`(恒'100') / `ACCOUNT_PERIOD` / `COST_CENTER` / `FACTORY_CODE`(DWD层=`M`+码) / `COST_TITLE`(科目编码) / `PRODUCT_CODE`(经CDT8映射到钢种) / `CONSUME` / `COST`(金额,元) / `DATA_SOURCE`(3当天/4月累)

**SIDE_COST**：`ACCOUNT_PERIOD` / `DATA_TYPE`(3/4) / `RC_TYPE`(1/2/3) / `FACTORY_CODE`(ADS层=纯数字) / `ORDER_SEQ`(1汇总/100明细/9999合计) / `VISABLE_FLAG`(必须='Y') / `EARN_N`(商品材产量) / `UNIT_SIDE_COST` / `UNIT_PROFIT`

### 编码字典

**成本中心**：`1004506`=中板 / `100430701`=一高 / `100430702`=二高 / `100430703`=三高 / `100430801`=一棒 / `100430802`=圆棒(三棒) / `10043080301`=中大棒 / `100430401`=炼钢

**DWD FACTORY_CODE**（`M`+码）：`M023`=圆棒 / `M024`=中大棒 / `M031`=中板 / `M053`=三高线
**ADS FACTORY_CODE**（纯数字）：`23`=圆棒 / `24`=中大棒 / `31`=中板 / `52`=二高 / `53`=三高

> ⚠️ 跨层过滤用 `COST_CENTER`，不要用 `FACTORY_CODE`。

---

## 4. 取数 SQL 模板（可直接复制执行）

### 4.1 分钢种成本与单位成本（V1，DS3 当天 / DS4 月累）

```sql
WITH COST AS (
  SELECT NVL(T8.SG_SIGN,'?') AS SG, SUM(NVL(A.COST,0)) AS C
  FROM SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_COST A
  LEFT JOIN SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT8 T8
    ON A.COMPANY_CODE=T8.COMPANY_CODE AND A.PRODUCT_CODE=T8.PRODUCT_CODE
  WHERE A.COMPANY_CODE='100' AND A.DATA_SOURCE='3'
    AND A.ACCOUNT_PERIOD='20261013V1' AND T8.LOADER='1'
    AND A.COST_CENTER='100430802'
  GROUP BY NVL(T8.SG_SIGN,'?')
),
EARN AS (
  SELECT NVL(T8.SG_SIGN,'?') AS SG, SUM(NVL(A.EARN_N,0)) AS E
  FROM SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_EARN A
  LEFT JOIN SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT8 T8
    ON A.COMPANY_CODE=T8.COMPANY_CODE AND A.PRODUCT_CODE=T8.PRODUCT_CODE
  WHERE A.COMPANY_CODE='100' AND A.DATA_SOURCE='3'
    AND A.ACCOUNT_PERIOD='20261013V1' AND T8.LOADER='1'
    AND A.COST_CENTER='100430802'
  GROUP BY NVL(T8.SG_SIGN,'?')
)
SELECT COST.SG, COST.C AS COST_AMT, EARN.E AS EARN_TON,
  CASE WHEN EARN.E=0 THEN NULL ELSE DOUBLE(COST.C)/DOUBLE(EARN.E) END AS UNIT_COST
FROM COST JOIN EARN ON COST.SG=EARN.SG
ORDER BY UNIT_COST DESC
```

### 4.2 产线整体加权单位成本（不需要 CDT8，最适合校验）

```sql
WITH C AS (
  SELECT SUM(NVL(COST,0)) AMT FROM SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_COST
  WHERE COMPANY_CODE='100' AND DATA_SOURCE='3'
    AND ACCOUNT_PERIOD='20261013V1' AND COST_CENTER='1004506'
),
E AS (
  SELECT SUM(NVL(EARN_N,0)) EN FROM SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_EARN
  WHERE COMPANY_CODE='100' AND DATA_SOURCE='3'
    AND ACCOUNT_PERIOD='20261013V1' AND COST_CENTER='1004506'
)
SELECT C.AMT, E.EN, CASE WHEN E.EN=0 THEN NULL ELSE DOUBLE(C.AMT)/DOUBLE(E.EN) END AS UNIT_COST
FROM C, E
```

### 4.3 V4 标准成本（物化表直取）

```sql
SELECT SG_SIGN, COST, EARN_N, UNIT_COST
FROM SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_SG_SIGN_COST
WHERE COMPANY_CODE='100' AND ACCOUNT_PERIOD='20261013V4' AND COST_CENTER='1004506'
ORDER BY UNIT_COST DESC
```

### 4.4 科目构成/差异归因（含中文名）

```sql
SELECT NVL(T8.SG_SIGN,'?') AS SG, A.COST_TITLE,
  NVL(G.COST_TITLE_DESC, A.COST_TITLE) AS CT_NAME, SUM(NVL(A.COST,0)) AS AMT
FROM SMBB_M_S_CB00.T_DWD_FACT_CBCP_CACA_PRODUCT_COST A
LEFT JOIN SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT8 T8
  ON A.COMPANY_CODE=T8.COMPANY_CODE AND A.PRODUCT_CODE=T8.PRODUCT_CODE
LEFT JOIN SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT7 G
  ON G.COST_TITLE=A.COST_TITLE AND G.COMPANY_CODE='100'
WHERE A.COMPANY_CODE='100' AND A.DATA_SOURCE='4'
  AND A.ACCOUNT_PERIOD='20261013V1' AND T8.LOADER='1'
  AND A.COST_CENTER='1004506'
GROUP BY NVL(T8.SG_SIGN,'?'), A.COST_TITLE, NVL(G.COST_TITLE_DESC, A.COST_TITLE)
ORDER BY SUM(NVL(A.COST,0)) DESC
```

吨钢化在应用层做：某钢种吨钢科目 = 该科目金额 ÷ 该钢种产量。**禁止 SQL 内 AVG**。

### 4.5 边际贡献/利润（逐 Sheet）

```sql
SELECT FACTORY_CODE, ORDER_SEQ, ITEM_CODE, EARN_N,
  NO_TAX_PRICE, UNIT_CHANGE_COST, UNIT_SIDE_COST, UNIT_PROFIT
FROM SMBB_M_A_CB01.T_ADS_SRV_CACA_SIDE_COST
WHERE ACCOUNT_PERIOD='20261013V1' AND DATA_TYPE='4' AND RC_TYPE='2'
  AND VISABLE_FLAG='Y' AND ORDER_SEQ IN (1,9999)
ORDER BY ORDER_SEQ, FACTORY_CODE
```

### 4.6 保本线恒等式

```
单位利润 = 单位边际贡献 − 保本线
保本线 = UNIT_MANUAL_COST + UNIT_DEPRECITION_COST + UNIT_FEE_COST
       + UNIT_REPAIR_COST + UNIT_SERVICE_COST + UNIT_PERIOD_COST
残差 = (边际−利润) − 六项加总 = 0（实测 ±1e-6）
```

五线保本线（元/吨）：中板 495.16 / 圆棒 530.13 / 中大棒 561.58 / 二高 500.00 / 三高 575.86

三级决策：`UNIT_PROFIT>0`→保；`UNIT_SIDE_COST>0` 但 `UNIT_PROFIT≤0`→保量·提价；`UNIT_SIDE_COST≤0`→谈价或停产。

---

## 5. 三级校验体系

| 级 | 校验内容 | 方法 |
|---|---|---|
| **一级** | 与日成本主表对账 | 分钢种 ΣCOST/ΣEARN_N ≈ `DAY_COST.DAY_ALL_VAL` |
| **二级** | 科目差异可加分解 | Σ(本钢种吨钢科目−基准吨钢科目) = 实际单位成本差，残差=0 |
| **三级** | 漏跑判定 | 主表产量 vs 分钢种 EARN_N 汇总 → 相等=完整，不等=漏跑 |

**圆棒专属规则**：一级校验必须扣 `90054 回收自来水`（主表冲减了它）。主表值 + 0.4566 = 现算值。

**中板定位规则**：`ITEM_NAME2='中板成本' AND ITEM_NAME3='中板成本' AND ITEM_NAME4='中板成本'`（三列同名）。

---

## 6. 自检锚点（基准账期 20261013V1）

### 当天成本（V1+DS3）

| 产线 | 成本中心 | 单位成本(元/吨) |
|---|---|---|
| 中板 | `1004506` | **3,283.632192** |
| 二高线 | `100430702` | **3,288.734565** |
| 三高线 | `100430703` | **3,447.041738** |
| 圆棒 | `100430802` | **3,842.412555** |

### 月累成本（V1+DS4）

| 产线 | 单位成本(元/吨) |
|---|---|
| 中板 | **3,302.414661** |
| 二高线 | **3,312.715202** |
| 三高线 | **3,544.180625** |
| 圆棒 | **3,457.486662** |
| 中大棒 | **3,600.643884** |

### 边际贡献（V1+DT4+RC2+ORDER_SEQ=1）

| 产线 | 单位边际贡献 | 单位利润 |
|---|---|---|
| 中板 | 177.33 | −317.83 |
| 圆棒 | 78.55 | −451.58 |
| 中大棒 | −3.17 | −564.75 |
| 二高线 | 91.14 | −408.86 |
| 三高线 | −66.15 | −642.00 |

---

## 7. 坑清单（P1–P38 · 全量38坑 · 2026-10-19更新）

| # | 坑 | 正解 |
|---|---|---|
| P1 | 只按月份过滤 `LIKE '202610%'` | `= '20261013V1'` |
| P2 | 把主表 `MON_VAL` 当月累实际成本 | 回 DWD 现算（DS=4） |
| P3 | `COST`用DS3、`EARN_N`用DS4 | 同 DS |
| P4 | 关联 CDT8 不加 `LOADER='1'` | 必须加 |
| P5 | 对 `UNIT_COST` 做 `AVG()` | ΣCOST ÷ ΣEARN_N |
| P6 | 查 `DAY_COST` 用 schema `SMBB_M_S_CB00` | 在 `SMBB_M_A_CB01` |
| P7 | SQL 里写 `FETCH FIRST` | 用接口 `limit` |
| P8 | 边际贡献表不加 `VISABLE_FLAG='Y'` | 必须加 |
| P9 | 不限定 `ORDER_SEQ` | IN(1,9999)或=100 |
| P10 | 拿成本表 `EARN_N` 当商品材产量 | 成本表=挣得量，商品材看 `SIDE_COST.EARN_N` |
| **P16** | **某天查不到就以为"没生产"** | **实际是 ALTERBB_INSTER 回退到上一版本** |
| **P17** | **圆棒校验直接比主表** | **必须扣 90054 回收自来水(+0.4566)** |
| **P23** | **以为成本表只有 V1/V4** | **九版并存 V1–V9，随手 LIKE 会返回 7 组数** |
| **P27** | **ORDER BY DESC 取最新** | **DAY_COST 会先命中占位行 `'LD      V1'`** |
| **P30** | **查 CDT8 报"表不存在"就判中断** | **CDT8 在 SMBB_M_S_CB00，28,072行，存在！先查 SYSCAT** |
| **P31** | **DWD 用 M023 → 去 ADS 也找 M023** | **DWD=M+码(M023)，ADS=纯数字(23)** |
| **P34** | **SQL 省略 schema → -204** | **默认 schema 是 SGJYSU，不是 SMBB_M_S_CB00** |
| **P35** | **CONSUME_DAY/PUR_DAY 写 YYYYMMDDV1** | **无版本后缀，写 '20261018'** |
| **P37** | **批量对全部过程 LOCATE/LENGTH** | **CLOB 全表扫描→504，逐个过程分段取** |
| **P38** | **用 ROUTINEDEP 判断"没人用"** | **动态 SQL 是盲区，改用结构标记反查(§19.7)** |

> 完整 38 坑清单（含 DB2 精度坑/P16-P34 中间坑/数据源避雷）见权威手册 §8。

---

## 8. 口径决策树

```
用户问成本/利润 → 
  ├─ 问"成本/单位成本/分钢种/日成本"
  │   ├─ 未强调 → V1+DS3(当天) ★默认
  │   ├─ "月累/累计" → V1+DS4
  │   └─ "标准/计划" → V4(YYYYMMDDV4 物化表)
  ├─ 问"利润/边际贡献/赚不赚钱"
  │   ├─ 未强调 → V1+DT4+RC2(月累-市场价) ★默认
  │   ├─ "结算价" → RC3 / "库存价" → RC1
  │   └─ "当天即时" → V3+DT3+RC1
  ├─ 问"成本构成/为什么贵" → PRODUCT_COST 按 COST_TITLE 归因
  ├─ 问"该不该保" → 保本线法(§4.6)
  └─ 默认口径无数据 → 如实说明+给替代口径，不得静默换
```

回答必须交代四件事：**账期** + **口径** + **范围**(产线/钢种/半成品) + **校验结论**(与主表差多少)。

---

## 9. FAQ 速配表（标准问题 → 口径一键映射）

| 用户问法 | 口径 | 落点 | 必带过滤 |
|---|---|---|---|
| 昨天 X 产线成本多少 | V1+DS3 | PRODUCT_COST÷PRODUCT_EARN | COMPANY_CODE, COST_CENTER, 精确账期 |
| 这个月 X 产线月累成本 | V1+DS4 | 同上 | 同上 |
| X 钢种成本多少 | V1+DS3+钢种 | 同上 ⋈ CDT8 | LOADER='1' |
| 标准成本多少 | V4 | SG_SIGN_COST (YYYYMMDDV4) | 账期后缀 V4 |
| X 钢种为什么贵 | 可加分解 | PRODUCT_COST GROUP BY COST_TITLE | 残差必须为 0 |
| 成本构成是什么 | 科目归因 | 同上 ⋈ CDT7 | COMPANY_CODE='100' |
| 边际贡献多少 | V1+DT4+RC2 | SIDE_COST | VISABLE_FLAG='Y', ORDER_SEQ=1 |
| 利润多少 | 同上 | 同上 | 同上 |
| 这个品种该不该保 | 保本线法 | 同上 | 六列加总=边际−利润 |
| 月度品种效益全景 | — | GRADE_BENEFIT | ACCOUNT_PERIOD='YYYYMM' |
| 今天成本出了吗 | — | 新鲜度+主表产量对比+日志表 | 三步判断 |
| 某科目为什么没进成本 | — | CACC_LOGS | CAL_DATE+JOB_CODE |

---

## 10. 链路可用性自证清单

当怀疑"表不存在/链路中断"时，先跑这 5 条。任一条返回 0，先怀疑自己的 schema/表名/条件，**不是怀疑表不存在**：

| # | 自证项 | SQL | 期望值 |
|---|---|---|---|
| ⓪ | 确认 schema | `SELECT RTRIM(TABSCHEMA) FROM SYSCAT.TABLES WHERE TABNAME LIKE '%CDT8%'` | SMBB_M_S_CB00 |
| ① | 映射表存在 | `SELECT COUNT(1) FROM SMBB_M_S_CB00.T_DWD_FACT_CACB_CDT8` | **28,072** |
| ② | 钢种可映射 | `...WHERE COMPANY_CODE='100' AND LOADER='1' AND TRIM(SG_SIGN)='20CrMnTiH'` | **61** |
| ③ | 成本事实有数 | `SELECT COUNT(1) FROM ...PRODUCT_COST WHERE ACCOUNT_PERIOD='...V1' AND DATA_SOURCE='3' AND COST_CENTER='100430802'` | **≥0** |
| ④ | 产量事实有数 | `SELECT COUNT(1) FROM ...PRODUCT_EARN WHERE ...` | **≥0** |
| ⑤ | 端到端现算 | §4.1 模板 | 产生具体数值 |

> 判断原则：取不到数时，优先怀疑顺序：SQL 写对了吗 → 这层有这个字段吗 → 这个口径存在吗 → 最后才怀疑"数据没跑/表不存在"

---

## 11. 产量口径差异（成本表 vs 边际贡献表）

- 成本表 `EARN_N` = **挣得量**（工序产出，含内部移交）
- 边际贡献表 `EARN_N` = **商品材/可售量**
- 中板比值 61.3%、圆棒 97.7%、五线合计 77.1%
- **算单位成本用成本表 EARN_N；算单位边际贡献/利润用边际贡献表 EARN_N。绝不能交叉。**

---

## 12. 过程日志排查

`SMBB_M_S_CB00.T_DWD_FACT_CACC_LOGS`（约 132.5 万行）：
- `CAL_DATE`=带版本后缀的日期（如 `20261018V1`）
- `JOB_CODE`=出问题的存储过程名
- `ERROR_TYPE='B-无分离规则'` 是最常见非致命告警

三步判断"今天成本出了没有"：① 查新鲜度 → ② 查主表产量 vs 分钢种汇总 → ③ 查日志表

---

## 13. 过程全景

**总调度**：`P_AUTOMATION_COST_DAY`

**实际成本链（C 系列）**：取附加成本/库存 → 生成预测 → 生成分摊因子与比例 → 非生产性结转 → 无产量平移 → 产品成本分离 → 落 DWD

**预算链（S 系列）**：标准编制 → 预算平衡 → 非生产性结转 → 产品差异结转 → 毛利计算

S 算"应该多少"（标准/预算），C 算"实际多少"。两者之差=成本差异，由 S070 处理。

---

## 14. 数据新鲜度

| 表 | 最新账期 | 格式 |
|---|---|---|
| `PRODUCT_COST` / `PRODUCT_EARN` | `YYYYMMDDV1/V3/V7/V8/V9` | 每天，DS3 与 DS4 并行 |
| `SG_SIGN_COST` | `YYYYMMDDV4` | **仅 V4** |
| `SIDE_COST` | `YYYYMMDDV1/V3/V5/V6` | 每天 |
| `DAY_COST` | `YYYYMMDDV1` | 每天 76 行 |
| `GRADE_BENEFIT` | **`YYYYMM`（6 位）** | **滞后约 1 个月** |

通用新鲜度检查：`SELECT ACCOUNT_PERIOD, COUNT(1) FROM ... WHERE ACCOUNT_PERIOD LIKE '20%V_' GROUP BY ACCOUNT_PERIOD ORDER BY ACCOUNT_PERIOD DESC`

---

## 15. 采购单价溯源（原燃料类能追，能源/投坯料不能 · 2026-10-19打通）

**"成本科目单价从哪来、能不能追到采购价"**：

| 类别 | 能否溯源 | 原因 |
|------|:--:|------|
| **原燃料类**（1xxxx科目，A码物料） | ✅ 能 | ODS→PUR_DAY→MAT_INFO→CONSUME_DAY→PRODUCT_COST 五段全通 |
| 能源介质（601xx，N码物料） | ❌ 不能 | N码是内部编码，采购价表里全没有 |
| 投坯料（10170） | ❌ 不能 | CONSUME_DAY 里 MAT_CODE 为空，成本来自上游工序结转 |

**实测打通效果（202610月）**：35 组科目×物料中 26 组可取采购价，平均偏差 4.43%，覆盖金额 71.4%。

**关键表**：`SMBB_M_S_CB00.T_DWD_FACT_CBZX_CACA_PUR_DAY`（采购价·无版本后缀）← `P_DWD_FACT_CBZX_CACA_PUR_DAY_NEW` 按月全量重刷

取数要点：
- `CONSUME_DAY.ACCOUNT_PERIOD` = `YYYYMMDD`（无版本后缀），`PUR_DAY` 同理
- `PUR_DAY.DATA_TYPE='1'`=原燃料，`'2'`=半成品（当前全表 0 行）
- `MAT_CODE LIKE 'A%'` 取原燃料编码

---

## 16. 滚存价 vs 采购价（✅ 已确证：成本单价 = 滚存期末价）

> **成本侧不用当月采购均价，用滚存（出库加权平均）价。**

**铁证**：`SMBB_M_S_CB00.T_DWD_FACT_CACC_IQMN`（实际域滚存表 × 物料级）的 `END_AMOUNT ÷ END_QUANTITY` 与 `PRODUCT_COST.COST ÷ CONSUME_DAY.CONSUME`，**27/27 科目精确一致，误差仅浮点级**。

**两种价格的差异**（4.43% 不是错误，是固有差异）：

| | 采购均价 | 滚存期末价 |
|---|---|---|
| 口径 | 当月采购加权均价 | 期初+收入−发出 后的库存加权平均 |
| 含期初 | 否 | **是** |
| 原料涨价时 | **领先** | **滞后**（库存还在摊薄） |

> **做量价分析必须两个价同时看**：采购价解释"市场"，滚存价解释"账上"。

---

## 17. 对比分析可比性规范（横向对比前必读）

> **错把结构差当绩效差，是最常见的分析事故。**

**三档可比性**：A（同牌号×同工序/同产线环比·可下结论）| B（同产线同比·可下结论）| C（相似产线结构对比·仅参考）| ✗ 跨工艺路线平均成本·严禁对比

**本厂唯一可做的 A 级对比**：**二高 vs 三高线**（11 个共同牌号，三高系统性高 +142.24 元/吨）

**三类不可比（都会被误认为可比）**：
1. 跨工艺路线：圆棒 vs 中板（差在工+费+回收结构，不是效率）
2. 成品 vs 半成品：中板 vs 中板坯（COST_CENTER=1004506 vs 1004505）
3. 小批量失真：产量 < 50t 的钢种不能纳入对比

**横向结论强制自检**：同钢种 ✓ / 同生产阶段 ✓ / 同口径 ✓ / 双侧≥50t ✓ / 结论是效率还是结构？

---

## 18. 与其他技能的边界

| 场景 | 用谁 |
|---|---|
| **成本域物理结构/血缘/口径** | **本技能** |
| 日成本建模与预测 | `sg-cost-ops` |
| 成本异常检测 | `sg-anomaly-detect` |
| 成本批次监控 | `sg-cost-ops` |
| 成本日报报表 | `sg-cost-ops` |
| 生产-成本双轮管控 | `sg-cost-ops` |
| 业务语义 | `sg-semantic-layer` |
| 意图解析与路由 | `sg-intent-parse-dispatch` |
| 智能问数主流程 | `sg-nl2sql-query` |

### 知识库协同（强制）

本技能全部知识源（同一优先级）：
① **权威手册**：`knowledge/domains/cbprod/三钢成本域与利润域_数据口径与计算链路权威手册.md`（103KB，2026-10-19更新：20章/38坑/采购溯源/滚存确证/对比规范/附录ABC）
② 三份指标血缘文档 + `T_ADS_DIM_GZ01.csv`（指标口径与 SQL1）
③ 域知识文档：`成枢_成本域CBPROD_知识库文档.md`
④ DB2 实表查询（仅前三层缺失时）

**协同铁律**：血缘文档 SQL 与 SQL1 执行结果必须交叉对拍，相对误差 >1e-6 触发复算/告警。

---

## 19. 成本结论交付规范

回答必须交代四要素：**账期+口径+范围+校验结论**。

数据规范：单位成本 4 位小数、金额 2 位小数、产量 3 位小数。科目必须中文名。差异必须带符号(+/-)。

结论结构：① 一句话答案（数字+单位+口径）→ ② 关键差异/归因 → ③ 机理说明 → ④ 可行动建议 → ⑤ 待确认项显式标注。