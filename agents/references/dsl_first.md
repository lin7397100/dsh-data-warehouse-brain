# DSL 先行铁律 · 契约与模板（GATE-2d）

> **依据**：主理人 MD「GATE-2d · DSL 先行铁律」（2026-11-06 新增）
> **一句话**：任何 DB2 SQL 在到达数据库之前，**必须先有 DSL 声明，再由 `sg-dsl-compiler` 确定性编译**。

---

## 1. 为什么必须这样

| 反模式 | 后果 |
|---|---|
| 专家团直接手写 SQL | 口径漂移、JOIN 扇出、跨基地污染、方言错误 —— 每次都是"新错误" |
| 先跑通再补 DSL | 伪造编译记录，审计链断裂 |
| 即席场景豁免 | E11 铁律失效，准确率崩塌 |

> **规则存在 ≠ 规则生效。** 本契约的价值在于把散落的规则收进**必经路径**。

---

## 2. DSL 标准 Schema（语义专家产出）

```json
{
  "dsl_version": "1.0",
  "intent": "metric_query | trend | compare | drill_down | rank",
  "indicator_refs": [
    {
      "code": "1600213",
      "name": "本部经营日报(1)_炼钢_钢铁料耗_日平均",
      "level": "atomic | derived | composite | business",
      "unit": "kg/t"
    }
  ],
  "dimensions": ["YMD", "FACTORY_DIV"],
  "filters": {
    "YMD": {"op": "between", "value": ["20261030", "20261105"]},
    "FACTORY_DIV": {"op": "in", "value": ["11"]},
    "ZB_CODE": {"op": "in", "value": ["1600213"]}
  },
  "guards": ["ratio_not_additive", "version_locked"],
  "assumptions": [
    "近7日 = 昨天往前推7天含昨天",
    "基地仅本部（COMPANY_CODE='100'）"
  ],
  "source_hint": {
    "table": "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01",
    "from": "indicator_registry.materialized_sql_file"
  }
}
```

### 字段必填规则

| 字段 | 必填 | 说明 |
|---|:--:|---|
| `dsl_version` | ✅ | 固定 `"1.0"` |
| `intent` | ✅ | 决定 SQL 骨架（见编译规则 1） |
| `indicator_refs[]` | ✅ | 至少 1 个；`code` 用于命中物化 SQL |
| `dimensions[]` | ✅ | 空数组表示不分组 |
| `filters` | ✅ | 至少含时间条件 |
| `guards[]` | ⚠️ | 比值型指标必填 `ratio_not_additive` |
| `assumptions[]` | ✅ | 默认假设必须显式声明，可审计 |

---

## 3. 编译输出契约（淬锋产出）

```json
{
  "sql": "SELECT ...",
  "mode": "materialized | compiled",
  "compile_log": {
    "template": "③ 时间序列",
    "params_expanded": {"$D7$": "20261030", "$TD$": "20261105"},
    "joins": ["维表:厂部 ON FACTORY_DIV"],
    "guards_applied": ["ratio_not_additive"],
    "checks": {
      "syntax": "pass",
      "table_exists": "pass",
      "reasonable": "pass"
    },
    "assumptions": ["时间范围默认近 7 天"]
  }
}
```

**三查不过 → 不产出 SQL。** 禁止产出"看起来能用"的语句。

---

## 4. 六种 SQL 模板（编译规则 2）

| # | 模板 | 适用 | 关键结构 |
|---|---|---|---|
| ① | 单值直取 | 单指标当前值 | `SELECT ZB_VALUE … WHERE ZB_CODE=? AND YMD='$TD$'` |
| ② | 分组汇总 | 按维度聚合 | `GROUP BY FACTORY_DIV` |
| ③ | 时间序列 | 趋势 | `WHERE YMD BETWEEN '$D7$' AND '$TD$'` |
| ④ | 同环比 | 对比 | `LAG(…) OVER (ORDER BY YMD)` |
| ⑤ | 下钻 | 层级展开 | CTE 递归 / 层级字段分段 |
| ⑥ | 排名 TopN | 排名 | `ROW_NUMBER() OVER(…)` 排序，限量走 `limit` 参数 |

