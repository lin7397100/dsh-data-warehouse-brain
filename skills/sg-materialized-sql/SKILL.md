---
name: sg-materialized-sql
description: "三钢数仓智脑：物化 SQL 直查引擎。智能问数命中已注册指标时，直接调用固化 SQL（indicator_registry + materialized_sql/<ZB_CODE>.sql），替换时间占位符后交 sg-db2-executor 执行（DB2 MCP 优先，REST 需用户自备 token），免实时编译，秒级（≤5 分钟）响应。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, materialized, sql, registry, fast-query]
owner: sg-development
---

# sg-materialized-sql · 物化 SQL 直查（免编译）

## 定位

智能问数的**性能快车道**。当问数命中 `indicator_registry.json` 中已固化的指标时，
**不进入 sg-dsl-compiler 的模板编译流程**，而是直接取预校验过的物化 SQL 执行 —— 把"编译延迟"
从「LLM 生成 + 模板映射 + 三查」压到「参数替换 + 执行」，**保证 ≤5 分钟（典型秒级）响应**。

## 两个核心产物（由 `sg-indicator-system/engine/import_gz01.py` 生成）

| 产物 | 路径 | 说明 |
|---|---|---|
| 指标注册表 | `knowledge/design/indicator/indicator_registry.json` | 全量 6155 指标；每条约含 `zb_code / zb_name / domain / level / sql1 / params / source_tables / source_layers / lineage_chain / materialized_sql_file` |
| 物化 SQL | `knowledge/design/indicator/materialized_sql/<ZB_CODE>.sql` | 每个可计算指标的固化 SQL（保留 `$TD$`/`$D4$` 等时间占位符） |
| 合并版 | `knowledge/design/indicator/materialized_sql/all_indicators.sql` | 一次性参考 |

> 注册表为权威基线（本地 `knowledge/`）；如需对外副本可经 WeKnora K3 指标库同步（见 `sg-indicator-system`；腾讯文档通道已 disabled）。

## 直查流程（六步 · 全程零全量加载）

```
1. 取 zb_code（由 sg-nl2sql-query 零步 / sg-semantic-layer 引擎三 调离线匹配器
   skills/sg-indicator-system/engine/lookup_indicator.py 得到，绝不把 2.18MB 索引或
   4.68MB 注册表载入 LLM 上下文）。
2. **先过加载断言**：调用 `scripts/materialized_sql_guard.py` 的 `load_guarded(path)` （或 `is_blocked(path)`）校验；剥离注释后非 `SELECT/WITH` 起手者抛 `NON_READONLY_HEAD` 并**终止快车道**，转人工登记或实时编译链路，严禁把「注释头 + 常量 0」的空壳当作有效结果返回（D4 伪零值防护）。
   > **代码级强制（2026-11-05 整改 R-04/R-05，不再是纯描述）**：离线匹配器
   > `skills/sg-indicator-system/engine/lookup_indicator.py` 在返回候选前已强制调用同一 guard，
   > 空壳码自动置 `has_sql=false` / `fast_lane_ready=false` 并附 `blocked_reason`；构建期
   > `build_indicator_index.py` 同源校验，防止下一轮索引再把空壳标成 true。
   > **边界**：14 份空壳源文件仍在磁盘上，绕过本技能手工 `open()` 仍能读到常量 `0`；
   > 该行为属违规操作，真实口径须由业务侧补齐并经设计态资产变更流程确认，本技能不编造 SQL。
   校验通过后，直接按文件名读取 materialized_sql/<ZB_CODE>.sql（路径由 zb_code 决定，无需加载注册表）；
   解析文件头部注释（ZB_CODE / ZB_NAME / DOMAIN / LEVEL / FACTORY / UNIT /
   SOURCE_TABLES / PARAMS / **MATURITY / CALIBER_SOURCE / CONFIDENCE**）作为元数据 —— 单文件 KB 级，零全量加载。
3. 依据时间意图做占位符替换 / 区间聚合（见下方「区间与同比聚合」）。
4. 应用 guards（ratio_not_additive 等；物化 SQL 已固化表达式，仅做空值/分区兜底）。
5. 交 sg-db2-executor 执行（DB2 MCP 优先，REST 需用户自备 lightcodegtw-token） → 返回结果集 + 命中来源（sql 文件名）。
6. 含「同比/环比/对比」时按步骤 3 跑两期，在渲染层算 delta（见 sg-qa-render）。
```

