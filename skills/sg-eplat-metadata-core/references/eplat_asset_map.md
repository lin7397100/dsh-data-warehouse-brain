# EPLAT 5S 平台七类资产映射（MCP 实测版）

> 取证时间：**2026-11-25**（DSH 侧经 `mcp__eplat__oracle_*` 直连复测）
> 数据源：`oracle-mcp 1.0.0` → Oracle 19c，`owner=EPLAT`，`current_schema=KETTLE`，`write_privileges_held=[]`
> 规模口径：全部为 `COUNT(*)` 实查；`ALL_TABLES.NUM_ROWS` 仅参考，不作结论。
> 列名口径：全部经 `oracle_describe_table` 核对（勿凭记忆写列名）。

## 0. 总览

EPLAT 是大数据 5S 平台的**设计态元数据控制面**，不是业务数据表。专家团要把沉淀的指标体系落地到 5S，必须以 EPLAT 作为查重、定域、建模、加工、服务、治理的入口。

```text
业务术语 / 数据元 / 业务对象 / 业务过程 / 数据域
        ↓ 约束与命名
业务指标 → 原子指标 → 派生指标 → 复合指标
        ↓ 依赖
维度模型 / 事实模型 / ER 模型 → 模型字段 → 数据资源实体（物理表）
        ↓ 加工
TBEDD0105（P_ 步骤）→ TBEDG91 / TBEDG93（表级 / 字段级血缘）
        ↓ 服务
TBEDM1105（M_ 服务单元）→ TBEDM11（D_A API + API_SQL）→ TBEDM12（参数）
        ↓ 治理
TBEDD05 质量规则 + TBEDF6101~6112 安全 / 重要 / 风险 / 授权 / 脱敏
```

## 1. 业务术语与数据元

| 表 | 中文名 | 实测行数 | 关键字段（已 describe 核对） |
|---|---|---:|---|
| `TBEDF11` | 业务术语信息 | 1,184 | `UUID`, `ELEMENT_ENAME`, `ELEMENT_CNAME`, `ELEMENT_ID`, `ELEMENT_DOMAIN`, `ELEMENT_DESC`, `ELEMENT_USAGE`, `ELEMENT_TYPE`, `ELEMENT_STATE`, `IS_ENABLE`, `REFERENCE_COUNT`, `RELEASE_STATE` |
| `TBEDF12` | 数据元信息表 | 29,187 | `UUID`, `FIELD_ENAME`, `FIELD_CNAME`, `FIELD_TYPE`, `FIELD_LENGTH`, `MEASURE_UNIT`, `FIELD_DOMAIN`, `FIELD_DESC`, `FIELD_SAFETY`, `OBJECT_UUID`, `IS_NULL`, `FIELD_STATE`, `RELEASE_STATE` |
| `TBEDF1302` | 待补录业务术语 | 0 | `ELEMENT_UUID`, `ELEMENT_ENAME`, `ELEMENT_CNAME`（空表≠无术语） |

**UUID 前缀**：业务术语 `DY_EL_00_00_`；数据元 `DY_FD_00_00_`。

**对齐规则**：用户口语 → `TBEDF11.ELEMENT_CNAME/ENAME` → `TBEDF12.FIELD_CNAME/ENAME` + `MEASURE_UNIT` → 模型字段 UUID → 指标表达式。
术语命中**不等于**口径已校准，仍须走 `sg-semantic` 的 `maturity` 分级（`certified` / `draft` / `indexed`）。

## 2. 业务对象、业务过程、数据域、数据层级

