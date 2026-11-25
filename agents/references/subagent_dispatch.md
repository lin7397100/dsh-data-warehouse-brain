### ⚡ 子 Agent 派发机制（2026-10-28 · 强制规范 · 不可降级 · 2026-11-03 P2.1 派发方式统一）

> **P2.1 修复 · 派发三态统一（2026-11-20 DSH 对齐）**：`todo_write` ≠ 派发专家。派发必须用 `delegate_expert`（组队 = 同一消息内多条并行）。`todo_write` 只创建追踪卡片。

| 你想要的 | 正确的工具调用 | 错误用法 |
|---|---|---|
| 派发 1 个专家独立执行并返回结果 | `delegate_expert({agent_preset: "sg-xxx", name: "...", prompt: "..."})` → `wait_agent({timeout_ms})` | `todo_write([{content: "sg-xxx", status: "pending"}])` ← 只建卡片 |
| 派发 1 个专家并行执行（不等待） | `delegate_expert({...})`（默认即异步，无附加参数） | `todo_write` |
| 组队协作（多专家） | 同一消息内多条 `delegate_expert` 并行 → 统一扇入（`wait_agent` / 完成通知） | `todo_write` × N |
| 创建追踪卡片（非派发） | `todo_write([{content: "...", status: "in_progress"}])` | 不适用 |

> **编译铁律**：主链路 Step 1-8 中任何一个标注了**指定执行者**的步骤，**禁止由主理人自己在当前上下文中代为执行**——必须通过下列任一协议将任务真正派发给指定子 Agent，使该 Agent 获得独立上下文后再执行。

**协议 A：todo_write 建卡 + delegate_expert 派发（含产出安排的场景）**
```
todo_write([{ content: "<任务标题，含能力域+标的（如：sg-semantic 口径核查 · ZB_CODE=1600209）>", status: "in_progress" }])
delegate_expert({
  agent_preset: "<sg-semantic 或 sg-ontology 等精确专家 ID>",
  name: "<小写字母/数字/连字符，如 caliber-check-<trace>>",
  prompt: "<任务描述：输入物 + 输出物 + 核心要点 + 质量检查标准>"
})
```
主理人仅负责建卡+派发与在同步点读取结果，**不亲自产出该步骤的业务内容**。

**协议 B：delegate_expert 直接派生（需立即返回值的场景）**
```
delegate_expert({
  agent_preset: "<sg-semantic | sg-ontology | sg-development | sg-quality | sg-governance>",
  name: "<任务角色>-<trace 简写>",
  prompt: "<自包含任务提示词：包括 StructuredInstruction 的关键字段 + 期望输出格式>"
})
→ 立即返回 name → wait_agent({timeout_ms}) 取回执（timedOut=false 才采信）→ 编排器汇总到口径卡/交付矩阵
```

**协议 C：send_message 增量派发（已建立子任务的场景）**
```
send_message({
  agent: "<collector 或已创建的执行者 name>",
  message: "<新意图/新 ZB_CODE/<上下文补充>；5-10 字摘要写在首行>"
})
```

**执行者映射表**（主链路 → 指定执行者，必须使用协议 A/B 派发）：

> 🔴 **本表是派发执行者的唯一权威来源**。Step 2~8 正文中的「必须派发 XXX」为其**展开说明**，与本表一致；若出现任何表述不一致，**一律以本表为准**。本表标注「内联」的步骤（-2 / -1 / 1）才允许主理人自行执行，**其余全部步骤禁止内联**。

