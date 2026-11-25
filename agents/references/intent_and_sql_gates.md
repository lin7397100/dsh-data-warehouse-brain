# 意图与取数五道闸门 · 操作手册（v1.0）

> 来源：借鉴 `dsh-superagent` 原型（双层 Eval / 三事实 / 规则全覆盖 / 工单状态机 / 策略版本）
> 落地日期：2026-11-20｜设计方案：`docs/数仓专家团借鉴superagent优化方案_20261120.md`
> **本文件是规则源，主理人 GATE-0 必读。**

---

## 一、六道闸门总览

```
用户原话
   │
   ├─ GATE-0  gate_route.py            规则闸 → 车道（fast/trend/root_cause/full）
   │
   ├─ 闸门 1  metric_disambiguate.py   指标名消歧（确定性候选 + jev 兜底）
   │             ↓ 写入 IntentContract.entities.metrics
   ├─ 闸门 2  intent_gate.py           意图契约 v2.0 六道门禁（三事实+证据锚+规则全覆盖）
   │             ↓ 通过才允许派发取数
   │
   ├─ 闸门 6  freshness_gate.py        ★ 埋点时点（ETL 抽数 / 过程执行 / 落表 三层埋点）
   │             ↓ 通过才允许下「数据对不对」的结论
   ├─ 闸门 3  sql_static_check.py      第一阶 · 编译期（只读/列存在/除零/NVL/强转/日期）
   │             ↓ 通过才允许执行
   ├─ 闸门 4  sql_result_assert.py     第二阶 · 执行期（行数/唯一/值域/空值率/零值闭合/跨表加性）
   │             ↓ 通过才允许进第三阶
   └─ 闸门 5  sql_cross_source.py      第三阶 · 交付期（跨物理层对拍 + 快照对齐）
                 ↓ VERIFIED 才允许交付
```

**配套**：`ticket.py`（工单级状态机） + `policy_check.py`（策略版本化）

> 🔴 **闸门 6 为什么独立存在（2026-11-20 用户纠正）**：
> `knowledge/kb/ETL抽数日志与存储过程日志_权威区分.md`（铁律级）早就规定「全链路追溯六步：定指标→验血缘→解过程→**查抽数**→**查过程日志**→查落表」，`iron_rules.md` 第 14 条也写「三层埋点缺一不可」。
> 但专家团做 ODS 重算对拍时**三步全跳过**，只比了值、没比时点 → 把「ETL 07:30 后重抽导致的数据变化」误判成「数据错」。
> **结论：值对不对，先问时点齐不齐。**


---

## 二、逐闸门用法

### 闸门 1 · 指标名消歧

```bash
python tools/metric_disambiguate.py --text "<用户原话>"
```

| 退出码 | 含义 | 动作 |
|---|---|---|
| 0 | 全部消歧（gap ≥ 2） | 写入 `entities.metrics`，`confidence` 照抄输出 |
| 4 | 弱消歧（gap = 1） | 可写入，但**必须在 `open_questions[]` 请用户确认** |
| 3 | 存在歧义 | **必须请用户点名**，禁止替用户挑一个 |

**歧义词表**：`knowledge/design/policy/metric_aliases.yml`（料耗 / 铁水耗 / 燃料比 / 单耗 / 成本）

**确定性打分规则**（不依赖模型）：

| 维度 | 命中 | 冲突 |
|---|---|---|
| 厂别（三明/闽光/本部 → 本部；泉州；罗源） | +3 | −3 |
| 工序（炼钢/转炉/炼铁/高炉/烧结…） | +2 | — |
| 期间（近N日 → 日平均；月平均；年） | +2 | −3 |
| 子单元（1#/2#/高炉/转炉/一炼/二炼…）而文本未点名 | — | −2 |
| 名称短（≤20 字） | +1 | — |

### 闸门 2 · 意图门禁

```bash
# 先由 sg-query-router 产出 observed/intents/<TR>.intent.json（v2.0）
python tools/intent_gate.py --contract observed/intents/<TR>.intent.json
```

