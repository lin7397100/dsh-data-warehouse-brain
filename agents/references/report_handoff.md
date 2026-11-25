# ReportHandoff 交接契约 v1.0

> **生效**：2026-10-29 ｜ **适用**：明鉴(sg-insight) / 达仕(sg-zhishu-dashboard-designer) / 若溪(sg-zhishu-report-composer) / 铨度(sg-semantic) / 主理人(冶衡)
> **背景**：三者此前各写各的、无交接字段定义，导致「若溪先写完文案、明鉴后出图」→ 文案与图表对不上，或明鉴自产全部导致若溪空转。

---

## 一、核心原则

1. **只传结构化契约，不传原始数据、不传 HTML 全文**
2. **单向流动**：明鉴/达仕 → 若溪 → 主理人。不允许逆向修改
3. **禁止跨人改文件**：任何人不得 `Edit` 他人产出的 HTML / Markdown
4. **单一收口人**：最终 HTML 由明鉴唯一生成（T4/T5 场景由达仕生成）

---

## 二、契约结构（JSON）

```jsonc
{
  "handoff_version": "1.0",
  "trace_id": "TR-20261029-001",
  "stage": "data_ready | charts_ready | text_ready | assembled",
  "scene": "T1 | T2 | T3 | T4 | T5",

  // ── 口径（由 sg-semantic 产出，全链只读）──
  "caliber": {
    "metrics": [
      {
        "alias": "steel_mat_rate",
        "zb_code": "1600213",
        "zb_name": "本部经营日报(1)_炼钢_钢铁料耗_日平均",
        "unit": "kg/t",
        "factory": "管控中心",
        "maturity": "draft",            // draft | certified | indexed
        "confidence": 0.95,
        "calibration_note": "⚠ 未经人工校准"
      }
    ],
    "lineage": "T_ODS_TMMSM21 → T_DWS_FACT_ZZGZ_LG01 → T_ADS_DIM_GZ01",
    "producer": "P_DWS_FACT_ZZGZ_0003"
  },

  // ── 数据（数值 + 闭合校验，不带原始行）──
  "data": {
    "dates": ["20261021", "...", "20261027"],
    "series": {
      "benbu": [1052.88, "..."],
      "luoyuan": [1049.24, "..."]
    },
    "closure": {
      "sum_parts": 14726120,
      "total": 14726120,
      "diff": 0,
      "note": "Σ构成项 = 落库分子"
    },
    "residual": {
      "value": 704110,
      "pct": 4.78,
      "note": "其他金属料（未逐项拆分·残差）· 禁止定量归因"
    }
  },

  // ── 图表（明鉴/达仕产出，只传路径 + 清单）──
  "charts_html_path": "artifacts/analysis/xxx.html",
  "charts_manifest": [
    {
      "chart_id": "cSteel",
      "title": "钢铁料耗 · 三基地 7 日趋势",
      "type": "line",
      "series_count": 5,
      "data_points": 35,
      "key_findings": [
        "罗源 10-26 起连续两日跳升 +18.21 kg/t",
        "泉州近 7 日极差 0.04，无趋势解释力"
      ],
      "producer": "sg-insight",
      "slot": "#charts"
    },
    {
      "chart_id": "cContrib",
      "title": "贡献度拆解（帕累托）",
      "type": "pareto",
      "series_count": 1,
      "data_points": 7,
      "key_findings": ["铁水贡献 79.85%，废钢 14.57%"],
      "producer": "sg-zhishu-dashboard-designer",
      "slot": "#charts-extra"
    }
  ],

  // ── 文案（若溪产出，只传路径）──
  "text_md_path": "artifacts/analysis/xxx_text.md",
  "text_sections": [
    {"heading": "执行摘要", "target_slot": "#conclusion", "order": 1},
    {"heading": "关键发现", "target_slot": "#conclusion", "order": 2},
    {"heading": "口径红线", "target_slot": "#caliber",   "order": 3}
  ],

  // ── 组装信息 ──
  "assembly_slot": ["#hero", "#kpi", "#charts", "#charts-extra", "#tables", "#caliber", "#conclusion"],
  "assembler": "team-lead",

  // ── 质量与遗留 ──
  "quality_gate": {
    "j1_brace_leak": 0,
    "j1b_no_cdn": true,
    "j2_node_check": "pass",
    "j3_render": {"charts": 4, "empty_series": 0, "page_errors": 0}
  },
  "open_issues": [
    {"id": "OI-1", "level": "warn", "desc": "罗源分母塌陷，管理动作应查产量"}
  ]
}
```

---

## 三、各阶段必填字段

| stage | 必填 | 产出方 | 消费方 |
|---|---|---|---|
| `data_ready` | `caliber` + `data` | 铨度 + 淬锋 | 明鉴 / 达仕 / 若溪 |
| `charts_ready` | `charts_html_path` + `charts_manifest` | 明鉴 / 达仕 | 若溪（按 manifest 写文案） |
| `text_ready` | `text_md_path` + `text_sections` | 若溪 | 主理人（组装） |
| `assembled` | `quality_gate` + 最终 HTML | 明鉴（收口） | 主理人（J1-J3 + present_files） |

