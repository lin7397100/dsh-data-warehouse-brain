# 专家团 API 对齐规范（旧 harness → DSH 现行 API）

> **版本**：v2.0（2026-11-20 · 衍薪 全包对齐修复 P0）
> **适用范围**：`agents/` · `docs/` · `skills/` 下全部现行规范文件。
> **不适用**：`knowledge/design/supervision/**`、`knowledge/kb/**`、`observed/**`、`scripts/**`、`tools/**`（历史留痕与代码层，见文末豁免声明）。

## 0. 根因（为什么要立这份规范）

专家团包写于**旧版 harness**，通篇使用 `TaskCreate` / `Agent()` / `TeamCreate` / `TaskOutput` / `SendMessage` 等**当前 DSH 会话中根本不存在的工具**。2026-11-20 全包实测：`todo_write` 命中 **0 次**，而 `TaskCreate` 59 次、`Agent(` 48 次、`TeamCreate` 44 次、`SendMessage` 19 次、`TaskOutput` 12 次、`run_in_background` 36 次、`subagent_type` 33 次。

后果有两层：

1. **派发链路整体失效**：主理人照抄旧 API 派发必然报"工具不存在"，退化成本人内联代做 → 调度违规、覆盖率 0%。
2. **双轨留痕断裂**：台账 `trace_log.py` 照记，但内置任务清单（todo）从不推进 → 面板冻结在开工快照，用户看到的是"永远第一步未完成"。

本规范是**唯一权威映射来源**。凡与任何技能/参考文件中残留的旧写法冲突，**以本文件为准**。

## 1. 权威映射表（旧 API → DSH 现行 API）

| 旧 API（失效） | 原语义 | DSH 现行 API | 关键差异 |
|---|---|---|---|
| `TaskCreate({...})` | **仅建追踪卡片，非派发** | `todo_write([{content,status}])` | DSH 的 todo 清单就是追踪卡片；一次可批量写多项 |
| `Agent({subagent_type,name,prompt,run_in_background})` | 派发子专家 | `delegate_expert({agent_preset,name,prompt})` | 字段更名 `subagent_type`→`agent_preset`；**立即返回 name，天然异步** |
| `run_in_background:false` | 阻塞等待回执 | 派发后显式 `wait_agent({timeout_ms})` | DSH 无此参数，等待是独立调用 |
| `run_in_background:true` | 后台扇入 | 直接 `delegate_expert`（默认即异步） | 删除该参数 |
| `TaskOutput({block:true})` | 阻塞取结果 | `wait_agent({timeout_ms})` | 返回值含 `timedOut` |
| `TaskOutput({block:false})` | 轮询 | **禁止轮询**；用完成通知或 `list_agents` | 轮询会空耗上下文 |
| `SendMessage({to,content,summary})` | 增量派发/追问 | `send_message({agent,message})` | 字段更名 |
| `TeamCreate(...)` | 多专家组队 | 同一消息内多条 `delegate_expert` 并行 | DSH 无 Team 实体 |
| `interrupt` | 中断子代理 | `interrupt_agent({agent})` | — |

## 2. 使用示例（照此写，不要自创）

### 2.1 单专家派发 + 等待回执（原 `run_in_background:false`）

```
① delegate_expert({
     agent_preset: "sg-semantic",
     name: "caliber-check-<trace>",
     prompt: "输入：<自包含前提>；输出：<可核验交付物>；边界：<不得越权>"
   })
   → 立即返回 name（此时专家在跑，尚未有结论）
② wait_agent({timeout_ms: 300000})   ← 等待是独立调用，不是参数
   → 返回值含 timedOut；timedOut=false 才可采信结论
③ python <包根>/scripts/trace_log.py finish --step <N> --owner sg-semantic --artifact "<摘要>"
   + todo_write([{content:"Step <N> 口径核查", status:"completed"}])   ← 铁律 A
```

### 2.2 并行扇出（原 `run_in_background:true` × N）

```
同一条消息内：
  delegate_expert({agent_preset:"sg-quality",       name:"phase0-indicator-classify", prompt:"..."})
  delegate_expert({agent_preset:"sg-metadata",      name:"physical-lineage-<trace>",  prompt:"..."})
  delegate_expert({agent_preset:"sg-metric-builder",name:"metric-lineage-<trace>",    prompt:"..."})
  delegate_expert({agent_preset:"sg-ontology",      name:"domain-detect-<trace>",     prompt:"..."})
  delegate_expert({agent_preset:"sg-semantic",      name:"caliber-card-<trace>",      prompt:"..."})
→ 再对每路 wait_agent 或统一等待完成通知；禁止每 10s 轮询
```

