---
name: sg-intent
description: "[指针桩] 意图解析与派单统一入口。权威技能：sg-intent-parse-dispatch（六类意图→五域路由→StructuredInstruction JSON）。本文件不含可执行规则。"
version: 2.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, unified]
owner: data-warehouse-brain-team-lead
---

# sg-intent · 指针桩

> ⚠ 本文件为兼容别名，**不含可执行规则**。所有规则以权威技能为准。

**权威技能**：
- 意图解析与派单（六类意图 / 五域路由 / StructuredInstruction JSON）→ `sg-intent-parse-dispatch`
- 域前置分流与判型 → `agents/references/task_classify.md`
- 路由触发词映射 → `agents/references/routing.md`

**主责**：编排器 `data-warehouse-brain-team-lead`（冶衡）

**已从本文件删除的过时条款**：
- ❌ 重复 4 次的同名合并 description
- ❌ owner 由 `sg-metadata` 修正为 `data-warehouse-brain-team-lead`（意图解析是编排器主责）

> 说明：原技能已并入 `sg-intent-parse-dispatch`，本目录保留为兼容别名。Schema 定义见 `sg-intent-parse-dispatch/SKILL.md` §输出规范。