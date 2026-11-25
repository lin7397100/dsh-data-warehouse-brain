---
deprecated: true
alias_of: sg-intent
dispatch: false
name: sg-intent-parse-dispatch
description: "三钢数仓智脑：意图解析与领域路由分派。命中「查/分析/报表/成本/根因/SQL/表结构/看板/报告」等数据分析诉求时先用本技能分类，再路由到对应专家。领域路由优先，防止 6077 个 KPI 一次性入上下文。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, data-warehouse, intent, routing]
owner: sg-metadata
---

> ⚠️ **本目录为兼容别名，不参与派发**。统一入口：`sg-intent`。
> 保留原因：入口技能在部分章节引用本目录的详细内容（references/schema），删除会导致跨机复现断链。
> ⚠️ 已合并：本技能已并入 `sg-intent`。保留目录以兼容旧引用，新任务请调用 `sg-intent`。


# sg-intent-parse-dispatch · 意图解析与领域路由分派

## 定位

智能问数与一切数据诉求的**入口解析器**。只做「业务语言 → 结构化意图」，不生成 SQL、不查数据。

## 触发条件

用户提出任何数据分析类诉求（问数 / 报表 / 成本 / 根因 / 开发 / 治理 / 看板 / 报告）时，编排器首调用本技能。

## 工作流程

### Step 0 · 任务类型判定（Q1-Q5 规则白名单 · 2026-10-29 复盘落地）

> 在六类 `intent_type` 之上叠加 **Q1-Q5 业务分型**（驱动 SLA 与专家派发强度）。Q1/Q2 占问数流量 70%+，默认**零专家深审**。

| 型 | 触发词（含近义/口语） | 语义派发角色 | SLA 档 | 禁止派单 |
|---|---|---|---|---|
| Q1 问数 | 查/看/多少/几/拉一下/近N日/对比同期 | 取数事实意图解析 + SQL + 渲染 | L0 | dev/quality/gov 深审 |
| Q2 问数+报表 | Q1 + 生成报告/HTML/趋势图 | 取数 + 呈现（模板渲染） | L1 | 同 Q1 |
| Q3 归因 | 为什么/原因/下滑/异常/归因分析 | 根因 + sg-quality（轻量 A1-A4 + 离群） | L2 | — |
| Q4 口径/建模 | 口径修改/指标开发/新建表/注册变更 | + sg-development + sg-governance | L3 | — |
| Q5 治理/合规 | 合规/脱敏/越权/审计 | 治理 + sg-governance 常驻 | L3 | — |

- **规则白名单优先**：命中即定 `task_type`，无需模型调用。
- **模型一票**：规则未命中且意图置信度 < 0.8 时，仅做 **1 次** 4 分类调用，并输出**判据字符串**写入 trace。
- **Q1/Q2 禁止派单列表（铁律）**：`sg-development` / `sg-quality` / `sg-governance` / `sg-root-cause-fullchain` / `sg-quality-rule-gen` 在 Q1/Q2 下一律不派发。
- **Trace 三字段必填**：输出 `StructuredInstruction` 须含 `task_type`（Q1-Q5）、`fast_lane`（bool）、`qt_level`（L0-L3）；缺一则编排器不得进入主链。

### Step 1 · 意图分类（六类）

| intent_type | 说明 | 主责专家 |
|---|---|---|
| `metric_query` | 指标查询（单值 / 分组 / 趋势 / 对比 / 下钻 / TopN） | 语义 → 开发 → 治理 → 洞察 |
| `report` | 报表汇总（生产日报 / 日成本报表 / 周报 / 月报） | 洞察（+ 开发 / 质量） |
| `root_cause` | 数据质疑与根因分析 | 质量（+ 元数据 / 语义 / 本体并行取证） |
| `dual_control` | 生产-成本双轮管控 / 成本异常 / 批处理监控 | 质量（+ 本体 / 洞察） |
| `dev` | SQL / 存储过程 / 指标配置 / 优化 | 开发 |
| `governance` | 安全 / 权限 / 分级 / 合规 | 治理 |

### Step 2 · 领域路由（P0，先粗后细）

先定业务域，再在域内展开字段 —— **禁止把 6077 个 KPI 一次性装入上下文**。

| domain | 覆盖范围 | 典型 Schema |
|---|---|---|
| `production` | 生产管制（铁/钢/材/能源） | `SMBB_M_S_ZZ00`、`GZPROD` |
| `daily_cost` | 日成本（成本中心/科目/毛利） | `SMBB_M_S_CB00`、`CBPROD` |
| `purchase` | 采购与原料 | `YL01`、`CGGZ_0001` |
| `energy` | 能源介质 | 能源相关 DWS |
| `quality` | 质量与检验 | 质量相关 DWS |

### Step 3 · 抽取关键属性

从用户问题与对话上下文中抽取**会影响后续拆解走向**的属性（能抽几个算几个，不强制齐全）：

