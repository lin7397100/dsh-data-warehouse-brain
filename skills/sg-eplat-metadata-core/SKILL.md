---
name: sg-eplat-metadata-core
description: "EPLAT 5S 平台设计态元数据控制面（MCP 直连版）。经 mcp__eplat__oracle_* 只读查询业务术语/数据元/业务对象/业务过程/四级指标/事实维度模型/字段 UUID/表字段血缘/数据质量/数据安全/数据服务 API，并给出 5S 平台落地清单（BEDF52→BEDK01→BEDF54→BEDK02/BEDK03→BEDD00→BEDR17）。触发词：EPLAT、5S平台已有指标、指标查重、业务术语、数据元、业务过程、DY_MO_FM、字段UUID、数据质量规则、数据安全标准、D_A API、M_ 服务单元、指标在5S落地。"
version: 1.1.0
author: SanSteel Data Warehouse Brain
tags: [sangang, eplat, 5s, metadata, oracle, mcp]
owner: sg-metadata
dispatch: true
tools_required: [mcp__eplat__oracle_query, mcp__eplat__oracle_describe_table, mcp__eplat__oracle_list_tables, mcp__eplat__oracle_ping]
---

# sg-eplat-metadata-core · EPLAT 5S 平台元数据控制面

## 0. 一句话定位

本技能回答三件事：**平台里已经有什么**（查重）、**它们怎么连**（UUID→字段→模型→表→ETL 步骤→血缘）、**要怎么落地到 5S**（可执行开发清单）。

> **三权分立（不可混用）**：EPLAT = 5S **设计态**元数据权威；DB2 = **运行态**数据权威；WeKnora K7 = **5S 开发规范**权威。
> 冲突时：数值取 DB2、设计对象取 EPLAT、开发规范取 K7；**冲突必须显式披露，禁止静默择一**。

## 1. 通道与边界（MCP 直连，2026-11-25 实测）

| 项 | 值 |
|---|---|
| MCP 服务 | `eplat`（`@deepseek-ai/dsh-mcp-client`，streamable-http） |
| 端点 | `http://10.18.136.38:8770/mcp`（可用 `SG_EPLAT_MCP_URL` 覆盖） |
| 服务端 | `oracle-mcp 1.0.0` → Oracle 19c，`current_schema=KETTLE`，`write_privileges_held=[]` |
| 元数据库 | schema `EPLAT`，809 张表，表名以 `TBED*` 为主 |
| 只读边界 | 仅 `SELECT` / `WITH` 开头的**单条**语句；禁止 DDL/DML；禁止无边界全库扫描 |

**四个 MCP 工具（唯一合法入口）**：

| 工具 | 必填 | 可选 | 用法要点 |
|---|---|---|---|
| `mcp__eplat__oracle_ping` | — | — | 开工自检：连通性 + 版本 + schema + 写权限 |
| `mcp__eplat__oracle_describe_table` | `table` | `owner`(默认 EPLAT) | 查列名/类型/长度/可空；**写 SQL 前先 describe，禁止猜列名** |
| `mcp__eplat__oracle_list_tables` | — | `owner`/`pattern`/`limit` | 按表族定位，`pattern` 如 `TBEDF5%` |
| `mcp__eplat__oracle_query` | `sql` | `max_rows`(默认200/上限2000)、`timeout_ms`(默认30000) | 只读取数；大表统计显式传 `max_rows` |

