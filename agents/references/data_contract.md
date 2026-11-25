# Agent 间信息传递契约（P5.1 修复 · 2026-11-03 新增）

> 编排器必须按本文件定义的格式在 Agent 之间传递数据。Agent prompt 中引用本格式。

---

## 关键交接格式

| 交接环节 | 输出方 | 输入方 | 格式 | 必含字段 |
|---|---|---|---|---|
| ① Phase 0 → 编排器 | 砺真 | 编排器 | JSON | indicators[], decomposition, clues[], focus_areas[] |
| ② Phase 0.5 → 编排器 | 舆图 | 编排器 | JSON | gates:{G1,G2,G3}, verdict, ready |
| ③ 物理取证 → 编排器 | 舆图 | 编排器→砺真 | JSON | physical_lineage, gates[G1,G2,G3] |
| ④ 指标血缘 → 编排器 | 矩衡 | 编排器→砺真 | JSON | 标准血缘 JSON（§0.4b格式） |
| ⑤ 过程解析 → 编排器 | 鼎元 | 编排器→砺真 | JSON | procedure_name, factory_div_logic, join_conditions, tmp_tables[] |
| ⑥ 语义校验 → 编排器 | 铨度 | 编排器→砺真 | YAML | 口径冻结卡（caliber_freeze.md §二） |
| ⑦ 域证据 → 编排器 | 管枢/成枢 | 编排器→砺真 | JSON | domain: prod|cost, metrics[], domain_notes |
| ⑧ 证据包 → 砺真 | 编排器 | 砺真 | JSON | evidence_package: {phase0, gate, physical_lineage, metric_lineage, procedure, caliber, domain(可选), completeness:{每路证据的completeness字段}} |
| ⑨ 裁定 → 编排器 | 砺真 | 编排器→明鉴/若溪 | JSON | root_cause, confidence, evidence_summary, gates |
| ⑩ 交付数据包 → 明鉴/若溪 | 编排器 | 明鉴/若溪 | JSON | data_package: {caliber, data:{metrics[], ods_details[]}, root_cause(可选), charts_spec:{required[], dimensions[]}} |

---

## evidence_package 完整格式

```json
{
  "trace_id": "TR-20261103-XXXX-XXX",
  "phase0": { /* 砺真 Phase 0 输出 */ },
  "gate": { /* 舆图 Phase 0.5 输出 */ },
  "physical_lineage": { /* 舆图 Phase 1 输出 */ },
  "metric_lineage": { /* 矩衡 Phase 1 输出 */ },
  "procedure": { /* 鼎元 Phase 1 输出 */ },
  "caliber": { /* 铨度 Phase 1 输出 */ },
  "domain": { /* 管枢/成枢 Phase 1 输出（可选） */ },
  "completeness": {
    "physical_lineage": "full|partial|missing",
    "metric_lineage": "full|partial|missing",
    "procedure": "full|partial|missing",
    "caliber": "full|partial|missing",
    "domain": "full|partial|missing|n/a"
  }
}
```

---

## data_package 完整格式（Step 8 交付数据包 · P5.3 修复）

```json
{
  "caliber": {
    "zb_code": "1600213",
    "zb_name": "本部经营日报(1)_炼钢_钢铁料耗_日平均",
    "factory_div": "管控中心",
    "factory_label": "本部（三明闽光）",
    "sql1_key": "SELECT ... FROM T_DWS_FACT_ZZGZ_LG01 WHERE ZB_CODE='1600213'",
    "creater": "P_DWS_FACT_ZZGZ_0003",
    "maturity": "draft"
  },
  "data": {
    "metrics": [
      {"zb_code": "1600213", "date": "20261102", "value": 1054.83, "unit": "kg/t"}
    ],
    "ods_details": [
      {"factory": "一炼", "date": "20261102", "heat_count": 70, "iron_sum": 12345, "steel_sum": 11700, "cons_sum": 12340}
    ]
  },
  "root_cause": {
    "verdict": "正常波动",
    "confidence": 0.93,
    "description": "11/02 钢铁料耗 1054.83 处于10月全月正常区间...",
    "evidence_chain": ["证据1...", "证据2..."]
  },
  "charts_spec": {
    "required": ["trend", "composition"],
    "dimensions": ["date", "factory"],
    "title": "本部钢铁料耗近7日趋势"
  }
}

---

## 合并步与产物连贯性（P6 新增 · 2026-11-03）

> 上一任务 TR-20261103-1926-CD6F 的失败根因之一是：并行 Agent 返回自由文本，编排器手工拼装，下游（明鉴/若溪）各自重查 DB2，导致下钻数据与主表对不齐、产物割裂。本段把「信封 → 落盘 → 下游只读」固化为硬规则。完整扇出/扇入/再派发流程见 `agents/references/parallel_coordination.md`。

### 合并步（Merge · 编排器职责，禁止下游各自取数）

1. 扇入完成后，编排器按上方 `evidence_package` / `data_package` 模板组装对象。
2. **落盘为文件**（唯二事实源）：
   - `observed/evidence_<trace>.json` —— 取证阶段全部证据（含每路 `completeness`）
   - `observed/data_package_<trace>.json` —— 交付阶段数据（caliber + data + root_cause + charts_spec）
3. 闭合校验：汇总 `completeness`；关键路径 `missing` → 回到 `parallel_coordination.md §4` 补派，不可带缺口进入裁定。

### 产物连贯性（Artifact Coherence）

| 规则 | 说明 |
|---|---|
| **下游只读文件** | 砺真（裁定）/ 明鉴 / 若溪 / 达仕 的 prompt 必须写明「读取 `observed/evidence_<trace>.json`（或 `data_package_<trace>.json`），禁止重新查询 DB2」 |
| **禁止重查分叉** | 任何下游 Agent 不得自行 `DeferExecuteTool(mcp__db2__*)` 取数——只消费数据包，否则数值分叉、下钻对不齐 |
| **下钻逐行一致** | HTML 报告 `window.__D` 下钻数据须与 `data_package.json` 数值**逐行一致**；交付前 `verify_report.js` 比对 |
| **单一事实源** | 全链路只存在上述两个文件作为事实源；跨 Agent 传递一律传文件路径，不传大段 SQL 结果 |

### 再派发触发（Re-dispatch）

- 合并后发现某 slot `missing` → 针对性补派该 slot 的 **1 个** Agent（不重跑全链路），结果回填文件。
- 下游消费发现数据缺口 → 回到对应上游 slot 补派，回填文件后重消费。
- 原则：**只补缺失的那一路**，这是压缩耗时、避免产物割裂的关键。
```