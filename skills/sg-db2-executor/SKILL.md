---
name: sg-db2-executor
description: "三钢数仓智脑：DB2 执行统一权威（MCP 优先 + REST 降级双通道）。优先走 DB2 MCP 直连（需三钢内网/VPN）；无 MCP 时降级 5sApi REST 桥接，凭据须由用户自备（企微智能表格 / 环境变量 / 本地 env），专家包不随包分发 token，脚本 scripts/sgdw_rest.env 仅为注释模板。"
version: 2.2.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, executor, mcp, rest, sql, readonly, unified]
owner: sg-development
---

# sg-db2-executor · DB2 执行统一权威（MCP 优先 + REST 用户自备凭据）

## 定位

**所有 DB2 只读 SQL 执行的唯一收口点**。无论是快车道物化直查、实时编译、即席构建，
还是主链路八步，最终"把 SQL 真正跑出结果"这一步**一律经过本技能**。

> `sg-materialized-sql` / `sg-dsl-compiler` / `sg-nl2sql-query` / `sg-adhoc-indicator` 在执行步骤统一写「交 `sg-db2-executor` 执行」。

## 通道判定（每一条 SQL 执行前必做）

```
IF  当前环境存在 mcp__db2__execute_sql 工具
THEN  Channel A —— DB2 MCP 直连（默认主通道，速度快，需三钢内网/VPN）
ELSE IF  凭据可从企微智能表格获取（见下方凭据读取策略）
THEN  Channel B —— 5sApi REST 桥接（公网可达，凭据自动从智能表格读取）
ELSE  如实告知「无 MCP 且凭据不可用，无法执行 SQL」
```

> **核心原则**：MCP 是默认主通道；REST 是自动降级通道，凭据从企微智能表格 `数仓智脑凭据管理` 中自动读取，不依赖本地文件。专家包已清除本地硬编码凭据以满足 G5-SEC 合规。

## 网络可达性

| 端点 | 地址 | 可达性 | 适用人群 |
|---|---|---|---|
| DB2 MCP | `10.18.136.38:8765` | ⚠️ 仅三钢内网/VPN | 内部用户（默认） |
| 5sApi REST | `eqms.fjsg.com.cn:9443` | ✅ 公网可达 | 已自备 token 的用户 |

## 只读护栏（两通道通用，先于执行）

- 仅允许 `SELECT` / `WITH` 起手；`INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE/GRANT/REVOKE/CALL` 一律拒绝。
- 本技能只产出**执行结果**，不改写 SQL 语义（编译/血缘/口径由上游负责）。

---

## Channel A · DB2 MCP 直连（**默认主通道 · 速度最快**）

优先通道。当环境存在 `mcp__db2__execute_sql` 工具时直接使用：

```
mcp__db2__execute_sql(sql="<只读SQL>")
```

> 前提：三钢内网或 VPN 连接到 `10.18.136.38`，且已在 DSH 的 MCP 配置中挂载并信任 DB2 MCP。
> 失败时自动降级走 Channel B（REST，但**凭据须用户自备**；未注入时按输出契约如实返回
> `无可用通道`，不得编造结果）。

---

## Channel B · 5sApi REST 桥接（**自动降级 · 凭据从智能表格读取**）

### 凭据（从企微智能表格自动获取 · G5-SEC 合规 · 2026-10-27）

接口用 `lightcodegtw-token` Cookie 鉴权。专家包本地文件已清除凭据，改为从企微智能表格自动读取。

**凭据读取策略（三步兜底）**：
1. **优先**：从企微智能表格读取 → `mcp__wecom-group__smartsheet_get_records`（docid: `s3_AMAA4RTkAAAPdEHhUJAQe6kgdnyOq_a`，sheet_id: `q979lj`）
2. **兜底**：环境变量 `SGDW_LIGHTCODE_TOKEN` / `SGDW_USER_ID` / `SGDW_CLIENT_ID`
3. **最后**：`~/.dsh/.sgdw_rest.env` 本地文件

### 执行方式一 · curl 直连（**推荐 · 零 Python 依赖**）

```bash
# 1) 读凭据（用户自备；专家包内 scripts/sgdw_rest.env 仅为注释模板，无有效键值）
TOKEN="<用户自备的lightcodegtw-token>"
UID="<用户ID>"
CID="sgdw-sc01"

# 直连 5sApi 执行只读 SQL
curl -s -X POST "https://eqms.fjsg.com.cn:9443/com.baosight.sg.bdds/service/proxy/5sApi/D_A_SMBBMASC01_SQLEXECUTE" \
  -H "Content-Type: application/json" \
  -H "Cookie: lightcodegtw-token=$TOKEN" \
  -d "{\"sql\":\"<只读SQL>\",\"clientId\":\"$CID\",\"modelId\":\"\",\"showCount\":\"true\",\"offset\":\"0\",\"userId\":\"$UID\",\"limit\":\"20000\"}"
```

响应解析：`status==1` 为成功；数据行在 `datas` 数组；归一化为 `{ok:true, count:N, rows: datas}`。

### 执行方式二 · Python 脚本（备选 · 需用户先配置凭据）

用户先按上述方式配置 `~/.dsh/.sgdw_rest.env`，然后：

```bash
python3 scripts/sgdw_sql_exec.py --sql "<只读SQL>"
```

> 脚本按 `__file__` 定位同目录 `sgdw_rest.env`；该文件在专家包中**仅为注释模板**，
> 需用户自行填写或改用环境变量 `SGDW_LIGHTCODE_TOKEN` / `SGDW_USER_ID` / `SGDW_CLIENT_ID`。
> 未配置时脚本返回「未配置凭据」并终止，REST 通道记为 SKIP，属预期行为。

---

## 输出契约（两通道统一）

```json
{"ok": true, "count": N, "rows": [{"列名": "值", ...}], "channel": "mcp | rest"}
```

- `channel` 字段标注实际走的通道，便于溯源与排障。
- `ok:false` 时带 `error`，如实上抛，**禁止编造**。

## 错误处理

| 返回 | 含义 | 处置 |
|---|---|---|
| `{"ok":true,...}` | 成功 | 按请求形态组装 |
| `READONLY_GUARD` | SQL 非只读被拦截 | 改写为 SELECT/WITH |
| `无可用通道` | 无 MCP 且 REST 网关不可达 | 检查公网连通性（eqms.fjsg.com.cn:9443） |
| `API_ERROR:<msg>` | 接口非成功状态 | 提取 msg，如实告知 |
| `NET_ERROR` / `HTTP xxx` | 网络/网关错误 | 检查网络连通性 |

## 与其它技能的衔接

- **上游（编译/取数）**：`sg-materialized-sql`、`sg-dsl-compiler`、`sg-nl2sql-query`、`sg-adhoc-indicator` 统一写「交 `sg-db2-executor` 执行」。
- **下游（渲染）**：结果集照常交 `sg-qa-render`（渲染并落盘 HTML，无独立 `sg-qa-html-report` 技能）。
- **治理**：只读护栏见 `sg-sql-safety-check`。

## 分享说明

> 专家团被分享给他人时，对方不在三钢内网**也可能**通过 REST 通道取数，但**必须自行注入凭据**。
> G5-SEC：专家包已清除本地硬编码 token，`scripts/sgdw_rest.env` 仅保留 6 行注释模板，
> 不含任何有效键值。接收方未注入凭据时应如实告知「无 MCP 且凭据不可用，无法执行 SQL」，
> 不得降级为编造结果。