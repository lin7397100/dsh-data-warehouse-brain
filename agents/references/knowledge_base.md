### 指标血缘与域知识库（按需加载 · 防上下文爆炸 · 最高优先级）

> **第 0 优先通道（2026-10-27 新增）：weknora 知识库检索 —— 本体/语义/指标/血缘/规范知识一律先经知识库检索，不再依赖本地硬编码。**
> **本地 `knowledge/kb/` 降级为离线兜底（weknora 不可达时使用）。**
> **T_ADS_DIM_GZ01 不再使用本地 CSV 镜像，改为通过 sg-db2-executor 执行 DB2 SQL 实时查询实表。**

#### weknora 七库（主通道 · MCP · 2026-10-28 六库分治 · 2026-11-02 增补 K7 大数据5S平台知识库）

| # | 知识库 | KB ID | 职责 |
|---|---|---|---|
| K1 | 数仓智脑专家团-表结构 | `0ae8e2cc-0770-4f4c-95fa-ababd7416292` | 物理数据模型（DDL 表结构） |
| K2 | 数仓智脑专家团-存储过程 | `7ff70441-7f55-48dd-8dfd-ebafe3a5b9a9` | 数据加工逻辑（过程/函数源码） |
| K3 | 数仓智脑知识库-指标体系 | `227f0a01-c36b-488a-8049-5b5869175782` | 指标语义与口径（IND/SEM/血缘/公式） |

> ### ⚠️ K3/K4 归属错位已知问题（2026-10-29 实测发现 · 待治理）
>
> **实测现象**：`SEM-语义-指标语义-GZPROD-分片01` 文档实际落在 **K4**(`6838e00b`) 而非规范要求的 **K3**(`227f0a01`)。
> **影响**：按「问口径 → K3」检索时，该分片**不会被命中**，可能漏掉语义条目。
> **临时对策（必须遵守）**：
> - 问「语义/同义词/maturity/置信度」类问题时，**必须同时检索 K3 和 K4**：
>   `knowledge_base_ids: ["227f0a01-c36b-488a-8049-5b5869175782", "6838e00b-fb8e-4de3-9f08-425af71dbdbd"]`
> - 命中结果如来自 K4 且标题以 `SEM-` 开头，标注为「K4 代管语义条目」
> **根治方式**：把该分片迁移回 K3，或更新本表的归属说明（需人工确认后执行）。
| K4 | 数仓智脑专家团知识库业务规则 | `6838e00b-fb8e-4de3-9f08-425af71dbdbd` | 业务规则与规范（DOM/REF/手册/索引·兜底库） |
| K5 | 数仓智脑知识库本体建模信息 | `5339e1f8-32e5-40ca-94b4-52e6b14b648d` | 本体模型与知识图谱（ONT-*） |
| K6 | 数仓智脑专家团记忆知识库 | `c6e2d1ef-bed2-4356-b89b-d3bcd1ba377d` | 对话记忆与经验沉淀（MEM-*） |
| **K7** | **大数据5S平台知识库** | **`d12f3c32-bf50-41cc-8be8-77af4c45bb35`** | **5S 平台开发规范与指标建模方法论**：数据分层架构（ODS→CDM[DWD/DWS]→ADS）、数据域建设、数据模型设计、业务指标管理、API 数据服务、命名规范、**指标开发全流程步骤**、原子/派生/复合指标定义 |
| **🆕 K8** | **数仓智脑专家团-记忆进化** | **`9253f7f9-5396-4ffd-8dc6-cceb736c240d`** | **v1.5.0 新增 · 专家团持续学习进化专用**：chunk=512/overlap=64/bge-large-zh/vector+keyword 双引擎；存五类记忆（教训/发现/决策/纠错/规则固化）四元组格式；**起手必查**；主责写入=衍薪 |

**按意图类别定向检索（必须显式指定 `knowledge_base_ids`，禁止跨库混检）**：

