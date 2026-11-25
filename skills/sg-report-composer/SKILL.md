---
name: sg-report-composer
description: "三钢数仓智脑：报告撰写统一出口。基于已有数据生成单图/轻报告/综合报告/看板四档形态，以 Markdown、HTML、docx 承载并落盘到产物目录。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, insight, report, markdown, html, docx]
owner: sg-insight, sg-zhishu-report-composer
---

# sg-report-composer · 报告撰写统一出口

## 定位

数据交付物的**统一收口**：一次调用完成「规划形态 → 生成产物 → 落盘」，返回路径清单。

> 本技能**只生成 + 落盘**，不上传、不外发。推送由编排器在用户确认后走通知 MCP。

## 形态决策（四档）

| shape | 长什么样 | 场景信号 |
|---|---|---|
| `chart` | 一张图 + 一句话结论 | 1 条发现 + 1 个图表，无 KPI / 无建议素材 |
| `lite` | ≤3 KPI + 1~2 章节 + 图 + 精简结论 | 1~2 条发现，聚焦单一主题（**兜底档**） |
| `full` | Hero KPI 网格 + 多章节 + SQL 折叠 + 综合洞察 + 建议(≥3) | ≥3 条发现，或有明确行动建议素材 |
| `dashboard` | 多卡片网格，一屏概览，每卡一指标 + 迷你图 | 多个并列指标 + 强调一屏总览 |

> 判定顺序：`chart` → `dashboard` → `full` → 其余落 `lite`。
> ⚠️ **不要把 `chart`/`lite` 硬撑成 `full`** —— 没有建议素材却强行编三条是凑数，稀释可信度。宁可诚实出 `lite`。

## 载体决策

| 载体 | 不可替代价值 | 何时出 |
|---|---|---|
| **Markdown** | 可当文章顺序读、数据-SQL 可溯源、能打印 PDF | 有值得当文字读的叙事 |
| **HTML** | 可交互可视化、点击下钻、一屏仪表盘 | 有值得点着看的可视化 |
| **docx** | 正式交付、可编辑流转 | **用户明确要求时才导出** |

原则：既有叙事又有可视化 → 两者都出；天然单模态 → 只出一个（孤图/看板只出 html）；拿不准 → 倾向 `lite` 出两者但 md 写精简。

## 工作流（五步）

### Step 1 · 规划形态与骨架

按场景信号判定 shape + formats，规划骨架（章节与图表位）。

### Step 2 · 提炼产物

从对话中已有的数据 / 结论 / 图表素材中提炼：几条发现？每条有没有配套图表与建议素材？

### Step 3 · 生成内容

**结论先行**结构：

```
# 标题
> 一句话核心结论（含关键数字与方向）

## 一、核心发现
  发现 1：……（数据支撑 + 图表）
  发现 2：……
## 二、原因分析
## 三、影响与建议
## 附录：数据口径与 SQL 溯源（折叠）
```

### Step 4 · 图表生成

DataFrame → 图表配置（ECharts option）→ 可嵌入 HTML 片段。

**图表规范**：坐标轴标注单位、时间序列不插值、分类过多时 Top N + 其他、颜色语义（生产升为好 / 成本降为好）。

### Step 5 · 落盘

统一落盘到 `<workspace_folder>/artifacts/analysis/`，返回路径清单。

## HTML 工程约束

| 项 | 要求 |
|---|---|
| 自包含 | 单文件，CDN 依赖显式声明 |
| 主题 | **浅色主题**，深色文字，保证可读 |
| 移动端 | 栅格自适应，图表不重叠 |
| 交互 | 图表可交互，明细可折叠 |
| 自检 | 生成后检查：依赖完整、图表渲染、移动端宽度、无控制台报错 |

## 输出规范（path-mode JSON）

```json
{"shape": "full", "formats": ["md", "html"],
 "md_path": "<workspace>/artifacts/analysis/xxx.md",
 "html_path": "<workspace>/artifacts/analysis/xxx.html",
 "docx_path": null,
 "summary": "一句话摘要", "size_bytes": 128000}
```

## 注意事项

1. **只基于已有数据生成** —— 不现编数据、不现编建议。
2. 建议素材不足就出 `lite`，不硬撑 `full`。
3. docx 仅在用户要求时导出（走 HTML → docx 转换，保持格式一致）。
4. HTML 必须整份自检后再交付（依赖 / 主题 / 移动端 / 图表渲染）。
5. 报告中的口径与血缘必须附（复用 `sg-qa-render` 的口径说明卡内容）。
