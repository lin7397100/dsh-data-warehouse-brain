---
name: sg-analysis-engine
description: "[指针桩] 分析引擎统一入口，按 mode 分派（db2/general/science）。权威技能：sg-zhishu-analysis-engine（通用）/ sg-data-analysis-engine（DB2专属）。本文件不含可执行规则。"
version: 2.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, unified, analysis]
owner: sg-metadata
---

# sg-analysis-engine · 指针桩

> ⚠ 本文件为兼容别名，**不含可执行规则**。所有规则以权威技能为准。

**权威模式分派**：
- `mode=db2` → `sg-data-analysis-engine`（DB2 数仓专属分析优化）
- `mode=general` → `sg-zhishu-analysis-engine`（多源数据库/CSV/Excel/文档通用分析）
- `mode=science` → 砺真 `sg-quality`（Python 统计/ML）

**主责**：由分派后的权威技能的主责成员承担

> 说明：原三技能已保留各自目录（含 references/），本文件仅为路由入口。