`goal`（最终结论/交付物）· `metrics[]` · `timeWindow` · `dims[]` · `compareBaseline`（同比/环比/预算）· `anomalyDirection`/`anomalyMagnitude` · `suspectedFactors[]` · `deliverable`（一句话结论/图表/报告）· `factory`（三钢闽光/泉州/罗源）

### Step 4 · 歧义处理

- 模糊点先写入 `assumptions[]` 记录假设、`openQuestions[]` 记录待确认项
- **默认按假设继续推进，不打断用户**
- 只有"指标/对比目标/时间范围缺失，且不同补齐方式会改变问题语义"时才提问

### Step 5 · 结构化输出（含隐含需求补全）

将 Step 1~4 的解析结果 + 隐含需求补全，组装为 **StructuredInstruction JSON**（v1.0.0 schema）：

```json
{
  "meta": {"si_version":"1.0.0", "generated_at":"<ISO8601>", "generator":"sg-intent-parse-dispatch",
           "raw_query_hash":"<sha256>", "task_type":"<Q1-Q5>", "qt_level":"<L0-L3>", "fast_lane":false},
  "intent": {"primary_type":"<六选一>", "sub_types":[], "is_root_cause":false, "is_cross_domain":false,
             "complexity":"<simple|medium|complex>", "estimated_team_size":1},
  "domain": {"primary":"<五域选一>", "secondary":[], "factory":"<三钢闽光|罗源闽光|泉州闽光|multi>"},
  "entities": {"metrics":[{"raw_term":"钢铁料耗", "canonical_name":"...", "zb_code":"1600209",
                "confidence":0.95, "source":"SEM-同义词"}], "dimensions":[], "processes":[], "products":[]},
  "temporal": {"time_type":"relative", "raw_expression":"最近7天", "granularity":"day"},
  "constraints": {"factory_filter":[], "version":"V1", "compare_baseline":[], "anomaly_direction":null},
  "deliverable": {"format":"html", "rich_visual":true, "include_lineage":true, "mobile_ready":true},
  "assumptions":[], "open_questions":[],
  "implicit_needs":[{"category":"caliber_cross_check", "description":"...", "source_rule":"..."}],
  "route": {"primary":"sg-semantic", "chain":["sg-development","sg-governance","sg-quality","sg-insight"],
            "observers":["sg-supervisor","sg-skill-evolution"]},
  "raw_query":"<用户原始输入>"
}
```

**隐含需求补全规则（三类 · 自动注入 `implicit_needs[]`）**：

| 类别 | 触发条件 | 自动注入的 implicit_need |
|---|---|---|
| `caliber_cross_check` | 成本域指标 | 需展示日成本/核算/预算/累计四口径对比 |
| `factory_isolation` | 产量/消耗类指标 | 严禁跨基地混数；合计码与分炉不得同时 SUM |
| `html_report_default` | 任何含"数据"的问数 | 最终必须产出富交互 HTML 可视化报告 |

**Trace 日志写入**：原始 QUERY + StructuredInstruction JSON 一并写入 `<workspace>/traces/<YYYYMMDD>/<trace_id>.json`。

### Step 6 · 路由交付

将 `route.chain` 交编排器执行后续 Step -1 链路。

## 路由速查表

| 关键词 | 路由 |
|---|---|
| 看板 / 仪表盘 / 驾驶舱 / 大盘 / dashboard | `sg-insight` → `sg-kanban-builder`（**排斥智能取数**） |
| 报告 / 复盘 / 汇报 / docx / HTML 报告 | `sg-insight` → `sg-report-composer` |
| 日报 / 周报 / 成本日报 | `sg-insight` → `sg-production-report-auto` / `sg-cost-ops` |
| 数据不对 / 为什么 / 波动 / 根因 | `sg-quality` → `sg-root-cause-fullchain` |
| 成本异常 / 批处理 / 预算偏差 | `sg-quality` → `sg-cost-ops` / `sg-cost-ops` |
| SQL / 存储过程 / 优化 / 指标配置 | `sg-development` |
| 表结构 / 字段 / 血缘 / Schema | `sg-metadata` |
| 口径 / 语义 / 指标定义 | `sg-semantic` |
| 业务逻辑 / 本体 / 计算过程 | `sg-ontology` |
| 权限 / 安全 / 分级 / 敏感 | `sg-governance` |
| 经常做 / 固化成技能 / 技能不好用 | `sg-skill-evolution` |
| 深度研究型 / 宽泛模糊型 | 先 `sg-task-planner` 出 Plan |

## 输出规范

- 意图 JSON（字段以实际抽到的为准，不强制结构）
- 路由决策（primary + chain）
- 假设与待确认项清单

## 注意事项

1. **只解析不执行** —— 不生成 SQL、不查数据、不渲染。
2. 领域路由优先于指标匹配，未定域前不得展开字段清单。
3. 复合诉求拆成多条意图，逐条路由（如"出日报并解释成本异常" = `report` + `dual_control`）。
4. 相对时间（今天/上月/去年）保留原文，由开发专家编译期展开为绝对日期。
