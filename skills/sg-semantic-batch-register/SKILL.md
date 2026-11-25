---
name: sg-semantic-batch-register
description: "三钢数仓智脑：KPI 语义模型分批注册与成熟度分级。按 L0 核心池（人工校准 certified）/ L1 扩展池（自动注册 draft）/ L2 长尾池（仅索引 indexed）三层推进，为每条语义标注 maturity、caliber_source、confidence，消除「注册即合规」的虚假安全感，同时避免 6077 条全量灌入导致的长上下文腐化。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, semantic, kpi, registration, maturity]
owner: sg-semantic
---

# sg-semantic-batch-register · KPI 语义模型分批注册与成熟度分级

## 定位

**注册 ≠ 校准。**

「未注册指标不可查」是准确率地基，但这条铁律有个致命漏洞：如果为了达成「已注册」而批量灌入未经人工确认的口径，指标就带着「合规」身份畅通无阻地进入执行 —— **形式上满足铁律，实质上架空铁律，比不注册更危险（虚假安全感）**。

同时必须正视两个事实：
- `T_ADS_DIM_GZ01` 本地 CSV 镜像实测 **5970 行**，且这是**配置表行数**，不等于**在用指标数**（大量是历史 / 停用 / 测试口径）
- 全量 6077 条灌入语义层，与「领域路由优先、渐进式上下文披露」直接冲突，会造成长上下文腐化

本技能用**三层池 + 成熟度分级**解决这个两难：用 L0 的 5% 投入覆盖 80% 问数流量，长尾降级处理。

## 三层池设计

| 层级 | 规模 | 来源 | `maturity` | 查询策略 |
|---|---|---|---|---|
| **L0 核心池** | ~300 条 | 高频问法反推 + 55 个生产存储过程输出指标 | `certified` | 直接查，全置信度 |
| **L1 扩展池** | ~1000–1500 条 | 按域批量自动注册（DB 注释 + 代码枚举 + 过程输出字段） | `draft` | **可查，但强制标注**：置信度 + 口径来源 + 「未人工校准」提示 |
| **L2 长尾池** | 其余 | 仅建索引 | `indexed` | 走「未注册」流程，提示补充口径或转人工登记 |

> 帕累托依据：L0 约 300 条（占总配置 ~5%）覆盖约 **80% 实际问数流量**。

## 语义记录 Schema

```json
{
  "zb_code": "2000514",
  "zb_name": "质量_圆棒当日合格量",
  "maturity": "certified|draft|indexed",
  "caliber_source": "T_ADS_DIM_GZ01.SQL1 + 人工确认@2026-09-01",
  "confidence": 0.95,
  "owner_domain": "production-rolling",
  "measure_or_metric": "measure",
  "unit": "吨",
  "aliases": ["圆棒合格量", "圆棒当日合格"],
  "factory_scope": ["三钢闽光", "泉州闽光", "罗源闽光"],
  "version": "v1",
  "guards": {"ratio_not_additive": false, "semi_additive": false, "dedup_required": true},
  "open_issues": []
}
```

## 铁律升级（本技能的核心规则）

| `maturity` | 执行 | 交付要求 |
|---|---|---|
| 未注册 / `indexed` | **禁止进入执行** | 输出「未匹配原因 + 建议补充信息 + 近似候选（标注差异）」 |
| `draft` | 允许执行 | **必须标注**：置信度 + 口径来源 + 「⚠ 该口径未经人工校准」 |
| `certified` | 允许执行 | 正常交付 |

> 交付时若漏标 `draft` 提示，视为**违反铁律**，结果作废重走。

## 工作流（五步）

### Step 1 · 候选来源盘点

按优先级收集候选 KPI：