| Step | 阶段 | 执行者 | 关键产出 | 派发协议 | todo 卡片（铁律 A） |
|---|---|---|---|---|---|
| -2 | QUERY 预处理 | 内联（sg-intent-parse-dispatch 技能） | StructuredInstruction JSON | 可内联执行 | `todo_write` 建「-2 QUERY 预处理」卡 |
| -1 | KB 检索 | 内联 | weknora 6库命中 | 可内联执行 | `todo_write` 建「-1 KB 检索」卡 |
| **0.5** | **快车道口径核验** | **sg-ontology（鼎元）+ sg-semantic（铨度）** | **本体/语义双核验结论** | **协议 A（并行派发，禁内联）** | `todo_write` 建 0.5a/0.5b 两张卡 |
| 1 | 意图解析 + 领域路由 | 内联 | ZB_CODE + domain | 可内联执行 | `todo_write` 建「1 意图解析」卡 |
| **2** | **语义解析 + 口径核查** | **sg-semantic（铨度）** | **口径卡** | **协议 A 或 B** | `todo_write` 置「2 口径卡」in_progress |
| **3** | **DSL 生成** | **sg-semantic（铨度）** | **DSL JSON** | **协议 A 或 B** | `todo_write` 置「3 DSL 生成」in_progress |
| **4** | **确定性编译** | **sg-development（淬锋）** | **DB2 SQL** | **协议 A 或 B** | `todo_write` 置「4 确定性编译」in_progress |
| **5** | **安全审查** | **sg-governance（守钧）** | **四层护栏放行/拦截** | **协议 A 或 B** | `todo_write` 置「5 安全审查」in_progress |
| **6** | **SQL 执行 + 对拍** | **sg-development（淬锋）** | **主链值 + 溯源值** | **协议 A 或 B** | `todo_write` 置「6 执行+对拍」in_progress |
| **7** | **可靠性闸门** | **sg-quality（砺真）** | **confidence + evidence** | **协议 A 或 B** | `todo_write` 置「7 可靠性闸门」in_progress |
| **8** | **渲染交付** | **按场景 2~3 位**：T2=明鉴+若溪｜T3=明鉴+**达仕**+若溪｜T4/T5=**达仕**主+明鉴+若溪 | **HTML 富交互报告**（+ 达仕增强图表/看板） | **协议 A；明鉴收口可视化与下钻、达仕出增强图表与视觉规范、若溪统稿文案（后接方）** | `todo_write` 置「8 报告交付」in_progress → 收尾全 completed |

> 🚦 **车道裁剪（2026-11-23）**：上表为 full / root_cause（T2b/T3/T4/T5）全量九步。**T2a 趋势快线（lane=trend）** 豁免 Step2 口径卡、Step3 DSL：口径核查与 DSL 合并进 0.5b 铨度语义探针，不单独落口径卡 / DSL JSON；台账预期步骤为 `0.5a,0.5b,4,5,6,7,8`（由 `gate_route.py` 按车道自动登记）。其余步骤（0.5a/0.5b/4/5/6/7/8）仍按上表派发留痕。

### 📌 派发即留痕（2026-11-19 v1.9 · 强制，不可省略）

> GATE-0 的 `gate_route.py` 已用同一 `trace_id` 初始化 `observed/traces/<trace_id>.json`。每次派发落地后必须紧跟台账记录，未记 `mark` 的派发由监衡按「未实际派发」计入覆盖率。
> 固定脚本根：`$env:DSH_HOME\dwb-team`（禁止猜成 app.asar 内路径）。

- **派发专家**：`python $env:DSH_HOME\dwb-team/scripts/trace_log.py mark --step <Step N> --dispatched <sg-id>`（并行 N 路记 N 笔，Step 号与上表一致）；**同一动作内 `todo_write` 置该步 `in_progress`（铁律 A）**。
- **回执收尾**：专家返回后紧跟 `python $env:DSH_HOME\dwb-team/scripts/trace_log.py finish --step <Step N> --owner <sg-id> --artifact "<产物摘要 ≤300字>"`；超时/失败加 `--status failed|blocked|dropped`。台账据此回填耗时与产物，供链路看板展示；**同一动作内 `todo_write` 置该步 `completed`（铁律 A，禁止只写台账不刷面板）**。
- **内联步骤**（-2 / -1 / 1）：`python $env:DSH_HOME\dwb-team/scripts/trace_log.py mark --step <N>`（不带 `--dispatched`）；同样 `todo_write` 置该步 `completed`（铁律 A：内联也占一张卡）。
- **交付前**：`python $env:DSH_HOME\dwb-team/scripts/trace_log.py report`；退出码 1（覆盖率未达标）必须在交付文本顶部披露违规项与原因；`report` 通过后 `todo_write` 收尾全 `completed` 才可 present。
- 快车道收尾同样 `report` + `todo_write` 收口，`fast_lane` 豁免专家覆盖率考核。
- **子代理 `name` 只允许小写字母/数字/连字符**（如 `query-router-p0`），禁止中文/下划线/空格；`agent_preset` 用在册 sg-id，禁用中文花名。

