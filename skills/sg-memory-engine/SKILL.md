---
name: sg-memory-engine
description: "三钢数仓智脑：记忆与技能进化引擎。每日 0:00 增量/全量构建本体建模/语义层/指标体系；对话记忆每日备份 WeKnora 记忆知识库；对反复流程与问数自动生成技能；将每个派生/复合指标的业务 SQL 独立封装为单个技能；大数据指标预编译结果存 WeKnora；维护技能清单，用户问数优先调用既有技能直出结果。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, memory, evolution, automation, weknora]
owner: sg-memory
---

# sg-memory-engine · 记忆与技能进化引擎

## 定位

专家团的"自进化中枢"。把**构建、记忆、技能、缓存**四件事编排成每日可复跑的闭环，使系统越用越准、越用越快。

## 每日 0:00 定时构建（incremental / full）

由自动化（recurring, 00:00）触发，编排各组件：

| 组件 | 编排对象 | 引擎/动作 |
|---|---|---|
| 本体建模 | `sg-ontology` 鼎元 | `sg-ontology-asset-bootstrap` / `sg-ontology-modeling`（增量：仅新资产；全量：周期末） |
| 语义层 | `sg-semantic` 铨度 | `sg-semantic-batch-register` / `sg-semantic-layer` |
| 指标体系 | `sg-metric-builder` 矩衡 | `sg-indicator-system/engine/import_gz01.py`（重固化全量指标 + 物化 SQL） |

构建前做**双轨变更检测**（元数据扫描 vs 设计态），冲突升级编排器裁决；构建后写回归报告并推送（只推送不合入）。

## 对话记忆备份 WeKnora 记忆知识库

- 整理当日用户对话为结构化 Markdown（问答 / 决策 / 未决项 / 偏好）。
- 落本地 `knowledge/observed/memory/对话记忆_YYYY-MM-DD.md`（权威基线）。
- 同步 WeKnora：**数仓智脑专家团记忆知识库**（`kb_id=c6e2d1ef-bed2-4356-b89b-d3bcd1ba377d`，连接器 `mcp__weknora-admin__`）：每日记忆以单条知识条目写入，标题 `MEM-记忆-YYYY-MM-DD`，正文为结构化 Markdown，`status="publish"` 即时建索引：
  `create_knowledge_from_text(kb_id="c6e2d1ef-bed2-4356-b89b-d3bcd1ba377d", title="MEM-记忆-YYYY-MM-DD", content=markdown, status="publish")`。
- 检索回灌：会话需要时经 `hybrid_search(kb_id="c6e2d1ef-bed2-4356-b89b-d3bcd1ba377d", query=...)` 召回相关记忆注入上下文。
- **脱敏**：账号/口令/内部 IP 不写出外部。

## WeKnora 写入降级与补同步（L2/L3 · 2026-10-30 新增）

> 本技能是 WeKnora 写入主责（记忆 / 台账 / 业务规则 / 预编译）。完整编排器侧规范 → `agents/references/weknora_fallback.md`。

**写入失败（WeKnora 不可达）→ 绝不丢弃**
- 所有待同步内容（`MEM-记忆-*`、`LEDGER-*`、`RULE-定额-*` / `RULE-分摊-*`、`PRECOMP-*`）先落本地暂存：
  `knowledge/observed/pending_sync/<YYYYMMDD-HHMM>-<title>.md`，并登记索引 `_pending_index.json`
  （字段：`target_kb_id` / `title` / `file` / `content_hash` / `status`=`pending` / `created_at`）。
- 本地权威基线不变且**立即可用**：`knowledge/observed/memory/`（记忆）、`knowledge/design/rules/`（N5/N7 规则，**落盘后本次会话直接解析执行，用户上传即生效**）、`knowledge/design/ledger/`（台账）。
- 会话内提示进入降级模式；trace 记 `weknora_status=down` + `pending_sync=N`；交付文本「数据限制」段必须披露。

**恢复后补同步**（用户说"补同步"/"同步 WeKnora"触发，或每日 0:00 构建自动尝试）
1. 读 `_pending_index.json` 筛 `status=pending`；
2. 逐条 `create_knowledge_from_text(kb_id=记录.target_kb_id, title=记录.title, content=<文件正文>, status="publish")`；
3. **幂等防重**（关键）：先按标题 `hybrid_search` / `list_knowledge` 查是否已存在 → 已存在改用 `update_knowledge_from_text(knowledge_id, content)`，**禁止产生重复条目**；
4. 成功标 `status=done` + `synced_at`；失败保留 `pending` 并告警，下次重试。

## 自动生成技能（用户偏好进化）

监测信号触发 `sg-skill-evolution`（衍薪）固化技能：
- 反复执行的流程（同类型操作 ≥3 次）→ 领域技能。
- 反复问数的问题（同问数意图 ≥3 次）→ 问数技能（封装 DSL + 物化 SQL 调用）。
- 生成后登记进 `knowledge/design/skill_inventory.json` 并通知编排器。

## 指标 → 单技能封装（派生/复合）

对每个 `level ∈ {derived, composite}` 指标，将其业务 SQL 独立封装为单个技能：
- 技能名 `ind-<ZB_CODE>`（如 `ind-2000514`）。
- 内容：指标定义、`materialized_sql/<ZB_CODE>.sql` 路径、调用方式（直查 `sg-materialized-sql`）、口径卡模板。
- 批量封装脚本：`skills/sg-indicator-system/engine/encapsulate_indicator_skills.py` → 生成到 `skills/ind-<ZB_CODE>/`。
- 用户问数命中该指标时**优先调用既有 `ind-<ZB_CODE>` 技能直接执行**，不再走编译。

