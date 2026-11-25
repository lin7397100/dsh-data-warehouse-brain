# WeKnora 不可访问降级预案（三级 · 2026-10-30 新增）

> **定位**：WeKnora 是当前方案的单点依赖（记忆备份 / N5-N7 规则同步 / 降本台账 / 预编译缓存 / KB 检索主通道）。本文件定义其**不可访问时的降级与恢复补同步**规范。
> **铁律**：命中降级**必须 Read 本文件**再执行；禁止静默降级、禁止编造数值、禁止因 WeKnora 不可用而丢弃用户已上传的文档。

---

## 0. 连通性探测（前置 · 每次 KB 检索 / 每轮任务开始）

| 步骤 | 动作 |
|---|---|
| ① 探测 | 对目标 kb 执行一次轻量 `hybrid_search(kb_id, query="口径", match_count=1)`，短超时（≤8s）。 |
| ② 判定 | 正常返回（有结果或空结果但**无报错**）→ **L1 主通道**；报错 / 超时 / 连接拒绝 → **L2 降级**。 |
| ③ 留痕 | 写入 trace：`weknora_status` = `up` \| `down`。`down` 时同时记录 `pending_sync=N`。 |
| ④ 披露 | `down` → **必须在交付文本「数据限制」段披露**"本轮 WeKnora 不可用，已降级执行"。 |

> 慎用 `list_knowledge_bases` 做探测：返回约 93KB，易触发上下文膨胀/超限。

---

## 1. 影响面盘点（WeKnora down 时谁会受影响）

| 功能 | 依赖 WeKnora 的什么 | down 时后果 | 本地兜底 |
|---|---|---|---|
| **KB 检索**（口径/本体/语义/指标/血缘） | 主通道 `search_knowledge` | 主通道失效 | ✅ 有（见 §2.2）→ **降级但可继续** |
| **每日记忆备份** | 记忆库 `create_knowledge_from_text` | 云副本写入失败 | ✅ 本地 `knowledge/observed/memory/` 本就是**权威基线** → 记忆不丢 |
| **N5/N7 缺口闭环同步**（最严重） | 业务规则库 写入 + `hybrid_search` | 用户上传后无法落库/无法检索命中 | ✅ 本地落盘 + **本次会话直接用本地文件执行**（见 §2.1） |
| **N10 降本台账** | 记忆库 `LEDGER-*` 写入 | 写入失败 | ✅ 落本地暂存，恢复后补同步 |
| **N8 连续对话上下文** | 记忆库 `hybrid_search` 召回 | 召回失效 | ✅ 改读本地 `knowledge/observed/memory/` |
| **N11 验收闸门检索** | 记忆库历史验收口径 | 检索降级 | ✅ 改读本地 `knowledge/` 设计态文件 |
| **预编译缓存** `PRECOMP-*` | 记忆库 写入/检索 | 缓存读写失败 | ✅ 退回本地缓存或直算（慢但正确） |

**结论**：唯一"不可接受"的风险是 **N5/N7 用户已上传却用不了**（用户白传 + 规则丢失）。其余功能因"本地为权威基线 + 离线兜底"均可降级继续。

---

## 2. L2 降级（WeKnora 不可达）—— 三不原则：**不丢数据 · 不阻塞 · 不静默**

### 2.1 写入降级（最关键）

所有待同步内容**一律不得丢弃**，先落本地暂存区：

```
knowledge/observed/pending_sync/<YYYYMMDD-HHMM>-<title>.md     # 正文
knowledge/observed/pending_sync/_pending_index.json             # 索引
```

`_pending_index.json` 每条记录：
```json
{
  "target_kb_id": "6838e00b-fb8e-4de3-9f08-425af71dbdbd",
  "title": "RULE-分摊-工序成本-2026-10-30",
  "file": "20261030-0140-RULE-分摊-工序成本.md",
  "content_hash": "<md5 或 sha1，用于补同步幂等判重>",
  "status": "pending",
  "created_at": "<ISO8601>"
}
```

