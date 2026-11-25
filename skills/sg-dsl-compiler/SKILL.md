---
name: sg-dsl-compiler
description: "三钢数仓智脑：DSL 编译器。把语义专家的 DSL 确定性编译为 DB2 SQL —— 模板映射、外键属性化 JOIN 生成、按维对齐、日期参数展开、DB2 方言强制与三查自校验。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, dsl, compiler]
owner: sg-development
---

# sg-dsl-compiler · DSL 编译器（确定性编译）

## 定位

智能问数链路中**唯一不允许概率性发挥**的环节：把「概率性 LLM」从精确 JOIN/口径中剥离。

> 铁律：第⑤层（DSL → SQL）必须确定性编译。交给模型临场发挥 = 准确率崩塌。

### v1.1 两段式隔离与三令牌护栏（2026-11-16 · 源自 Data Agent 调研）

**权威规则**：`agents/references/guardrail_and_eval_loop.md` + `agents/references/thick_semantic_layer.md`。

1. **MQL 格式硬闸**：进入本编译器前，校验 DSL 只含业务语义（指标名/维度/时间/口径版本/filters）。**若 DSL 中出现物理表名或字段名 → 判格式错误，拒绝编译**，退回铨度重做。（本团 DSL 的 `metric/dimensions/time/guards/ontology_refs` 符合纯业务语义；表名只允许在编译时从本体 relations 解析。）
2. **选表四准则**：粒度覆盖 × 维度覆盖 × 预聚合 × 权威等级（金 > 银，废弃跳过）。不可凭印象选表。
3. **JOIN 键唯一来源**：本体的 `relations.join_key`；**永不猜测 JOIN**，关系基数 1:1/1:N/N:M 决定是否需要去重子查询。
4. **查询令牌校验**：执行前携带由「用户确认 MQL 后」签发的确认令牌指纹；翻译成功后 SQL 原文绑定查询令牌，执行时 SQL 须与令牌绑定内容逐字一致。确认令牌随语义变更失效（须重确认）。
5. **只读执行 + 行数上限**：`FORBIDDEN` 正则拦截写操作；DB2 MCP 自动分页，SQL 内禁手写 `FETCH FIRST`（SQLCODE=-104）；靠 MCP limit 参数控行数（参考 ≤1000）。
6. **翻译失败如实报错**：不猜"能跑但不准"的 SQL；无表/无 JOIN 键 → 返回明确错误 + 缺失项。

## 双模式：物化直查（快车道） + 实时编译（慢车道）

| 模式 | 触发 | 路径 | 延迟 |
|---|---|---|---|
| **A 物化直查** | DSL 的 `indicator_refs[].code`（即 ZB_CODE）命中 `knowledge/design/indicator/indicator_registry.json` 且 `materialized_sql_file` 非空 | 直接读 `materialized_sql/<ZB_CODE>.sql` → 替换时间占位符 → DB2 MCP 只读执行（**跳过模板编译**） | 秒级（≤5 分钟） |
| **B 实时编译** | 未命中注册表，但语义层有口径 | 走下方规则 1~7 确定性编译 | 秒~分钟 |

> 优先级：**A 优先**。命中物化 SQL 即直查，不进入模板编译与三查的"生成"环节（仅做分区/空值兜底与只读校验）。
> 机制详见 `sg-materialized-sql` 技能。完全未注册指标转 `sg-adhoc-indicator` 即席构建。

## 编译规则表

### 规则 1 · 意图 → SQL 骨架

| DSL intent | SQL 骨架 |
|---|---|
| `metric_query` | `SELECT 维度…, AGG(度量) FROM 事实表 [JOIN 维表] WHERE 过滤 GROUP BY 维度` |
| `trend` | 骨架 + 时间维度分组 + `ORDER BY 时间` |
| `compare` | 骨架 + LAG/自关联 或 同期子查询 |
| `drill_down` | 骨架 + 层级维度展开（CTE 递归或层级字段） |

### 规则 2 · 六种 SQL1 模板

| # | 模板 | 适用 | 关键结构 |
|---|---|---|---|
| ① | 单值直取 | 单指标当前值 | `SELECT ZB_VALUE … WHERE ZB_NAME=? AND YMD='$TD$'` |
| ② | 分组汇总 | 按维度聚合 | `GROUP BY FACTORY_DIV` |
| ③ | 时间序列 | 趋势 | `WHERE YMD BETWEEN '$D30$' AND '$TD$'` |
| ④ | 同环比 | 对比 | `LAG(。.) OVER (ORDER BY YMD)` 或自关联 |
| ⑤ | 下钻 | 层级展开 | CTE 递归 / 层级字段分段 |
| ⑥ | 排名 TopN | 排名 | `ROW_NUMBER() OVER(。.)` + `FETCH FIRST n ROWS ONLY` |

### 规则 3 · 外键属性化（JOIN 由编译器生成）

