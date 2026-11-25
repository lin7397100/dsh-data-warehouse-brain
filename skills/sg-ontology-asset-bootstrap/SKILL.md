---
name: sg-ontology-asset-bootstrap
description: "三钢数仓智脑：本体资产骨架契约初始化。定义 design/observed 双轨目录、六大业务域边界、四元组 JSON Schema、文件命名规范、验收标准与本体-语义锚点字段，产出 CONTRACT.md 与空骨架文件，为 sg-ontology-modeling / sg-cost-ops 的逐域填充提供可增量更新的地基。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, ontology, bootstrap, contract, asset]
owner: sg-ontology
---

# sg-ontology-asset-bootstrap · 本体资产骨架契约初始化

## 定位

**先立契约，再生产内容。**

`sg-ontology-modeling` 负责「把业务逻辑翻译成四元组本体」，但它只规定了「按业务域拆分落盘」，没有规定目录、Schema、命名与验收标准。若跳过本技能直接建模，会产出一堆格式各异的 JSON —— 第二次运行无法判断「哪些变了」，**增量更新与版本回滚全部失效**。

本技能是本体资产的**地基工程**：一次性（或按需重建）产出契约文件与空骨架，之后所有本体生产都必须遵守。

## 何时使用

| 场景 | 是否使用 |
|---|---|
| `knowledge/` 为空目录，首次建本体 | ✅ 必须先跑本技能 |
| 域边界 / JSON Schema 需要调整 | ✅ 重跑（会先备份 CONTRACT.md） |
| 已有契约，只是往某个域里填内容 | ❌ 用 `sg-ontology-modeling` |
| 检查本体资产是否合规 | ✅ 用本技能的「验收自检」章节 |

## 双轨目录契约（核心设计）

本体资产必须区分**设计态**与**数据态**，二者绝不可混放 —— 设计态含人工校准成果，**禁止自动覆盖**。

```
$ONTOLOGY_HOME/
├── CONTRACT.md                  ← 本技能产出（契约正文）
│
├── design/                      ← 设计态：人工校准，禁止自动覆盖
│   ├── ontology/
│   │   ├── domain-production-rolling.json   生产域·轧钢
│   │   ├── domain-production-ironmaking.json 生产域·炼铁
│   │   ├── domain-production-steelmaking.json 生产域·炼钢
│   │   ├── domain-production-material.json   生产域·原料
│   │   ├── domain-purchase.json               采购域
│   │   ├── domain-energy.json                 能源域
│   │   └── domain-daily-cost.json             成本域（十步链）
│   ├── semantic/
│   │   ├── kpi-core.json        L0 核心池（certified）
│   │   ├── kpi-extended.json    L1 扩展池（draft）
│   │   └── kpi-index.json       L2 长尾池（indexed）
│   └── bloodline/
│       └── bloodline-{域}.md
│
├── observed/                    ← 数据态：自动刷新，可随时重建
│   ├── schema/                  表结构快照
│   ├── procedures/              存储过程清单与版本
│   └── lineage/                 物理血缘
│
├── .changes/                    ← 每日变更清单（YYYY-MM-DD.md）
└── .versions/                   ← 版本库（design/ 每次合入前自动备份）
```

## 六大业务域边界

| 域 | 标识 | 覆盖范围 | 主要 Schema / 过程 | 域间边界说明 |
|---|---|---|---|---|
| 生产·轧钢 | `production-rolling` | 轧制计划、产线作业率、成材率、合格量 | `SMBB_M_S_ZZGZ_ZG01` / `P_DWS_FACT_ZZGZ_ZG01` | 与成本域在 **C010C 生产实绩** 交汇 |
| 生产·炼铁 | `production-ironmaking` | 高炉炉次、铁水产量、焦比煤比、利用系数 | `SMBB_M_S_*LT01*` | 铁水产量是成本域投入侧来源 |
| 生产·炼钢 | `production-steelmaking` | 转炉炉次、钢水产量、合金消耗 | `SMBB_M_S_*LG01*` | 同上 |
| 生产·原料 | `production-material` | 烧结、球团、原料库存 | `SMBB_M_S_*YL01*` | 库存类指标为**半累加**，禁跨时间求和 |
| 采购 | `purchase` | 采购订单、到货、结算、价格 | `SMBB_M_S_CGGZ_0001` | 单价是成本三因子之一 |
| 能源 | `energy` | 能源介质消耗、单价、成本分摊 | `SMBB_M_S_*NY*` | 与成本域共用介质单价 |
| 成本 | `daily-cost` | 日成本十步链、成本中心、品种成本 | `SMBB_M_S_CB00` / `P_AUTOMATION_COST_DAY` | **C010C 为双轮交汇点**（成本域只读生产实绩，不改） |