### 2.3 增量追问（原 `SendMessage`）

```
send_message({agent:"executor-<trace>", message:"再取罗源基地 SGP3Z1 的同期值，格式同上"})
```

### 2.4 中断（原 `interrupt`）

```
interrupt_agent({agent:"executor-<trace>"})
```

### 2.5 双轨留痕（台账 + todo 面板）

```
todo_write([
  {content:"GATE-0 健康自检",              status:"completed"},
  {content:"Step 0.5 本体+语义双核验并行",  status:"in_progress"},
  {content:"Step 2 口径卡",                status:"pending"},
  {content:"Step 8 报告交付",              status:"pending"}
])
```

## 3. 两条新增铁律（本次根因 · 最高优先级）

### 铁律 A · 双轨留痕

每步 `trace_log.py finish` 回填台账后，**必须同步 `todo_write` 推进该项状态**：

```
开工建清单（全 pending）
  → 每步派发时置 in_progress
  → 每步 finish 回填台账的同一时刻置 completed
  → 收尾时全部 completed
```

**只写台账不刷 todo 面板 = 面板冻结为开工快照，属交付缺陷**（等同于"派发未留痕"，监衡按未完成计）。两套记录必须逐项对齐，禁止只写其一。

### 铁律 B · 语义不可混

`todo_write` **只做追踪**，**永远不能替代 `delegate_expert`**。

原规范「`TaskCreate` ≠ 派发」的约束在 DSH 下等价表述为「**`todo_write` ≠ 派发**」：写一条 todo 不等于派出了一位拥有独立上下文的专家。派发独立上下文的唯一合法动作是 `delegate_expert`。

> 该区分必须保留，用于防止主理人**用刷 todo 冒充派发专家**——这是旧包 RC3 违规在 DSH 下的等价形态，一旦混同，监衡的派发覆盖率将永久失真。

## 4. 禁止项

1. ❌ 禁止在任何规范文件里再写 `TaskCreate` / `Agent(` / `TeamCreate` / `TaskOutput` / `SendMessage` / `run_in_background` / `subagent_type`（历史档案除外，见 §5）。
2. ❌ 禁止用 `TaskOutput(block=false)` 或"每 10s 查一次"式轮询等待子代理——用完成通知或 `list_agents` 查状态，`wait_agent` 取结果。
3. ❌ 禁止给 `delegate_expert` 传 `run_in_background`（不存在该参数，异步是默认行为）。
4. ❌ 禁止在 DSH 中寻找/模拟 Team 实体；组队 = 同一消息内多条 `delegate_expert` 并行 + 统一扇入。
5. ❌ 禁止用刷 todo 冒充派发（铁律 B）。
6. ❌ 禁止只写台账不刷 todo（铁律 A）。
7. ❌ 禁止机械替换掉语义：涉及"历史事故复盘""旧版行为描述"的句子，若替换后语义失真，保留原文并在修复报告中列出（`residual_notes[]`）。

## 5. 历史档案豁免声明

> **`knowledge/design/supervision/flow_TR-*.md` 内仍含旧 API 字样，属历史监察档案，只读保留，不作为现行规范依据。**

同批豁免：`knowledge/design/supervision/health.json`、`knowledge/kb/**`、`observed/**`（含历史 trace/报告/评测快照）、`panel/roster.json`（自动生成的配置快照）、`scripts/**`、`tools/**`。

理由：这些文件是**监察证据**与**代码层资产**。改动历史留痕等于篡改证据链，会使违规追溯与回归对比失去基准；代码层 API 调用需单独评估，不在本次文档措辞对齐范围内。

## 6. 变更记录

| 版本 | 日期 | 变更 | 依据 |
|---|---|---|---|
| v1.0 | 2026-11-20 | 首版：9 条映射 + 2 条新增铁律 + 禁止项 + 豁免声明 | 全包旧 API 实测（todo_write 0 次 vs TaskCreate 59 次） |
| v2.0 | 2026-11-20 | 补使用示例（同步/并行/追问/中断/双轨留痕）、补禁止项 4~7、补豁免范围与理由 | 17 个规范文件逐文件替换 + 四项验证 |