**命中即直查；仅在未命中离线匹配器时，才降级到 sg-dsl-compiler 实时编译（或转 sg-adhoc-indicator 即席构建）。快车道绝不加载 indicator_registry.json 全量。**

## 区间与同比聚合（性能关键 · 把"日统计"变"月/年累计 + 同比"）

物化 SQL 多为单日口径（`YMD='$TD$'`）。自然语言常问"本月 / 今年 / 同比"，需做**区间聚合**而非逐日调用：

| 时间意图 | 改写规则 | 占位符 |
|---|---|---|
| 当日 | 原样 `YMD='$TD$'` | `$TD$` = 指定日 |
| 本月（累计） | `SUM(ZB_VALUE)`，谓词 `YMD BETWEEN '$YM_START$' AND '$YM_END$'` | 月初~月末 |
| 本年（累计） | `SUM(ZB_VALUE)`，谓词 `YMD BETWEEN '$Y_START$' AND '$Y_END$'` | 年初~当前 |
| **同比**（本月 vs 去年同月） | 跑**两期**：本期 `BETWEEN 今年YM_START~YM_END`，对比期 `BETWEEN 去年YM_START~YM_END`；各自 `SUM` 后渲染层算 delta | `$YM_START$`/`$YM_END$` + 年偏移 |
| 环比（本月 vs 上月） | 同上，对比期改为上月区间 | — |

> 改写模板（通用，作用于带 `YMD=。.` 谓词的物化 SQL）：
> ```sql
> SELECT SUM(ZB_VALUE) AS ZB_VALUE
> FROM <源表>
> WHERE ZB_NAME='<ZB_NAME>' AND YMD BETWEEN '$START$' AND '$END$'
> ```
> `$START$`/`$END$` 由 DSL.time 映射为 `YYYYMMDD`；同比的对比期 = 同期年份 -1。
> 仅对 `LEVEL IN (atomic, derived)` 且 `PARAMS` 含日期的可加指标使用聚合，复合/比率型指标（如成材率）走原口径不盲目 SUM。

## 时间占位符替换表

| 占位符 | 含义 | 典型映射 |
|---|---|---|
| `$TD$` | 当日 | `VARCHAR_FORMAT(CURRENT DATE,'YYYYMMDD')` 或 DSL.time.to |
| `$D1$`~`$D7$` | 前 N 日 | `TD - N DAYS` |
| `$D4$` | 前 4 日 | 同规则 |
| `$D30$` | 前 30 日 | 同规则 |
| `$YM$` | 当前会计期间 | 月初~月末 |

> 若 SQL 使用 `$D4$` 而用户要"今日"，编译器按 `DSL.time` 选择最接近的可用占位符；
> 多占位符 SQL 仅替换出现在该 SQL `params` 列表中的令牌，其余原样保留。

## 与 DSL 编译器的分工

| 场景 | 路径 | 延迟 |
|---|---|---|
| `code` 命中注册表 | **物化直查（本技能）** | 秒级 |
| 未命中但语义层有注册口径 | `sg-dsl-compiler` 实时编译 | 秒~分钟 |
| 完全未注册指标 | `sg-adhoc-indicator` 即席构建 DWD/DWS | 首查较慢，二次命中转直查 |

## 输出规范

**⚠ maturity 出口（2026-11-05 P1-9 补齐）**：`maturity` / `caliber_source` / `confidence` 三个字段来自步骤 2 解析的物化 SQL 头部注释，**必须原样透传**，不得省略、不得擅自写死 `certified`。下游 `fast_lane_response.md` 的「maturity 来源声明」消费本字段；三档语义见 `agents/references/caliber_check.md`（`indexed`/未注册走五级回退、`draft` 须标注置信度+口径来源+"未经人工校准"、`certified` 正常查询）。字段缺失 → 下游按 `maturity=draft` 降级并披露 `[未经语义层校验]`。