| 表 | 中文名 | 实测行数 | 关键字段 |
|---|---|---:|---|
| `TBEDF15` | 业务对象 | 180 | `UUID`, `OBJECT_ENAME`, `OBJECT_CNAME`, `OBJECT_DESC`, `OBJECT_USAGE`, `OBJECT_RANGE`, `OBJECT_STATE`, `RELEASE_STATE` |
| `TBEDF1501` | 业务对象-工作空间 | 3 | `OBJECT_UUID` 等 |
| `TBEDF1502` | 业务对象-数据域 | 0 | `OBJECT_UUID`, `DOMAIN_UUID`（空表须按从严披露） |
| `TBEDF33` | 业务过程 | 361 | `UUID`, `PROCESS_CODE`, `PROCESS_NAME`, `PROCESS_DESC`, `AREA_UUID`, `PROCESS_OWNER`, `PROCESS_STATE`, `PROCESS_USAGE` |
| `TBEDG43` | 数据域 | 17 | `UUID`, `DOMAIN_ID`, `DOMAIN_ENAME`, `DOMAIN_CNAME`, `PARENT_DOMAIN_ID`, `OWNER_GROUP` |
| `TBEDF31` | 数据层级 | 5 | `UUID`, `LEVEL_ENAME`, `LEVEL_CNAME`, `PARENT_LEVEL_ID`, `LEVEL_RELATIVE_PRIORITY` |
| `TBEDG4301` | 数据域-分类关系 | 229 | `UUID`, `DOMAIN_UUID`, `AREA_UUID`, `WEIGHT` |

**实测 17 个数据域**：GG00 公共域、SMBBZZ00 制造、SMBBCB00 成本、SMBBCG00 采购、SMBBNY00 能源、SMBBLG00 炼钢、SMBBHP00 中厚板、SMBBYS00 云商、SMBBSB00 设备、SMBBHR00 人力、SMBBCW00 财务、SMBBYX00 营销、SMBBJX00 绩效、SMBBGC00 工程、SMBBLYMG00 罗源闽光、SMBBQZMG00 泉州闽光、SMBBZHKJ00 资环科技。

**实测 5 个数据层级**：源数据层(ODS)、公共数据层(CDM)、明细数据层(DWD)、汇总数据层(DWS)、应用数据层(ADS)。

**UUID 前缀**：业务过程 `DY_NO_00_00_`；业务对象 `DY_BO_00_00_`。

## 3. 四级指标体系

### 3.1 主表

| 层级 | 表 | 实测行数 | UUID 前缀 | 关键字段 |
|---|---|---:|---|---|
| L1 业务指标 | `TBEDF51` | 1,210 | `DY_IN_BS_00_` | `INDEX_0_ENAME/CNAME`, `INDEX_0_DEFINITION`, `CALCULATE_FORMULA`, `INDEX_0_STATE`, `INDEX_LEVEL`, `DEFINE_PERSON`, `MANAGER`, `CHECK_RESULT`, `CORRESPONDING_TABLENAME/FIELD`, `WORK_REGION_UUID` |
| L2 原子指标 | `TBEDF54` | 1,065 | `DY_IN_TC_00_` | `MODEL_UUID`, `INDEX_1_ENAME/CNAME`, `EXPRESSION`, `SOURCE_UUID`, `DEPT_NAME`, `CHECK_RESULT`, `APPLY_TYPE` |
| L3 派生指标 | `TBEDF5401` | 2,238 | `DY_IN_TC_00_` | `INDEX_1_UUID`, `INDEX_2_ENAME/CNAME`, `INDEX_2_TABLE_JSON`, `INDEX_2_FIELD`, `INDEX_2_VDOING`, `DIM_ALIAS`, `INDEX_TYPE`, `CALCULATION_DEF_VALUE`, `PHYSICAL_STATE` |
| L4 复合指标 | `TBEDF5403` | 600 | `DY_IN_TC_00_` | `INDEX_3_ENAME/CNAME`, `EXPRESSION`, `STATIS_DIMENSION`, `DIM_ALIAS`, `INDEX_TYPE`, `DATA_TYPE`, `PHYSICAL_STATE` |

### 3.2 关联表

| 表 | 中文名 | 实测行数 | 关键字段 | 说明 |
|---|---|---:|---|---|
| `TBEDF5404` | 目录与技术指标关系 | 3,906 | `UUID`, `INDEX_TYPE`, `INDEX_UUID`, `CATALOG_UUID` | `INDEX_TYPE`：1=原子 **1,067**、2=派生 **2,239**、3=复合 **600** |
| `TBEDF5406` | 业务指标-技术指标关联 | 1,432 | `BUSINESS_INDEX_UUID`, `TECHNOLOGY_INDEX_UUID` | 业务 → 技术映射 |
| `TBEDF5101` | 业务指标-数据域 | 1,085 | 业务指标 UUID、域 UUID | 域归属 |
| `TBEDF5102` | 业务指标-数据分类 | 1,200 | 业务指标 UUID、分类 UUID | 分类归属 |
| `TBEDF5405` | 技术指标-数据域 | 2,869 | 技术指标 UUID、域 UUID | 域归属 |

