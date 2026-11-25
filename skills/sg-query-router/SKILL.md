---
name: sg-query-router
description: "三钢数仓智脑：P0 前置意图理解分析编排（query-router）。把用户自然语言请求转译为专家团与 LLM 均可确定性执行的『意图契约 IntentContract JSON』——判任务型/业务域/指标候选/基地/期间/维度/口径/交付形态/物化状态/路由链/血缘要求，并锁死歧义门禁。主理人不得内联替代本技能。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, intent, query-router, contract, p0, routing]
owner: sg-query-router
---

# sg-query-router · P0 意图理解分析编排（query-router）

> **定位**：专家团的**唯一入口语义编译器**。用户请求都是自然语言，主理人（编排器）**不直接理解**，必须派发 `sg-query-router`（辨枢）用本技能把 NL 编译成**意图契约（IntentContract）**，之后专家团 SOP 只消费契约、不消费原始口语。
> **铁律**：意图契约未产出前，禁止取数、禁止判型落 trace、禁止派发任何取数 Agent。

## 一、为什么需要本技能（根因）

TR-2026-11-15 用户复盘确认：主理人凭口语默认路径判型，曾把「成本域」误走 GZ01 指标注册层、未进 CBPROD 知识库与存储过程链，导致用户需人工点明路径。根因 = **缺少独立的意图理解前置层**：主理人既当"理解者"又当"编排者"，认知负荷过高且无结构化产物可审计。

本技能把"理解"从主理人剥离为**专职专家 + 确定性契约**，落实已固化的跨项目规则「业务域路由与血缘优先」。

## 二、强制前置：业务域路由（第零步，先于一切判型）

> 引用契约：`agents/references/task_classify.md` 第零步 + 用户长期记忆「业务域路由与血缘优先」。
> **CBPROD 是业务域标识，不是 DB2 schema 名**；禁止凭域名猜 schema。

```
命中 成本|利润|边际贡献|保本线|科目构成|吨材|工序成本|轧制费|成材率|为什么贵
  → domain=cost，物理落点 SMBB_M_S_CB00 / SMBB_M_A_CB01
    → 强制加载 sg-cbprod-warehouse v2 + 成本域口径决策树
    → 必读《三钢成本域与利润域·数据口径与计算链路权威手册》
    → 版本口径：V1=当日(DAY_ALL_VAL)、V4=月值(MON_VAL)、V3 不闭合(禁作主口径)
命中 库存|存货|存货日管控|库龄|周转|资金占用|库区
  → domain=inventory，K7 口径 + K2 加工 + K1 表结构（ZZCH 表），禁查 GZ01 判无数据
命中 生产|高炉|转炉|轧线|产量|铁水|钢坯|能源
  → domain=prod，SMBB_M_A_GZ01 + GZPROD 主链路
命中 驾驶舱|经营驾驶舱|cockpit|领导驾驶舱
  → domain=cross，直派 sg-insight + sg-cockpit-report，跳过单域拆分
均未命中 → domain=prod（默认），但 confidence 降 0.1 并在 open_questions 标注
```

**基线动作**：查表前必须先列 schema 清单（SYSCAT / list_tables），禁止臆造 `GZPROD`/`CBPROD` 这类不存在的 schema 名。

## 三、意图契约生成流程（六步）

### Step 1 · 任务型判定（Q1-Q6，规则白名单优先）
按 `task_classify.md`：Q1 问数 / Q2 问数+报表 / Q3 归因 / Q4 口径建模 / Q5 治理 / Q6 建设元任务。
- 规则命中即定 `task_type`，零模型调用；规则未命中且置信度 <0.8 → 仅 1 次 4 分类模型调用，判据字符串写 `open_questions`。
- **Q6 优先于 Q1/Q2 禁止派单**（元任务不产生取数流量）。
- 校验三字段：`task_type`（Q1-Q6）+ `fast_lane`（bool）+ `qt_level`（L0-L3），缺一不得输出契约。

### Step 2 · 指标候选解析（零全量加载）
1. 离线匹配器 `skills/sg-indicator-system/engine/lookup_indicator.py` 取候选（**禁止**把 4.68MB registry 载入上下文）。
2. 候选含 `zb_code / zb_name / domain / level / confidence / materialized_sql_file`。
3. 交叉核验双码体系（如热装率 1600xxx vs 8000xxx），口径不一致写 `open_questions`。

### Step 3 · 业务实体抽取
从 NL 与上下文抽取：`metrics[]` · `dimensions[]`（厂别/产线/工序/钢种/日期粒度）· `factory`（本部三明闽光/罗源/泉州/multi）· `time_range`（原文相对表达保留）· `compare_baseline` · `granularity` · `filters[]`。
- **基地口径铁律**：`factory` 必须显式，本部 `COMPANY_CODE='100'`；缺失时标 `needs_clarification`，禁止默认全基地。

### Step 4 · 物化状态判定（决定快/慢车道 —— 本技能核心增量）

> 对每个候选指标查 `indicator_registry.json.materialized_sql_file` + `materialized_sql_guard.is_blocked()`。