```json
{"mode": "materialized",
 "zb_code": "6015400",
 "source_file": "materialized_sql/6015400.sql",
 "sql_executed": "SELECT ZB_VALUE FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_0002 WHERE ZB_NAME='。.' AND YMD='20260903'",
 "params_substituted": {"$TD$": "20260903"},
 "maturity": "draft",
 "caliber_source": "materialized_sql/6015400.sql 头部注释",
 "confidence": 0.70,
 "compile_log": {"template": "prebuilt", "checks": {"syntax":"pass","table_exists":"pass","reasonable":"pass"}},
 "lineage": [{"stage":"DWS","tables":["SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_0002"]},{"stage":"IND","note":"由 SQL1 计算"}]}
```

## 注意事项

1. **物化 SQL 已通过 import 期校验**（层级/血缘/参数提取），运行期只做时间替换与分区兜底，不改动表达式。
2. 仅只读执行；仍需过 `sg-quality` 可靠性闸门后才交付。
3. `unresolved` 指标（注册表中 `level="unresolved"`、无 `materialized_sql_file`）**不可直查**，须转 `sg-adhoc-indicator`。
4. 大数据量指标可配置"预编译"：由记忆专家每日跑一次存 WeKnora（见 `sg-memory`；腾讯文档通道已 disabled）。

## 物化写回入口（2026-11-15 新增 · 指向 sg-sql-materialization）

**本技能只做”读取+执行“。未物化指标经慢车道编译、用户确认后，**物化写回**（本地 materialized_sql + markdown 指标卡 + 注册表 + WeKnora K3 双写 + 血缘三闸门）由 `sg-sql-materialization` 负责（`sg-skill-evolution` 衍薪主责调度）。详见 `skills/sg-sql-materialization/SKILL.md` 六步闭环。写入前必须过 `scripts/materialized_sql_guard.py`，禁止常量 0 / 非只读头入库。

## 离线快照回退（无 DB2 环境）
若 DB2 MCP 与 REST 网关均不可用，每个指标的样例取数快照已固化于：
`knowledge/design/indicator/sample_results/<zb_code>.json`（相对专家团根目录，最多 50 行样例行）。
可据此向接收方展示指标口径示例；实时数据仍须走 DB2 MCP 或 REST 网关（需自备 token）。
全局索引：`knowledge/design/indicator/sample_results/_index.json`。


<!-- SG-QA-FLOW-GUARD v1 -->
## 智能数问流程硬约束（不可跳过）

1. **禁止直调 `ind-*` 取数**。`ind-<ZB_CODE>` 只是单指标档案（口径 / SQL / 样例快照），不是执行入口；
   且已在 `plugin.json` 中**取消登记**，不作为可加载技能。任何"绕过流程直接给数"均属违规。
2. **固定链路，缺一不可**：
   意图解析（`sg-intent-parse-dispatch`）
   → 指标路由（`sg-semantic-layer`，查 `knowledge/design/indicator/indicator_registry.json`、
     `indicator_index.json` 与 DB2 `T_ADS_DIM_GZ01`）
   → SQL 物化（`sg-materialized-sql`，取 `knowledge/design/indicator/materialized_sql/<ZB_CODE>.sql`）
   → 执行取数
   → 渲染交付（`sg-qa-render` / `sg-report-composer`）。
3. **执行通道**：优先 DB2 MCP `mcp__db2__execute_sql`；MCP 不可用时降级 REST 网关
   `scripts/sgdw_rest_exec.py`（凭证见 `scripts/sgdw_rest.env`）。两通道的 SQL 与口径必须完全一致。
4. **口径溯源**：结论必须能回溯到 `ZB_CODE` + `sql1` / 物化 SQL + 所用执行通道，禁止凭先验给数。
