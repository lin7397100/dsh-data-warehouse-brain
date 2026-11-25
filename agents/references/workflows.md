# 专家团预设 Workflow 全集（A~G）

> 由 team-lead 外置（2026-10-29 重构）
> **加载时机**：任务明显落入某个 Workflow 模式（深度研究 / 多源分析 / CSV 画像 / 知识增强 / 纯问答）时 Read。
> **主链路（智能问数）不在此文件**，仍在主文件 Step 0~8。

---

## 通用分析子团预设 Workflow

> 以下 4 套 Workflow 由通用分析能力（主理人）的编排经验提炼，现并入本团主理人冶衡的统一调度；调用时按**在册**成员 ID spawn 子 agent（原秦逸/赛奇/瑞卡三段分别改派淬锋 `sg-development`/砺真 `sg-quality`/铨度 `sg-semantic`），成员产出经 `send_message` 回传主理人汇总。DB2 数仓口径性问数不在此列（走八步主链路）。

**Workflow D · 全链路数据分析（数据库 → 报告）**
触发：用户提供多源数据库连接/文件，要求从数据中获取洞察并生成报告。
```
Phase 1（串行）：sg-development（淬锋，承接原秦逸的多源 SQL 分析） → 连接数据源、探索 Schema、执行查询
 ↓ [查询结果 + 数据概要]
Phase 2（串行）：sg-quality（砺真，承接原赛奇的统计分析） → 基于查询结果做深度统计分析
 ↓ [分析结论 + 关键发现]
Phase 3（并行）：
 sg-zhishu-dashboard-designer → 基于分析结果设计可视化
 sg-zhishu-report-composer → 基于分析结论撰写报告（等可视化完成后嵌入）
 ↓ [可视化图表 + 分析报告]
主理人汇编 → 综合交付
```

**Workflow E · CSV/Excel 数据画像**
触发：用户上传 CSV/Excel 文件，要求生成数据画像或分析报告。
```
Phase 1（串行）：sg-quality（砺真，承接原赛奇的数据科学分析） → 加载文件、数据清洗、EDA 分析
 ↓ [数据概要 + 统计结论 + 关键发现]
Phase 2（并行）：
 sg-zhishu-dashboard-designer → 生成数据画像仪表盘
 sg-zhishu-report-composer → 撰写数据画像报告
 ↓ [可视化 + 报告]
主理人汇编 → 综合交付
```

**Workflow F · 知识库增强分析**
触发：用户上传文档 + 提出需要结合数据和文档的综合分析。
```
Phase 1（并行）：
 sg-development（淬锋） 或 sg-quality（砺真） → 结构化数据分析
 sg-semantic（铨度，承接原瑞卡的知识检索） → 文档检索与知识提取
 ↓ [数据结论 + 知识上下文]
Phase 2（串行）：sg-zhishu-report-composer → 综合数据分析和知识检索结果撰写报告
 ↓ [综合分析报告]
主理人汇编 → 综合交付
```

**Workflow G · 纯知识问答**
触发：用户上传文档，仅需基于文档回答问题或生成摘要。
```
Phase 1（串行）：sg-semantic（铨度，承接原瑞卡的知识检索） → 文档解析、语义检索、生成带引用的回答
 ↓ [检索回答 + 来源引用]
Phase 2（串行，可选）：sg-zhishu-report-composer → 如需正式报告格式，撰写结构化输出
 ↓ [格式化报告]
主理人汇编 → 交付
```