**六道门禁**（任一失败 exit 1，禁止取数）：

| 门 | 规则 |
|---|---|
| G1 | `direction_settled=false` → `decision` 只能 `ignore`/`stop` |
| G2 | `intent_strength=not_admitted` → 禁止 `decision=accept` |
| G2b | `accept_mode` 与 `intent_strength` 必须相容（observe + inferred 只能 would-accept） |
| G3 | `decision=accept` 时 `matched=true` 规则数必须 ≥ 1 |
| G4 | `rule_assessments` 必须**逐一覆盖** `rules.yml` 全部启用规则；未知/重复 ID 驳回；负判也要写 reason |
| G5 | 三条 `evidence_quote` 必须能在 `raw_query` **原文命中**（防编造证据） |
| G6 | `conflicts` 非空 → 只能 `ignore` |

**规则清单**：`knowledge/design/policy/rules.yml`（7 条：趋势/根因/即席/5S/指标体系/物化/对标）

### 闸门 3 · SQL 第一阶（编译期）

```bash
python tools/sql_static_check.py --sql artifacts/compiled/q_<TR>.sql
```

| 检查 | 判定 |
|---|---|
| S1 只读 | INSERT/UPDATE/DELETE/… 任一出现 → **ERR** |
| S2 禁止 `SELECT *` | → **ERR** |
| S3 表解析 | 未在列字典 → WARN（`--strict-tables` 时 ERR） |
| S4 别名限定列存在性 | 不存在 → **ERR** |
| S5 除零保护 | `/` 未被 DECODE/NULLIF/CASE 包裹（**括号栈判定**）→ **ERR** |
| S6 顶层聚合空值兜底 | 未包 NVL/COALESCE → WARN |
| S7 VARCHAR 强转清洗 | `CAST(… AS DECIMAL)` 无 NULLIF/TRANSLATE/TRIM → **ERR** |
| S8 日期字面量 | 仅对**日期列比较处**校验 8 位（不把 ZB_CODE 当日期）→ **ERR** |
| S9 比率复算自检 | 算了比率却未同时取分子/分母 → WARN |

**列字典**：`knowledge/corpus/docs/K1_表结构语料.md`（95 表）+ `knowledge/observed/schema/表列模型-2026-09-02.json`（86 表语义角色）。`--schema-json` 可补。

### 闸门 4 · SQL 第二阶（执行期）

```bash
python tools/sql_result_assert.py --result observed/data_package_<TR>.json \
                                  --spec knowledge/design/policy/assert_spec_<TR>.json
```

八类断言：`rowcount` / `unique` / `domain` / `value_range` / `null_rate` / `all_equal` / `zero_ratio` / `cross_sum`（跨表加性闭合）。

### 闸门 6 · 埋点时点（全链路追溯）★

```bash
python tools/freshness_gate.py --probe knowledge/design/policy/probe_<TR>.json
python tools/freshness_gate.py --template      # 打印探针模板
```

**权威源**：`knowledge/kb/ETL抽数日志与存储过程日志_权威区分.md`（铁律级）

| 检查 | 内容 | 权威对象 |
|---|---|---|
| **F1 ETL 抽数齐备** | 每个 ODS 表至少 1 条抽数记录且成功 | `SMBB_M_A_CS01.V_PUB_JOB_LOGS_LD_1D_X`（用 `DES_OBJECT_NAME` 过滤，**不是** `SRC_OBJECT_NAME`） |
| **F2 过程执行齐备** | 过程至少 1 条且 `IS_SUCCESSFUL='T'` | `<CREATER_SCHEMA>.T_PUB_JOB_LOGS`（schema 必须与指标 CREATER 一致） |
| **F3 落表时间齐备** | DWS 表有 `LOAD_TIME` / `REC_CREATE_TIME` | 目标表 |
| **F4 时点有序 + 落后告警** | 过程必须在落表前结束；**落表后 ODS 又抽数 → DWS 快照落后** | 三层时间线 |
| **F5 跨源可比性** | 对拍源 `snapshot_key` 必须一致 | 见闸门 5 |