| 需求 | 目标库 | query 建议 | mode | 命中文档前缀 |
|---|---|---|---|---|
| **表结构/字段类型/中文名/主键** | **K1** | `<表名>` 或 `<字段名> 字段` | keyword | `DDL-表结构-<SCHEMA>`（96 schema / 9,167 表） |
| **存储过程/函数源码、加工逻辑** | **K2** | `<过程名>` 或 `P_DWS_FACT_<名>` | keyword | `PROC-过程-<GZPROD\|CBPROD\|OTHERPROD\|GZ01PROD>-*`（165 脚本） |
| **库存/存货/存货日管控（加工逻辑+查询SQL）** | **K2** | `存货日管控` 或 `P_DWD_FACT_ZZCH_ZH_<名>` | hybrid | `存货日管控：P_DWD_FACT_ZZCH_ZH_*`（加工过程 + 自助查询 SQL，含本部/泉州_QZ/罗源_LY） |
| **库存目标表结构/字段（T_DWD/DWS_FACT_ZZCH_ZH_*）** | **K1** | `<目标表名>` | hybrid | `DDL-表结构-SMBB_M_S_ZZ00` |
| ind- 指标全量（3,253 条） | **K3** | `ind-<ZB_CODE>` 或 `<指标名>` | keyword | `IND-指标-*` |
| 指标语义/业务口径/维度粒度 | **K3** | `<指标名> 业务口径 维度` | semantic | `SEM-语义-*` |
| 同义词/用户问法归一 | **K3** | `<用户原词>` | keyword | `SEM-语义-同义词与业务术语映射-*` |
| 指标血缘文档 / CREATER 映射 | **K3** | `<KPI_ID>` 或 `<ZB_CODE>` | keyword | `ZZGZ_指标血缘.md`、`T_ADS_DIM_GZ01_CREATER映射表` |
| 业务规则/口径铁律/FAQ | **K4** | `<问题> 成本 口径` | semantic | 成本权威手册、`REF-指标-CBPROD-*` |
| 血缘链路（表级/字段级） | **K4** | `<表名> 血缘` | keyword | `DOM-域-血缘-*` |
| 5S 平台规范/报错排查 | **K4** | `<报错码或页面号> 5S` | keyword | `REF-规范-5S-*` |
| 域知识（管枢/成枢） | **K4** | `<域> 加工逻辑` | semantic | `管枢_*`、`成枢_*` |
| 专家团技能定位 | **K4** | `<触发词>` | keyword | `REF-专家团-技能清单-*` |
| **本体实体/关系/知识图谱** | **K5** | `<实体名> 关系 血缘` | keyword | `ONT-*` |
| **历史讨论/之前怎么解决的** | **K6** | `<业务关键词> 历史` | semantic | `MEM-记忆-*` |
| **5S 开发规范/数据分层/指标建模步骤/命名规范/API数据服务** | **K7** | `指标建模流程` 或 `数据分层 ODS CDM ADS` 或 `原子指标 派生指标 复合指标` | hybrid | 《大数据5S平台开发流程ODS-API》《5S平台数据模型开发规范》《XDATA-数成_用户手册》 |
| **指标从零构建（无ZB_CODE/纯自然语言起点）** | **K7** | `指标开发 全流程 步骤` | hybrid | 同上；用于把业务白话 → 标准指标卡（口径六要素） |
| **🆕 教训/口径纠错/分层报错/之前踩过的坑** | **K8** | `{指标名} {域} 教训` 或 `{表名} JOIN 翻倍` | hybrid | 起手必查！memory_kb_spec.md 四元组格式；命中则必须引用 |

#### 🆕 DB2 实查语料（2026-11-16 新增 · 已摄入 WeKnora + 本地 corpus/）

> 由 DB2 `SYSCAT.COLUMNS / ROUTINES / TABLES` 实查转录，逐表逐过程保真，非编造。主理人派发铨度/构枢/诠枢时可指定这些标题精确命中。

| 文档标题 | 所在库 | 用途 | 本地权威副本 |
|---|---|---|---|
| `DOM-表结构-DB2核心表字段语义-20261116` | K1 | 16 张核心表 151 字段 + 语义角色（关联/维度/度量/词典） | `knowledge/corpus/docs/K1_表结构语料.md` |
| `PROC-过程目录-CBPROD-20261116` | K2 | 264 过程清单 + 源码长度 + 家族 + 变体标记 | `knowledge/corpus/docs/K2_存储过程目录语料.md` |
| `SEM-语义-DB2核心指标与计算口径-20261116` | K3 | 厚语义层四支柱（JOIN键/维度/公式/do_not/词典） | `knowledge/corpus/docs/K3_厚语义层语料.md` |
| `ONT-本体-DB2核心域五件套-20261116` | K5 | 本体 objects/functions/relations/glossary/config | `knowledge/corpus/docs/K5_本体五件套语料.md` |

