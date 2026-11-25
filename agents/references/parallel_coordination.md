# 多专家并行协同与产物衔接协议（P6 · 2026-11-03 新增 · 硬协议）

> **缘起**：上一任务 TR-20261103-1926-CD6F 暴露四大反模式——
> ① 砺真 Phase0 做成串行硬卡点，编排器反复 `wait_agent` 空等 45min+；
> ② 并行专家返回自由文本而非 `evidence_package`，编排器手工拼装、产物割裂、下钻数据对不齐；
> ③ 矩衡 61min 才失败、砺真 2h54m 才返回，无硬超时熔断；
> ④ 守钧审查滞后于执行（GATE-2 顺序颠倒），编排器本人直连 DB2。
> 本文件是「扇出 → 扇入 → 合并 → 再派发」的**唯一权威协议**，取代此前的口头习惯。凡涉及 ≥2 路并行的取证/分析，必须先 Read 本文件。

---

## 0. 总原则（不可违背）

| # | 铁律 | 违反后果 |
|---|---|---|
| P6-1 | **并行专家一律先派发不等待**（`delegate_expert` 默认即异步），编排器只做扇入与合并，不阻塞等待单路 | 单路卡死即拖垮全链路 |
| P6-2 | **统一信封**：每个专家必须返回 `data_contract.md` 定义的结构化信封（JSON/YAML），禁止自由文本 | 返回自由文本 → 编排器拒收并令其重发 |
| P6-3 | **单一事实源**：取证落盘 `observed/evidence_<trace>.json`，交付落盘 `observed/data_package_<trace>.json`；下游专家 **读取文件消费，禁止各自重查 DB2** | 下游重查 → 数值分叉、产物割裂 |
| P6-4 | **硬超时熔断**：总扇入窗口 ≤300s（取证）/≤180s（逻辑判定），到时未返回即熔断 + 补派 | 无限等待等同上轮 45min 空等 |
| P6-5 | **GATE-2 顺序**：编译（淬锋）→ 守钧审查放行 → 执行（淬锋执行实例）；编排器本人禁止直连 `mcp__db2__*` | 顺序颠倒 / 直连 → 标 `[治理审查缺失]` |
| P6-6 | **槽位 overlay 归口**：补派产出独立文件后，编排器必须生成 `evidence_resolved_<trace>.json` 合并视图（原始 evidence 保持不可变），下游只读 resolved，禁止直接读 evidence 判定 completeness | 否则「文件已补齐、产物仍标数据存疑」的割裂 |

---

## 1. 扇出（Fan-out）

```
① 同一条消息内并行下发 N 条 `delegate_expert`，禁止串行等待
② 每条 prompt 内嵌：trace_id + 输出 schema（引用 data_contract.md 对应环节字段）+ 格式自检
③ 关键路径标注：physical_lineage / metric_lineage 为「关键路径」；其余为「次要路径」
④ Phase0（砺真逻辑判定）也同样并行派发 + 扇入，不得做串行硬前置卡点
```

**派发模板（强制含 output schema）**：
```
delegate_expert({
  agent_preset: "<sg-xxx>",
  name: "<role>-<trace>",
  prompt: "输入：<自包含前提>；
           输出：<引用 data_contract.md 环节 N 的字段，例如 evidence_package.physical_lineage 结构>；
           格式：JSON（禁止自由文本）；
           自检：返回前确认含 completeness 字段（full|partial|missing）。"
})
```

---

## 2. 扇入（Fan-in · 取代无限 block）

- 启动扇入计时器（取证 300s / 逻辑 180s）。
- 用完成通知 / `list_agents` 核对 N 路状态（**禁止 10s 轮询**），记录已完成结果。
- 窗口到：
  - **全返回** → 进入 §3 合并。
  - **关键路径缺失** → 宽限 60s；仍无 → **触发熔断**：补派替代专家（或编排器内联 + `[专家超时]` 标注），结果回填。
  - **次要路径缺失** → 先合并已有结果，`completeness` 标 `partial|missing`，**不阻塞**后续。
- 🚫 禁止：单次 `wait_agent({timeout_ms})` > 120s；对单个专家反复等待累计 > 300s。
- 🚫 禁止：因某一路未返回而反复 `wait_agent` 累计超过扇入窗口。

---

## 3. 合并（Merge · 解决「产物无法衔接」核心）

- 编排器将 N 路结果按 `evidence_package` 模板组装为一个对象。
- **落盘 `observed/evidence_<trace>.json`**（唯一事实源）。
- 闭合校验：汇总每路 `completeness`；若存在 `missing` 且属关键路径 → 回到 §4 补派；否则标注降级。
- 下游专家（砺真 / 明鉴 / 若溪）**一律消费该文件**，prompt 写明「读取 observed/evidence_<trace>.json，禁止重新查询」。

**合并伪码**：
```
evidence = { trace_id, phase0, gate, physical_lineage, metric_lineage,
             procedure, caliber, domain(可选), completeness:{} }
for each agent_result:
    evidence[slot] = agent_result.body
    evidence.completeness[slot] = agent_result.completeness
write observed/evidence_<trace>.json
if completeness 有 missing(关键): → §4 补派
```

### 3.1 补派产物的槽位 overlay（P6-6 · 2026-11-03 实战补强）

