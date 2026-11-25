---
name: sg-db2-rest
description: "三钢数仓智脑：DB2 REST 只读桥接（db2 mcp 降级通道）。当 DB2 MCP 不可用时（如专家团被分享给未配置 db2 mcp 的环境），通过 5sApi 接口执行只读 SQL，与 db2 mcp 执行语义对齐。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, rest, fallback, sql, readonly]
owner: sg-development
---

# sg-db2-rest · DB2 REST 只读桥接（降级通道）

## 何时启用

满足以下任一条件时，用本技能**替代** `mcp__db2__execute_sql`：

- 当前环境**未配置 DB2 MCP**（典型场景：专家团被分享给其他人，对方无 db2 mcp server）；
- DB2 MCP 调用失败且无其他可用通道。

> **判定方式**：执行阶段若发现没有 `mcp__db2__execute_sql` 工具可用，即走本通道。
> 只要 DB2 MCP 可用，**优先用 MCP**（更稳、有治理护栏直连）；本通道是等价降级，不是默认路径。

## 执行方式

统一走脚本 `scripts/sgdw_sql_exec.py`（Python 标准库实现，无需额外依赖）：

```bash
"$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" \
  scripts/sgdw_sql_exec.py --sql "<只读SQL>"
```

- 大结果集**自动分页**（接口单页上限 20000），无需手工分页；可用 `--max-rows N` 加总闸。
- 输出 JSON 到 stdout：`{"ok":true,"count":N,"rows":[{列名:值,...}]}`。
- 需落盘 CSV：`--csv <path>`（UTF-8 BOM，Excel 可直接打开）。

## 凭据（共享模型）

接口用 `lightcodegtw-token` Cookie 鉴权。**专家包已清除真实凭据（G5-SEC 合规），用户需自行提供 token**。联系团队管理员获取。

读取顺序（高优先级优先，先到先得）：
1. 环境变量 `SGDW_LIGHTCODE_TOKEN` / `SGDW_USER_ID` / `SGDW_CLIENT_ID`（最高）
2. 个人本地文件 `~/.dsh/.sgdw_rest.env`（本机专用）
3. 团队内置 `scripts/sgdw_rest.env`（默认，token 已内置）

## 只读防护

脚本内置基础护栏（与 `sg-sql-safety-check` 互补，但不替代）：

- 仅允许 `SELECT` / `WITH` 起手的语句；`INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE/GRANT/REVOKE/CALL` 一律拒绝；
- 先剥离字符串字面量与注释再做关键字匹配，降低误判。

仍建议在落库前走治理专家 `sg-sql-safety-check` 四层护栏。

## 错误处理

| 返回 | 含义 | 处置 |
|---|---|---|
| `{"ok":true,...}` | 成功 | 按请求形态组装（同 `sg-nl2sql-query` Step 4） |
| `READONLY_GUARD` | SQL 非只读被拦截 | 改写为 SELECT/WITH |
| `未配置凭据` | 找不到 token | 配置 `.sgdw_rest.env` 或环境变量 |
| `API_ERROR: <msg>` | 接口返回非成功状态 | 提取 msg，如实告知，**禁止编造** |
| `NET_ERROR` / `HTTP xxx` | 网络 / 网关错误 | 检查连通性与 token 有效性（是否过期） |

## 与其它技能的衔接

- 取代 `mcp__db2__execute_sql` 的**执行动作**；编译（DSL / 物化 SQL）、安全审查、结果组装**保持不变**。
- `sg-nl2sql-query` / `sg-materialized-sql` / `sg-dsl-compiler` 在执行步骤注明本降级通道。
- 与 `sg-data-analysis-engine` 的「数据源连接」铁律一致：凭据不写入技能文件。
