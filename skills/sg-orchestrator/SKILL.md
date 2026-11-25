---
name: sg-orchestrator
description: "三钢数仓智脑：专家团协作编排与运行控制。承载六阶段(P0~P5)+五道闸门(G0~G5)调度内核、阶段契约(C0~C5)台账、写者独占令牌、唯一签发权、防过早发布与防回溯返工红线。针对『对标本周各工序炼钢成本与定额标准，标出超定额项并给出降本建议』类任务，给出可执行的 SOP 与运行时。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, orchestration, governance, sop, sign-off]
owner: data-warehouse-brain-team-lead
---

# sg-orchestrator · 专家团协作编排与运行控制

## 定位

专家团改造方案的**执行内核**。把「人人都能最后一改、各自为政、过早发布、结论回溯」的失控模式，
收束为「单一真相源 + 阶段契约 + 唯一签发权 + 写者独占 + 范围上下文」的确定性协作。

> 改造背景：TR-20261106-1555-FF39 真实 trace —— 单次任务耗时 2h43m / 22 版回执 / 20 次 md5 漂移 / 6 层缺陷。
> 根因一句话：缺少「单一真相源 + 阶段契约 + 唯一签发权」，导致并行写冲突、回溯失控、上下文膨胀。

## 何时加载本技能

- 启动一个**跨阶段 / 多专家**的任务（对标、根因、报表、成本管控等）之前；
- 需要判断「是否走 Fast-Lane 短路」时；
- 需要登记/校验**阶段契约**、交接**写者令牌**、申请**重开**时；
- 需要在 P5 之前跑**全闸门绿证**与**稳定性采样**时。

## 设计原则（5 条，不可违背）

1. **单一真相源 SSOT**：数据/口径/模板各只有一份权威件，禁止副本漂移。
2. **阶段契约 Contract**：每阶段产出冻结契约，下游只消费契约，不回改上游。
3. **唯一签发权 Single Sign-off**：只有 P5 总监节点能宣布「最终交付」，且仅在全闸门绿后。
4. **写者独占 Write-Exclusivity**：任意时刻产物只有一个活跃写者，其余只读。
5. **范围上下文 Scoped Context**：sub-agent 只拿「宪章 + 本阶段契约」（≈5KB），不吃全量历史（≈200KB）。

## 六阶段 + 五道闸门（主流程）

```
P0 宪章 ──G0──▶ P1 取数 ──G1──▶ P2 计算 ──G2──▶ P3 报告 ──G3──▶ P4 治理 ──G4──▶ P5 签发
 (意图)         (数据)        (计算)        (草稿)        (闸门)        (最终)
   │                                                                           │
   └──────────── 回溯必须走「重开申请」，不得静默覆盖 ───────────────────────────┘
```

| 阶段 | 主责专家 | 协作(可并行) | 产出契约 | 退出闸门 |
|---|---|---|---|---|
| **P0 任务宪章** | sg-semantic（意图解析） | 无 | C0 宪章 JSON | G0 意图已确认 |
| **P1 取数层** | sg-development（唯一写者） | 按基地 fan-out 取数，归并到 1 人 | C1 权威数据集 + SQL | G1 C-GOV-3 + 取数闭合 |
| **P2 计算层** | sg-quality（唯一写者） | 无（强依赖 C1） | C2 计算结果集 + 闭合 | G2 三重闭合残差=0 + 双盲一致 |
| **P3 报告层** | sg-insight + zhishu-report-composer | 无（填模板） | C3 报告草稿 | G3 模板填充 + 图表非空 |
| **P4 治理审核** | sg-governance（唯一写者） | 可并行跑静态断言 | C4 闸门报告 | G4 C-GOV-4 + C-G11 + 语法零错 |
| **P5 总监签发** | sg-supervisor（唯一签发权） | 无 | C5 最终交付物 | G5 全绿 + 稳定采样 + 用户确认 |

**双盲二次校验**：P2 完成后，由 sg-gzprod（生产域）/ sg-cbprod（成本域）做独立 second verifier；
结论不一致触发「重开 P2」，不进 P3。

## 每阶段 SOP（进入 / 动作 / 交付物标准 / 退出闸门）

### P0 · 任务宪章（C0）
- **进入**：收到用户任务语句。
- **动作**：解析范围（账期/基地/科目集）、口径版本（如 2026M11 L3c）、交付物形态（单文件 HTML/四层下钻）、闸门清单、TOKEN 预算。
- **交付物标准（C0）**：结构化 JSON，含 `scope / caliber / bases / deliverable_type / gate_list / token_budget / reopen_budget`。
- **退出 G0**：宪章回显给用户确认（或默认确认），禁止在 P0 直接开工。