> **返回体格式**：工具返回是**文本 + 内嵌 ```json 代码块**，需先提取 `{`…`}` 再解析 `columns` / `rows` / `truncated`；`truncated=true` 说明命中行数上限，必须收窄条件或调大 `max_rows`（≤2000）。

**实测坑位（2026-11-25 用 Q00~Q17 全模板跑通后固化，别再踩）**：

| 坑 | 现象 | 正确做法 |
|---|---|---|
| 视图字典写错 | `ALL_TAB_VIEWS` → `ORA-00942` | 用 `ALL_VIEWS` |
| CLOB 截断过长 | `DBMS_LOB.SUBSTR(x,4000,1)` → `ORA-06502` | amount **≤2000**（AL32UTF8 字节缓冲） |
| 别名用 `LEVEL` | `AS level` → `ORA-00923` | 改 `AS idx_level` |
| `ORDER BY` 用别名 | UNION 后 `ORDER BY t` 报 `ORA-00904` | 去掉 ORDER BY 或写完整列名 |
| 占位符直接发 | `:uuid` 原样发送 → 语法错 | MCP 不支持绑定变量，**先替换为字面量** |
| 血缘列当字段名 | `TBEDG93.*_COLUMN_NAME` 实际存 UUID | 见 §5.3，先解析 `DY_TB_TF_00_` → `TBEDG2102` |
| `API_ID` 当单值 | `WHERE API_ID='D_A_...'` 查不到 | `API_ID = MODEL_ID \|\| '.' \|\| API_NAME`（复合键） |

**降级**：MCP 不可达时，如实报「EPLAT 设计态不可达」并给出 5S 平台页面路径（BEDF52/BEDF54/BEDK02 等）供人工核对；**禁止**用记忆、DB2 表名或历史文档冒充 EPLAT 设计态结论。

## 2. 开工三步（每次必做，禁止跳步）

1. **ping**：`oracle_ping` 确认连通与只读边界（`write_privileges_held` 必须为 `[]`）。
2. **describe**：涉及的表先 `oracle_describe_table`，拿到真实列名再写 SQL。
3. **query**：一次一条语句，先 `WHERE` 收窄（UUID / 表名 / 关键词），再聚合；数量结论一律 `COUNT(*)` 实查，**`ALL_TABLES.NUM_ROWS` 不作结论**。

## 3. 七类资产速查（实测 2026-11-25，`COUNT(*)`）

| 资产类 | 主表 | 实测规模 | 锚点字段 |
|---|---|---:|---|
| 业务术语 | `TBEDF11` | 1,184 | `UUID`(`DY_EL_00_00_`)、`ELEMENT_ENAME/CNAME` |
| 数据元 | `TBEDF12` | 29,187 | `UUID`、`FIELD_ENAME/CNAME`、`MEASURE_UNIT`、`OBJECT_UUID` |
| 业务对象 | `TBEDF15` | 180 | `UUID`(`DY_BO_00_00_`)、`OBJECT_ENAME/CNAME` |
| 业务过程 | `TBEDF33` | 361 | `UUID`(`DY_NO_00_00_`)、`PROCESS_CODE/NAME`、`AREA_UUID` |
| 数据域 | `TBEDG43` | 17 | `DOMAIN_ID/EN/CNAME`、`PARENT_DOMAIN_ID` |
| 业务指标 L1 | `TBEDF51` | 1,210 | `UUID`(`DY_IN_BS_00_`)、`INDEX_0_*`、`CALCULATE_FORMULA` |
| 原子指标 L2 | `TBEDF54` | 1,065 | `UUID`(`DY_IN_TC_00_`)、`EXPRESSION`、`MODEL_UUID` |
| 派生指标 L3 | `TBEDF5401` | 2,238 | `UUID`、`INDEX_1_UUID`、`INDEX_2_TABLE_JSON`（733 含计算逻辑） |
| 复合指标 L4 | `TBEDF5403` | 600 | `UUID`、`EXPRESSION`、`STATIS_DIMENSION`、`DIM_ALIAS` |
| 事实模型 | `TBEDF5204` | 1,009 | `UUID`(`DY_MO_FM_00_`)、`MODEL_ENAME/CNAME`、`PHYSICAL_STATE` |
| 维度模型 | `TBEDF5203` | 198 | `UUID`(`DY_MO_DM_00_`)、`MODEL_ENAME/CNAME`、`DIMENSION_TYPE` |
| 事实字段 | `TBEDF5208` | 60,442 | `UUID`、`FACT_UUID`、`FIELD_ENAME`、`MEMO` |
| 维度字段 | `TBEDF5207` | 1,333 | `UUID`、`DIMENSION_UUID`、`FIELD_ENAME` |
| 数据资源实体 | `TBEDG2101` | 4,306 | `UUID`(`DY_TB_TN_00_`)、`TABLE_ENAME/CNAME`、`HAS_BLOOD` |
| 物理数据资源字段 | `TBEDG2102` | 202,268 | `UUID`(`DY_TB_TF_00_`)、`TABLE_UUID`、`FIELD_ENAME`、`MEMO` |
| 表级血缘 | `TBEDG91` | 13,641 行 / **11,095 去重边** | `SRC/DEST_TABLE_GUID`、`DISPATCH_ID` |
| 字段级血缘 | `TBEDG93` | 90,266 行 / 89,248 去重边 | `SRC/DEST_COLUMN_NAME`、`DISPATCH_ID` |
| 数据质量规则 | `TBEDD05` | 224 | `UUID`(`DS_TK_DQ_00_`)、`RULE_NAME`、`BLOCK_TYPE`、`IS_ENABLE` |
| 数据安全标准 | `TBEDF6101~6103` | 3 / 4 / 2 | `SAFETY_CODE_RANK`(L1~L3)、`IMPORTANT_CODE_RANK`(P0~P3)、`RISK_CODE_RANK` |
| 数据服务 API | `TBEDM11` | 4,005（`D_A*`） | `API_NAME`、`MODEL_ID`(`M_*`)、`API_SQL`、`SAFETY_LEVEL` |

完整表族与 JOIN 路径见 `references/eplat_asset_map.md`；可复制 SQL 见 `references/eplat_sql_templates.sql`（Q00~Q17）。

## 4. UUID 前缀判型（**最高频防错规则**）

| 前缀 | 含义 | 解析表 |
|---|---|---|
| `DY_IN_BS_00_` | 业务指标 UUID | `TBEDF51.UUID` |
| `DY_IN_TC_00_` | 技术指标 UUID（原子/派生/复合） | `TBEDF54/5401/5403.UUID` |
| `DY_MO_FM_00_` | **事实模型字段** UUID | `TBEDF5208.UUID` |
| `DY_MO_DM_00_` | **维度模型字段** UUID | `TBEDF5207.UUID` |
| `DY_MO_ER_00_` | ER 模型 UUID | `TBEDF5209.UUID` |
| `DY_EL_00_00_` | 业务术语 UUID | `TBEDF11.UUID` |
| `DY_FD_00_00_` | 数据元 UUID | `TBEDF12.UUID` |
| `DY_NO_00_00_` | 业务过程 UUID | `TBEDF33.UUID` |
| `DY_BO_00_00_` | 业务对象 UUID | `TBEDF15.UUID` |
| `DY_TB_TN_00_` | 物理表 / 数据资源 UUID | `TBEDG2101.UUID` |
| `DY_TB_TF_00_` | **物理数据资源字段** UUID（血缘用） | `TBEDG2102.UUID` |
| `DS_TK_DQ_00_` | 数据质量规则 UUID | `TBEDD05.UUID` |
| `DS_TK_SQ_00_` | **ETL 加工步骤 UUID**（血缘边的执行实体） | `TBEDD0105.STEP_UUID` |

> **两套字段体系，千万不能混**：
> - **模型字段**（指标表达式里 `${}` 用的）：事实 `TBEDF5208`、维度 `TBEDF5207` —— 这是「设计模型字段」。
> - **物理字段**（血缘 `TBEDG93.*_COLUMN_NAME` 里存的）：`TBEDG2102` —— 这是「落表字段」。
> 同一个业务字段在两套体系里 UUID 不同，**跨链时必须显式换算并说明用的是哪一套**。

**典型误判纠正**：

```text
#{sum}(${DY_MO_FM_00_c0314be176764e2e8667ddb2f897ad4f})
```

- ❌ 错：把 `DY_MO_FM_00_xxx` 当原子指标 UUID
- ✅ 对：它是**事实模型字段 UUID** → `TBEDF5208.UUID` → `FIELD_ENAME` / `MEMO` → `FACT_UUID` → `TBEDF5204.MODEL_CNAME`
- 查不到时标注「**失效引用**」，禁止改写成「原子指标 UUID」，也不得笼统说「全库查无字段」

**表达式语法**：`#{sum|count|avg|max|min}` = 聚合函数；`${DY_MO_FM_00_xxx}` = 字段 UUID 引用；`${字段} 运算符 值` = 通用限定。