**机读语料**（供诠枢/构枢程序化处理）：`knowledge/corpus/semantic/semantic_corpus.json`（四支柱+151字段）、`knowledge/corpus/ontology/{objects,functions,relations,glossary,config,procedure_catalog}.json`（本体五件套+264过程）、`knowledge/corpus/lineage/lineage_corpus.json`（血缘链）、`knowledge/corpus/docs/kb_index.json`（10库索引）。
**保真披露**：CDT7 仅转录 12 个高频属性字段（实表 60+，已标 `transcription:partial`）；过程目录收录 62 个核心 P 过程（范围内共 410 个 P），其余待增量补录。禁止把部分语料当作完整元数据。

> **六库铁律（2026-10-28）**：
> 1. **必须显式指定 `knowledge_base_ids`**，禁止不指定（会跨 6 库混检污染结果）
> 2. **单一意图只查对应库**；跨库检索须显式声明"跨库"并说明理由
> 3. 检索结果须标注 **来源库名 + 文档标题**（如「来源：K3 指标体系｜文档：SEM-语义-指标语义-GZPROD」）
> 4. **表结构/过程源码铁律**：查字段、类型、主键、中文名、SQL 加工逻辑时**必须先查 K1/K2**，不得凭记忆回答或 `SELECT *` 试探
> 5. **本体语义铁律**：本体模型/实体关系/维度定义/指标语义/同义词映射**必须经 K3/K5 检索**，禁止硬编码作答
> 6. **5S 规范铁律（2026-11-02）**：涉及「开发规范 / 数据分层(ODS→CDM→ADS) / 指标建模步骤 / 原子·派生·复合定义 / 命名规范 / API 数据服务 / 正向建模方法论」时**必须查 K7**（`d12f3c32-bf50-41cc-8be8-77af4c45bb35`）。**零指标起点问数、断链兜底正向建模前必须先查 K7**，禁止凭记忆或臆断建模流程。
> 7. **K7 非兜底库**：K7 是「链路应该长什么样」的**标准/方法论源**，与 K1(物理模型)/K2(加工逻辑)/K3(指标口径) 互补，不互相替代。
> 8. **🆕 K8 起手必查铁律（v1.5.0）**：**每次任务在 GATE-Q 产出 IntentContract 后必须查 K8**（`9253f7f9-5396-4ffd-8dc6-cceb736c240d`），query=`{指标名} {域} {基地} 教训 OR 口径 OR JOIN`，命中记忆必须显式引用。参考 `memory_kb_spec.md`。

> **⚠️ 检索模式铁律（2026-10-28 实测修正）**：weknora 的 `keyword` 分词器把 `_` 当分隔符，**含下划线的标识符（表名/过程名/字段名）用 `keyword` 会返回 0 结果**。
> | 查询内容 | 正确 mode | 实测 |
> |---|---|---|
> | `T_DWS_FACT_ZZGZ_LG01`（含下划线） | **`hybrid`** | keyword ❌ 0 结果 / hybrid ✅ 命中 score 0.70 |
> | `P_DWS_FACT_ZZGZ_LG01`（含下划线） | **`hybrid`** | keyword ❌ 0 结果 / hybrid ✅ 命中 score 0.93 |
> | `1600209`（纯数字编码） | `keyword` | ✅ 命中 score 1.00 |
> | `ONT-本体-GZPROD-实体清单`（含连字符） | `keyword` | ✅ 命中 score 1.00 |
>
> **规则**：含 `_` 的标识符一律用 `hybrid`；纯数字 ZB_CODE、带 `-` 的文档标题可用 `keyword`；不确定时默认 `hybrid`。

**跨库组合检索（复杂任务）**：