### P1 · 取数层（C1）
- **进入**：持 C0。
- **动作**：按基地 fan-out 取数 → 归并；执行 C-GOV-3；口径锁死 L3c 同域。
- **交付物标准（C1）**：权威数据集 + SQL；**字段名与下游契约字面一致**（数据用 `quota/imp/me`，渲染层不得写 `quotaW/impact/matchedPC`）。
- **退出 G1**：C-GOV-3 通过 + 取数行数闭合。

### P2 · 计算层（C2）
- **进入**：持 C1（只读）。
- **动作**：差异额/率、闭合校验、超定额判定；双盲校验。
- **交付物标准（C2）**：计算结果集 + 三重闭合残差（必须 = 0.000000）+ 超定额清单。
- **退出 G2**：闭合残差=0，双盲一致。

### P3 · 报告层（C3）
- **进入**：持 C2（只读）+ 标准模板。
- **动作**：填标准模板（shell.html 类），图表绑定 C2 字段；**先验证 comparableRows 等非空**（防空白图）。
- **交付物标准（C3）**：报告草稿，图表全部非空，数值与 C2 字面一致。
- **退出 G3**：模板填充完成 + 4/4 脚本语法校验 + 图表数据数组非空。

### P4 · 治理审核（C4）
- **进入**：持 C3。
- **动作**：跑 C-GOV-4 产物自证（11 必含 + 22 禁含）、C-G11 三形态断言（元/千分位/万元）、C28/C29 口径断言、CDN=0、语法校验。
- **交付物标准（C4）**：闸门报告（每项 PASS/FAIL + 证据）。
- **退出 G4**：全部 PASS，无红色项。

### P5 · 总监签发（C5）—— 唯一可宣布「最终交付」的节点
- **进入**：持 C4 全绿。
- **动作**：跑完整断言链 + 稳定性采样（≥3 次 md5 一致）+ 冻结（chmod 444 + build/.LOCK）；**向用户回显全闸门绿证后**再宣布最终。
- **交付物标准（C5）**：最终交付物 + 指纹（md5/sha256/size）+ 闸门清单。
- **退出 G5**：全绿 + 稳定 + 用户确认。

## 统一协调与审核节点（杜绝各自为政）

1. **契约台账 Contract Ledger**（`assets/contract_ledger.js`）：C0~C5 每个契约带 hash 登记；下游引用契约 hash，不引用「某人的临时文件」。
2. **变更日志 Change Log**：任何结论变更必须 `author + reason + before/after` 记一笔；未登记的改动视为违规。
3. **共享宪章 Shared Charter**：所有 agent 读同一份 C0，禁止各自解读范围/口径。
4. **活跃写者令牌 Writer Token**：产物任一时刻只有 1 个写者；交接 = 显式 `transfer(writer, phase)`，非并行编辑。

## 防返工 / 防过早发布 红线（硬约束）

| 风险 | 机制 |
|---|---|
| 过早宣布「最终交付」 | 只有 P5 可发「最终」；sub-agent 只能报「阶段完成/草稿就绪」，禁用「定稿/final/最终交付」措辞 |
| 结论回溯静默覆盖 | 契约冻结后不可改；P4 发现上游错 → 提「重开 P1/P2」申请（带理由）→ 重算 → 下游契约失效重验 |
| 20 次漂移 | SSOT + 写者独占 + `build/.LOCK` 前置检查（C-GOV-6）；重建前先查锁 |
| 口径横跳 | 口径在 C0 锁死（L3c），全程不得切换；切换=重开宪章 |
| 文档≠SQL | C-GOV-4 产物自证 + C-G11 三形态；报告口径名与 SQL 别名字面一致 |

**回溯红线**：同一产物被「重开」超过 `reopen_budget`（默认每阶段 ≤ 2 次）即升级人工裁决，禁止无限返工。

## 效率与 TOKEN 优化策略

