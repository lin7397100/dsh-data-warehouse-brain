---
name: sg-sql-materialization
description: "三钢数仓智脑：SQL 物化闭环引擎。未物化指标经专家团编译 SQL、用户确认后，由衍薪主责把 SQL 物化到知识库（本地 materialized_sql + markdown 指标卡 + 注册表）并同步 WeKnora K3，同时校验数据血缘、指标血缘与业务计算逻辑准确性，使下次同类请求从慢车道转快车道秒级命中。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, materialization, sql, lineage, knowledge-base, fast-lane]
owner: sg-skill-evolution
---

# sg-sql-materialization · SQL 物化闭环（确认后写回）

> **定位**：把"专家团本次编译的临时 SQL"沉淀为"下次可秒级直查的物化资产"。这是慢车道的**出口**，也是快车道资产**增长**的唯一合法路径。
> **触发前提（硬门禁）**：SQL 已经用户**明确确认**。"用户说可以 / 就这么取 / 固化它"等显式确认才可物化；**未经确认禁止写库**（防错误 SQL 污染资产库）。

## 一、为什么需要本技能（根因）

现状：`sg-materialized-sql` 只会**读**物化 SQL；衍薪（`sg-skill-evolution`）只管**技能**进化，不管 SQL 资产。未物化指标每次都走慢车道（编译→审查→执行），无法沉淀。本技能补齐"确认→物化→双血缘→计算逻辑校验→知识库同步"闭环，实现用户诉求：**"用户确认的 SQL 物化到知识库，创建 markdown 存储指标与 SQL，数据血缘/指标血缘/计算逻辑准确"**。

## 二、物化六步（缺一即物化失败，禁止登记为物化资产）

### Step 1 · 用户确认门禁（不可跳过）
- 输入：慢车道编译的 SQL + 专家团对口径的说明。
- **必须**得到用户显式确认（原话记录到 `confirmation.raw_quote` + `confirmation.at`）。
- 无确认 → 终止，SQL 仅作为本次临时结果，**不物化**。

### Step 2 · 计算逻辑三查（准确性质检 · 砺真执行）
| 查 | 内容 | 不过处置 |
|---|---|---|
| 语法 | DB2 方言；只读 `SELECT/WITH` 起手；无 `FETCH FIRST`（MCP 自动分页）；无写操作 | 退回 sg-development 重编译 |
| 口径 | 版本/账期/基地/期间口径正确（成本域 V1/V4/V3 口径族）；DOUBLE 除法；加权 SUM/SUM 非 AVG | 退回 sg-semantic 复核口径 |
| 防翻倍 | JOIN 维表先去重（CDT6 限 YEAR + GROUP BY COST_CENTER；CDT8 LOADER='1'）；合计码不与分炉同 SUM | 退回 sg-development 修 SQL |

三查全过才进入写库；任一不过写 `validation.verdict=reject` 并留痕。

### Step 3 · 数据血缘定义（舆图执行 · 第零铁律）
按主理人 §第零铁律产出**标准血缘 JSON**（三闸门：结构完整 / 链路连续 / 设计态-数据态一致）：
- 反向追溯：SQL1 有 + CREATER 可取 → `sg-data-lineage` 解析 ODS→DWD/DWS(+tmp)→ADS；
- 断链（SQL1 空 / CREATER 取不到）→ `sg-metric-builder` 正向建模，标注 `[正向建模·待实据核验]`，置信度低于反向实据；
- 无 ADS 层直接用 CDM 展示是合法终点，不判断裂。
- 血缘 JSON 写入 markdown 卡的 `## 数据血缘` 段 + 注册表的 `lineage_chain` 字段。

### Step 4 · 指标血缘定义（矩衡执行）
按四级体系标注 `level`（L1 业务/L2 原子/L3 派生/L4 复合）+ `expression` + `components/atomic_ref`：
- 派生必 `atomic_ref` 指向已存在原子；复合必给 `formula`；
- 比率类：分子分母各自聚合后相除 + `NULLIF` 保护；
- 指标血缘写入 markdown 卡的 `## 指标血缘` 段。

