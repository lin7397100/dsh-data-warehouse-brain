---
name: sg-indicator-system
description: "三钢数仓智脑：四级指标体系构建与血缘定义。依据《5S平台数据模型开发规范》构建 业务/原子/派生/复合 四级指标，为每个指标定义 ODS→DWD→DWS→ADS→IND 数据血缘，产物落地第三层知识引擎层（本地 knowledge/ 为权威，外部副本经 WeKnora K3 指标库同步；腾讯文档通道已 disabled），供智能问数接入提升准确率。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, indicator, metric, lineage, 5s]
owner: sg-metric-builder
---

# sg-indicator-system · 四级指标体系构建与血缘

## 定位

指标构建专家（矩衡）的主引擎。把"指标建对、血缘说清"作为唯一职责，产物同时服务于：
- **语义层**（铨度用作口径校验锚点，复用 `ZB_CODE`）
- **本体图谱**（鼎元融合 `lineage_graph.json` 的实体-关系-过程-指标）
- **智能问数**（语义解析阶段三引擎之一，提升命中率与口径准确性）

## 权威来源

> 乐享知识库 → 团队「AI赋能」→ 空间「大数据5S开发平台知识库」→ 文档《5S平台数据模型开发规范》
> entry_id：`753517e1c89f40cf955f97136abaad38`（35MB .doc，线下同步）

指标建设体系 = **四级指标 + 数据血缘**：

| 层级 | 是否可计算 | 依赖 |
|---|---|---|
| L1 业务指标 | 否 | `maps_to` → L3/L4 |
| L2 原子指标 | 是 | 业务过程 + 度量 + 聚合 |
| L3 派生指标 | 是 | `atomic_ref` + 周期 + 维度 + 限定 |
| L4 复合指标 | 是 | `components`（原子/派生）+ 公式 |

## 工作流（四步）

### Step 1 · 采集来源
- `T_ADS_DIM_GZ01` 本地 CSV 镜像（5970 行 KPI 配置，含 `ZB_CODE`）
- 业务过程清单 / 55 个存储过程输出字段反推
- 用户口述的业务指标需求

### Step 2 · 分层构建（顺序强制：L2 → L3 → L4 → L1）
- 先建原子（绑定 `source_table`/`grain`/`agg`）
- 再建派生（`atomic_ref` 必须已存在）
- 再建复合（`components` 必须已存在，给 `formula`）
- 最后业务（`maps_to` 必须指向已存在派生/复合）

### Step 3 · 血缘定义（每个指标必填 `lineage.chain`）
```
ODS 源表 → DWD 明细 → DWS 汇总 → ADS 应用(T_ADS_DIM_GZ01) → 指标
```
- 原子：止于 DWS；派生：复用原子血缘 + 周期/维度；复合：合并组件血缘。
- 物理表/字段未知 → 标 `unknown` 并触发质量闸门复核，**禁止臆造表名**。

### Step 4 · 校验 + 落地 + 持久化
- 引用完整性校验（派生 ref 原子、复合 ref 组件、业务 ref 下层），失败退出码 1。
- 落地第三层知识引擎层：
  - 设计态：`knowledge/design/indicator/{indicator_system.json,.yaml,lineage_graph.json,indicator_report.md}`
  - 运行态：`knowledge/observed/indicator/indicator_run_<date>.json`
- **外部可分享副本（腾讯文档通道已 disabled）**：将 `indicator_report.md` 落本地 `knowledge/design/indicator/` 为权威，并预留 WeKnora K3 指标库（`227f0a01-c36b-488a-8049-5b5869175782`）同步；原腾讯文档方案见下（已弃用）。

## 运行命令

```bash
cd "$DSH_HOME/skills/sg-indicator-system"
python engine/build_indicator_system.py --out 。/。/knowledge
# 增量合并：--indir 。/。/knowledge/design/indicator/indicator_system.json
```

## 外部可分享副本（腾讯文档通道已 disabled）

指标构建专家将 `indicator_report.md` 落本地 `knowledge/design/indicator/`（腾讯文档 MCP 已 disabled，原流程如下、已弃用）：

```
mcp__tencent-docs__doc.create_with_markdown(
    title="三钢数仓 · 四级指标体系（设计态基线）",
    markdown=<indicator_report.md 全文>)
→ 返回 doc_id / 可分享链接，回传编排器与用户
```

> 本地 `knowledge/` 为权威基线；腾讯文档同步副本已弃用（tencent-docs disabled），改经 WeKnora K3 指标库同步（待排期）；每日自动化或按需重新构建后同步。

## 与智能问数的接入（三引擎）

语义解析阶段（`sg-semantic-layer`）从「语义层 + 本体」扩展为**三引擎**：

1. **语义层**（6077 KPI 精确匹配）
2. **本体子图**（实体-关系-过程定位）
3. **指标体系**（本技能产物 `indicator_system.json`）：先按 `ZB_CODE`/名称命中指标 → 取其 `level`、`domain`、`expression`、`lineage` 回填 DSL 的 `indicator_refs` 与 `lineage_refs`

问数渲染的口径卡新增字段：`指标层级(level)`、`复合公式(formula)`、`数据血缘(lineage)`。

## 产物清单

| 产物 | 路径 | 用途 |
|---|---|---|
| 全量模型 JSON | `knowledge/design/indicator/indicator_system.json` | 机读、问数接入 |
| 基线 YAML | `knowledge/design/indicator/indicator_system.yaml` | 人类可读基线 |
| 血缘图 | `knowledge/design/indicator/lineage_graph.json` | 并入本体图谱 |
| 报告 MD | `knowledge/design/indicator/indicator_report.md` | 本地评审 / WeKnora K3 同步（腾讯文档 disabled） |
| 运行快照 | `knowledge/observed/indicator/indicator_run_<date>.json` | 回归比对 |

## 铁律

1. 四级不可倒置；引用必须存在，否则校验失败。
2. 血缘不可臆造；未知字段标 `unknown` 交质量闸门。
3. `ZB_CODE` 为跨层唯一锚点，与语义层/本体层一致。
4. 比率类（合格率/吨钢成本/吨钢利润）必须"分子分母各自聚合后相除 + NULLIF"。
5. 产物落本地权威：本地知识引擎（权威）；外部副本原走腾讯文档（disabled），改 WeKnora K3 指标库同步（待排期）。
6. 增量合并，禁止覆盖式重建；版本号随变更递增。