> ⚠️ **禁写 `FETCH FIRST n ROWS ONLY` / `LIMIT`**：MCP 与 5sApi 两条通道都会在 SQL 尾部自动拼限行子句，SQL 文本再写一段直接 `SQLCODE=-104`（重复限行）。TopN 排序由窗口函数完成，返回行数交工具 `limit` 参数控制。

---

## 5. 七条编译规则（`sg-dsl-compiler` 全量）

| # | 规则 | 要点 |
|---|---|---|
| 1 | 意图 → SQL 骨架 | 五种 intent 对应不同骨架 |
| 2 | 六种 SQL1 模板 | 见上表 |
| 3 | 外键属性化 | JOIN 由编译器按语义层预定义生成，**模型不参与选择** |
| 4 | 按维对齐 | 多事实表向公共维度 `FULL JOIN`，维度组合不丢失 |
| 5 | 日期参数展开 | `$TD$`/`$D1$~$D7$`/`$D30$`/`$YM$`；**无法确定基准日则回退澄清，禁臆造** |
| 6 | DB2 方言强制 | SQL 文本禁写 `FETCH FIRST`/`LIMIT`（走 limit 参数）/ 大表强制注入 `YMD` / 除法 `NULLIF(分母,0)` / `VARCHAR_FORMAT` |
| 7 | guards 落地 | `dedup_required`→先 DISTINCT；`ratio_not_additive`→分子分母各自 SUM 后相除；`semi_additive`→时间维取 MAX 快照；`version locked`→强制版本条件 |

---

## 6. 违规判据（编排器派发前自检）

```
□ 本次 SQL 是否有对应的 DSL JSON？              无 → 违规 DF1「裸写裸出」
□ DSL 是否经 sg-dsl-compiler 编译？              无 → 违规 DF1
□ compile_log.checks 三项是否全 pass？           否 → 违规（三查未过）
□ 是否先跑 SQL 后补 DSL？                        是 → 违规 DF3，结果作废
```

### 四条硬禁令（DF = DSL First，避免与 report_rules 的 D1~D5 下钻闸门重名）

| # | 禁令 |
|---|---|
| **DF1** | 禁止「裸写裸出」：直接产出可执行 SQL 并提交 DB2，未经 DSL→编译→三查 |
| **DF2** | 禁止 `sg-adhoc-indicator` 即席场景豁免：即席指标同样只允许写 DSL |
| **DF3** | 禁止「先跑通再补 DSL」：事后补 DSL 视为伪造编译记录，结果作废 |
| **DF4** | 禁止域专家 prompt 内嵌 SQL：成枢/管枢只描述需求，由淬锋编译 |

---

## 7. 与既有 GATE 的关系

> **G2a 是「谁编译」，G2d 是「编译什么」。**

| 场景 | G2a | G2d | 结论 |
|---|:--:|:--:|---|
| 淬锋编译了手写的 SQL | ✅ | ❌ | **违规** —— 无 DSL，仍在临场发挥 |
| 有 DSL 但未编译 | ❌ | ✅ | **违规** —— 未确定性产出 |
| 有 DSL + 编译 + 三查 | ✅ | ✅ | 合规 |
| **G2d 未过** | 任意 | ❌ | **即使 G2a/G2b/G2c 全绿，SQL 仍不得执行** |

---

## 8. 快速自检命令

```bash
# 1. 检查 DSL 是否缺失（本次任务是否有 dsl json 落盘）
ls observed/dsl/ 2>/dev/null || echo "❌ 无 DSL，触发 DF1 违规"

# 2. 检查编译日志
python -c "import json,glob; f=sorted(glob.glob('observed/dsl/*.json')); print('DSL 文件数:', len(f))"

# 3. 检查三查结果
grep -o '"checks":{[^}]*}' observed/dsl/*.json 2>/dev/null
```

---

## 9. 版本

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-11-06 | 首版。补主理人 MD 缺失的 DSL 先行铁律（GATE-2d），收敛散落于 5 处 reference 的规则到必经路径 |