> **交汇点仲裁**：C010C（生产实绩）实体归属**生产域**，成本域以 `ref` 方式引用，禁止在成本域内复制一份 —— 复制即产生双写，是口径漂移的头号来源。

## 四元组 JSON Schema（固化）

所有 `design/ontology/domain-*.json` 必须严格符合以下结构，缺字段视为不合规：

```json
{
  "schema_version": "1.0",
  "domain": "production-rolling",
  "domain_name": "生产域·轧钢",
  "generated_by": "sg-ontology-modeling",
  "generated_at": "2026-09-01T09:00:00+08:00",
  "version": "v1",
  "maturity": "certified|draft",
  "entities": [
    {"id": "E_ROLLING_LINE", "name": "轧机产线", "source_table": "SMBB_M_O_XXX",
     "keys": ["LINE_CODE"], "attributes": ["轧制计划号", "钢种标志", "生产时间"],
     "semi_additive": false}
  ],
  "relations": [
    {"id": "R_LINE_EXEC_PLAN", "from": "E_ROLLING_LINE", "to": "E_ROLLING_PLAN",
     "type": "执行", "cardinality": "1:N"}
  ],
  "processes": [
    {"id": "P_DWS_FACT_ZZGZ_ZG01", "name": "轧钢日作业率计算",
     "pattern": "A|B|C|D",
     "inputs": ["SMBB_M_O_XXX"], "outputs": ["SMBB_M_S_ZZGZ_ZG01"],
     "chain": [{"step": "T1", "logic": "计划×钢种关联"},
               {"step": "T2", "logic": "时间窗过滤"}],
     "decode_maps": [{"field": "FACTORY_DIV", "map": {"1": "三钢闽光"}}],
     "aggregation": {"level": "day", "group_by": ["YMD", "FACTORY_DIV"]}}
  ],
  "metrics": [
    {"zb_code": "2000514", "zb_name": "质量_圆棒当日合格量",
     "owner_entity": "E_ROLLING_LINE",
     "measure_or_metric": "measure|metric",
     "bloodline": ["KPI", "语义", "DWS", "存储过程", "ODS"],
     "maturity": "certified"}
  ],
  "refs": [
    {"target_domain": "daily-cost", "entity": "E_PROD_ACTUAL",
     "note": "C010C 生产实绩，成本域引用不复制"}
  ],
  "open_issues": []
}
```

## 本体-语义锚点字段（对齐契约）

本体与语义层的对齐锚点**唯一且必须是 `zb_code`**：

| 层 | 主键 | 交叉引用 |
|---|---|---|
| 本体 `metrics[]` | `zb_code` | `owner_entity` → 本体 `entities[].id` |
| 语义 `kpi-*.json` | `zb_code` | `owner_domain` → 本体 `domain` |
| 血缘 `bloodline-*.md` | `zb_code` | 双向可查（KPI 下钻 / ODS 上卷） |

**禁止**用中文字段名（如「质量_圆棒当日合格量」）作为跨层关联的键 —— 名称会随业务改口径而变，`zb_code` 不会。

## 文件命名规范