## 5. 四条链（必须逐环给出）

### 5.1 四级指标链

```text
业务指标 TBEDF51.UUID (DY_IN_BS_00_)
  → TBEDF5406.BUSINESS_INDEX_UUID / TECHNOLOGY_INDEX_UUID
    → 技术指标 TBEDF54 / TBEDF5401 / TBEDF5403.UUID (DY_IN_TC_00_)
      → TBEDF5404.INDEX_TYPE = 1原子(1,067) / 2派生(2,239) / 3复合(600)
      → 原子 TBEDF54.MODEL_UUID → TBEDF5204 事实模型 / TBEDF5203 维度模型
      → 派生 TBEDF5401.INDEX_1_UUID → 原子；INDEX_2_TABLE_JSON → 聚合/过滤/字段引用
      → 复合 TBEDF5403.EXPRESSION → 派生/原子之间的算术运算
```

### 5.2 字段 UUID 解析链

```text
TBEDF5208.UUID
  → FIELD_ENAME / MEMO / FIELD_DESC
  → FACT_UUID → TBEDF5204.UUID → MODEL_ENAME / MODEL_CNAME
  → MODEL_ENAME 对照 TBEDG2101.TABLE_ENAME（设计模型名 ≠ 物理表名，须再确认）
```

维度字段同理：`TBEDF5207.UUID → DIMENSION_UUID → TBEDF5203`。