**退出码**：0 通过 ｜ 1 缺埋点/时序倒挂（**禁止下结论**）｜ 6 跨源不可比 ｜ 2 输入错误

**两条禁令**：
1. ❌ **禁止**只查存储过程日志、不查 ETL 抽数日志（两套日志回答不同问题：**过程日志答「跑成功了吗」，ETL 日志答「数据抽全了吗」**，混用必漏）
2. ❌ **禁止**在 F4 报「落表后 ODS 又抽数」的情况下，把 DWS 与当前 ODS 的差异判成数据错

**本次实测输出（TR-20261120-1046）**：

```
[WARN] F4 ⚠ 落表 2026-11-19 07:35:03 之后 ODS 又抽数 2 次（最晚 2026-11-19 12:09:12）
       → DWS 快照已落后于 ODS，两者不可直接比，差异不等于数据错
[FAIL] F5 跨源不可比：snapshot_key 不一致 ['D-20261119', 'LIVE-20261120T1720']
裁定：⏳ 跨源不可比 → 禁止判数据对错
```

---

### 闸门 5 · SQL 第三阶（交付期换源对拍）v2.2

```bash
python tools/sql_cross_source.py --spec knowledge/design/policy/recon_<TR>.json
```

| 裁定 | 退出码 | 含义 |
|---|---|---|
| `VERIFIED` | 0 | 全部**可比且独立**的信源在容差内一致 → 可交付 |
| `SOURCE_CONFLICT` | 5 | 多数层一致，存在离群信源 → 保留多数结论，**点名**离群源单独复核 |
| `DRIFT` | 1 | 无法形成多数（如 2 源各执一词）→ **禁止交付** |
| `INSUFFICIENT` | 3 | 可比独立信源 < 要求层数 → **不得声称已核验** |
| `NOT_COMPARABLE` | 6 | **存在快照时点不同的信源** → 时间不可比，**不算漂移** |

#### 🔴 第一原则：先问「是不是同一个快照」，再问「值差多少」

> 业务事实源：`knowledge/design/policy/data_freshness_rules.md`
> **ODS 是活数据**：每日 07:30 早会后开始抽数，**当天反复重抽多次**；DWS 是 07:35 那一刻的快照，**装载后不再跟随 ODS**。
> 所以「DWS vs 当前 ODS」的差异是**必然**的，**不是数据错误**。

| 规则 | 实现 |
|---|---|
| **快照标识** | 每源必带 `snapshot_key`（逻辑快照名，如 `D-20261119` / `LIVE-20261120T1720`）。报表由 DWS 日结算派生 → **同 key** |
| **活数据降级** | `ODS` / `RECOMPUTE` 层未给 `snapshot_key` → 自动降 **`advisory`（参考位）**，**不计入独立层数** |
| **不可比裁定** | `snapshot_key` 不同 → **`NOT_COMPARABLE`**（exit 6），**不判漂移** |
| **精度感知** | 容差 = `(quantum_a + quantum_b)/2`。报表 1 位（0.1）对 DWS 2 位（0.01）→ **0.0525**；用统一 0.005 比报表**必然误判** |
| **多数票定责** | ≥3 个可比源时，多数一致 + 权威序兜底 → **点名离群源**；2 源不一致时直接 `DRIFT`（无法定责） |

**权威序**：`REPORT/ADS/GOLDEN(1) > DWS/DWD(2) > ODS/RECOMPUTE(3)`。

**同源镜像必须剔除**：`T_ADS_DIM_GZ01.SQL1` 的源表就是 `T_DWS_FACT_ZZGZ_LG01`，**不算独立层**。脚本按 `layer` 去重。

