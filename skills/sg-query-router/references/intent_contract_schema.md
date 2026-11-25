# IntentContract Schema v1.0.0（专家团唯一意图交换格式）

> 由 `sg-query-router`（辨枢）在 P0 前置产出。P0 宪章、GATE-1、所有取数 Agent 只消费本契约，禁止各自解析原始 NL。

## 一、字段全表

| 字段路径 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `contract_version` | string | ✅ | 固定 `1.0.0` |
| `trace_id` | string | ✅ | `TR-YYYYMMDD-XXXX` |
| `meta.generated_by` | string | ✅ | 固定 `sg-query-router` |
| `meta.raw_query_hash` | string | ✅ | 原始 NL 的 sha256，防歧义回溯 |
| `routing.task_type` | enum | ✅ | Q1 问数 / Q2 问数+报表 / Q3 归因 / Q4 口径建模 / Q5 治理 / Q6 建设元任务 |
| `routing.fast_lane` | bool | ✅ | 快车道标志，与 materialization_status 联动 |
| `routing.qt_level` | enum | ✅ | L0 裸查 / L1 趋势 / L2 根因 / L3 全链 |
| `routing.lane` | enum | ✅ | `fast` 快车道 / `slow` 慢车道编译 / `root-cause` 根因 |
| `routing.materialization_status` | enum | ✅ | `materialized` / `partial` / `unmaterialized` / `no_registry` |
| `intent.primary_type` | enum | ✅ | metric_query/report/root_cause/dual_control/dev/governance |
| `intent.is_root_cause` | bool | ✅ | 命中为什么/原因/异常/归因/波动/诊断/溯源 |
| `intent.is_cross_domain` | bool | ✅ | 跨生产+成本+存货 |
| `domain.primary` | enum | ✅ | cost/prod/inventory/cross |
| `domain.physical_schema` | string[] | ✅ | 域对应物理 schema，如 `["SMBB_M_S_CB00","SMBB_M_A_CB01"]` |
| `domain.kb_required` | string[] | ✅ | 必加载技能/知识文档，如 `sg-cbprod-warehouse` |
| `entities.metrics[]` | object[] | ✅ | 指标候选，见下 |
| `entities.factory` | enum | ✅ | 本部三明闽光/罗源/泉州/multi/需澄清 |
| `entities.time_range` | object | ✅ | raw/granularity/绝对日期编译期展开 |
| `deliverable.format` | enum | ✅ | `html` / `value` / `docx` |
| `deliverable.analysis_required` | bool | ✅ | Q3+/含分析词 → true，触发函数实算链 |
| `route.primary` | string | ✅ | 主责专家 ID |
| `route.chain` | string[] | ✅ | ≥3 位专家，顺序编排 |
| `route.observers` | string[] | ✅ | 旁路专家 |
| `materialization.candidates_to_materialize` | string[] | ✅ | 慢车道产出后待用户确认的指标 code |
| `materialization.confirmation_required` | bool | ✅ | 慢车道=true，须用户确认后才物化 |
| `assumptions/open_questions/implicit_needs` | object[] | ✅ | 歧义与隐含需求，可空数组 |

## 二、metrics[] 子结构

```json
{
  "raw_term": "用户口语指标名",
  "zb_code": "注册码（无则空）",
  "canonical_name": "注册全名",
  "confidence": 0.95,
  "materialized_sql_file": "materialized_sql/1600213.sql（无则空）",
  "blocked_reason": "NON_READONLY_HEAD|无|空壳常量0"
}
```

## 三、materialization_status 判定真值表

| 条件 | status | fast_lane | lane |
|---|---|---|---|
| 全部指标有物化 SQL 且 guard 通过 | materialized | true | fast |
| 部分命中 | partial | true（命中部分） | fast+slow 混合 |
| 有注册但无物化 SQL / SQL1 空 / 断链 | unmaterialized | false | slow |
| 指标表根本没有 | no_registry | false | slow（+矩衡正向建模） |

## 四、契约校验（监衡硬规则）

- 必填字段任一缺失 → 驳回重派，禁止进入 GATE-1。
- `fast_lane=true` 但 `materialization_status≠materialized/partial` → 驳回。
- `route.chain.length < 3` → 驳回（多专家协同铁律）。
- `domain.primary=cost` 但 `kb_required` 不含 `sg-cbprod-warehouse` → 驳回。
- `entities.factory` 为"需澄清"且任务型≠Q1 裸查 → 编排器须先向用户确认基地。
