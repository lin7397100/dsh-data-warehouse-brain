# 编排器边界与副作用队列（源自 dsh-superagent 007-architecture + prompts/shared · 2026-11-16 提炼）

> 来源：dsh-superagent-prototype `docs/007-architecture.md`、`prompts/shared.md`
> 目的：防止主理人（冶衡）既当编排者又当执行者，以及多 Agent 并行写同一产物导致冲突。

## 一、编排器四不越权（直接移植shared.md铁律）

| # | 禁令 | 本团落地 |
|---|---|---|
| 1 | 编排器不做执行者的调查工作 | 冶衡**不亲自**查代码/日志/文档细节/技术讨论，不替专家解决阻塞——这些都由被派发的专家完成 |
| 2 | 派发不重写用户需求 | 派单 prompt 只传**原始意图契约**（IntentContract），**禁止**主理人擅自加需求、实现计划、验收标准、重复的策略清单 |
| 3 | 执行者从原始源与常设策略取需求 | 各专家从契约 + 本角色规范推导任务，不从主理人的"转述加料"推导 |
| 4 | 编排器只做路由与汇编 | 派发、转交、汇总、裁决；专业产出必须由对应专家输出后再采信 |

**判据**：如果主理人发现自己在"顺手查一下 SQL 对不对 / 顺手算一下数值 / 顺手画个图"，即为越权，立即停下改派专家。

## 二、单一写入者原则（One writer per state）

源自 007-architecture：每类状态只有一个写者，其他只读或请求该写者。

| 状态 | 唯一写者（本团映射） |
|---|---|
| 意图契约 IntentContract | 辨枢 sg-query-router |
| 权威数据集 + SQL | 淬锋 sg-development |
| 计算结论 findings | 砺真 sg-quality |
| 报告 HTML / 图表 | 明鉴 sg-insight（报告）；达仕 sg-zhishu-dashboard-designer（图表插槽，与明鉴约定不同插槽） |
| 物化 SQL / 注册表 / markdown 卡 | 衍薪 sg-skill-evolution |
| 语义注册与成熟度 | 铨度 sg-semantic |
| 向量索引 | 诠枢 sg-semantic-modeler |
| Neo4j 图谱 | 构枢 sg-ontology-modeler |
| 最终签发 | 监衡 sg-supervisor（唯一签发权，P5） |

**铁律**：任意时刻一个产物只有一个活跃写者；阶段交接走显式令牌（`orchestrate.js` 的 `transferWriter`），**禁止并行编辑同一 HTML/SQL**。

## 三、持久化副作用队列（Effects 模式，简化移植）

源自 007-architecture 的 Effects：命令在**事务内入队**，**提交后才执行**；每 `(kind,key)` 一行实现幂等；失败指数退避；同类保证顺序。

本团落地（无需真的实现 SQLite，按纪律执行）：
1. **先记录后动作**：派发、回执、落库、通知等副作用，先在 trace/ledger 登记，再实际执行。失败可按 ledger 重放。
2. **幂等键**：副作用键 = `trace_id + 动作类型 + 目标`。同键重复入队覆盖 payload、不改变顺序，绝不产生两个产物（防重复物化 / 重复建图节点）。
3. **提交后执行**：契约未冻结前不落库；P5 签发前宣布"阶段草案"而非"最终交付"。
4. **失败退避**：2s→4s→…→60s；连续 3 次失败才上报系统问题，不因一次失败中断整链。
5. **顺序保证**：同一产物的 relay/notice 按队列顺序，前者失败阻塞同类后者（防报告先于数据到达）。

## 四、按角色裁剪上下文（Model-facing interfaces 启示）

dsh-superagent 对 main Session 与 Executor 暴露**不同的工具集与资源视图**：Executor 只读自己的 Ticket 及其线程，看不到别的 Ticket 与决策。

本团落地：
- 派发给专家的 prompt **只含**该阶段契约（C0~C4）+ 本角色必需资料（≈5KB），禁止灌全量历史（与 `scoped_context.js` 一致）。
- 专家**不得**读取其他专家的中间草稿，只读契约与权威产物。
- 主理人给专家的 `orchestrator_read` 等价能力按角色裁剪：语义专家给 K3/语义层，本体专家给 K5/Neo4j，开发专家给 DB2/SQL，不再"人人全量"。

## 五、Prompt 版本化与漂移检查（Versions 启示）

- 专家 prompt/规范改动走版本号 + 备份（衍薪已有 `.versions/`），改动后跑回归。
- 新增/修改规则后，必须检查"模型可见面"（工具/技能/指令）一致性——本团对应烟测的静态契约 + 功能实跑两层。

## 六、最小注意力落地到面板

- 只展示**需要人**的事项：等待确认的物化候选、待澄清的歧义、失败告警。
- 健康状态不占版面；过程中静默，仅关键节点通报。
