# MCP 一键开关（面板「MCP 连接」页签）

> v1.1.0 起，五台内网 MCP 不再写在 preset 里，改由面板托管：
> **点开关即时连/断，不重启、不改环境变量、不跑命令。**

## 为什么改

原先每台 MCP 是 preset 内的一行 `mcp-client`：

```yaml
- id: mcp-weknora
  disabled: !!js "process.env.SG_MCP === 'off' || !process.env.DWB_INTERNAL_MCP"
```

两个硬限制：

1. `disabled` 在**预设首次激活时求值一次**，之后由选中的 Agent 共享 —— 改环境变量必须重启进程；
2. 插件页对 **Agent 预设条目只读**，`dsh-mcp-manager` 也明确「只治理全局面」，preset 内的实例既不被列出也不受治理。

v1.1.0 改用运行时注册（`ctx.mcpManager.register(name, entry)`），开关就是注册/注销：

- 开启 → 注册，工具立刻进入模型工具列表；
- 关闭 → `dispose()`，工具立刻注销、**不占上下文**；
- 状态持久化到 `<团队根>/mcp-state.json`，重启后自动恢复。

## 怎么用

侧边栏 **数仓专家团 → MCP 连接**：

| 列 | 含义 |
|---|---|
| 状态灯 | 绿=已连接（显示工具数）、黄=连接中/重连、红=失败、灰=未启用 |
| 开关 | 「启用」/「停用」，点了立即生效 |
| 测试连接 | 只探活不注册工具（`probe`），显示耗时与工具数，用于排错 |
| 需配令牌 | `知识库 WeKnora` 需要 `.env` 里的 `SG_WEKNORA_TOKEN` |

五台服务器与默认端点（均可用环境变量覆盖）：

| 名称 | 端点 | 覆盖变量 | 默认 |
|---|---|---|---|
| `weknora` | `http://10.233.2.32:9080/mcp` | `SG_WEKNORA_MCP_URL` | **关** |
| `db2` | `http://10.18.136.38:8765/mcp` | `SG_DB2_MCP_URL` | **关** |
| `eplat` | `http://10.18.136.38:8770/mcp` | `SG_EPLAT_MCP_URL` | **关** |
| `wecom-group` | `http://10.18.136.38:8766/mcp` | `SG_WECOM_GROUP_MCP_URL` | **关** |
| `wecom-user` | `http://10.18.136.38:8767/mcp` | `SG_WECOM_USER_MCP_URL` | **关** |

> 全部默认关闭是刻意的：公网用户不会被必失败连接拖慢。内网用户按需点开。
> `SG_MCP=off` 仍然有效，会一次性关停所有 MCP（含面板托管的）。

## 边界与护栏

- **主理人（冶衡）看不到 `mcp__*` 工具**：启动时若检测到该 agent 持有 `delegate_expert`（只有主理人挂），就在它的 scope 里 `tools.restrict({ deny: [...mcp__*] })`。
  - 局限：这是**会话创建那一刻的快照**。若某台 MCP 在会话创建之后才连上，新工具不会自动被屏蔽 —— 新建会话即可。
- 其他专家之间的可见性仍由 persona 约束（`sg-semantic` 不该调 db2、`sg-5s-qa` 不该投企微等）。需要硬隔离时可在 `mcp.js` 里按工具名前缀加同样的 `restrict`。
- 面板自身不存令牌：只显示「需在 .env 配置」，值仍来自 `$DSH_HOME/.env`（见 `docs/AUTH-SETUP.md`）。

## 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| 面板显示「不可用」 | 当前 profile 没挂 `dsh-mcp-manager`（非 web/desktop profile） | 用 `dsh web` 或 Desktop；或把 `mcp` 行加进 profile |
| 点开关报 `当前 profile 未挂载 MCP 管理器` | 同上 | 同上 |
| 点开关报 `name is taken` | profile patch 里还有同名 `mcp-client` 行 | 升级到 v1.1.0（已自动删除 preset 内 MCP 行）；或检查自己的 patch |
| 测试连接失败（connect 阶段） | 端点不可达 / 不在内网 | 先 `curl -m 5 <端点>` 探活 |
| 已连接但模型看不到工具 | 工具被 `restrict` 或该会话创建于连接之前 | 新建会话；或查主理人护栏日志 |
| 令牌缺失 | `SG_WEKNORA_TOKEN` 未配 | `python scripts/write_env.py --set SG_WEKNORA_TOKEN=xxx` |

## 相关文件

| 文件 | 作用 |
|---|---|
| `mcp.js` | 服务器清单、状态持久化、注册/注销、路由 `/dwb-team/api/mcp*` |
| `index.js` | 挂载控制器、主理人护栏、恢复持久化状态 |
| `client.js` | 「MCP 连接」页签与开关/测试按钮 |
| `scripts/build_package.py` | 生成 patch 时自动剔除 preset 内的 `mcp-*` 行 |