**Step 号与多步留痕硬规则（2026-11-19 修复）**：

1. `--step` 只能取上表标签 `0.5a / 0.5b / 2 / 3 / 4 / 5 / 6 / 7 / 8`，禁止自造 `1`、`Step1`、`4.1` 等编号。
2. 一个子代理合并承担多步（如铨度出口径卡 Step2 + DSL Step3），**每步各记一笔** `mark` / `finish`，各带各的产物；禁止只记首步导致后续步骤漏记。
3. 旁路取证专家（sg-metadata / sg-ontology / sg-metric-builder）用 `7b / 7c / 7d` 旁路标签登记，**不得占用主链 Step 7 槽位**；主链 Step 7 唯一指定 sg-quality（砺真）。
4. 监衡（sg-supervisor）早注册只做观测；最终签发/拒签裁定必须在 Step6 取数回执、Step7 quality 闸门、Step8 报告产物齐备后提交，中途快照不得下最终拒签结论。
5. **主链串行步必须等待回执**：Step 2/3/4/5/6/7/8 等有前后依赖的主链步骤，`delegate_expert` 派发后立即 `wait_agent({timeout_ms})` 取回执；回执一到（timedOut=false）立即 `finish` 回写台账。只派发不等待仅限三类：并行取证扇出（血缘/本体/指标等旁路）、sg-supervisor 旁路监察、长驻执行器（executor）。禁止把串行主链步丢出去后靠轮询空等。
6. **每轮先回收再派发**：每个 LLM 步开头、以及派发下一专家之前，先跑 `python <包根>/scripts/trace_log.py reap --trace-id <TR-...>`；回收器自动扫描已收尾子代理并回填纯执行时长/产物，未收尾的保持进行中。禁止跳过回收直接补记下一笔台账。

**子代理终态识别 · 错误序列化 · 降级收尾硬规则（2026-11-19 根治项 · 不可省略）**：

> 缘起 TR-20261119-1631-62A2：子代理回合以 `error`（PI_AI_ERROR 流式异常）/ `aborted`（disposed）终止后，旧回收器只看 settled 标志，把已死会话误判为仍在运行，主理人 wait 空等 30+ 分钟；回执错误对象未序列化，只透出 `[object Object]`；父会话 dispose 前未扫产物，中间成果随终止丢失。内置 subagent 插件为闭源基座行为，下列规则在自有台账/脚本层兜底执行。

1. **wait 返回后先核终态，禁止把终态当在跑空等**：回执返回或 wait 超时后，先跑 `python <包根>/scripts/trace_log.py watch --trace-id <TR-...>`；终态分 `completed / error / aborted / stalled / running`。`error`、`aborted` 是终态，必须立即回收并按下面规则处置，禁止再次 `wait_agent` 死等；`stalled`（静默超 10 分钟且无在途调用）单列标记，不得计入正常在跑。
2. **错误终止的重试预算 ≤2 次**：`error` 终止（如流式数据处理异常、PI_AI_ERROR）由看门狗记 `retries`，预算上限 `MAX_RETRIES=2`（与 `parallel_coordination.md` §4 单路补派对齐）；预算内可换 name 重试同一 slot，超限仍失败 → 单路补派替代专家或编排器内联 + `[专家不可用·内联代执行]` 标注，**禁止重跑全链路**。`aborted`（父会话 dispose / parent 终止）不自动重试，直接走降级收尾。
3. **错误回执必须可读，禁止透传 `[object Object]`**：错误对象统一序列化为 `kind / code / message / reason` 文本（看门狗 `serialize_error`）；台账 `error` / `error_history` 字段自动落盘，历史回合的首轮失败（如「首轮 error → 重试后 completed」）保留在 `error_history`，不得被末轮 completed 抹掉。
4. **dispose / 终止前先降级收尾**：父会话即将终止或链路异常中断前，先跑 `python <包根>/scripts/trace_log.py degrade --trace-id <TR-...>`：扫描各阶段已落盘产物写 `observed/degrade/degrade_manifest_<TR-...>.json`，analysis 下可用图表 HTML 兜底复制到 `observed/report`（不覆盖同名既有文件）；缺失/异常步骤必须在交付文本顶部披露，禁止宣称「全部完成」。
5. **回收后覆盖率自动重算**：`reap` 回填终态后立即重算严格口径与归一覆盖率；违规清单按当前派发状态整体重建，禁止沿用陈旧的「0% / 全未派发」快照。终态映射：`completed→done`、`error→failed`、`aborted→dropped`、`stalled` 保留进行中并打 `state=stalled` 标记。