### 3.3 指标计算逻辑

- 原子指标：`TBEDF54.EXPRESSION` = `#{sum}(${DY_MO_FM_00_xxx})`（1,065 条全部有表达式）。
- 派生指标：`TBEDF5401.INDEX_2_TABLE_JSON`，形如 `#{sum}(${...})/#{count}(${...})`；**733 条含计算逻辑**（406 聚合 + 308 条件过滤 + 17 字段引用 + 2 常量），`sum` 出现 345 次为最主要聚合。
- 复合指标：`TBEDF5403.EXPRESSION` 为多指标算术运算，维度见 `STATIS_DIMENSION` / `DIM_ALIAS`。
- `#` = 聚合函数；`${}` = **模型字段 UUID**，不是指标 UUID。

## 4. 模型、字段与数据资源

| 表 | 中文名 | 实测行数 | 关键字段 |
|---|---|---:|---|
| `TBEDF5204` | 事实模型表 | 1,009 | `UUID`(`DY_MO_FM_00_`), `MODEL_ENAME/CNAME`, `PHYSICAL_STATE`, `RELEASE_STATUS`, `SAFETY_CODE_RANK`, `OWNER_GROUP`, `DATA_SOURCE` |
| `TBEDF5203` | 维度模型表 | 198 | `UUID`(`DY_MO_DM_00_`), `MODEL_ENAME/CNAME`, `DIMENSION_TYPE`, `IS_UNION_PK`, `PHYSICAL_STATE`, `RELEASE_STATUS` |
| `TBEDF5208` | 事实模型字段表 | 60,442 | `UUID`, `FACT_UUID`, `DIMENSION_FIELD_UUID`, `FIELD_ENAME`, `MEMO`, `FIELD_DESC`, `IS_PK`, `IS_PARTITION`, `SAFETY_CODE_RANK` |
| `TBEDF5207` | 维度模型字段表 | 1,333 | `UUID`, `DIMENSION_UUID`, `FIELD_ENAME`, `MEMO`, `IS_PK` |
| `TBEDF5209` | ER 模型表 | 44 | `UUID`(`DY_MO_ER_00_`), `MODEL_ENAME/CNAME`, `LEVEL_UUID`, `AREA_UUID`, `PHYSICAL_STATE` |
| `TBEDF5210` | ER 模型字段表 | 588 | `UUID`, `ER_UUID`, `FIELD_ENAME`, `MEMO` |
| `TBEDK01` | 维度表 | 382 | `UUID`, `DIMENSION_ENAME/CNAME`, `DIMENSION_TYPE`, `TABLE_UUID`, `AREA_UUID` |
| `TBEDK02` | 派生指标生成表 | 1,352 | `FACT_UUID`, `MODEL_UUID`, `DER_INDEX_ENAME/CNAME`, `PARAMETERS`, `COMMON_LIMIT`, `DIM_FIELD_NAME`, `INDEX_TYPE` |
| `TBEDK0201` | 复合指标生成表 | 214 | `MODEL_UUID`, `COMP_INDEX_ENAME`, `DER_INDEX_INFO`, `COMP_EXPRESSION` |
| `TBEDK03` | 指标汇总表 | 124 | `TABLE_UUID`, `DIM_FIELD_NAME`, `QUALITY_RULES`, `CONNECT_UUID` |
| `TBEDG2101` | 数据资源实体表 | 4,306 | `UUID`(`DY_TB_TN_00_`), `TABLE_ENAME/CNAME`, `MODEL_UUID`, `HAS_BLOOD`, `HAS_FIELD_BLOOD`, `SAFETY_CODE_RANK`, `IMPORTANT_CODE_RANK`, `RISK_CODE_RANK`, `ROW_COUNT`, `UPDATE_FREQUENCY` |
| `TBEDG2102` | 数据资源字段表（**物理字段**） | 202,268 | `UUID`(`DY_TB_TF_00_`), `TABLE_UUID`, `FIELD_ENAME`, `MEMO`, `FIELD_TYPE`, `DATA_ELEMENT`, `SAFETY_CODE_RANK` |