1. **Fast-Lane 短路**（`assets/fast_lane.js`）：单指标/已知指标查询直接走物化 SQL，不建 team、不跑 P1~P4 全链。
2. **范围上下文注入**（`assets/scoped_context.js`）：sub-agent 只收 `C0 + 本阶段契约`（≈5KB），不再灌入完整对话（≈200KB）→ 单次 handoff 上下文 ≈ 1/40。
3. **迭代封顶 + 预算告警**：全局 TOKEN 预算 + 每阶段 reopen 上限；超阈即告警/升级。
4. **口径/指标预注册**（`assets/caliber_registry.js`）：80030、L3c、quota 等固化为契约，不再每次重新推导。
5. **单一确定性构建**：`build/build.js` 以 `build/_c0.js` 为 ECharts 本地单一源 + C-GOV-6 锁检，消除「忘了重建」假象。
6. **模板复用**：报告层是「填空」而非「重设计」，P3 耗时从 redesign 降为 fill。
7. **并行安全区**：P1 内按基地并行取数（fan-out），但归并到唯一写者，避免并行写冲突。
8. **断言前置到本地**：P3 自检（图表非空、语法）在交付前跑完，减少 P4→P3 来回。

## 运行时资产（本技能自带，可直接 require）

| 文件 | 职责 | 改造项 |
|---|---|---|
| `assets/contract_ledger.js` | 契约台账 + 写者令牌 + 重开 + 变更日志 | P0-2 |
| `assets/gates.js` | G0~G5 + C-GOV-3/4/6 + C-G11 + C28/C29 + D1~D5 可调用校验器 | P1-3 |
| `assets/fast_lane.js` | 单指标短路路由 | P1-4 |
| `assets/scoped_context.js` | 宪章 + 阶段契约范围上下文（≈5KB） | P1-4 |
| `assets/caliber_registry.js` | L3c 口径 / 80030 / quota·imp·me 字段契约 | P2-5 |
| `assets/orchestrate.js` | 六阶段(P0~P5)调度驱动器：包装上述运行时为可实例化 `Orchestrator`（start / enterPhase / exitPhase / handoff / signOff） | 接入实际调度 |

## 与既有门禁体系对齐（复用不另造）

- **GATE-0/2d/2b**：意图/DSL/治理放行 → 对应 P0/P1/P4
- **D1~D5**：下钻闸门 → 并入 P3 交付标准
- **C-G11**：三形态断言 → 并入 P4
- **C-GOV-3/4/5/6/7**：数据源/自证/写者独占/查锁/剥离 script → 并入 P1/P4/P5
- **C28/C29**：多产品集差异率/产品集一致性 → 并入 P2

## 典型调用示例

```js
const ContractLedger = require('./assets/contract_ledger');
const gates = require('./assets/gates');
const { route } = require('./assets/fast_lane');
const { buildScopedContext } = require('./assets/scoped_context');

// 1) 判断是否短路
if (route({ text: '查一下 80030 钢铁料耗口径' }) === 'fast') { /* 走物化 SQL，不建 team */ }

// 2) 记宪章、拿写者令牌
const ledger = new ContractLedger({ reopenBudget: 2 });
ledger.acquireWriter('sg-development', 'P1');
const c1 = ledger.registerContract('C1', { rows: 21, caliber: 'L3c' }, 'sg-development');

// 3) 给 sub-agent 范围上下文（非全量）
const scoped = buildScopedContext(charter, c1, {});

// 4) P5 前跑全闸门
const report = gates.runAll(['G0','G1','G2','G3','G4','G5'], ctx);

// 5) 实际调度：直接实例化 Orchestrator 驱动器（推荐）
const { Orchestrator } = require('./assets/orchestrate');
const o = new Orchestrator({ reopenBudget: 2 });
o.start({ scope:'本周炼钢成本定额对标', caliber:'L3c', confirmed:true });
o.enterPhase('P1','sg-development');
o.exitPhase('P1', { dataSourceExists:true, srcExists:true, rowCountClosed:true, contractPayload:{rows:21} });
```

## 已接入实际调度（2026-11-06 改造落地）

本技能的运行时不再只是文档，已**接入真实任务流**作为强制控制平面：

- **编排器（team-lead）**：`agents/data-warehouse-brain-team-lead.md` §4.1「六阶段 SOP 强制调度」→ 任务起手必须 `new Orchestrator()`，全程驱动 P0~P5 + 写者独占 + 唯一签发权 + 防过早发布/回溯。
- **签发节点（sg-supervisor）**：`agents/sg-supervisor.md`「六阶段签发管制（P5 唯一签发权）」→ 只有它能调用 `signOff` 宣布最终交付，且须全绿 + 稳定采样 + 冻结 + 回显绿证。
- **强制规范文件**：`agents/references/orchestrator_runtime.md`（六阶段指令 + 驱动器 bootstrap + 令牌/签收/回溯红线）。

> 下次「对标本周炼钢成本」类任务起手即走六阶段，杜绝「忘了走流程」与「各自为政」。
```