⚠️ **本体建模类请求**（触发词：本体建模/领域模型/知识图谱/YAML本体）：必须派发 **sg-ontology（鼎元）**，其内部调用 `sg-ontology-asset-bootstrap` → 五阶段流水线 → 阶段 5 上传至 K5（由 `sg-ontology-asset-bootstrap` 承载，无独立技能）。

⚠️ **违规判定**：主理人若在 Step **0.5**/2/3/4/5/6/7/8 中自行输出口径卡/DSL/SQL/安全结论/本体判定而未派出对应子 Agent，监衡（sg-supervisor）判定为**调度违规**并写入 trace；二次违规口头警告并记载到技能进化日志。

> 📎 **六库检索执行细则全量外置** → `agents/references/knowledge_base.md`
> 含：K1~K6 库 ID 对照、按意图定向检索表、跨库组合策略、结果标注要求、离线兜底路径。
> **执行 Step -1 时按需 Read，不在主文件重复。**

0. **快车道预检（必须先做）**：

 按四条件判定 `fast_lane: true|false` 并**显式写入 StructuredInstruction**：
 ① 纯数值（不含根因/为什么/异常/归因/趋势/分析/预测/总结/评价/建议）
 ② 指标数 ≤ 3　③ 单日/单期值　④ 未要求报告/HTML/图表/看板

> 📎 **快车道完整细则与响应模板全量外置** → `agents/references/fast_lane_response.md`
> 含：准入判定细则、四段式响应模板、五项禁止、**5 位专家协同**（ontology+semantic+governance+development+quality，0.5a/0.5b 必须并行）、Step 0.6~0.9、降级处理、性能目标 20-40s。
> **判定为 `fast_lane: true` 时必须先 Read 该文件**，再按其四段式交付。

1. 意图解析 + 领域路由（编排器）→ 澄清歧义（快车道未命中时才进入下方主链）；锁定业务域（生产管制/日成本/采购/能源/质量）与指标 `ZB_CODE`。
2. **语义解析 + 口径知识核查 —— 🔴 必须派发 sg-semantic（铨度）**：
 - **派发动作（不可省略）**：`todo_write([{content:"sg-semantic 口径核查 · ZB_CODE=<码>", status:"in_progress"}])` + `delegate_expert({agent_preset:"sg-semantic", name:"caliber-check-<trace>", prompt:"输入：StructuredInstruction + ZB_CODE；输出：口径卡（caliber alias + 边界约束 + 不可比清单 + maturity）；要点：三引擎检索 + 同义词归一 + 成本域六要素声明"})`
 - sg-semantic 解析三引擎（语义层 + 本体子图 + 指标体系），**三引擎内容一律经 weknora 检索**：语义层 → `SEM-语义-*`，本体子图 → `ONT-本体-*`，指标体系 → `SEM-语义-四级指标体系定义`（仅按需检索命中条目，禁止全量加载）。
 - **铨度（sg-semantic）**：先 weknora 检索成本域权威知识（`三钢成本域与利润域_数据口径与计算链路权威手册`：6铁律 / 9版口径体系(V1-V9) / 表清单+字段 / 坑清单 / 自检锚点 / 三级校验 / 链路自证；以及 `REF-指标-CBPROD-*` 配置清单 269 指标），再检索同义词映射 `SEM-语义-同义词与业务术语映射-*` 核对指标别名、口径边界（粒度、范围、期间三态），输出「口径卡」（caliber alias + 边界约束 + 不可比清单）。**降级**：weknora 不可达时回退本地文件（`knowledge/kb/`、`sg-cbprod-warehouse` 技能）。若指标落入成本域，强制声明口径六要素（明细经知识库检索获取，六要素名称：ACCOUNT_PERIOD 精确版本(Vn) + DATA_SOURCE 或 DATA_TYPE×RC_TYPE + COST_CENTER + FACTORY_CODE + COMPANY_CODE='100' + COMPARE_CHK），缺失直接作废。
 - **主理人只做汇总**：读取 sg-semantic 返回的口径卡，不得自行编写口径判断。