---

## 四、字段传递规则（什么传、什么不传）

| 从 → 到 | 传 | **不传** |
|---|---|---|
| 铨度 → 明鉴 | `caliber` 全量（含 maturity/confidence） | 口径卡原文 4KB |
| 铨度 → 若溪 | `caliber.metrics[]` 摘要 + `calibration_note` | 同上 |
| 明鉴 → 若溪 | **`charts_manifest`**（含 `key_findings`）+ `caliber` | **HTML 全文**（1MB） |
| 达仕 → 若溪 | 自己那份 `charts_manifest` 条目 | 增强图表 HTML 全文 |
| 若溪 → 主理人 | `text_md_path` + `text_sections` | Markdown 全文 |
| 主理人 → 三方 | 同一份 `ReportHandoff` | 各自中间产物 |

> **核心约束**：`charts_manifest.key_findings` 是若溪写文案的**唯一事实来源**。若溪不得凭数据自己编结论，只能基于 manifest 中已声明的发现点展开。

---

## 五、插槽组装规范

### 5.1 标准插槽（HTML 骨架）

```html
<div class="container">
  <section id="hero">      <!-- 标题 + 副标题 + 元信息（时间/基地/口径）  → 主理人 -->
  <section id="kpi">       <!-- KPI 卡片组                                    → 明鉴 -->
  <section id="charts">    <!-- 基础图表（趋势/对比/饼图）                    → 明鉴 -->
  <section id="charts-extra"><!-- 增强图表（贡献度/帕累托/雷达/桑基/热力）   → 达仕（T3+） -->
  <section id="tables">    <!-- 明细表 + 四层抽屉下钻                         → 明鉴 -->
  <section id="caliber">   <!-- 口径卡 + 血缘 + 数据限制                      → 铨度 + 若溪解读 -->
  <section id="conclusion"><!-- 执行摘要 / 关键发现 / 结论建议                → 若溪 -->
</div>
```

### 5.2 组装规则

| # | 规则 |
|---|---|
| 1 | 每个插槽**只有一个产出方**，不允许两人填同一插槽 |
| 2 | 产出的 HTML 片段必须是**合法 HTML 子集**（无 `<html>`/`<head>`/`<body>` 包裹） |
| 3 | CSS 统一由达仕输出 `visual_tokens.css`（配色/字号/间距变量），三方共用 |
| 4 | 组装由主理人执行：按 `assembly_slot` 顺序字符串拼接 |
| 5 | 组装后必须跑 `scripts/verify_report.js`（J1/J2/J3） |
| 6 | 若溪的 Markdown 由主理人用简易 md→html 转换后注入 `#conclusion`，**不由若溪直接产 HTML** |

### 5.3 禁止事项（违反即判定违规，监衡记档）

- ❌ 明鉴 `Edit` 达仕产出的 HTML
- ❌ 达仕 `Edit` 明鉴产出的 HTML
- ❌ 若溪产 HTML（她只产 Markdown）
- ❌ 任何人修改 `caliber` 中的数值（铨度独占写权）
- ❌ 若溪在未收到 `charts_manifest` 前动笔
- ❌ 主理人绕过 J1-J3 直接 `present_files`

---

## 六、与主理人派发的对应关系

| 场景 | 阶段序列 | 契约 stage 流转 |
|---|---|---|
| T1 快车道 | 无报告 | 不产生契约 |
| **T2** 单指标趋势 | 明鉴 → 若溪 → 主理人 | `data_ready` → `charts_ready` → `text_ready` → `assembled` |
| **T3** 多指标含归因 | 明鉴 ∥ 达仕 → 若溪 → 主理人 | `data_ready` → `charts_ready`(×2) → `text_ready` → `assembled` |
| **T4** 数据画像 | 达仕(主) → 明鉴(补) → 若溪 | 同上，`assembler` 可为达仕 |
| **T5** 看板 | 达仕(主) → 若溪 | 同上 |

---

## 七、错误处理

| 情形 | 处理 |
|---|---|
| 明鉴未产出 `charts_manifest` | 若溪**拒绝动笔**，向主理人索要 |
| 达仕增强图表与明鉴基础图表数据不一致 | `confidence<0.6` → `escalate`，主理人主持双路复算 |
| 插槽冲突（两人填同一 slot） | 后者丢弃，前者保留，主理人记违规 |
| J1-J3 未过 | 退回**唯一收口方**（明鉴/达仕）重做，禁止他人修补 |
| 契约字段缺失 | 视为未完成，不进入下一阶段 |

---

## 八、版本与变更

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-29 | 首版。基于 2026-10-29 架构诊断，解决「三者无交接定义」「若溪先于明鉴动笔」「跨人改文件」三大问题 |