**两套字段体系（2026-11-25 实测澄清，最易混）**：

| 体系 | 用途 | 事实侧表 | 维度侧表 | UUID 前缀 |
|---|---|---|---|---|
| **模型字段** | 指标表达式 `${...}` 引用的设计模型字段 | `TBEDF5208` | `TBEDF5207` | `DY_MO_FM_00_` / `DY_MO_DM_00_` |
| **物理字段** | 血缘 `TBEDG93.SRC/DEST_COLUMN_NAME` 存的落表字段 | `TBEDG2102`（`TABLE_UUID`→`TBEDG2101`） | 同左 | `DY_TB_TF_00_` |

同一个业务字段在两套体系里 UUID 不同，**跨链时必须显式换算并说明用的是哪一套**。

**字段 UUID 解析链**：

```text
TBEDF5208.UUID = '${字段UUID}'
  → FIELD_ENAME / MEMO / FIELD_DESC
  → FACT_UUID → TBEDF5204.UUID → MODEL_ENAME / MODEL_CNAME
  → MODEL_ENAME 对照 TBEDG2101.TABLE_ENAME（设计模型名 ≠ 物理表名，须再确认）
```

维度字段同理：`TBEDF5207.UUID → DIMENSION_UUID → TBEDF5203`。

## 5. 数据加工与血缘

| 表 | 中文名 | 实测行数 | 关键字段 |
|---|---|---:|---|
| `TBEDD0105` | 数据加工步骤 | — | `STEP_UUID`(`DS_TK_SQ_00_`), `STEP_ALIAS`, `STEP_TYPE`, `STEP_DEFINITION`(CLOB), `PROJECT_NAME`, `PLUGIN_NAME` |
| `TBEDD0104` | 任务-步骤关系 | — | 任务 UUID、步骤 UUID |
| `TBEDD0101` | 任务信息 | — | 任务 UUID、任务名 |
| `TBEDG91` | 表级血缘 | 13,641 行 / **11,095 去重边** | `SRC_TABLE_GUID`, `DEST_TABLE_GUID`, `DISPATCH_ID`, `NODE_CODE`, `ENGINE_TYPE` |
| `TBEDG93` | 字段级血缘 | 90,266 行 / **89,248 去重边** | `SRC/DEST_TABLE_GUID`, `SRC/DEST_COLUMN_NAME`, `DISPATCH_ID` |
| `TBEDG92` | 血缘关系表（空） | 0 | 结构同 `TBEDG91`，当前为空，**不作权威源** |

**回溯链（已实测自证）**：

```text
TBEDG91/TBEDG93.DISPATCH_ID (= DS_TK_SQ_00_...)
  → TBEDD0105.STEP_UUID
  → STEP_ALIAS（如 P_ADS_SRV_CGWL_CLKC08）
  → DBMS_LOB.SUBSTR(STEP_DEFINITION, 2000, 1)（加工 SQL）
```

实证：`T_ADS_SRV_CGWL_CLKC08` → `DISPATCH_ID=DS_TK_SQ_00_63e02d344f844d15a61ad4aa398f0251` → `STEP_ALIAS=P_ADS_SRV_CGWL_CLKC08`（`HIT_STEP`）。

**字段级血缘列存的是 UUID（2026-11-25 纠正原基线误判）**：

```text
TBEDG93.SRC_COLUMN_NAME / DEST_COLUMN_NAME
  ├─ DY_TB_TF_00_... → TBEDG2102.UUID → FIELD_ENAME / MEMO / TABLE_UUID → TBEDG2101（物理字段）
  └─ DY_TB_TN_00_... → TBEDG2101.UUID（整表流转行）
```

实测分布（全表 `COUNT(*)`）：

| 侧 | `DY_TB_TN_00_`（表级） | `DY_TB_TF_00_`（字段级） |
|---|---:|---:|
| SRC | 70,241 | 18,943 |
| DEST | 22,344 | 67,922 |

→ 解析字段名必须 `JOIN TBEDG2102`，并用 `COALESCE` 兜住表级行，否则漏掉 2 万+ 边（模板 Q07）。

> ⚠ **重复边**：`TBEDG91` 13,641 行仅 11,095 条去重边、`TBEDG93` 90,266 行仅 89,248 条。统计血缘条数与影响面**必须 `DISTINCT`**，否则重复计数。

