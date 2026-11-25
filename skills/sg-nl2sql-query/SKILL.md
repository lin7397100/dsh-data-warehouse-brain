---
name: sg-nl2sql-query
description: "[指针桩] 自然语言→SQL 问数统一入口。权威技能：sg-dsl-compiler（确定性编译）/ sg-intent-parse-dispatch（意图解析）。本文件不含可执行规则。"
version: 2.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, unified]
owner: sg-development
---

# sg-nl2sql-query · 指针桩

> ⚠ 本文件为兼容别名，**不含可执行规则**。所有规则以权威技能为准。

**权威技能**：
- DSL 确定性编译 → `sg-dsl-compiler`（E11 铁律：禁止任何环节绕过编译器直接产出可执行 SQL）
- 意图解析与 StructuredInstruction 生成 → `sg-intent-parse-dispatch`
- 只读执行 → `sg-db2-executor`

**主责成员**：淬锋 `sg-development`

**已从本文件删除的过时条款**：
- ❌ "SQL 编译：本技能出 SQL" → E11 铁律要求所有 SQL 必须经 `sg-dsl-compiler` 编译并过三查，本技能不直接产出 SQL
- ❌ 重复 4 次的同名合并 description

> 说明：原技能已并入 `sg-dsl-compiler` 等权威技能，本目录保留为兼容别名。