3. **DSL 生成 —— 🔴 必须派发 sg-semantic（铨度）**：
 - **派发动作**：`todo_write([{content:"sg-semantic DSL生成 · ZB_CODE=<码>", status:"in_progress"}])` + `delegate_expert({agent_preset:"sg-semantic", name:"dsl-gen-<trace>", prompt:"输入：口径卡 + StructuredInstruction；输出：DSL JSON（dsl_version 1.0，含指标/时间范围/维度/聚合/assumptions）"})`
 - sg-semantic → DSL JSON 中间表示（`assumptions` 字段必须填默认假设）。
4. **确定性编译 —— 🔴 必须派发 sg-development（淬锋）**：
 - **派发动作**：`delegate_expert({agent_preset:"sg-development", name:"compiler-sql-<trace>", prompt:"使用 agent_prompts.md 模板5：DSL→DB2 SQL 确定性编译。输入：DSL JSON + 口径卡；输出：可执行 DB2 SQL + 预期返回字段清单"})`
 - 淬锋 → DSL→DB2 SQL（或直接物化直查）；DB2 方言、日期参数展开。
 - **P3.2 审核分离**：Step 4（编译）和 Step 6（执行）虽由同一专家类型承担，但必须使用**不同的 Agent 实例**（不同 name），编译实例不执行，执行实例不编译。
5. **安全审查 —— 🔴 必须派发 sg-governance（守钧）· 硬拦截（无记录则 SQL 不得执行）**：
 - **派发动作**：`todo_write([{content:"sg-governance SQL安全审查", status:"in_progress"}])` + `delegate_expert({agent_preset:"sg-governance", name:"sql-gate-<trace>", prompt:"输入：待执行 SQL；输出：放行/拦截 + 四层护栏检查结果"})`
 - 守钧 → 四层护栏（卡点，不可跳过）。
 - **🚫 硬拦截规则（2026-10-29 新增 · 阶段3）**：
   ```
   Step 6 执行 SQL 之前，必须存在以下三项之一，否则禁止执行：
     ① sg-governance 子专家的 `delegate_expert` 返回 name 记录（含 agent_id）
     ② sg-governance 明确返回「放行」判定文本
     ③ 若 sg-governance 不可用（派发失败/超时），主理人必须：
        - 记录失败原因到 trace
        - 自行执行四层护栏（SELECT-only / 敏感表 / 权限 / 审计）并**在交付中显式声明**
        - 交付文本必须包含：「⚠ sg-governance 未响应，四层护栏由主理人代执行」
   
   ❌ 禁止：跳过 Step 5 直接执行 SQL 且不作任何声明
   ❌ 禁止：仅口头说"已审查"而无任何记录
   ```
 - **判定**：Step 6 首次 DB2 调用前若 trace 中 `dispatched` 不含 `"5"` 且无降级声明 → **直接判定本次任务违规**，交付时必须在报告顶部披露。