## 6. 数据质量

| 表 | 中文名 | 实测行数 | 关键字段 |
|---|---|---:|---|
| `TBEDD05` | 校验规则信息 | 224 | `UUID`(`DS_TK_DQ_00_`), `RULE_NAME`, `RULE_CONTENT`(CLOB), `TABLE_UUID`, `TABLE_NAME`, `SCHEMA_NAME`, `QUALITY_CODE_CLASSIFY`, `BLOCK_TYPE`, `IS_ENABLE`, `APPROVAL_STATUS`, `STEP_UUID` |
| `TBEDD0506` | 校验规则信息（扩展） | 223 | 在 `TBEDD05` 基础上多 `TEST_RULE`, `RULE_CATEGORY` |
| `TBEDD0501` | 校验结果信息 | 0 | 结果明细（空表≠无质量结果） |
| `TBEDA0404` / `TBEDA040401` | 质量问题指派 / 校验 | 0 / 0 | 问题分派与明细 |

**实测分类分布（`GROUP BY QUALITY_CODE_CLASSIFY, BLOCK_TYPE`）**：

| 分类 | 含义 | 合计 | 弱规则 `BLOCK_TYPE=0` | 强规则 `BLOCK_TYPE=1` |
|---|---|---:|---:|---:|
| `accuracy` | 准确性 | 175 | 157 | 18 |
| `integrity` | 完整性 | 43 | 16 | 27 |
| `authenticity` | 真实性 | 5 | 5 | 0 |
| `timeliness` | 及时性 | 1 | 1 | 0 |

> `BLOCK_TYPE=1` = 强规则/拦截型，未通过一票否决。`IS_ENABLE` / `APPROVAL_STATUS` 必须纳入审查：未启用或未审批的规则**不得作为放行依据**，但要披露。
> `RULE_CONTENT` 是 CLOB：禁止 `TRIM()`，读取用 `DBMS_LOB.SUBSTR(RULE_CONTENT, 2000, 1)`。

## 7. 数据安全

| 表 | 中文名 | 实测行数 | 取值 / 说明 |
|---|---|---:|---|
| `TBEDF6101` | 数据安全标准 | 3 | `SAFETY_CODE_RANK` = `L1/L2/L3`；`SAFETY_NAME` = 一级/二级/三级 |
| `TBEDF6102` | 数据重要标准 | 4 | `IMPORTANT_CODE_RANK` = `P0/P1/P2/P3` |
| `TBEDF6103` | 数据风险标准 | 2 | `RISK_CODE_RANK` = `normal` 普通 / `serious` 严重 |
| `TBEDF6104` | 群组-安全标准 | 102 | `LABEL_ID` + `SAFETY_CODE_RANK` 授权组关系 |
| `TBEDD1041` | 脱敏白名单配置 | 0 | 白名单（空≠无要求） |
| `TBEDD1042` | 脱敏全局配置 | 1 | 全局开关/规则 |
| `TBEDD1043` | 数据安全插件 | 1 | 插件配置 |
| `TBEDF6110~6112` | 行级授权策略 / 详情 / 作用表 | 0 / 0 / 0 | **空 ≠ 无权限要求，按从严处理** |

> ⚠ **编号不可等同**：EPLAT `L1/L2/L3`（一级/二级/三级）与本团 `L1~L4`（数据分级）**不是同一套编号**，必须显式映射并经 `sg-governance` 确认；冲突按**从严**原则处理并披露，禁止按数字直接等同。

## 8. 数据服务 API

| 表 | 中文名 | 实测行数 | 关键字段 |
|---|---|---:|---|
| `TBEDM1105` | 服务单元 | — | `MODEL_ID`(`M_*`), `PROJECT_NAME`, `PROJECT_UUID`, `NODE_ID` |
| `TBEDM11` | 数据服务 API | 4,005（`D_A*`） | `API_ID`, `API_NAME`, `MODEL_ID`, `API_SQL`(CLOB), `API_TYPE`, `API_STATUS`, `SAFETY_LEVEL`, `API_URL`, `API_DESC`, `OBJECT_UUID`, `PROCESS_UUID`, `DOMAIN_UUID` |
| `TBEDM12` | API 参数 | — | `PARAM_ID`, `PARAM_NAME`, `API_ID`, `FIELD_NAME`, `FIELD_CNAME`, `OPERATOR`, `REQUIRED`, `FIELD_UUID` |
| `TBEDG2214` | 服务单元-API 关联 | 3,770 | `MODEL_ID`, `API_ID` |