**按内容类型**：

| 类型 | 命名 | 暂存/本地落点 |
|---|---|---|
| 每日记忆 | `MEM-记忆-YYYY-MM-DD` | 本地 `knowledge/observed/memory/对话记忆_YYYY-MM-DD.md` 已是权威基线（够用）；同时入 `_pending_index` 待补同步 |
| 降本台账 | `LEDGER-*` | 落本地 `knowledge/design/ledger/` + 入索引 |
| 预编译 | `PRECOMP-指标名-YYYY-MM-DD` | 落本地 + 入索引 |
| **N5 定额 / N7 分摊**（用户上传） | `RULE-定额-*` / `RULE-分摊-*` | **额外落盘 `knowledge/design/rules/` 并立即在本次会话解析本地文件执行**（见下） |

**N5/N7 上传即用（防白传）**：用户上传文档后 → 本地落盘 `knowledge/design/rules/RULE-定额-<名>.md` / `RULE-分摊-<名>.md` → **直接解析该本地文件执行 N5/N7 对标/校验**，不依赖 WeKnora 检索 → 交付文本标注"已本地生效，待 WeKnora 恢复后补同步"。**用户上传立刻可见效，不阻塞。**

### 2.2 读取降级（KB 检索主通道失效）

切换到**本地离线兜底**（功能不中断）：

1. `knowledge/kb/` 6 份文档 Grep/Read（入口 `knowledge/kb/知识库索引.md` 可直读全文）；禁止全量加载大文件（三个血缘文档 >100KB），必须 Grep 精确定位后分段读。
2. 成本域权威手册 `knowledge/domains/cbprod/三钢成本域与利润域_数据口径与计算链路权威手册.md`（81KB，含 6 铁律 / V1-V9 / 10 表 / 5 类 SQL 模板 / 34 坑 / FAQ 速配）。
3. 域知识文档（合计 <16KB 可安全全量加载）：`管枢_生产管制域GZPROD_知识库文档.md`、`成枢_成本域CBPROD_知识库文档.md`。
4. 物化 SQL：`knowledge/design/indicator/materialized_sql/`。
5. **技能内置**：`sg-cbprod-warehouse` v2.0 已把手册核心知识内化为可检索结构。
6. **DB2 实表（事实源）**：经 `sg-db2-executor` 查 `SMBB_M_A_GZ01.T_ADS_DIM_GZ01`（只用五列，禁 `SELECT *`）取 ZB_CODE / ZB_NAME / SQL1 / CREATER —— **口径与指标注册的最终事实源，不依赖 WeKnora**。

→ 交付文本须标注："口径来源 = 本地 KB + DB2 实表；WeKnora 主通道本轮不可用"。

### 2.3 上下文 / 验收降级
- N8 上下文：改读本地 `knowledge/observed/memory/` 近期对话记忆文件。
- N11 验收：改读本地 `knowledge/` 设计态与历史验收口径文件。

### 2.4 告警与披露（不静默）
- 会话内提示进入降级模式；
- trace 写 `weknora_status=down, pending_sync=N`；
- 交付文本「数据限制」段写明："本轮 WeKnora 不可用，已降级执行；待补同步 N 条"。

---

## 3. L3 恢复补同步（WeKnora 恢复后 · 由铭枢 `sg-memory` 执行）

1. 读 `knowledge/observed/pending_sync/_pending_index.json`，筛 `status=pending`。
2. 逐条 `create_knowledge_from_text(kb_id=记录.target_kb_id, title=记录.title, content=<文件内容>, status="publish")`。
3. **幂等防重**：先按标题 `hybrid_search` / `list_knowledge` 查是否已存在；
   - 不存在 → `create_knowledge_from_text`；
   - 已存在 → 改用 `update_knowledge_from_text(knowledge_id, content)` 更新，**禁止产生重复条目**。