### 5.3 血缘 → 加工步骤回溯链（已实测自证）

```text
TBEDG91/TBEDG93.DISPATCH_ID (= DS_TK_SQ_00_...)
  → TBEDD0105.STEP_UUID
  → STEP_ALIAS（P_ 加工步骤名）
  → DBMS_LOB.SUBSTR(STEP_DEFINITION, 2000, 1)（加工 SQL）
```

实证：`T_ADS_SRV_CGWL_CLKC08` → `DISPATCH_ID = DS_TK_SQ_00_63e02d...` → `STEP_ALIAS = P_ADS_SRV_CGWL_CLKC08`（`HIT_STEP`）。

**字段级血缘的列是 UUID，不是字段名**（原基线文档误判，已纠正）：

```text
TBEDG93.SRC_COLUMN_NAME / DEST_COLUMN_NAME
  ├─ DY_TB_TF_00_... → TBEDG2102.UUID → FIELD_ENAME / MEMO / TABLE_UUID（物理字段，67,922 条 DEST 侧）
  └─ DY_TB_TN_00_... → TBEDG2101.UUID（整表流转行，22,344 条 DEST 侧）
解析字段名必须 JOIN TBEDG2102 且用 COALESCE 兜住表级行，否则漏 2 万+ 边
```

> ⚠ **血缘边会重复**：`TBEDG91` 13,641 行只有 11,095 条去重边（同 src/dest/dispatch 多行）。统计血缘条数、算影响面**必须 `COUNT(DISTINCT ...)` 或 `DISTINCT`**，否则重复计数。

### 5.4 5S 落地链（专家团沉淀 → 平台开发，7 步顺序不可颠倒）

| 步 | 动作 | EPLAT 取证 | 平台落点 |
|---|---|---|---|
| 1 查重 | 按中/英文名查是否已有指标（Q13） | `TBEDF51/5401/5403` | — |
| 2 定域 | 选数据域，对齐业务过程/对象 | `TBEDG43`、`TBEDF33`、`TBEDF15` | — |
| 3 定模型 | **先维度模型，再事实模型**（含字段） | `TBEDF5203/5204`、`TBEDF5207/5208` | BEDF52 → BEDK01 物化 → BEDP1004 审批 |
| 4 定指标 | 原子（表达式）→ 派生（统计维度+限定）→ 复合（算术） | `TBEDF54`、`TBEDF5401`、`TBEDF5403` | BEDF54 / BEDK02 / BEDK03 |
| 5 定加工 | 加工步骤 + 表/字段血缘 | `TBEDD0105`、`TBEDG91/93` | BEDK02/BEDK03 生成、BEDD00 编排、BEDD0002 审批 |
| 6 定服务 | 服务单元 → API + `API_SQL` + 参数 | `TBEDM1105`、`TBEDM11`、`TBEDM12` | BEDR17 上线 |
| 7 定治理 | 质量规则 + 安全分级/授权 | `TBEDD05`、`TBEDF6101~6110` | 交 `sg-governance` 审查 |

**顺序铁律**：维度模型必须先于事实模型并完成物化；事实明细模型必须先于原子指标；**数据起点在 ODS，禁止把 ODS 表直接当事实明细模型绑原子指标**。

