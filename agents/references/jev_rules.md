# jev 小模型判定闸 · 规则权威源（v1.6）

> 适用：主理人冶衡与快问（dwb-fast-ask）。jev 只做**判定/建议**，不出数、不写回注册表。
> 端点：`http://10.233.2.32:11434/v1/systemone`，模型 `tev1:4b-32k`（4.3B / decision 能力）。环境变量 `JEV_URL` / `JEV_MODEL` 可覆盖。
> 实测（2026-11-18 本机 → 服务器，5 次取样）：单问 0.67–0.94 s；8 候选长名 1.7 s；首次冷启约 7.5 s；600 字长文 1.8 s。

## 1. 脚本与预置

| 脚本 | 作用 | 调用方式 |
|---|---|---|
| `tools/jev_router.py` | 规则闸 + jev 融合判型（五车道） | `python tools/jev_router.py --text "<原话>" --format text` |
| `tools/jev_query.py` | 单预置结构化判定（choice/score/noul） | `python tools/jev_query.py --preset <预置> --state "<原文>" --text` |
| `tools/jev_pick.py` | fast_ask 多候选定案 | `python tools/jev_pick.py --text "<原话>" --from-fastask <json 路径>` |
| `tools/jev_eval.py` | 改口径后复评 | `python tools/jev_eval.py --task quality\|rootcause` |

`jev_query.py` 预置：`intent`（五意图）/ `urgency`（是否紧急 noul）/ `emotion`（情绪档位 score）/ `quality`（五维质量）/ `rootcause`（五类根因）/ `domain`（业务域，仅建议）/ `level`（atomic/derived，**禁用**）。

## 2. 融合矩阵（规则优先，jev 只兜底/升级；jev 无权越过 HEAVY）

| 规则闸结论 | 是否问 jev | jev 可做什么 |
|---|---|---|
| fast / trend | 不问（规则已定，省一次往返） | — |
| root_cause | 不问（已是慢车道） | — |
| full 且含 HEAVY 词 | 不问（对标/各工序/报告类，jev 无权降级） | — |
| full 且无 HEAVY 词（兜底态） | **问** | 单指标→降 fast；趋势→降 trend；归因→升 root_cause；其余保持 full |

采纳阈值：choice `confidence ≥ 0.85`；低于则**弃权**，保持规则结论。jev 不可达（exit=4）→ 直接退回规则结论，禁止凭印象判型。

## 3. 各预置采纳门槛与用途

| 预置 | 门槛 | 用途边界 |
|---|---|---|
| intent（jev_router） | conf ≥ 0.85 | 仅做车道降级/升级；HEAVY 词一票否决降级 |
| urgency | P(急) ≥ 0.80 | 进流程前排优先级，不替代人工排班 |
| quality（五维） | conf ≥ 0.60 · **仅建议位** | 列出 top2 与概率，标「jev 建议，需人工确认」；不得据此关工单 |
| rootcause（五类） | conf ≥ 0.70 · **仅建议位** | 同上；双解工单过信率高，不得单独充当根因结论 |
| emotion | score 档位 | 辅助沟通语气，不进判定闸门 |
| domain | conf ≥ 0.80 · 仅建议 | 实测 80%，必须披露「jev 建议，需人工复核」，不得直接写注册表 |
| level（atomic/derived） | **禁用** | 实测 30 条真值仅 40% 准确 |

## 4. 八条不可逾越（违反任一条等同编造）

1. **含 HEAVY 词的请求，jev 无权降级**（对标 / 本周 / 各工序 / 各基地 / 报告 / 汇总 / 分析…）。脚本已内建，禁止绕过。
2. 网络不可达（脚本 exit=4）→ **退回规则结论**，禁止凭印象判型。
3. 问题没指定编号而候选全带编号（1#/2#/5#…）→ **必须请用户点名**，不得替用户挑一个炉子。
4. 编号不存在（如 9#）→ 直接弃权，**不得改答别的编号**。
5. 指标级别 atomic/derived 预分类**禁用**。
6. 业务域预分类只作建议：必须披露「jev 建议，需人工复核」，不得直接写入注册表。
7. jev 只判定、不出数：取数仍只走 `fast_ask.py` → 物化 SQL → `mcp__db2__execute_sql`。
8. **quality / rootcause 只进报告不上闸**：必须把 top2 与概率一并列出并标「jev 建议，需人工确认」，不得据此关闭工单、不得写回注册表、不得单独充当根因结论。

## 5. 确定性预检（GATE-0 必跑）

每轮含取数/分析/派发的任务，第一步先跑融合路由（规则 + jev，落盘路由 JSON）：

```
python tools/gate_route.py --text "<用户原话>" [--date YYYYMMDD] [--trace-id <TR-...>]
```

- 输出 JSON：`lane / task_type / fast_lane / source(rules|jev) / agreement / confidence / signals / reasons / next`。
- `lane=fast` 且 `source=jev` 或规则直判 fast、`conf≥0.85` → 可走快车道 `fast_ask.py`，**无需**先派辨枢出契约；否则按 GATE-Q 派辨枢。
- 路由结果写入 `observed/routes/<trace_id>.json`，供面板与监衡留痕。

## 6. 专家侧 jev 接线（建议位 · 2026-11-18）

主理人 GATE-0 用 `gate_route.py` 做确定性判型；以下专家在各自环节用 `tools/jev_query.py` 做**辅助判定**，全部受第 4 节八条禁令约束，jev 只建议、不出数、不写回注册表。

| 专家 | 预置 | 环节 | 边界 |
|---|---|---|---|
| sg-quality 砺真 | `quality`（五维，conf≥0.60）/ `rootcause`（五类，conf≥0.70） | 质量归类、根因预判 | 仅建议位；列 top2+概率并标「jev 建议，需人工确认」；不得据此关工单、不得单独充当根因结论 |
| sg-query-router 辨枢 | `intent`（conf≥0.85）/ `urgency`（P≥0.80）/ `emotion`（语气辅助）/ `domain`（conf≥0.80） | 意图契约编译前的辅助判型 | intent 与规则闸交叉验证；urgency 仅排优先级；emotion 不进闸门；domain 须披露「需人工复核」；`level` 禁用 |
| sg-supervisor 监衡 | `quality` / `rootcause` | 旁路抽检专家结论 | 低置信或与专家结论冲突时记档复核；不替代人工结论 |

CLI：`python tools/jev_query.py --preset <预置> --state "<原文>" --text`；jev 不可达（exit=4）退回大模型研判。