4. 成功 → 索引标 `status=done` + `synced_at`；失败 → 保留 `pending` 并告警，下次重试。
5. **触发方式**：手动（用户说"补同步"/"同步 WeKnora"）或每日 0:00 构建任务自动尝试。

### 3.1 更新生效判定（2026-10-30 实测 · 写入后必须看状态，不能"写完就当生效"）

`update_knowledge_from_text` 返回 `success: true` **只代表内容已入库，不代表可检索**。写入后条目会进入重建索引窗口，须用 `get_knowledge(knowledge_id)` 看三个字段判定：

| 字段 | 刚写完（观察点 1） | 稍后（观察点 2） | 生效判据 |
|---|---|---|---|
| `parse_status` | `pending`（`pending_subtasks_count=29`） | `finalizing`（`pending_subtasks_count=55`） | 变为 `completed` 才算全量就绪 |
| `enable_status` | `disabled` | `enabled` | **`enabled` 即视为可检索**（观察点 2 已能召回新内容） |
| `summary_status` | `completed` | `completed` | 摘要重生成完毕，`knowledge_description` 已含新增章节关键词 |
| `metadata.version` | `2` | `2` | 每次更新 +1，用于对账"副本版本 ≥ 本地版本" |
| `storage_size` | 246,962 B | **461,358 B** | ⚠ **旧 chunk 未即时回收，体积近乎翻倍** |

**结论与操作约束**：

1. **"写完即生效"是错的**：写入后若要立刻依赖该内容（比如同会话内跨会话召回），须先 `get_knowledge` 确认 `enable_status=enabled`；仍为 `disabled` 时按 L2 读取兜底处理，不要断言"已同步"。
2. **`pending_subtasks_count` 会在重建中先涨后落**（29 → 55 → 0），属正常排队，不误判为"写入失败"。
3. **避免高频重复更新**：每次 `update` 都会触发全条目重新分块 + 重嵌入，且旧 chunk 回收滞后（`storage_size` 翻倍）。**同一条目 1 小时内不重复更新**，多处理论上攒成一次写入。
4. **对账口径**：跨会话读取到副本后，用 `metadata.version` 与本地文件版本号比对，版本落后即判定漂移（详见 `docs/专家团运行SOP.md` 头部「版本漂移防护」）。

---

## 4. 为什么这样设计不会崩（关键原则）

- **本地为权威基线**：记忆 / 规则 / 台账的权威副本始终在本地 `knowledge/`，WeKnora 只是"可检索副本 / 共享副本"。**WeKnora 挂 ≠ 数据丢失**，只是"检索与跨会话共享"暂失。
- **上传即用**：N5/N7 用户上传的文档本地落盘后立即在本次会话可用（直接解析本地文件），不因 WeKnora 挂而阻塞或让用户白传。
- **不静默**：降级必须披露，不伪装成正常；补同步必须幂等，不产重复。

---

## 5. 目标库与 kb_id / 暂存映射

| 库 | kb_id | 承载内容 | 暂存 / 本地落点 |
|---|---|---|---|
| 数仓智脑专家团记忆知识库 | `c6e2d1ef-bed2-4356-b89b-d3bcd1ba377d` | `MEM-记忆-*`、`LEDGER-*`、`PRECOMP-*`、`MEM-CLAW-*` | `knowledge/observed/memory/`（权威）+ `pending_sync/` |
| 数仓智脑专家团-业务规则 | `6838e00b-fb8e-4de3-9f08-425af71dbdbd` | `RULE-定额-*`、`RULE-分摊-*` | `knowledge/design/rules/`（立即生效）+ `pending_sync/` |
| 数仓智脑知识库-指标体系 | `227f0a01-c36b-488a-8049-5b5869175782` | 指标口径检索 | 读取走本地 `knowledge/kb/` + DB2 实表兜底 |

---

**维护**：WeKnora 地址/库 id 变更或降级策略调整时，同步更新本文件。