```
全部候选 materialized_sql_file 非空且 guard 通过
  → materialization_status = "materialized"     → 快车道（秒级/分钟级）
部分命中 → materialization_status = "partial"  → 命中走快车道，未命中走慢车道并列表
全部未命中 / 无指标表 / SQL1 空 / CREATER 断链
  → materialization_status = "unmaterialized"  → 慢车道（专家团编译 SQL）
指标表中根本没有该指标
  → materialization_status = "no_registry"     → 慢车道 + 矩衡正向建模（指标卡）
```

**空壳防护**：物化 SQL 文件存在但 guard 判 `NON_READONLY_HEAD` / 常量 0 → 视为未物化，禁止当快车道执行。

### Step 5 · 歧义与隐含需求门禁
- 模糊点写入 `assumptions[]` + `open_questions[]`；默认按假设继续，**仅当**指标/对比目标/时间/基地缺失且不同补齐会改变语义时才 interrupt 用户。
- 自动注入 `implicit_needs[]`（成本域→四口径对比；产量消耗→严禁跨基地混数；任何取数→富交互 HTML 报告；任何分析→强制函数实算，见 `analysis_model_driven.md`）。

### Step 6 · 路由链编排（多专家协同，主理人不得独揽）
按任务型 + 域 + 物化状态装配 `route.chain` + `route.observers`，规则见 §四。

## 四、路由链编排矩阵（多专家协同强制）

| 任务型×物化 | primary | chain（顺序） | observers |
|---|---|---|---|
| Q1/Q2 × materialized（快车道） | sg-semantic | sg-development(执行) → sg-quality(三查) → sg-insight(模板渲染，Q2 才派) | sg-governance(SQL预检)、sg-supervisor |
| Q1/Q2 × unmaterialized（慢车道） | sg-semantic | sg-metric-builder(指标卡/断链正向建模) → sg-development(DSL→SQL) → sg-governance(审查) → sg-development(执行) → sg-quality(三查) → sg-insight | sg-supervisor、sg-skill-evolution(物化候选识别) |
| Q3 归因 | sg-quality | sg-semantic+sg-metadata+sg-ontology+sg-metric-builder(并行取证) → sg-development(SQL) → sg-quality(分解裁定) → sg-insight | sg-governance、sg-supervisor、域专家(sg-cbprod/sg-gzprod) |
| Q4 口径建模 | sg-metric-builder | sg-ontology → sg-semantic → sg-development → sg-governance | sg-supervisor、sg-skill-evolution |
| Q6 建设元任务 | 按 routing.md | 按 routing.md 触发词派对应专家 | sg-supervisor |

**硬约束**：任何 chain 至少 3 位专家；`Q1/Q2 × materialized` 快车道保留 5 位协同（见 `fast_lane_response.md` §四），不得降为单人。

## 五、输出契约（IntentContract JSON · 唯一交换格式）

完整 schema 见 `references/intent_contract_schema.md`。核心字段：

```json
{
  "contract_version": "1.0.0",
  "trace_id": "<TR-YYYYMMDD-...>",
  "meta": {"generated_by":"sg-query-router","generated_at":"<ISO8601>","raw_query_hash":"<sha256>","si_version":"2.0.0"},
  "routing": {"task_type":"Q1-Q6","fast_lane":true,"qt_level":"L0-L3","lane":"fast|slow|root-cause","materialization_status":"materialized|partial|unmaterialized|no_registry"},
  "intent": {"primary_type":"","sub_types":[],"is_root_cause":false,"is_cross_domain":false,"complexity":""},
  "domain": {"primary":"cost|prod|inventory|cross","secondary":[],"physical_schema":["SMBB_M_S_CB00"],"kb_required":["sg-cbprod-warehouse"]},
  "entities": {"metrics":[{"raw_term":"","zb_code":"","canonical_name":"","confidence":0.0,"materialized_sql_file":"","blocked_reason":""}],"dimensions":[],"factory":"","time_range":{},"filters":[]},
  "deliverable": {"format":"html|value|docx","rich_visual":true,"include_lineage":true,"analysis_required":false},
  "route": {"primary":"sg-xxx","chain":[],"observers":[]},
  "materialization": {"candidates_to_materialize":[],"confirmation_required":false,"target_kb":"K3"},
  "assumptions":[],"open_questions":[],"implicit_needs":[],
  "raw_query":"<原文>"
}
```

**下游消费铁律**：P0 宪章、GATE-1 init、所有取数 Agent prompt **只引用本契约**，不再各自解析原始 NL。`fast_lane` / `materialization_status` 两字段缺一 → 监衡驳回重派。

## 六、输出规范
- 主产物：IntentContract JSON（落盘 `<workspace>/traces/<YYYYMMDD>/<trace_id>.contract.json`）。
- 附：一句话人话回显（"已理解你的请求为：…；准备走 X 车道 / Y 专家链"），**不含**任何数值/SQL。

## 七、注意事项
1. 只理解不执行：不生成 SQL、不取数、不渲染、不给结论。
2. 领域路由优先于指标匹配；未定域前不展开 KPI 清单。
3. 复合诉求拆多条意图逐条路由（如"出日报并解释成本异常" = report + dual_control）。
4. 相对时间保留原文，由编译期展开绝对日期（成本域 V1/V4 口径由域专家确认）。
5. 本技能是 P0 前置门禁，与 `task_classify.md` 判型规则一致；冲突时以本技能契约为准并写 `open_questions`。