| 任务 | 检索顺序 |
|---|---|
| 智能问数（Step -2 预处理后） | K3（口径+同义词）→ K1（表字段核对）→ K2（加工逻辑确认） |
| 根因分析 | K3（口径）→ K2（过程链路）→ K4（域血缘）→ K5（本体关系） |
| 本体建模 | K1（表结构）+ K2（过程源码）→ 建模 → K5（发布） |
| 成本域问数 | K4（权威手册六铁律）→ K3（CBPROD 指标口径）→ K1/K2 补充 |
| 本体语义核验（Step 0.5） | K5（本体落地/产出关系）+ K3（语义粒度/范围） |
| 历史追溯 | K6（对话记忆）→ K3/K4（原则知识核对） |
| **零指标起点问数（无ZB_CODE/纯自然语言）** | **K7（5S建模方法论/指标开发步骤）** → K3（确认确未注册）→ K1（ODS/DWD 表结构）→ K2（参考同类加工过程） |
| **断链兜底·正向建模（SQL1/CREATER缺失）** | **K7（原子·派生·复合定义 + 建模流程）** → K4（业务规则）→ K1（ODS 贴源表）→ 由矩衡正向构建血缘 |

#### KB 目录（本地兜底 · weknora 不可达时使用 · 专家团内相对路径）
```
knowledge/kb/
```

#### 资产清单

| 文件 | 大小 | 用途 | 何时加载 |
|---|---:|---|---|
| `ZZGZ_指标血缘.md` | 520,693 | ZZGZ 管制报表 240 指标完整血缘 + 91 数据集 SQL + 源表链路 | 命中 ZZGZ 域/三明本部指标时查 |
| `GZJD02LDY_指标血缘.md` | 295,490 | 泉州闽光 71 指标完整血缘 + 85 数据集 SQL + 累计量修正逻辑 | 命中泉州/罗源域指标时查 |
| `ZZGZ_JD02_指标血缘.md` | 111,433 | 罗源/计划类 36 指标 + 9 数据集 SQL + 2023 年累计量修正 | 命中罗源/计划类指标时查 |
| `T_ADS_DIM_GZ01_CREATER映射表.md` | 758,297 | T_ADS_DIM_GZ01 全部有效指标的 ZB_CODE→CREATER→表名 映射 | CREATER缺失/存疑时查；Step 1 补充校验 |
| `管枢_生产管制域GZPROD_知识库文档.md` | 8,065 | 生产域主责管枢的知识文档：55 过程/425 表/840 血缘/373 JOIN/3801 指标 | 溯源加工逻辑/JOIN/存储过程时查 |
| `成枢_成本域CBPROD_知识库文档.md` | 7,310 | 成本域主责成枢的知识文档：49 过程/204 表/1140 血缘/269 成本指标/期间三态 | 成本域口径/期间三态/分摊逻辑时查 |
| `三钢成本域与利润域_数据口径与计算链路权威手册.md` | 103,424 | 成本域权威手册(DB2实测全量)：6铁律/9版口径(V1-V9)/10表清单+全字段/34坑清单/三级校验/链路自证 | **成本/利润/边际贡献类问数强制优先加载** |
| `库存管理_存货日管控_知识库文档.md` | ~9KB | 库存/存货日管控取数路径（WeKnora K2 落点 + 目标表/过程清单 + 计算逻辑摘要 + 检索步骤） | 命中 库存/存货/周转天数/库龄/合理·异常库存/资金占用 时查 |
| `知识库索引.md` | 3,827 | KB 资产的统一入口索引页，含完整协同查询流程与检索优先级 | 作为第一个加载的文件，确定检索路线 |

#### 指标口径查询（替代原 CSV 镜像 · 通过 sg-db2-executor 执行 DB2 SQL）

**精确查询（已知 ZB_CODE / KPI_ID）**：
```sql
SELECT ZB_CODE, FACTORY_DIV, ZB_NAME, SQL1, CREATER
FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01
WHERE ZB_CODE = '${ZB_CODE}' AND IS_VALID = '3'
```

**模糊查找（仅知中文名）**：
```sql
SELECT ZB_CODE, FACTORY_DIV, ZB_NAME, SQL1, CREATER
FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01
WHERE ZB_NAME LIKE '%${ZB_NAME}%' AND IS_VALID = '3'
```

> **铁律**：只用 ZB_CODE/ZB_NAME/FACTORY_DIV/SQL1/CREATER 五列，**禁止 `SELECT *`**；`IS_VALID='3'` 过滤启用态指标。
> SQL 执行统一经 `sg-db2-executor`（REST 默认公网可达 / MCP 可选内网加速）。