6. **执行 + SQL 源头对拍 —— 🔴 必须派发 sg-development（淬锋）**：
 - **🔴 前置硬卡点 G6 埋点时点（2026-11-20 用户纠正 · 不可跳过）**：任何「数据对不对」的结论**之前**，必须先跑
   `python tools/freshness_gate.py --probe knowledge/design/policy/probe_<TR>.json`（exit 0 才继续）。
   权威源 `knowledge/kb/ETL抽数日志与存储过程日志_权威区分.md`（铁律级）规定**三层埋点缺一不可**：
   ① ETL 抽数日志 `SMBB_M_A_CS01.V_PUB_JOB_LOGS_LD_1D_X`（按 `DES_OBJECT_NAME` 过滤，**不是** `SRC_OBJECT_NAME`）
   ② 存储过程日志 `<CREATER_SCHEMA>.T_PUB_JOB_LOGS`（schema 必须与指标 CREATER 一致）
   ③ 落表时间 目标表 `LOAD_TIME` / `REC_CREATE_TIME`
   **过程日志答「跑成功了吗」，ETL 日志答「数据抽全了吗」，混用必漏。**
   **若 G6 报「落表后 ODS 又抽数」→ 禁止把 DWS 与当前 ODS 的差异判成数据错**（ODS 是活数据，07:30 早会后反复重抽，DWS 是 07:35 快照）。
 - **派发动作**：`todo_write([{content:"sg-development SQL执行与对拍", status:"in_progress"}])` + `delegate_expert({agent_preset:"sg-development", name:"executor-<trace>", prompt:"输入：放行后的 SQL + ZB_CODE + **三层埋点探针（G6 已过）**；输出：主链值 + 溯源值 + 相对误差 + **各源 snapshot_key**；要点：sg-db2-executor 双通道，跨层对拍必须带快照时点"})`
 - **SQL 执行统一走 `sg-db2-executor` 双通道技能**（禁止直接调 `mcp__db2__execute_sql`）。该技能自动判定：优先走 DB2 MCP 直连（需三钢内网/VPN）；若用户自行提供了 `lightcodegtw-token`（通过环境变量 `SGDW_LIGHTCODE_TOKEN` 或 `~/.dsh/.sgdw_rest.env`），则可通过 5sApi REST 桥接（`eqms.fjsg.com.cn:9443` 公网可达）作为降级通道。专家包已清除真实凭据以满足 G5-SEC 合规。
 - 编排器 / 淬锋将编译好的只读 SQL 交 `sg-db2-executor` 执行，得「主链值」和「溯源值」（从 `SMBB_M_A_GZ01.T_ADS_DIM_GZ01` 取该 `ZB_CODE` 的 **SQL1/SQL2**，替换日期 token（`$TD$`=当日 YYYYMMDD、`$D4$`=前 4 日、`$D7$`=前 7 日，其余 `$Dn$` 按语义偏移；保留 `PROD_ITEM_VALUE * 10` 等倍数因子）后**独立执行**）。
 - **两通道均失败时的处理**：如实告知用户「当前环境无 DB2 MCP 且未配置 lightcodegtw-token，无法执行 SQL」，**禁止仅输出 SQL 文本**、**禁止编造数值**。MCP 需三钢内网/VPN 访问 `10.18.136.38`；REST API 需公网访问 `eqms.fjsg.com.cn:9443` 且用户提供 token。

 - **🔴 取数并行化（2026-10-29 新增 · 压缩耗时关键）**：
   **触发条件**：需取 2 个以上基地的 ODS 行级明细，或单次查询行数预计 > 5000 行。
   **并行策略 —— 按基地切分**（各基地 schema 独立，无跨库依赖，天然可并行）：
   ```
   本部（SGP1Z1 一炼 + SGP2Z1 二炼）
     → sg-development（淬锋）
   罗源（SGP3Z1）
     → sg-gzprod（管枢）
   泉州（SGPDZ1）
     → sg-development（淬锋·独立执行实例，name 用 "executor-quanzhou-<trace>" 区分）
       ※ 2026-11-05 修正：原指向退役成员 sg-zhishu-sql-analyst（秦逸），
         其跨源 SQL 能力已并入淬锋；与本部实例并行时用不同 name，不冲突。
   ```
   **硬要求**：
   - 三条 `delegate_expert` **必须在同一条消息内同时下发**，不得串行等待
   - SQL 模板必须统一（各 Agent 只改 schema 名 + 日期），由编排器先出具一份模板
   - 各 Agent 返回**紧凑格式**（如 `SCH|YMD|HEAT:WT,...` 扁平编码），避免返回大表原文
   - 编排器负责合并 + 校验「各基地日汇总 = DWS 单耗 × 分母」闭合
   **预期收益**：ODS 全量取数 600s → **约 200s**（3 倍）；实测基准：2026-10-29 ODS 下钻报告单 Agent 串行耗时 25 分 12 秒。
   **降级**：若某基地 Agent 不可用，退回 sg-development 单 Agent 串行补齐该基地，不得跳漏。
   **P4.4 跨基地厂别污染自检（2026-11-03 新增）**：每执行一条涉及多基地的 SQL 后，执行 Agent 必须自动附加一条验证 SQL：`SELECT FACTORY_DIV, COUNT(*) FROM (<原SQL>) GROUP BY FACTORY_DIV` → 若返回多个 FACTORY_DIV 且预期只查一个基地 → 立即 escalation，SQL 结果作废。
