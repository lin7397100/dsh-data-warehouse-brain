---
name: sg-metadata-core
description: "[指针桩] 元数据统一入口。权威技能：DDL 检索（K1 表结构库 + DB2 SYSCAT）/ sg-data-lineage（血缘）/ sg-metadata 域知识检索。本文件不含可执行规则。"
version: 2.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, unified]
owner: sg-metadata
---

# sg-metadata-core · 指针桩

> ⚠ 本文件为兼容别名，**不含可执行规则**。所有规则以权威技能为准。

**权威入口**：
- 表结构 / 字段类型 → WeKnora K1（`DDL-表结构-<SCHEMA>`）+ DB2 `SYSCAT.COLUMNS` 实时对拍
- 物理血缘 / 变更监测 → `sg-data-lineage`
- 域知识检索 → `agents/references/routing.md`（管枢 / 成枢域文档）
- 资产漂移 → `sg-metadata-core`（Oracle 改名后上下文）

**主责成员**：舆图 `sg-metadata`

**已从本文件删除的过时条款**：
- ❌ 重复 4 次的同名合并 description

> 说明：原技能已合并，本目录保留为兼容别名。