| 类型 | 命名 | 示例 |
|---|---|---|
| 域本体 | `domain-{domain}.json` | `domain-production-rolling.json` |
| 语义池 | `kpi-{core|extended|index}.json` | `kpi-core.json` |
| 血缘 | `bloodline-{domain}.md` | `bloodline-daily-cost.md` |
| 变更清单 | `YYYY-MM-DD.md` | `2026-09-01.md` |
| 版本备份 | `{原文件名}.v{N}.{YYYYMMDDHHmm}.bak` | `domain-production-rolling.json.v3.202609010900.bak` |

## 工作流（四步）

### Step 1 · 环境校验

确认三个环境变量已设置：

| 变量 | 用途 | 缺失时 |
|---|---|---|
| `$ONTOLOGY_HOME` | 本体资产根目录 | **中止**，提示用户配置 |
| `$DB2_ASSETS_HOME` | DB2 DDL / 存储过程源 | 警告：可建骨架，但无法填充 |
| `$WORKSPACE` | 工作区 | 警告：产出落当前目录 |

### Step 2 · 生成契约与骨架

1. 若 `$ONTOLOGY_HOME/CONTRACT.md` 已存在 → **先备份到 `.versions/`**，再覆盖
2. 创建 `design/` `observed/` `.changes/` `.versions/` 四个目录
3. 按六大域生成**空骨架 JSON**（`entities/relations/processes/metrics` 均为空数组，`maturity: "draft"`）
4. 生成 `kpi-core.json` / `kpi-extended.json` / `kpi-index.json` 空池
5. 写出 `CONTRACT.md`（含本技能全文要点：双轨目录、域边界、Schema、命名、验收标准）

### Step 3 · 域优先级登记

在 `CONTRACT.md` 中写入填充顺序与理由（覆盖约 80% 高频 KPI）：

```
1. production-rolling  (轧钢 ZG01)
2. production-ironmaking (炼铁 LT01)
3. production-steelmaking (炼钢 LG01)
4. production-material (原料 YL01)
5. daily-cost          (日成本十步链)
6. purchase            (采购管制)
7. energy              (能源)
```

### Step 4 · 验收自检

按下方「验收标准」逐条自检，输出合规报告。

## 验收标准

| # | 标准 | 判据 |
|---|---|---|
| 1 | 目录双轨分离 | `design/` 与 `observed/` 均存在，且 `design/` 下无任何自动写入标记 |
| 2 | 六域骨架齐全 | 7 个 `domain-*.json` 存在且符合 Schema |
| 3 | Schema 合规 | 所有 JSON 可被解析，`schema_version` 均为 `1.0` |
| 4 | 锚点唯一 | 每个 `metrics[].zb_code` 全局唯一，无重名键 |
| 5 | 交汇点无双写 | `refs[]` 正确引用，`daily-cost` 域内无 `E_PROD_ACTUAL` 实体副本 |
| 6 | 版本可回滚 | `.versions/` 存在且含本次操作前的备份 |
| 7 | 无硬编码路径 | 全库检索无绝对路径，均为 `$ONTOLOGY_HOME` / `$DB2_ASSETS_HOME` |

## 输出规范

- `$ONTOLOGY_HOME/CONTRACT.md` —— 契约正文（可读 Markdown）
- `$ONTOLOGY_HOME/design/ontology/domain-*.json` × 7 —— 空骨架
- `$ONTOLOGY_HOME/design/semantic/kpi-*.json` × 3 —— 空池
- 验收自检报告：7 条标准逐条 PASS / FAIL + 不合规项清单

## 注意事项

1. **纯文件操作工作流，不调用 MCP** —— 不查业务数据，只读环境变量与目录。
2. **先备份后覆盖**：`CONTRACT.md` 已存在时必须先备份，可回滚是底线。
3. **骨架是空的，不是猜的**：骨架阶段 `entities` 等字段必须为空数组，**禁止预填臆测内容**；不确定项写入 `open_issues`。
4. 本技能只做**一次性/按需**的地基工程；日常填充归 `sg-ontology-modeling`，变更检测归 `sg-metadata-core`。
5. 路径一律走环境变量，**禁止硬编码绝对路径**（跨电脑复用要求）。
