# 物化指标卡 Markdown 模板（<ZB_CODE>.md）

> 由 `sg-sql-materialization` Step 5 生成，本地落 `knowledge/design/indicator/materialized_cards/<ZB_CODE>.md`，并同步 WeKnora K3。

```markdown
# <ZB_NAME>（<ZB_CODE>）· 物化指标卡

> 物化时间：<ISO8601> ｜ 物化 ID：MAT-<trace_id> ｜ 状态：published|draft
> 用户确认原话：「<raw_quote>」（<at>）

## 一、指标定义
| 项 | 值 |
|---|---|
| ZB_CODE | <code> |
| 指标全名 | <zb_name> |
| 业务域 | <cost|prod|inventory> |
| 指标层级 | <L1业务|L2原子|L3派生|L4复合> |
| 单位 | <unit> |
| 基地/账套 | <factory> / COMPANY_CODE='<xxx>' |
| 期间口径 | <V1当日 / V4月值 / DS3日成本 / DS4累计 …> |
| 成熟度 | <maturity> |
| 口径来源 | <caliber_source> |
| 置信度 | <confidence> |

## 二、业务计算逻辑
<自然语言描述 + 数学表达式，例：单位成本 = SUM(COST) / SUM(EARN_N) 加权，非 AVG>

- 计算方式：<求和/统计/求平均/加权> 
- 通用限定条件：<filters>
- 防错要点：<DOUBLE 除法 / NULLIF 分母 / 合计码防翻倍 / CDT6 去重 …>

## 三、可执行 SQL（物化，秒级直查）
```sql
-- ZB_CODE: <code>
-- DOMAIN/LEVEL/FACTORY/UNIT: <...>
-- MATURITY/CALIBER_SOURCE/CONFIDENCE: <...> / <...> / <...>
-- SOURCE_TABLES: <...>
-- PARAMS: $TD$ / $D1..D7$ / $YM_START$ / $YM_END$
-- 时间占位符由 DSL.time 替换；运行时不得改动表达式
<SELECT/WITH …>
```

## 四、数据血缘（第零铁律三闸门）
| 闸门 | 结论 | 证据 |
|---|---|---|
| ① 结构完整 | pass|fail | T_ODS / T_DWD·T_DWS[+tmp] / T_ADS |
| ② 链路连续 | pass|fail | SQL1 / CREATER / ROUTINEDEP / 实查对账 |
| ③ 设计态-数据态一致 | pass|fail | 与 DB2 实查对账 |

- 链路：`T_ODS_* → T_DWD_*/T_DWS_* (+tmp:<proc>) → T_ADS_*`
- 存储过程：<CREATER / 过程名>
- lineage_mode：reverse|forward
- 若 forward：标注 `[正向建模·待实据核验]`，置信度低于反向实据

## 五、指标血缘（四级）
- level：<L?>
- atomic_refs：[<L2 原子 code...>]
- components：[<L3/L4 组件...>]
- expression：<表达式>
- 比率类：分子分母各自聚合后相除 + NULLIF；additivity=<additive|non_additive>

## 六、回归验证
| 项 | 结果 |
|---|---|
| 与用户确认结果一致 | pass|fail |
| lookup_indicator 命中 | pass|fail |
| fast_lane_ready / blocked_reason | true / 空 |
| 计算逻辑三查 | 语法 pass｜口径 pass｜防翻倍 pass |
```

## 落盘与同步checklist
- [ ] `materialized_sql/<ZB_CODE>.sql` 写入且过 guard（非只读头/非常量0）
- [ ] 本卡片写入 `materialized_cards/<ZB_CODE>.md`
- [ ] `indicator_registry.json` 增量更新 materialized_sql_file/maturity/confidence/lineage_chain/materialized_at
- [ ] 改动前 `.versions/` 备份 + CHANGELOG
- [ ] WeKnora K3 `create_knowledge_from_text` 成功（失败写 pending_sync 并披露）
- [ ] 同参数重跑结果一致 + fast_lane_ready=true