#### 检索优先级（强制 · 自上而下命中即止）

```
第 0 优先：weknora 知识库 search_knowledge（本体/语义/同义词/维度/指标全量/血缘/规范/域知识）
           └─ **K7 大数据5S平台知识库**（`d12f3c32-…`）= 开发规范 / 指标建模方法论 / 数据分层标准源
              → **零起点问数、正向建模、断链兜底 必查**；命中前不得凭记忆写建模步骤或 SQL
第 1 优先：T_ADS_DIM_GZ01 实表查询（DB2 SQL 经 sg-db2-executor）  → 实时值 + SQL1/CREATER 对拍
第 2 优先：本地 knowledge/kb/ 文件（Grep/Read）                     → weknora 不可达时的离线兜底
第 3 优先：三份指标血缘文档                                          → 完整数据集 SQL + 上游表链路
第 4 优先：管枢/成枢域知识文档                                       → ODS→DWD→DWS→ADS 加工链路
第 5 优先：DB2 其他实表查询                                          → 仅前述各层均缺失时使用
```

**禁止**：未经本 KB 检索就直接写 SQL 取数；**禁止**：血缘文档 SQL 与 SQL1 结果不一致时静默输出。

#### 大文件安全读取策略（agent 必读 · 防上下文爆炸）

| 文件 | 策略 |
|---|---|
| ZZGZ_指标血缘.md (520KB) | Grep 按数据集名/KPI_ID 定位后 Read offset+limit 读对应段；禁止全文 Read |
| GZJD02LDY_指标血缘.md (295KB) | 同上 |
| ZZGZ_JD02_指标血缘.md (111KB) | 同上 |
| 管枢/成枢知识文档 (均 < 10KB) | 可直接 Read 全文 |
| 知识库索引.md (3.8KB) | 直接 Read 全文 |

**上下文铁律**：三个血缘文档单文件超 100KB，严禁 Read 全文，必须 Grep 定位后分段读取。

#### 协同查询机制（T_ADS_DIM_GZ01 实表 + 血缘文档）

| 维度 | 指标血缘文档（`*_指标血缘.md`） | 指标主表（`T_ADS_DIM_GZ01` 实表） |
|---|---|---|
| 提供 | 数据集→指标→**完整可执行 SQL**→上游表链路 | `ZB_CODE`→`ZB_NAME`/`FACTORY_DIV`/`SQL1`/`CREATER` |
| 主用途 | 数据根因分析、链路下钻、还原加工过程 | 指标定位、口径核定、溯源对拍、存储过程线索 |
| 执行方式 | 文档内 SQL 经 `sg-db2-executor` 执行 | `SQL1` 直接执行；`CREATER` 线索用于存储过程溯源 |
| 互为校验 | 用 SQL1 对拍血缘文档 SQL 的结果值 | 用血缘文档还原 SQL1 的上游来源 |

#### 标准协同流程（编排器/agent 按此执行）

```
Step 0 · KB 检索（强制 · 不做不得查 DB2）
  0a. **weknora 检索（第 0 优先）**：mcp__weknora-1ba3462b__search_knowledge
      ├ 本体/语义/同义词/维度粒度/ind-指标/血缘/规范/域知识 → 按前缀表定向 query
      └ 命中 → 取口径/公式/血缘/定义（标注"口径来源：weknora KB"）
  0b. 查 T_ADS_DIM_GZ01 实表（经 sg-db2-executor 执行 DB2 SQL，实时值与 SQL1）
      ├ ZB_CODE 已知 → 精确查询（WHERE ZB_CODE='...'）
      └ 仅知中文名   → 模糊查找（WHERE ZB_NAME LIKE '%...%'）
      → 命中：取 ZB_CODE/ZB_NAME/FACTORY_DIV/SQL1/CREATER → 口径卡
      → 未命中：记录为「未注册指标」→ **不得据此判空**，按 `agents/references/caliber_check.md` 继续：
         L2 查三份血缘文档（ZZGZ / ZZGZ_JD02 / GZJD02LDY）+ CREATER 映射表 → 命中则由 sg-development 自写 SQL 计算
         L3 查 weknora（IND-指标-* / 表结构 / 业务规则）+ 本地 KB + 域文档 → 命中则据文档组装 SQL
         L4 双库皆无 → 指标新建（sg-metric-builder → sg-development → sg-5s-dev → 注册回流）
         L5 无法构建 → 如实说明缺失环节与解锁路径
  0c. weknora 不可达 → 本地兜底：Read 知识库索引.md → Grep 三份血缘文档
  0d. Read 管枢/成枢域知识文档（按域选择性加载，或 weknora 检索 DOM-* 文档）

Step 1 · 口径对拍
  1a. 执行血缘文档 SQL（替换日期 token）→ 血缘值
  1b. 执行 T_ADS_DIM_GZ01.SQL1（替换日期 token）→ 溯源值
  1c. 对拍：相对误差 > 1e-6 或单位不一致 → 触发复算/告警，禁止裸数直出

Step 2 · 根因定位
  CREATER → 存储过程溯源（数据加工逻辑核验）
  用 管枢/成枢域知识文档解释加工逻辑，定位异常所在 ODS/DWD/DWS/ADS 层

Step 3 · 输出
  数值 + 口径卡(ZB_CODE/ZB_NAME/FACTORY_DIV) + 血缘摘要(SQL1 溯源路径) + CREATER 过程线索 + 置信度 + 数据限制
```