| 来源 | 权重 | 抽取方式 |
|---|---|---|
| ① 55 个 GZPROD 生产存储过程的输出指标 | 最高 | 解析过程写入 `T_ADS*` 的 `ZB_CODE` |
| ② 50 个 CBPROD 成本过程的输出指标 | 高 | 同上 |
| ③ 高频问法日志（`sg-intent` 产出） | 高 | 命中频次 Top N |
| ④ `T_ADS_DIM_GZ01` 中近期有变更记录的行 | 中 | `UPDATE_TIME` 近 90 天 |
| ⑤ 其余配置行 | 低 | 直接入 L2 |

### Step 2 · L0 核心池组建（~300 条）

1. 合并来源 ①②③，去重
2. 按命中频次降序，取前 ~300 条
3. **逐条人工 / 半人工校准**：
   - 语义来源五法取口径（DB 注释 → 独立语义配置 → 代码枚举 → `T_ADS_DIM_GZ01` → 大模型辅助生成并**人工确认**）
   - 判定 `measure_or_metric`（Metric 必须定义分子分母，`sg-semantic-layer`）
   - 打四类计算错误防御标记（`sg-calc-error-guard`）
   - 成本域指标必须解析出**三要素**（`CAL_DATE` 版本 + `DATE_TYPE` + `Y_EDITION`）
4. 校准完成 → `maturity: certified`，`confidence` ≥ 0.9

### Step 3 · L1 扩展池批量注册（~1000–1500 条）

1. 按域切批（每批 ≤ 200 条，防上下文腐化）
2. 每批自动抽取：DB 注释 + 代码枚举 + 过程输出字段
3. 自动生成 `aliases`（从 `zb_name` 拆词 + 常见简称）
4. 打标：`maturity: draft`，`confidence` 按来源可靠性给 0.6–0.85
5. **自动生成不算校准** —— 标记 `open_issues: ["未经人工校准"]`

### Step 4 · L2 长尾索引

仅记录 `{zb_code, zb_name, owner_domain, exists: true}`，`maturity: indexed`，**不生成口径**。

### Step 5 · 落盘与版本化

- 写入 `$ONTOLOGY_HOME/design/semantic/kpi-{core|extended|index}.json`
- **合入前先备份**到 `.versions/`
- 变更后触发 `sg-eval-harness` 回归评测（准确率下降 > 2pp 自动回退）
- 同步 `zb_code` 变更清单给本体专家（更新 `domain-*.json` 的 `metrics[]`）

## 分批执行策略

| 批次 | 域 | 规模 | 产出池 |
|---|---|---|---|
| B1 | production-rolling | ~80 | L0 |
| B2 | production-ironmaking + steelmaking | ~90 | L0 |
| B3 | daily-cost | ~80 | L0 |
| B4 | purchase + energy + material | ~50 | L0 |
| B5–B10 | 按域切批，每批 ≤200 | ~1200 | L1 |
| B11 | 其余 | 剩余 | L2 |

> 每批完成后跑一次 `sg-eval-harness`，确认该域准确率不降。

## 输出规范

- 分批注册报告：批次 / 域 / 条数 / `maturity` 分布 / `confidence` 均值
- 三个语义池 JSON 文件（符合 Schema）
- **未校准清单**：所有 `draft` 条目 + 建议人工确认优先级排序
- 回归评测结论（准确率变化 + 是否触发回退）

## 注意事项

1. **禁止为凑数把 `draft` 标成 `certified`** —— 成熟度是本技能的生命线，虚标等于自毁地基。
2. **禁止全量装载**：每次语义检索按域过滤后再展开字段（渐进式上下文披露），防止长上下文腐化。
3. **`zb_code` 是唯一主键**，禁止用中文字段名做跨层关联（名称会随口径变更而变）。
4. 成本域指标未解析出三要素的，**一律不给 `certified`**。
5. 与本体专家的 `domain-*.json` 用 `zb_code` 对齐；不一致时以 DB2 实数据核验结果为准（冲突仲裁规则 #1）。
6. 路径走环境变量 `$ONTOLOGY_HOME` / `$DB2_ASSETS_HOME`，禁止硬编码绝对路径。