### Step 5 · 物化落盘（衍薪主责 · 本地 + WeKnora 双写）
**本地（权威基线）**：
1. SQL → `knowledge/design/indicator/materialized_sql/<ZB_CODE>.sql`，头部注释含 `ZB_CODE / ZB_NAME / DOMAIN / LEVEL / FACTORY / UNIT / SOURCE_TABLES / PARAMS / MATURITY / CALIBER_SOURCE / CONFIDENCE`。
   - 时间字面量参数化为 `$TD$`/`$Dn$`/`$YM_START$` 占位符（复用 sg-materialized-sql 占位符表）。
   - 写前先过 `scripts/materialized_sql_guard.py`，禁止空壳常量 0 入库。
2. markdown 指标卡 → `knowledge/design/indicator/materialized_cards/<ZB_CODE>.md`，模板见 `references/materialization_card_template.md`。
3. 注册表 → 增量更新 `knowledge/design/indicator/indicator_registry.json`：该 code 的 `materialized_sql_file` / `maturity` / `caliber_source` / `confidence` / `lineage_chain` / `materialized_at`。
   - **增量不覆盖**：已存在指标只补字段，不改其他指标。
4. 版本备份：改注册表/SQL 前按衍薪铁律备份到 `.versions/` 并记 CHANGELOG。

**WeKnora（RAG 可检索副本）**：
5. `create_knowledge_from_text(kb_id="227f0a01-c36b-488a-8049-5b5869175782", title="IND-物化-<ZB_CODE>-<ZB_NAME>", content=markdown 卡全文, status="publish")` → 指标库 K3。
   - 同步失败 → 写 `knowledge/observed/pending_sync/` 暂存 + 交付披露 `[K3同步待补]`，恢复后幂等补同步；**禁止**静默丢弃。

### Step 6 · 回归验证与转正（衍薪执行）
- 用同参数重跑物化 SQL，结果须与用户确认时的结果一致（量级/行数/关键值）。
- 快车道验证：`lookup_indicator.py` 能命中该 code 且 `fast_lane_ready=true`、`blocked_reason` 为空。
- 全通过 → 物化状态 `published`；否则 `draft` 观察（3~5 次同类任务成功率≥90% 再转正）。
- 回传主理人：物化 code 清单 / 落盘路径 / K3 同步状态 / 血缘三闸门结果 / 计算逻辑三查结论。

## 三、输出规范（物化报告）

```json
{
  "materialization_id": "MAT-<trace_id>",
  "confirmed_by_user": {"raw_quote":"...","at":"<ISO8601>"},
  "items": [{
    "zb_code":"...", "zb_name":"...",
    "validation":{"syntax":"pass","caliber":"pass","anti_double":"pass","verdict":"pass"},
    "data_lineage":{"gates":{"structure":"pass","continuity":"pass","design_vs_data":"pass"},"confidence":0.95},
    "indicator_lineage":{"level":"L3","expression":"...","atomic_refs":[]},
    "artifacts":{"sql":"materialized_sql/<code>.sql","card":"materialized_cards/<code>.md","registry_updated":true},
    "weknora_sync":{"kb_id":"227f0a01-...","status":"published|pending","doc_title":"IND-物化-..."},
    "regression":{"match":true,"fast_lane_ready":true},
    "status":"published|draft"
  }]
}
```

## 四、协作分工（多专家，不得衍薪独揽）

| 步骤 | 主责 | 配合 |
|---|---|---|
| 1 用户确认 | 主理人冶衡（向用户取证） | — |
| 2 计算逻辑三查 | 砺真 sg-quality | 淬锋（语法修复）、铨度（口径复核） |
| 3 数据血缘 | 舆图 sg-metadata | 鼎元（过程解析）、矩衡（正向建模兜底） |
| 4 指标血缘 | 矩衡 sg-metric-builder | 铨度（语义层对齐） |
| 5 物化落盘 | 衍薪 sg-skill-evolution | 淬锋（SQL 参数化）、舆图（注册表） |
| 6 回归验证 | 衍薪 sg-skill-evolution | 砺真（结果复核）、监衡（审计） |

## 五、铁律
1. **无用户确认不物化**（最高优先级）。
2. **无双血缘不物化**：数据血缘三闸门 + 指标血缘四级，缺一不登记为物化资产。
3. **计算逻辑三查不全过不物化**：准确率优先于覆盖率。
4. **先备份后修改**：注册表/SQL 改动走衍薪版本库，可回滚。
5. **双写不静默失败**：WeKnora 同步失败要暂存 + 披露。
6. **物化资产只读**：物化 SQL 运行时不改表达式，仅替换时间占位符。