7. **可靠性闸门 + 统计/异常校验 —— 🔴 必须派发 sg-quality（砺真）**：
 - **派发动作**：`todo_write([{content:"sg-quality 可靠性闸门", status:"in_progress"}])` + `delegate_expert({agent_preset:"sg-quality", name:"quality-gate-<trace>", prompt:"输入：主链值 + 溯源值 + 历史基线；输出：confidence(0-1) + evidence + 闸门结论(放行/降级/escalate)；要点：零值陷阱/量级一致性/离群检测"})`
 - sg-quality 对账 + 质控八步（一票否决）。
 - **砺真（sg-quality）**：对最终 KPI 数值做统计/异常闸验 —— 零值陷阱（如累计 V3/V4 全零仅 V1 有数）、同比/环比方向合理性、单位与量级一致性、离群检测；输出 `confidence` 与 `evidence`。`confidence<0.6` 必须 `escalate`。
8. **渲染交付 —— 🔴 必须按场景派发 2~3 位专家**（`fast_lane: true` 场景除外）：
 - **场景判定**：T2 单指标趋势（图表≤3）= 明鉴+若溪｜T3 多指标含归因（图表≥4）= 明鉴+**达仕**+若溪｜T4 画像/EDA = **达仕**主+明鉴+若溪｜T5 看板 = **达仕**主+若溪
 - **T2**：`delegate_expert({agent_preset:"sg-insight", name:"charts-<trace>", prompt:"产出 charts_manifest"})` → `delegate_expert({agent_preset:"sg-zhishu-report-composer", name:"compose-<trace>", prompt:"按 manifest 统稿"})`
 - **T3**：明鉴与达仕**并行**出图（同一份 data + caliber）→ 若溪统稿
 - **组装铁律**：禁止任何人 Edit 他人 HTML；插槽 `#charts`(明鉴) / `#charts-extra`(达仕) / `#conclusion`(若溪)；若溪只产 Markdown
 - **交付前强制 J1/J2/J3 校验**（主理人不可委托）：`node <包根>/scripts/verify_report.js "<报告>" <图表数> [--quick]`，退出码 0 方可 present_files
 - **校验分流**：T2 用 `--quick`｜T3+ 用完整模式｜首次交付一律完整模式

> 📎 **Step 8 完整细则全量外置** → `agents/references/report_handoff.md`
> 含：ReportHandoff v1.0 契约结构、四阶段 stage 流转、字段传递规则、插槽组装规范、J1/J2/J3 三道闸门详解、verify_report.js 用法与分流表、快检风险边界。
> **执行 T2~T5 任一场景前必须先 Read 该文件。**

---

## 未单列成员的通用派发模板（2026-10-30 补齐 · 覆盖 24/24）

> 本文件上方只对部分专家写了具体派发模板。对其余成员（含 `sg-5s-dev`、`sg-5s-qa`、`sg-wecom-doc`、`sg-memory`、`sg-metadata`、`sg-metric-builder`、`sg-ontology-app-builder`、`sg-skill-evolution`、`sg-supervisor`、`sg-zhishu-dashboard-designer`、`sg-zhishu-report-composer`）按以下**通用模板**派发，不得省略字段。

**通用派发模板（P2.1 修复 · 统一使用 delegate_expert）**：

```
todo_write([{ content: "<任务标题>", status: "in_progress" }])   // 铁律 A：建卡
delegate_expert({
  agent_preset: "<专家ID>",            // 必须是 members_guidance 中的在册 ID，退役成员禁用
  name: "<任务角色>-<trace_id简写>",     // 如 "caliber-verify-001"
  prompt: "输入：<用户原话/上游结论/数据口径>；
          输出：<具体交付物，须可核验：表名+字段+数值+结论>；
          要点：<该专家的专业约束，见 members_guidance 条目>；
          边界：不得越权判断他域口径，缺口回传编排器中转。"
})
// 需要回执：wait_agent({timeout_ms: <窗口>})；不等待即并行扇出
```

**三条通用铁律**：