- 维度键在**语义层预定义**（如 `FACTORY_DIV` → 厂部维表）
- 编译器按预定义拼 JOIN，**模型不参与选择**
- 禁止在编译期临时决定关联字段

### 规则 4 · 按维对齐

多事实表向公共维度对齐时自动 `FULL JOIN`，保证维度组合不丢失：

```sql
SELECT COALESCE(a.YMD, b.YMD) AS YMD,
       COALESCE(a.FACTORY_DIV, b.FACTORY_DIV) AS FACTORY_DIV,
       a.产量, b.成本
FROM 生产事实 a FULL JOIN 成本事实 b
  ON a.YMD = b.YMD AND a.FACTORY_DIV = b.FACTORY_DIV
```

### 规则 5 · 日期参数展开

| 占位符 | 展开为 |
|---|---|
| `$TD$` | 当日 `'YYYYMMDD'` |
| `$D1$` ~ `$D7$` | 前 N 日 |
| `$D30$` | 前 30 日 |
| `$YM$` | 当前会计期间起止 |

> 展开前必须从上下文或系统时间确定基准日；无法确定则回退语义专家澄清，**禁止臆造日期**。

### 规则 6 · DB2 方言强制

| 项 | 规则 |
|---|---|
| 分页 | `FETCH FIRST n ROWS ONLY`（禁用 `LIMIT`） |
| 分区 | 大表强制注入 `YMD` 或分区键条件 |
| 空值保护 | 除法一律 `NULLIF(分母, 0)` |
| 日期 | 使用 DB2 日期函数（`VARCHAR_FORMAT` / `DAYS()`） |
| 自校验 | 生成后附 `EXPLAIN` 建议（不执行，仅提示） |

### 规则 7 · guards 约束落地

| guard | 编译动作 |
|---|---|
| `dedup_required` | 先 `SELECT DISTINCT 主键` 再聚合 |
| `ratio_not_additive` | 分子分母各自 `SUM` 后相除 |
| `semi_additive` | 时间维取 `MAX(YMD)` 对应快照值，不 SUM |
| `version locked` | WHERE 中强制带版本条件 |

## 三查自校验（编译后必做）

| 查 | 内容 | 不通过处置 |
|---|---|---|
| ① 语法 | DB2 方言合法性（分页/函数/引号） | 修正后重编译 |
| ② 表存在性 | 对照 9167 DDL 校验表与字段 | 回退语义专家补信息 |
| ③ 合理性 | 分区条件是否注入、返回量级是否合理 | 补条件或加限制 |

任一不通过 → **不产出"看起来能用"的 SQL**。

> **E11 铁律（2026-11-02）· 三查覆盖即席构建**：
> 三查对**所有**交付 SQL 生效，**包括 `sg-adhoc-indicator` 即席构建场景产出的 SQL**。
> - 即席场景下模型**只允许写 DSL 声明**（源表/JOIN/聚合/维度/限定），**最终可执行 SQL 必须经本编译器生成并通过三查**；
> - **禁止任何环节绕过编译器直接产出可执行 SQL（"裸写裸出"）**——这是「确定性编译」铁律在即席场景的延伸，模型临场写 SQL = 准确率崩塌；
> - 三查任一不通过 → 修正重编译，**不交付**。

## 工作流

1. **先判模式**：DSL 含 `indicator_refs[].code` 且在 `indicator_registry.json` 命中 → 走**模式 A 物化直查**（见下）；否则模式 B。
2. **模式 A（物化直查）**：读 `materialized_sql/<ZB_CODE>.sql` → 按「时间占位符替换表」替换 → 交 sg-db2-executor 执行（DB2 MCP 优先，REST 需用户自备 token） → 输出 `mode:"materialized"` + 命中来源。
3. **模式 B（实时编译）**：选模板（六选一）→ 展开日期参数 → 生成 JOIN → 按维对齐 → 应用 guards → 注入分区 + `FETCH FIRST` → 三查自校验 → 输出 SQL + 编译日志。
4. 任一模式产物均须过治理护栏与质量闸门后才交付。

## 输出规范

```json
{"sql": "SELECT 。.",
 "compile_log": {"template": "③ 时间序列", "params_expanded": {"$D30$": "20260801", "$TD$": "20260831"},
   "joins": ["维表:厂部 ON FACTORY_DIV"], "guards_applied": ["ratio_not_additive"],
   "checks": {"syntax": "pass", "table_exists": "pass", "reasonable": "pass"},
   "assumptions": ["时间范围默认近 30 天"]},
 "cost_caliber": {"cal_date_version": "V1", "date_type": "1", "y_edition": "2023M12"}}
```

## 注意事项

1. **语义与物理解耦**：口径变更改语义层，方言调整改编译器规则，禁止混改。
2. 输出 SQL 必须**只读**，交治理专家四层护栏后再执行。
3. 禁止 `SELECT *`：必须显式列字段。
4. 编译日志必须完整 —— 它是后续根因分析"参数错误"类问题的排查依据。