## 6. 输出规范（缺项即不合格）

- 必标：`EPLAT 表名 + 关键字段 + UUID + 中文/英文名`。
- 指标：四级链路 + `INDEX_TYPE`；字段引用必须解析到字段名与所属模型。
- 血缘：`DISPATCH_ID → STEP_UUID → STEP_ALIAS`；查不到写 `unknown`，**禁止补造**。
- 落地清单：页面号 + 对象名（含 `_01` 后缀）+ 依赖对象 + 审批号 + API 名/服务单元名。
- 数量：附 `COUNT(*)` 实查 SQL。
- **双锚点并存**：`EPLAT UUID` + `ZB_CODE（如有）` + 物理表/字段 + `STEP_UUID/STEP_ALIAS`，禁止互相替代。

## 7. 铁律（违反即结果作废）

1. **只读**：只发 `SELECT/WITH` 单条语句；任何写操作直接拒绝。
2. **先判 UUID 再解析**：`DY_MO_FM_` 不是指标 UUID，`DY_IN_TC_` 不是字段 UUID。
3. **先查重再新建**：平台已有同义指标优先复用，不重复开发（Q13）。
4. **禁止猜列名**：写 SQL 前先 `describe_table`；MCP 报 `ORA-00904` 时先 describe 再改，不许反复试错。
5. **NUM_ROWS 不作结论**：一律 `COUNT(*)`。
6. **空表不算证据**：`TBEDG92`、`TBEDD0501`、`TBEDF6110~6112`、`TBEDF1502` 为空，不能据此断言「无血缘/无质量结果/无权限要求」；须用 `TBEDG91/93`、`TBEDD05/0506` 交叉核验并按**从严**披露。
7. **血缘去重**：`TBEDG91/93` 存在重复边，统计必须 `DISTINCT`。
8. **CLOB 纪律**：`RULE_CONTENT`、`API_SQL`、`STEP_DEFINITION` 是 CLOB —— 禁止 `TRIM()`、禁止直接 `=`/`LIKE` 大字段，读取用 `DBMS_LOB.SUBSTR(col, n, 1)`。
9. **安全分级不可等同**：EPLAT `L1/L2/L3`（一级/二级/三级）与本团 `L1~L4` 不是一套编号，必须显式映射并经 `sg-governance` 确认；冲突按**从严**处理并披露。
10. **拒绝即结论**：查不到就写「设计态缺失 / 失效引用」，不许拿 DB2 运行态或历史文档冒充设计态。

## 8. 交接分工（谁该调谁）

| 场景 | 主责 | 本技能提供 |
|---|---|---|
| 指标查重 / 四级链 / 落地清单 | `sg-metric-builder` | Q03、Q13、落地 7 步 |
| 术语 / 数据元 / 口径消歧 | `sg-semantic` | Q14 + `maturity` 提醒（登记 ≠ 校准） |
| 域 / 对象 / 过程 / ER 入图 | `sg-ontology` | Q15 + 9 类本体对象映射 |
| 字段解析 / 表字段血缘 / API | `sg-metadata`（**本技能 owner**） | Q02、Q04~Q07、Q10~Q12 |
| 质量规则 / 安全分级 | `sg-governance` | Q08、Q09 |
| 页面操作 / 审批步骤 | `sg-5s-dev` / `sg-5s-qa` | 落地链 7 步的平台落点列 |
| 设计态与运行态对拍 | `sg-quality`（根因） | 双锚点 + 血缘步骤 |

**唯一通道纪律**：`mcp__eplat__*` 只挂在 7 个 EPLAT 主责专家身上（本技能 owner `sg-metadata` 为主）。其他专家需要设计态对象时，**向对应主责专家索取结论**，不得自行猜测 UUID 或表名。

## 9. 参考文件

| 文件 | 内容 |
|---|---|
| `references/eplat_asset_map.md` | 七类资产完整表映射、字段、关系链、实测样例、与 DB2 的锚点对照 |
| `references/eplat_sql_templates.sql` | Q00~Q17 共 18 组只读 SQL（自检 / 盘点 / 判型 / 四条链 / 查重 / 质量 / 安全 / API / 物理字段解析），2026-11-25 已全部实跑通过 |