**实测样例**：`API_NAME=D_A_CGJX_PSCS_BJK2_001`，`MODEL_ID=M_DWD_FACT_CGJH_CLJH01_JX`，`API_TYPE=MULTI_SQL_API`，`API_SQL` 为完整 CTE SQL，可直接引用物理表（如 `SMBB_M_S_CG00.T_DWD_FACT_CGDD_CLDD04`）。服务单元前缀分布：`M_D` 2,429、`M_A` 1,532、`M_P` 18；上线页面 BEDR17。

## 9. 与 DB2 运行态的锚点关系（双锚点纪律）

| 锚点 | 所属域 | 用途 | 不可互替的原因 |
|---|---|---|---|
| `EPLAT.UUID` | 5S 设计态 | 指标/模型/字段/API 唯一身份 | 平台对象身份，跨环境稳定 |
| `T_ADS_DIM_GZ01.ZB_CODE` | DB2 运行态 | KPI 配置/报表展示 | 只有 DB2 侧有 SQL1/SQL2/CREATER 与实际口径 |
| `TBEDG2101.TABLE_ENAME` | 物理表 | 表级落点 | 设计模型名与物理表名可能不同 |
| `TBEDD0105.STEP_UUID` / `STEP_ALIAS` | ETL 步骤 | 加工 SQL 落点 | 是血缘边的执行实体 |

专家团输出必须同时保留：`EPLAT UUID` + `ZB_CODE（如有）` + 物理表/字段 + `STEP_UUID/STEP_ALIAS`；**禁止用一个覆盖另一个**。

## 10. 2026-11-25 复测差异（相对 2026-11-24 基线）

| 项 | 11-24 基线 | 11-25 复测 | 说明 |
|---|---:|---:|---|
| `TBEDF5404` 目录技术指标 | 3,856 | **3,906** | 索引目录新增 50 条；分布 1,067 / 2,239 / 600 |
| `TBEDF5406` 业务-技术关联 | 1,423 | **1,432** | 新增 9 条映射 |
| `TBEDK01` 维度表 | 373 | **382** | 新增 9 张 |
| `TBEDK02` 派生指标生成 | 1,343 | **1,352** | 新增 9 条 |
| `TBEDF5210` ER 模型字段 | 588 | **605** | 新增 17 个 |
| `TBEDF5405` 技术指标-数据域 | 2,869 | **2,895** | 新增 26 条 |
| `TBEDG2214` 服务单元-API | 3,770 | **3,872** | 新增 102 条 |
| `TBEDG2102` 物理字段 | 未测 | **202,268** | 原基线缺失此表，本次补齐 |
| `TBEDM12` API 参数 | 未测 | **10,181** | 原基线缺失，本次补齐 |

> 结论：设计态资产在持续增长，**任何数量结论都必须当日 `COUNT(*)` 实查**，禁止把本文件数字当永久事实。

## 11. MCP 调用坑位速查（2026-11-25 全模板实跑固化）

| 坑 | 报错 | 修法 |
|---|---|---|
| 视图字典写错 | `ORA-00942`（`ALL_TAB_VIEWS` 不存在） | 用 `ALL_VIEWS` |
| CLOB 截断过长 | `ORA-06502: character string buffer too small` | `DBMS_LOB.SUBSTR(col, 2000, 1)`，amount ≤2000 |
| 别名 `LEVEL` | `ORA-00923: FROM keyword not found` | 改 `AS idx_level`（LEVEL 是伪列） |
| UNION 后 `ORDER BY 别名` | `ORA-00904: "T": invalid identifier` | 去 ORDER BY，或写完整列名 |
| 绑定变量 | 语法错（`:uuid` 原样发送） | MCP 不支持绑定，先替换为字面量 |
| 只取前 200 行 | `truncated=true` | 收窄 WHERE 或 `max_rows` 调大（≤2000） |
| `API_ID` 查不到 | 返回 0 行 | `API_ID = MODEL_ID || '.' || API_NAME` |
