# 统一降级决策树（P2.3 修复 · 2026-11-03 新增）

> 编排器遇到任何降级场景时，查询本决策树确定处理路径。不再需要在多个文件中查找。

---

## 决策树

```
异常/降级场景
│
├─ WeKnora 不可达
│   ├─ L1: hybrid_search 探测（≤8s 超时） → 成功则正常走
│   ├─ L2: 读本地 knowledge/kb/ + sg-cbprod-warehouse v2.0 + T_ADS_DIM_GZ01 实表
│   └─ L3: 输出「知识库不可达，以下是 DB2 实表直查结果」
│          → maturity=indexed, confidence≤0.70, 披露「未经语义层校验」
│
├─ 口径未注册（T_ADS_DIM_GZ01 未命中）
│   → caliber_check.md L1→L5 五级回退链：
│     L1 GZ01已注册 → L2 血缘文档命中 → L3 知识库命中 → L4 指标新建 → L5 无法构建
│
├─ 血缘断链（SQL1为空/CREATER取不到）
│   → lineage_fallback.md 正向建模：
│     S1 用户业务规则 → S2 weknora K4 → S3 weknora K7 → S0 本地5s/
│     → sg-metric-builder 正向建模 → 标注 [正向建模·待实据核验]
│
├─ 数据可能未就绪
│   → data_ready_gate.md G1→G2→G3 三层门禁
│     结论：真异常|未就绪|半批次|重跑覆盖|补数缺失|口径错
│     非「真异常」→ 终止，不进入归因
│
├─ sg-governance 不可用（派发失败/超时）
│   → subagent_dispatch.md 硬拦截降级：
│     ① 记录失败原因到 trace
│     ② 编排器自行执行四层护栏（SELECT-only/敏感表/权限/审计）
│     ③ 交付文本显式声明「⚠ sg-governance 未响应，四层护栏由主理人代执行」
│
├─ Agent 派发超时（>60s）
│   → subagent_dispatch.md P4.1 异常处理矩阵
│     重试1次 → 仍失败：找替代专家 → 无替代：内联+标注 [专家不可用·内联代执行]
│     confidence ×0.7~0.8
│
├─ 上下文接近 100K tokens
│   → team-lead.md 上下文预算护栏 + P4.2 溢出恢复：
│     ① 前15轮压成状态纪要
│     ② 写 recovery.json 到 observed/
│     ③ 通知用户新会话续作
│
├─ 部署不同步（DSH 单向发布）
│   → team-lead.md 部署校验 标准动作序列：
│     verify_dsh_sync.py → --apply（发布）→ verify_dsh_sync.py 复核 → 重启会话
│     （旧 WorkBuddy 双副本序列 validate → register → sync_expert_cache → --verify 已废弃）
│
└─ 用户追问
    → team-lead.md P4.3 用户追问 trace 边界：
      同一 ZB_CODE → 同一 trace（Phase 0 重新判定）
      不同 ZB_CODE → 新 trace（重新 GATE-0→GATE-1）
      补充细节 → 同一 trace（Phase 1 补充取证）
```

---

## 降级记录规范

每次降级必须在 trace 中记录：
```json
{
  "fallback": {
    "trigger": "weknora_unreachable|agent_timeout|...",
    "chain": ["L1_failed", "L2_fallback"],
    "final_resolution": "L2_local_kb",
    "confidence_impact": 0.9,
    "disclosure": "已在交付文本中披露"
  }
}
```