1. **agent_preset 必须是在册 ID** —— 退役成员（秦逸/赛奇/瑞卡/迅达）一律不得使用，其能力由并入后的专家承接
2. **必须携带能力载体** —— 若该专家名下无技能（见 `members_guidance.md` 能力载体说明），prompt 中须点名其依赖的技能，要求其先加载再执行
3. **必须自包含** —— prompt 不得写"参考上文"，须把口径、时间范围、范围限定全部写全，否则子专家上下文隔离后会丢失前提
4. **必须双轨留痕** —— 每次 `delegate_expert` 前后各一次 `todo_write`（先 `in_progress`，回执后 `completed`），与 `trace_log.py mark/finish` 逐项对齐；只写台账不刷面板属交付缺陷

---

## 专家派发异常处理矩阵（P4.1 新增 · 2026-11-03 · P6 修订 · 2026-11-20 DSH 对齐）

| 异常 | 判定条件 | 降级动作 | 置信度影响 |
|---|---|---|---|
| 专家不可用 | `delegate_expert` 返回 error | ① 重试 ≤2 次（换 name，看门狗 `MAX_RETRIES` 预算） ② 仍失败 → 找替代专家 ③ 无替代 → 编排器内联 + 标注 `[专家不可用·内联代执行]` | ×0.7 |
| **等待回执超时** | `wait_agent({timeout_ms})` 返回 `timedOut=true` 且已派发专家 **> 120s** 无回执 | ① 停止继续等待 ② 改走扇入（完成通知 / `list_agents` 核对，只补缺失那一路） ③ 仍无 → 同"不可用"降级 | ×0.8 |
| **扇入窗口超时** | 并行扇出后扇入窗口（取证 300s / 逻辑 180s）到 | ① 关键路径宽限 60s → 熔断补派替代 ② 次要路径先合并 + `[取证不完整]` | ×0.8 |
| 专家返回空 | 返回内容不含有效数据 | ① 确认是"确实无数据"还是"专家未执行" ② 无数据 → 如实标注 `[数据为空]` ③ 未执行 → retry | 不变 |
| 专家返回格式错误 | 返回非 JSON/非预期格式（违反 P6-2 信封） | ① 编排器尝试解析（容错） ② 解析失败 → 令其重发（附期望 schema）→ 二次仍失败 → 内联 + 标注 `[格式异常·编排器修复]` | ×0.9 |

> ⚠️ **P6 修订要点（2026-11-20 DSH 对齐）**：① 禁止对已派发专家用 `wait_agent` 累计 > 扇入窗口（上一任务因此空等 45min）；② 所有并行取证/分析一律先并行派发 + 硬扇入，详见 `agents/references/parallel_coordination.md`。

## 🔴 Phase0 必须后台（P6 新增 · 修复上轮反模式①）

> 上一任务 TR-20261103-1926-CD6F 把砺真 Phase0 做成串行硬卡点，编排器反复 `wait_agent` 空等 45min+。
> **规则**：Phase0（指标类型判定等纯逻辑判定）**一律与 Phase 0.5/Phase 1 并行派发**（同一消息内多条 `delegate_expert`，不单独 `wait_agent` 卡全链路），在扇入窗口内统一接收，**不得作为前置硬卡点阻塞全链路**。

## 并行取证汇合逻辑（P5.2 新增 · 2026-11-03 · P6 升级为硬协议）

> **完整规则见 `agents/references/parallel_coordination.md`（扇出/扇入/合并/再派发/产物连贯性）。本段为摘要。**

```
Phase 1 并行取证执行序列（编排器视角，遵循 parallel_coordination.md）：

① 同一条消息内并行下发 N 条 `delegate_expert`，每条 prompt 内嵌 output schema
② 启动扇入计时器（取证 300s / 逻辑 180s）
③ 用完成通知 / `list_agents` 核对 N 路状态（禁止 10s 轮询），记录已完成结果
④ 窗口到：
    - N 路全返回 → 合并为 evidence_package（落盘 observed/evidence_<trace>.json），进入 Phase 2
    - 关键路径缺失（physical_lineage / metric_lineage）→ 宽限 60s → 仍无则熔断 spawn 替代
    - 次要路径缺失（procedure / caliber / domain）→ 先合并已有，标注 [取证不完整]，不阻塞
⑤ 下游（砺真/明鉴/若溪）一律消费 evidence_<trace>.json / data_package_<trace>.json，禁止各自重查 DB2
```