## 大数据指标预编译 → WeKnora

- 对数据量大/计算重的指标（全厂日报、跨期累计），由定时任务预跑一次，结果 + 口径卡以单条知识条目写入 WeKnora「数仓智脑专家团记忆知识库」（`kb_id=c6e2d1ef-bed2-4356-b89b-d3bcd1ba377d`），标题 `PRECOMP-指标名-YYYY-MM-DD`，`status="publish"` 即时建索引。
- 问数直接取缓存秒级返回；标注有效期，次日刷新。
- 适用标准：单次查询 > 阈值（如扫描行 > 1000 万）或计算链路 ≥ 3 层。
- 检索复用：经 `hybrid_search(kb_id="c6e2d1ef-bed2-4356-b89b-d3bcd1ba377d", query=指标名)` 召回预编译结果，命中即返回，避免重算。
- 若预编译条目增长过快影响记忆检索精度，可拆分至独立 KB「数仓智脑专家团预编译指标」（按需创建）。

## 知识缺口闭环（N5 定额 / N7 分摊规则）

当成本域功能在**既有来源全部缺失**时，走"通知→上传→同步→重跑"闭环，而非静默失败或编造：

**判定顺序（任一处命中即跳过闭环）**
1. DB2 实查（`mcp__db2__execute_sql`）：定额表 / 分摊规则表是否存在；
2. WeKnora 域库检索：`hybrid_search` 命中「数仓智脑专家团-业务规则」(`kb_id=6838e00b-fb8e-4de3-9f08-425af71dbdbd`) 或「指标体系」(`227f0a01-c36b-488a-8049-5b5869175782`)；
3. 本地文档知识库（`knowledge/` 下既有文档，含 sg-cbprod-warehouse 口径手册）。

**N5 定额源**
- 先 `mcp__db2__execute_sql` 实查定额主数据（ZB_CODE / 定额值 / 生效期）；有则直接对标。
- 三者皆缺 → **会话内明确告知用户**："未检索到 <指标名> 定额标准，请上传定额文档（Excel/PDF/制度文档，需含指标码 + 定额值 + 生效期），上传后我将同步至 WeKnora 业务规则库并重跑对标。"
- 用户上传后：本地解析抽取文本（docx/xlsx/pdf 走对应解析），调用
  `create_knowledge_from_text(kb_id="6838e00b-fb8e-4de3-9f08-425af71dbdbd", title="RULE-定额-<指标名>", content=<抽取文本>, status="publish")`；
- 同步完成 → 重跑 N5，`hybrid_search` 命中新条目即出对标结果。

**N7 分摊规则**
- 触发条件：业务规则库 + 指标体系库 + 本地文档 + DB2 **四源皆缺**。
- 会话内告知用户上传分摊规则文档（含分摊对象 / 动因 / 公式 / 适用范围）。
- 上传后同步：`create_knowledge_from_text(kb_id="6838e00b-fb8e-4de3-9f08-425af71dbdbd", title="RULE-分摊-<名称>", content=<抽取文本>, status="publish")`。
- 重跑 N7 分摊自洽校验（`sg-cbprod-warehouse` 6 铁律 + 新同步规则比对）。

**约束**
- 仅缺口时触发，已有命中路径零侵入、不降级。
- 上传文档可能含敏感口径 → 抽取时脱敏（账号 / 口令 / 内部 IP 不写外部）。
- 同步失败 / 连接器不可用 → 回退本地 `knowledge/` 暂存并告警，不阻断主流程。

## 技能清单维护

`knowledge/design/skill_inventory.json` 每项：`id / name / trigger / source / type / last_used / call_count`。
- 用户提问先**检索清单**：命中既有技能 → 直接调用（最高优先级）；未命中 → 常规链路（解析→编译/物化直查/即席构建）。
- 周期性清理长期零调用的试验性技能（标记 `deprecated`，不物理删除）。

## 与智能问数的衔接（优先级）

```
用户问数
  → ① 查 skill_inventory.json：命中 ind-<ZB_CODE> 或领域技能 → 直接调用（秒级）
  → ② 查 indicator_registry.json：命中 → sg-materialized-sql 物化直查
  → ③ 仅语义层注册 → sg-dsl-compiler 实时编译
  → ④ 完全未注册 → sg-adhoc-indicator 即席构建（首查较慢，二次命中转直查）
```

## 运行命令（手动/自动化均可）

```bash
# 指标体系重固化
cd skills/sg-indicator-system && python engine/import_gz01.py
# 派生/复合指标单技能封装（批量）
python engine/encapsulate_indicator_skills.py --out 。/。/skills --min-level derived
```

## 注意事项

1. **记忆只增不删**：对话记忆与技能清单为累计资产，过期仅标记。
2. **既有技能优先**：命中即直调，禁止重复编译已封装指标。
3. **WeKnora 为可检索副本**：本地 `knowledge/` 权威基线，WeKnora「数仓智脑专家团记忆知识库」为可 RAG 检索的共享副本（经 `hybrid_search` 召回）。
4. **自动化幂等**：每日构建可重复，增量合并不覆盖历史；失败告警并保留上一成功态。
5. **敏感信息不落外部**。