#### 日期 Token 替换规则（SQL1 / 血缘 SQL 通用）

| Token | 含义 | 示例（以 20261010 为当天） |
|---|---|---|
| `$TD$` | 当日 `YYYYMMDD` | `20261010` |
| `$D4$` | 前 4 日 | `20261006` |
| `$D7$` | 前 7 日 | `20261003` |
| `$Dn$` | 向前偏移 n 日 | 按语义 |

替换后**必须保留** `PROD_ITEM_VALUE * 10`、`NVL()` 等既有倍数/空值处理因子，不得擅自化简。

#### 各 Agent 的 KB 使用职责

| Agent | KB 操作 |
|---|---|
| 冶衡（编排器） | 问数任务第一步：Read 知识库索引.md → 指示下游 agent 执行 DB2 SQL 查询 T_ADS_DIM_GZ01 → 按需 Grep 血缘文档 |
| sg-semantic（铨度） | 执行 DB2 SQL 查 T_ADS_DIM_GZ01 实表取口径卡（ZB_CODE/ZB_NAME/FACTORY_DIV/SQL1/CREATER）；Grep 血缘文档取完整 SQL |
| sg-metadata（舆图） | Read 管枢/成枢域知识文档获取表结构/血缘/存储过程链路 |
| sg-development（淬锋） | 执行 SQL1 + 血缘 SQL 做溯源对拍；CREATER → 存储过程溯源 |
| sg-quality（砺真） | 用域知识文档解释加工逻辑、定位根因层 |
| sg-insight（明鉴）/ sg-zhishu-report-composer（若溪） | 渲染时从口径卡中引用 ZB_CODE/ZB_NAME/FACTORY_DIV |
| sg-wecom-doc（翰枢） | 报表导出前先执行 DB2 SQL 确认指标口径 |

#### Agent 安全读取示例（防上下文爆炸）

```
// ✅ 正确：DB2 SQL 精确查询指标口径
经 sg-db2-executor 执行：
SELECT ZB_CODE,FACTORY_DIV,ZB_NAME,SQL1,CREATER
FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01
WHERE ZB_CODE='1600230' AND IS_VALID='3';

// ✅ 正确：DB2 SQL 模糊查找指标
SELECT ZB_CODE,FACTORY_DIV,ZB_NAME,SQL1,CREATER
FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01
WHERE ZB_NAME LIKE '%圆棒%' AND IS_VALID='3';

// ✅ 正确：Grep MD 按 KPI_ID 定位后分段读
Grep({pattern: "KPI_ID.*8000003", path: "knowledge/kb/ZZGZ_指标血缘.md", output_mode: "content", "-n": true})

// ✅ 正确：Read 轻量文档全文
Read({file_path: "knowledge/kb/知识库索引.md"})

// ❌ 错误：全文读取超 100KB 的血缘文档
Read({file_path: "knowledge/kb/ZZGZ_指标血缘.md"})  // 520KB，禁止！

// ❌ 错误：SELECT * 从 T_ADS_DIM_GZ01
SELECT * FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01  // 禁止！只用 5 列
```