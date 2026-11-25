# 六阶段调度控制平面（sg-orchestrator）· 实际调度强制规范

> 权威源：`skills/sg-orchestrator/`（SKILL.md + assets/orchestrate.js + contract_ledger.js + gates.js + fast_lane.js + scoped_context.js + caliber_registry.js）
> 适用任务原型：**「对标本周各工序炼钢成本与定额标准，标出超定额项并给出降本建议」** 及一切"取数→计算→报告→治理→签发"型多专家任务。
> 来源：TR-20261106-1555-FF39 真实 trace（单次 2h43m / 22 版回执 / 20 次漂移 / 6 层缺陷）根因治理。

---

## 0. 为什么需要本规范（一句话根因）

此前协作失控的根因 = **缺少"单一真相源 + 阶段契约 + 唯一签发权"**，导致并行写冲突、回溯失控、上下文膨胀。
本规范把"人人都能最后一改"收束为"只有总监能签发、且签发前全绿、每阶段只有一个写者"。

## 1. 六阶段 + 五闸门（主流程，强制走）

```
P0 宪章 ─G0─▶ P1 取数 ─G1─▶ P2 计算 ─G2─▶ P3 报告 ─G3─▶ P4 治理 ─G4─▶ P5 签发
 (意图)       (数据)        (计算)        (草稿)        (闸门)        (最终)
   │                                                                           │
   └──────────── 回溯必须走「重开申请」，不得静默覆盖 ───────────────────────────┘
```

| 阶段 | 唯一写者（主责） | 退出闸门 | 交付契约 |
|---|---|---|---|
| **P0 宪章** | sg-semantic | G0 意图已确认 | C0 |
| **P1 取数** | sg-development | G1 + C-GOV-3 | C1（权威数据集 + SQL） |
| **P2 计算** | sg-quality | G2 + C28 + C29 | C2（闭合残差=0 + 超定额清单） |
| **P3 报告** | sg-insight | G3 + D1 | C3（图表非空 + 数值字面一致） |
| **P4 治理** | sg-governance | G4 + C-GOV-4 + C-G11 | C4（闸门报告全绿） |
| **P5 签发** | sg-supervisor（唯一签发权） | G5 + C-GOV-6 | C5（指纹 + 闸门清单） |

**双盲二次校验**：P2 完成后由 sg-gzprod / sg-cbprod 做独立 second verifier，不一致触发"重开 P2"，不进 P3。

## 1b. 五道脚本闸门（2026-11-20 新增 · G0~G5 的**可执行实现**）

> 上面的 G0~G5 是**概念闸门**（谁有权、谁签字）；下表是它们的**确定性脚本实现**——退出码非 0 即卡死，**不接受"我记得跑过"**。
> 权威源：`agents/references/intent_and_sql_gates.md`

| 脚本闸门 | 插入点 | 命令 | 卡死条件 |
|---|---|---|---|
| **G1 指标消歧** | P0 之后 · 写 `entities.metrics` 之前 | `python tools/metric_disambiguate.py --text "<原话>"` | exit 3 → 必须请用户点名；exit 4 → 写入 `open_questions` |
| **G2 意图门禁** | P0 出口（C0 冻结前） | `python tools/intent_gate.py --contract observed/intents/<TR>.intent.json` | exit 1 → 退回 sg-query-router 重出契约 |
| **G3 SQL 静态** | P1 入口（编译完成、执行前） | `python tools/sql_static_check.py --sql artifacts/compiled/q_<TR>.sql` | exit 1 → 退回 sg-development 重编 |
| **G4 结果断言** | P1 出口（C1 冻结前） | `python tools/sql_result_assert.py --result … --spec …` | exit 1 → 数据不可信，禁止进 P2 |
| **G5 换源对拍** | P4 治理 → P5 签发之间 | `python tools/sql_cross_source.py --spec …` | exit 1 `DRIFT` 阻断；exit 3 `INSUFFICIENT` → 不得声称已核验 |

**阶段与闸门的对应（漏一个即判流程违规）**：

```
P0 宪章 ──G1 消歧──▶ ──G2 意图门禁──▶ C0 冻结
P1 取数 ──G3 SQL静态──▶ 执行 ──G4 结果断言──▶ C1 冻结
P2 计算 ─▶ P3 报告 ─▶ P4 治理 ──G5 换源对拍──▶ P5 签发
```

**跨天/多轮任务**：P0 必须同时建工单 `python tools/ticket.py init --kind 5s-modeling …`，阶段门禁按 M1→…→MI 顺序执行；用户说「继续」时先 `ticket.py resume --thread <id>` 再进 P1。

**规则变更**：改 `rules.yml` / 本文件 / 任一专家 persona，必须 `python tools/policy_check.py bump …` + `notify`，否则在跑工单会按新旧混合规则验收。

**留痕**：G1~G5 的退出码必须写进 `trace_log.py finish --artifact` 的摘要（形如 `G1=0 G2=0 G3=0 G4=0 G5=VERIFIED`），监衡据此判定是否真跑过。


## 2. 实际调度：必须实例化 Orchestrator（控制平面）

编排器（team-lead）在任务启动时 **必须** `require` 并实例化 `sg-orchestrator` 的 `Orchestrator`，全程用它驱动阶段、令牌、闸门、签收：

