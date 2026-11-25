# GATE-Q · P0 前置意图理解门禁（query-router）

> 生效：2026-11-15 ｜ 引用契约：`skills/sg-query-router/SKILL.md` + `references/intent_contract_schema.md`
> 主理人 SOP 的 P0 宪章之前，必须完成本门禁。目的：主理人不直接理解 NL，先由辨枢编译为意图契约。

## 一、门禁位置（插入六阶段 SOP）

```
用户 NL 请求
  → [GATE-Q] 派发 sg-query-router 产出 IntentContract  ← 新增前置
  → GATE-0 健康自检 → GATE-1 init(task_type/lane/fast_lane/materialization_status 来自契约)
  → P0 宪章(sg-semantic) →G0→ P1 取数 →G1→ P2 计算 →G2→ P3 报告 →G3→ P4 治理 →G4→ P5 签发
```

## 二、GATE-Q 强制动作（不可跳过）

```
① 主理人派发（不内联）：
   delegate_expert({
     agent_preset:"sg-query-router", name:"qr-<trace_id>",
     prompt:"把以下 NL 请求编译为 IntentContract JSON（schema 见 skills/sg-query-router/references/intent_contract_schema.md）。
             输入：<用户原始 NL 全文>。产出契约落盘 <workspace>/traces/<YYYYMMDD>/<trace_id>.contract.json，
             返回：契约文件路径 + 4 关键字段(task_type/fast_lane/materialization_status/route.chain 长度)"
   })
   → 立即返回 name；wait_agent({timeout_ms:180000}) 取回执（timedOut=false 才采信）
② 校验契约（监衡硬规则）：
   - 三字段 task_type + fast_lane + materialization_status 齐全？缺 → 驳回重派
   - route.chain.length ≥ 3？否 → 驳回（多专家协同铁律）
   - domain=cost 但 kb_required 不含 sg-cbprod-warehouse？是 → 驳回
   - entities.factory=需澄清 且 任务型≠Q1 裸查？是 → 先向用户确认基地
③ 用契约字段驱动 GATE-1 init（禁止主理人另行判型）
④ 车道路由：
   - materialization_status=materialized/partial → 快车道（秒级/分钟级，复用 fast_lane_response.md）
   - unmaterialized/no_registry → 慢车道（专家团编译 SQL，出口进 sg-sql-materialization 物化闭环）
   - is_root_cause=true → 根因 Workflow B（多专家并行取证）
```

## 三、跳过后果
| 第N次跳过 | 后果 |
|---|---|
| 首次 | 交付顶部红色告警："⚠ 本次跳过 GATE-Q 意图理解，路由为主理人内联推断" |
| 二次 | 强制补做契约编译后重派 |
| 三次 | 触发 sg-skill-evolution 改写为 GATE-0 前置脚本硬断言 |

**唯一豁免**：纯对话/闲聊（不取数、不出报告、不派发子 Agent）。快车道**不豁免** GATE-Q。

## 四、与其他门禁的关系
- GATE-Q 产出的 `task_type/fast_lane/qt_level` 直接填入 GATE-1 `trace_log.py init` 参数，**不得二次判定**。
- GATE-0.5 KB-First 的检索指令由契约 `domain.kb_required` 驱动（成本域必带 sg-cbprod-warehouse + CBPROD 知识库）。
- GATE-2d DSL 先行的取数需求描述来自契约 `entities[]`，不再由主理人复述口语。