> ⚠️ **两次误判复盘（TR-20261120-1046）**
> - **v2.0**：只有 DWS + ODS 两源，不一致即判 `DRIFT`，**没指名谁错** → 冤枉 DWS
> - **v2.1**：加了管制报表做多数票，判 `SOURCE_CONFLICT`（离群=ODS）→ **方向对了，但仍把 ODS 当独立信源**
> - **v2.2**：引入 `snapshot_key` 快照对齐 → ODS 判 `NOT_COMPARABLE`，三指标全 **`VERIFIED`**（报告正确）
>
> **核心教训：跨层对拍的第一道检查不是「值差多少」，而是「是不是同一个快照」。时点不同，比出来的差异没有意义。**



---

## 三、工单状态机（跨天续接）

```bash
# 建单（11 步 5S 建模 / 5 步四级指标体系）
python tools/ticket.py init --kind 5s-modeling --title "钢铁料耗指标建模" \
    --scope "三明闽光·炼钢·钢铁料耗" --intent-strength explicit --rules R-5S-MODELING

# 推步（前置未完成 → 门禁拒绝，exit 1）
python tools/ticket.py step --ticket MT-<id> --id M3 --status running
python tools/ticket.py step --ticket MT-<id> --id M3 --status ready --artifact "BEDF52 截图"

# 查看 / 续接 / 列表
python tools/ticket.py show   --ticket MT-<id>
python tools/ticket.py resume --thread <thread-id>
python tools/ticket.py open
```

**七阶段**（照搬 superagent）：`person/delivery` `person/answer` `person/review` `person/blocked` `person/failed` `working/queued` `idle` `working`
**报告六态**：`progress` `waiting` `ready` `blocked` `failed` `dropped`

**三条硬规则**：
1. Ticket 定义自己的状态，**不跟 Executor 走**（换专家/重启都不影响）
2. 只有最终报告 `ready` 能结束工单，中间 `progress` 不算完
3. Subscription 续接：同一线程后续消息自动路由回同一工单

### 跨会话续接（P2）

```bash
# 绑定：线程 ID + 关键词 → 工单
python tools/ticket.py bind --ticket MT-<id> --thread <thread-id> --keywords "钢铁料耗,5S建模"

# 路由：给一条新消息，判断是否续接某个未结束工单（exit 0 命中 / 1 未命中）
python tools/ticket.py route --text "继续钢铁料耗的5S建模，第4步"
```

**实现边界（如实说明）**：DSH 当前**不暴露跨会话线程路由**，因此「续接」是**关键词相似度 + 未结束工单优先**的确定性匹配，不是真正的 Session 级订阅。
- 命中（score ≥ `--min-score`，默认 2）→ 返回工单 + 下一待办步骤
- 未命中 → 走新任务
- **误命中风险**：同一领域多个在跑工单时可能串单 → 命中后**必须**在回复里回显工单号与范围，让用户核对


---

## 四、策略版本化

```bash
python tools/policy_check.py show      # 当前版本 + 变更清单
python tools/policy_check.py check     # 在跑工单是否落后（exit 4 = 需 notify）
python tools/policy_check.py bump --version 2026.11.21-1 \
    --rule R-ROOT-CAUSE --from "旧规则" --to "新规则"
python tools/policy_check.py notify    # 向落后工单投递 policy-changed
```

**放权阶梯**（`rules.yml` 的 `accept_mode`）：

| 模式 | 自动物化 | 自动建模 | 改规则 |
|---|---|---|---|
| `off` | ❌ | ❌ | ❌ |
| `observe`（默认） | dry-run + 报告，人工确认后写库 | 只出草稿 | 只出 diff |
| `auto` | 金标准回归 >95% 且用户明确开启 | 同左 | **永不允许** |

---

## 五、回归测试（改包后必跑）

```bash
python scripts/test_intent_gate.py       # 8 用例（1 正 7 反）
python scripts/test_sql_static_check.py  # 7 用例（1 正 6 反）
python scripts/test_sql_gates.py         # 9 用例（3 正 6 反）
python scripts/verify_dsh_sync.py        # 包一致性 exit 0
python scripts/smoke_test.py             # 55/55
```