```js
const { Orchestrator, PHASE_WRITER } = require('skills/sg-orchestrator/assets/orchestrate');
const o = new Orchestrator({ reopenBudget: 2, ledgerPath: 'observed/ledgers/<trace_id>.json' });

// P0 建宪章 + 拿写者令牌（写者=sg-semantic）
o.start({ scope:'本周炼钢成本定额对标', caliber:'L3c', bases:['本部'], confirmed:true });

// 每阶段：校验主责 + 交接令牌 → 跑退出闸门 → 冻结契约
o.enterPhase('P1','sg-development');
const r1 = o.exitPhase('P1', { dataSourceExists:true, srcExists:true, rowCountClosed:true, contractPayload:{rows:21, caliber:'L3c'} });
if (!r1.ok) throw new Error('P1 闸门未全绿：' + JSON.stringify(r1.failed));

// 给 sub-agent 范围上下文（只装 C0 + 本阶段契约，≈5KB，非全量历史）
const scoped = o.handoff(o.ledger.getContract('C1'), 'sg-development');

// ……P2 / P3 / P4 同理，主责依次为 sg-quality / sg-insight / sg-governance……

// P5：仅 sg-supervisor 调用，跑 G5 + 稳定性采样 + 冻结
o.enterPhase('P5','sg-supervisor');
const signoff = o.signOff({ allGreen:true, stableMd5:true, userConfirmed:true, fingerprint, artifactPath });
if (!signoff.ok) throw new Error('P5 签发未通过：' + JSON.stringify(signoff));
```

> 完整 API：`skills/sg-orchestrator/assets/orchestrate.js`（含 `PHASE_EXIT_GATES` / `PHASE_WRITER` / `start` / `enterPhase` / `exitPhase` / `handoff` / `signOff`）。
> 零依赖，Node ≥ 12 可直接 `node -e` 跑通。

## 3. 写者独占（Write-Exclusivity · C-GOV-5）

- 任意时刻产物**只有一个活跃写者**（= 该阶段主责）。`enterPhase(phase, expert)` 校验 `expert === PHASE_WRITER[phase]`，越权进入立即抛错。
- 阶段交接 = 显式 `transferWriter`，**禁止并行编辑同一产物**。
- 仅 P5（sg-supervisor）能把产物标为「最终交付」。

## 4. 防过早发布（Anti-Early-Publish）

- sub-agent（P0~P4）**只能报"阶段完成 / 草案就绪"**，**禁止**使用「定稿 / final / 最终交付」措辞。
- 只有 P5 签收通过（G5 + 稳定采样 + 用户确认）后，编排器才能向用户宣布「最终交付」，**且必须先回显全闸门绿证**。

## 5. 防回溯返工（Anti-Backtrack）

- 契约冻结后不可静默覆盖。P4 发现上游错 → 提 `reopen('P1'|'P2', reason, author)`（带理由）→ 重算 → 下游契约失效重验。
- `reopenBudget` 默认每阶段 ≤ 2 次，超限抛错升级人工裁决（禁无限返工）。
- 任何结论变更必须记 Change Log（`author + reason + before/after`），未登记视为违规。

## 6. 效率与 TOKEN（Fast-Lane + 范围上下文）

- **Fast-Lane**：单指标 / 已知口径查询直接 `route(intent)→'fast'`，走物化 SQL，不建 team、不跑 P1~P4 全链（`skills/sg-orchestrator/assets/fast_lane.js`）。
- **范围上下文**：sub-agent 只收 `buildScopedContext(charter, phaseContract)`（≈0.7KB），不再灌全量历史（≈200KB → ≈1/40）（`scoped_context.js`）。

## 7. 口径锁死（C0 锁死 L3c）

- 口径在 C0 宪章锁死为 **L3c 同域口径**（唯一可加），全程不得切换；切换 = 重开宪章。
- 字段契约固化：`data_L3C.js` 用 `quota/imp/me`，渲染层必须字面一致（`caliber_registry.assertFieldContract` 可机检，旧别名 `quotaW/impact/matchedPC` 直接判 `ok:false`）。

## 8. 落地验收（改造闭环证据）

| 改造项 | 文件 | 自验 |
|---|---|---|
| P0-1 构建管线单一源 | `build/build.js`（本地 `_c0.js` + C-GOV-6 锁 + `--force`） | 两次重建 md5 一致；临时构建 `comparableRows()=21` |
| P0-2 契约台账 | `contract_ledger.js` | hash/令牌/预算/完整性 实跑通过 |
| P1-3 SOP 闸门 | `gates.js` + SKILL.md | G0~G5 + C-GOV-3/4/6 + C-G11 + C28/C29 + D1~D5 |
| P1-4 短路+范围上下文 | `fast_lane.js` + `scoped_context.js` | fast/full 路由正确；上下文 ≈0.7KB |
| P2-5 口径预注册 | `caliber_registry.js` | 旧别名被判 `ok:false`，现字段 `ok:true` |
| **接入实际调度** | 本文件 + `orchestrate.js` | `node -e` 端到端跑通六阶段 + 令牌 + 签收 |

> 本文件与 `orchestrate.js` 配套：本文件是"编排器/总监必读指令"，`orchestrate.js` 是"实际可执行的驱动器"。
> 下次同类任务起手即 `new Orchestrator()`，杜绝"忘了走六阶段"与"各自为政"。