> **实证**：TR-20261103-1926-CD6F 中，矩衡补派产出了独立 `metric_lineage_<trace>.json`（full），但 evidence 主文件里 `completeness.metric_lineage` 仍是 `missing` → 下游（报告 / 裁定 / 数据包）若读 evidence 判定 completeness，会**永远命中「血缘不完整·数据存疑」徽标**，形成「文件已补齐、产物仍存疑」的割裂。另有第二处：矩衡与我判熔断后的兜底文件写了**同一路径**，发生并发覆盖。

| # | 规则 |
|---|---|
| 1 | **原始 evidence 不可变** —— 它是取证快照；改它会让已产出的裁定 / 审计快照产生版本分歧。补派专家 **禁止回写** evidence 主文件，只写自己的独立产物文件 |
| 2 | 编排器在补派返回后生成 **`observed/evidence_resolved_<trace>.json`** = evidence + 以补派独立文件为该槽位权威值做 overlay；同步把 `completeness.<slot>` 置为 `full`；写 `_slot_overlays[]`（source_file / overlay_by / from→to / lineage_mode / maturity / confidence / design_vs_data_partial） |
| 3 | 保留 **`_prior_state`** 历史留痕（原 missing 的原因、fallback_sources、action），审计链不中断 |
| 4 | **下游统一消费 resolved**，禁止直接读 evidence 判定 completeness；`data_package` 亦从 resolved 组装 |
| 5 | **文件命名隔离**：补派一律写 `<slot>_<trace>.json` 或 `<slot>_v2_<trace>.json`，**不覆盖他人已落盘文件**；版本迭代写新文件（v2/v3），不覆盖 v1 |
| 6 | **`full ≠ 口径已校准`**：overlay 后 label 固定为「血缘已证实·口径待校准」；必须携带 maturity=draft、design_vs_data partial 项（如泉州 PROD_DATE）、ODS 字段级 unknown + review_required、逐炉明细不可回溯等 caveat，禁止写成「全部已确认」 |
| 7 | **生成脚本与校验脚本同受事实源约束**（2026-11-03 矩衡 RG-1 实证）：报告生成脚本（含内联 JS 数据注入）**禁止写入未登记来源的行数 / 明细值 / 抽数快照**；校验脚本须以 `evidence_resolved_<trace>.json` 为唯一数值来源，禁止把硬编码串当断言。修复必须「生成脚本 + 已生成 HTML + 由其派生的校验副本」**三处同步**，否则出现「页面已修、脚本回填又打回」的假修复 | 出现「零命中」假象后又被派生脚本污染 |
| 8 | **一次性校验副本用完即弃**（矩衡 RG-1 二次补强）：由 HTML 派生出的 `_check.js` / 快照 / 临时比对副本均为一次性产物，**禁止作为再生成源、回填源或自校验断言源**；修复后必须从已修好的权威产物重新派生或直接丢弃。否则旧副本会把已删除的违规值重新注入 | 出现「页面已修、旧副本又把违规值带回来」的假修复 |

---

## 4. 再协同与重派发（Re-dispatch Loop）

- Merge 后发现某关键环节缺失（如 `metric_lineage` 失败）→ **针对性补派 1 个专家**（非重跑全链路），结果回填 evidence 文件。
- 砺真（Phase 3 裁定）消费完整 `evidence_package`；若 `completeness` 有 `missing` 且影响结论 → confidence 自动降档并标注 `[取证不完整]`。
- 明鉴 / 若溪（Step 8）消费 `data_package.json`；报告下钻数据 `window.__D` 须与 data_package 数值**逐行一致**（交付前比对）。

**再派发的三种触发**：
| 触发 | 动作 | 范围 |
|---|---|---|
| 关键路径熔断 | 补派替代专家（换 name 重试 ≤2 次，看门狗 `MAX_RETRIES` 预算；仍失败则内联 + 标注） | 单路 |
| Merge 发现 missing | 针对性补派该 slot 的专家 | 单路 |
| 下游消费发现数据缺口 | 回到对应上游 slot 补派，回填文件 | 单路 |

> 原则：**永远只补派缺失的那一路，不重跑全链路**——这是压缩耗时的关键。
> 终态判定与降级收尾：子代理 `error / aborted / stalled` 终态由 `scripts/subagent_watchdog.py` 识别并落台账；父会话 dispose 前必须跑 `trace_log.py degrade` 扫描已落盘产物写降级清单（详见 `subagent_dispatch.md`「终态识别 · 错误序列化 · 降级收尾硬规则」）。

---

## 5. 产物连贯性保障（Artifact Coherence）

- 唯二事实源：`evidence_<trace>.json`（取证）+ `data_package_<trace>.json`（交付数据）。
- 任何下游专家的 prompt 必须写明「读取 <文件> 而非重新查询 DB2」。
- HTML 报告下钻数据 `window.__D` 必须与 `data_package.json` 数值逐行一致；交付前 `verify_report.js` 比对。
- 禁止：明鉴、若溪、达仕各自 `DeferExecuteTool(mcp__db2__*)` 取数——它们只消费数据包。

---

## 6. 监衡强制标记（覆盖率）

- 监衡 prompt 必须含：每个 Phase 完成即 `python scripts/trace_log.py mark <step>`。
- 未 mark → `trace_log.py report` 判定 coverage 缺失 → 编排器须补 mark 后方可 `present_files`。

---

## 7. 与既有文件的衔接

- 信封格式：`data_contract.md`（evidence_package / data_package）
- 派发方式：`subagent_dispatch.md`（协议 A/B/C、并行取数、异常矩阵）
- 触发：根因分析（Workflow B）、趋势快线（T2a）、全链路追溯（§11）涉及并行时，本文件优先于上述文件的具体措辞。
