# DSH 单向发布部署规范（One-Way Publish Protocol）

> **重写时间**：2026-11-20（v2.0）
> **原文件**：专家包双副本同步机制（Dual-Copy Sync Protocol，WorkBuddy 时代，2026-10-29）
> **重写原因**：本专家团已迁移到 **DSH（DeepSeek Harness）**。DSH 不存在 WorkBuddy 的
> `marketplaces ↔ cache` 双副本镜像，也没有「运行时回写源仓库」的概念。原双副本规范
> 在 DSH 下**指向不存在的目录**，继续沿用会让人误以为「改完源仓库就生效」。
>
> **一句话结论**：DSH 是**单向发布**——源仓库 → 运行时加载源，一次性推送、只读加载、**禁止回写**。

---

## 一、架构图（单向，无回写）

```
┌──────────────────────────────── 源仓库（唯一事实源）────────────────────────────────┐
│  C:/Users/<user>/Documents/deepseek-harness/data-warehouse-brain-team/              │
│                                                                                     │
│    agents/*.md            24 个专家 persona 源（主理人 + 22 专家 + 1 快问）           │
│    agents/references/     外置细则（disciplines / routing / api_alignment …）         │
│    skills/*/SKILL.md      59 个技能源（含 ontology-app-builder）                      │
│    panel/roster.json      面板只读镜像（tools/gen_roster.py 从 patch 生成）            │
│    knowledge/  scripts/  tools/                                                      │
└───────────────────────────────────────┬─────────────────────────────────────────────┘
                                        │
                        ①改源仓库  ②verify_dsh_sync.py --apply
                                        │   （单向发布，只推不拉）
                                        ▼
┌──────────────────────── DSH 运行时加载源（两个，均为普通目录/文件）────────────────────┐
│                                                                                     │
│   ~/.dsh/profiles/desktop/cordis.patch.yml    ← agents/*.md 渲染成的 preset/persona   │
│        └─ 24 个 preset（每个 preset 内 persona 插件持有 1 段 prefix 全文）              │
│                                                                                     │
│   ~/.dsh/skills/<skill>/SKILL.md              ← skills/*/SKILL.md 逐目录发布          │
│        └─ 59 个技能目录（DSH 另写 .dwb-skills-manifest.txt 清单，勿手改）              │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                   ③重启 DSH 生效
                                        │
                                        ▼
                              新会话加载新 persona / 新技能
```

**关键事实**：

| 事实 | 说明 |
|---|---|
| 单向 | 只有「源仓库 → 运行时」一个方向；运行时**不写回**源仓库 |
| 无 cache | DSH 没有 WorkBuddy 的 `plugins/cache/` 副本，不存在「两份物理目录」 |
| 不自动生效 | 发布只改磁盘；**会话启动时**才加载，运行中修改不重载 → 必须重启 DSH |
| 发布即覆盖 | 再次 `--apply` 会用源仓库覆盖运行时同名文件（所以禁手工改运行时） |

---

## 二、两个加载源与对应关系

| 加载源 | 路径 | 数量 | 由谁生成 | 源 | 校验层 |
|---|---|---:|---|---|---|
| **preset / persona** | `~/.dsh/profiles/desktop/cordis.patch.yml` | **24** 个 preset（558 个 id 节点 / 24 个 prefix） | 由 `agents/*.md` 渲染进 patch 内层 `config.plugins[id=persona].config.prefix` | `<包根>/agents/*.md` | `verify_dsh_sync.py` 第 2 层 |
| **skills** | `~/.dsh/skills/` | **59** 个技能目录 | 逐目录发布 `SKILL.md`（及其 scripts/references） | `<包根>/skills/*` | `verify_dsh_sync.py` 第 1 层 |
| 面板名册（只读镜像） | `<包根>/panel/roster.json` | 24 条 | `python tools/gen_roster.py`（读 patch → 写 JSON） | 由 patch 派生 | `verify_dsh_sync.py` 第 3 层 |

**对应关系要点**：

1. `agents/*.md` 的 **basename** 必须等于 patch 里 preset 的 **config.id**（`data-warehouse-brain-team-lead.md` ↔ `data-warehouse-brain-team-lead`）。
2. 24 个 agent ↔ 24 个 preset ↔ roster 的 `meta.count=24`，**三处数量守恒**，任一不等即为漂移。
3. `panel/roster.json` 是**只读镜像**：只允许 `gen_roster.py` 生成，**禁止手改**（改了下次生成即被覆盖，且面板与运行时不一致）。
4. 技能归属（owner）以 `skills/*/SKILL.md` 的 frontmatter `owner` 字段为权威结构化来源，`gen_roster.py` 按 owner 归到专家名下。

---

## 三、与 WorkBuddy 的本质区别

| 维度 | WorkBuddy（历史） | DSH（现行） |
|---|---|---|
| 部署模型 | **双副本同步**：`marketplaces`（编辑源）↔ `cache`（运行时源） | **单向发布**：源仓库 → 运行时 |
| 物理副本数 | 2 份（编辑源 + 运行时 cache） | 1 份源 + 1 份运行时加载产物（无镜像副本概念） |
| 同步方向 | marketplace → cache（单向），但机制上允许两侧各自演化 | 源 → 运行时（一次性推送，**禁回写**） |
| 回写能力 | 有（`register_expert.py` / `.in_use` 标记 / 平台写 settings.json） | **无**（DSH 不写源仓库，源仓库是唯一事实源） |
| 生效方式 | 同步 cache + **重启 WorkBuddy 客户端** | `--apply` 发布 + **重启 DSH** |
| 部署校验器 | `tools/_deprecated/sync_expert_cache.py --verify`（已归档） | **`scripts/verify_dsh_sync.py`**（本规范配套） |
| 名册生成 | `plugin.json` 的 agents/skills/members | `tools/gen_roster.py` 从 patch 生成 `panel/roster.json` |
| 遗留目录 | `~/.workbuddy/plugins/{marketplaces,cache}/…` | `~/.dsh/{profiles,skills}/…`（**使用 `~/.dsh`，不依赖 `~/.workbuddy`**） |

> **为什么不能照搬双副本经验**：WorkBuddy 时代的头号事故是「改造做对了但没送达运行时」。
> DSH 下这个风险依然存在（发布 ≠ 生效），但**处置方式不同**——不是「同步 cache」，
> 而是「发布 + 一致性校验 + 重启」。

---

## 四、部署三步（标准动作序列）

> 任何对 `agents/` `skills/` 的改动，都必须走完这三步才算「送达」。

### 第 1 步：改**源仓库**（唯一人工编辑入口）

```bash
cd <包根>            # 例：C:/Users/<user>/Documents/deepseek-harness/data-warehouse-brain-team
# 编辑 agents/*.md、skills/*/SKILL.md、agents/references/*.md
```

- ✅ 只改源仓库
- ❌ 禁直接改 `~/.dsh/skills/`、禁直接改 `cordis.patch.yml` 的 persona 段（见 §七）

### 第 2 步：发布到 DSH 运行时

```bash
# 先看计划（不写盘、不备份）
python scripts/verify_dsh_sync.py --apply --dry-run

# 确认后真正发布（自动备份 ~/.dsh/skills/ → backup/dsh_skills_<时间戳>/）
python scripts/verify_dsh_sync.py --apply
```

发布语义：

- **增量覆盖**：只覆盖源仓库存在的文件；**不删除**运行时独有文件（防不可逆丢失）
- **自动备份**：写盘前先整树备份 `~/.dsh/skills/`
- **排除项**：`__pycache__/` `*.pyc` `*.pyo` `materialized_sql/`
  （物化 SQL 由每日构建单向写入运行时，**禁止**发布回写，否则旧快照覆盖新产物）

### 第 3 步：重启 DSH（缺此步不生效）

- 关闭并重新打开 DSH（或结束桌面端进程后重启）
- 新会话才会重新读取 `cordis.patch.yml` 与 `~/.dsh/skills/`
- 验证：新会话里问一句该技能/专家的触发词，能命中即送达

> ⚠ **发布成功 ≠ 会话生效**。`--apply` 返回 0 只代表磁盘一致，不代表当前会话已加载。

---

## 五、校验命令（`scripts/verify_dsh_sync.py`）

### 5.1 用法

```bash
python scripts/verify_dsh_sync.py                 # 只校验，打印人类可读报告
python scripts/verify_dsh_sync.py --json          # 机器可读 JSON（供 CI / 面板消费）
python scripts/verify_dsh_sync.py --apply         # 发布：包内 skills → ~/.dsh/skills（自动备份）
python scripts/verify_dsh_sync.py --apply --dry-run   # 只打印发布计划，不写盘
```

### 5.2 四层校验

| # | 层 | 校验内容 | 通过标准 |
|---|---|---|---|
| 1 | skills | 逐技能目录比对 `SKILL.md` 的 MD5，状态 `same` / `drift` / `missing_in_dsh` / `extra_in_dsh` | 59 项全 `same` |
| 2 | agents | `agents/*.md` 数量 ↔ patch preset 数量（24↔24）+ 每个 preset 的 persona prefix 旧 API 残留 | 数量守恒 且 旧 API 残留 = 0 |
| 3 | roster | `panel/roster.json` 旧 API 残留 + `meta.count` | 残留 = 0 且 count = 24 |
| 4 | WorkBuddy | 校验器自身是否引用 `~/.workbuddy` 路径 | 引用数 = 0 |

> 「旧 API」指旧版 harness 的派发/组队/回执接口（具体清单见
> `agents/references/api_alignment.md` 的映射表，本文不重复罗列以免二次传播）。
> DSH 等价物是 `delegate_expert` / `wait_agent` / `send_message` / `todo_write` / `list_agents`。

### 5.3 退出码

| 退出码 | 含义 | 处置 |
|---:|---|---|
| `0` | 全一致（或 `--apply` 后复检通过） | 可交付；记得重启 DSH |
| `1` | 存在漂移 / 旧 API 残留 / 数量不守恒 | 按报告修复源仓库 → 重跑 `--apply` → 复检 |
| `2` | 环境异常（找不到 DSH 根 / patch / skills 目录） | 确认 DSH 已安装且 profile 为 `desktop` |

### 5.4 报告怎么看

```
【1】skills 层：包内 59 ↔ DSH 59
     same=59  drift=0  missing_in_dsh=0  extra_in_dsh=0  目录内文件差异=0
     ✅ 59 项 MD5 全一致
```

- `drift`：两侧都有但内容不同 → 源仓库改过没发布（跑 `--apply`）
- `missing_in_dsh`：源仓库新增技能没发布 → 跑 `--apply`
- `extra_in_dsh`：运行时独有（历史遗留/手工新建）→ 不自动删，需人工确认后处理

---

## 六、WorkBuddy 遗留处置

| 遗留物 | 状态 | 处置 |
|---|---|---|
| 旧 marketplace 编辑源目录 | **已归档并删除（2026-11-20）** | 归档件 `backup/workbuddy_purge_20261120/workbuddy_expert_copies.zip`，只读可审计；DSH 不加载 |
| 旧 cache 运行时副本目录 | **已归档并删除（2026-11-20）** | 同上归档件；DSH 无 cache 概念 |
| `tools/_deprecated/sync_expert_cache.py` | **已归档 `_deprecated/` 并标 DEPRECATED（2026-11-20）** | 不执行（DSH 无 cache 镜像可同步）；仅当回退 WorkBuddy 环境时从此目录取用 |
| `tools/_deprecated/reset_claw.py` | **已移入 `_deprecated/` 并标 DEPRECATED** | 不执行（DSH 无 Claw 机制） |
| `tools/_deprecated/convert_workbuddy_to_dsh.py` | **已移入 `_deprecated/`**（一次性迁移器） | 仅「再迁一台机器」时使用，不参与日常部署 |
| `skills/ontology-app-builder/**` | 模板内 `~/.dsh/skills/` 为**目标产物落位约定** | 按交付约定保留，不是部署依赖 |

> **旧双副本已不可回退**：目录已删除，回退只能靠源仓库 + `verify_dsh_sync.py --apply` 重新发布。
> DSH 环境下**不存在**任何可执行的 WorkBuddy 回退序列。

---

## 七、禁止项（红线）

1. ❌ **禁手工改 `~/.dsh/skills/`**
   —— 会被下次 `verify_dsh_sync.py --apply` **原样覆盖**（源仓库为准），手改丢失且无痕迹。
2. ❌ **禁手工改 `cordis.patch.yml` 的 persona prefix 段**
   —— 该段由 `agents/*.md` 渲染生成，手改后与源仓库不一致；且 `gen_roster.py` 会把它抽进
   `panel/roster.json`，造成面板与源仓库三方不一致。要改 persona 请改 `agents/*.md` 后重新发布。
3. ❌ **禁把物化 SQL 发布回写**
   —— `knowledge/**/materialized_sql/*.sql` 由每日构建**单向写入**运行时；把旧快照发布回去
   会覆盖新构建产物，属不可逆数据事故。`--apply` 已硬编码排除该项。
4. ❌ **禁依赖 WorkBuddy 路径**
   —— 任何脚本/规范不得以 `~/.workbuddy/...` 为运行前提（`verify_dsh_sync.py` 第 4 层会报警）。
   路径一律用 `os.path.expanduser('~')` 推断，**禁硬编码用户名**。
5. ❌ **禁镜像删除**
   —— 发布只做「增量覆盖」，绝不 `rm -rf` 运行时独有文件；删任何东西前必须人工确认 + 备份。
6. ❌ **禁「发布成功」当「已生效」**
   —— 交付话术必须同时给出：`verify_dsh_sync.py` 退出码 + 是否已重启 DSH。

---

## 八、故障排查速查

| 症状 | 首先查什么 |
|---|---|
| 改了源仓库但会话行为无变化 | 是否执行过 `--apply`？是否**重启 DSH**？（90% 是这两条） |
| 会话注入的是旧 persona | 跑 `verify_dsh_sync.py` 看 agents 层；再核对 patch 里该 preset 的 `prefix_len` |
| 技能触发不了 | `verify_dsh_sync.py` 第 1 层是否 `missing_in_dsh`；`~/.dsh/skills/<name>/SKILL.md` 是否存在 |
| 报告 `drift` | 源仓库有未发布改动 → `--apply` |
| 报告 `extra_in_dsh` | 运行时独有技能（历史/手工），人工确认后再决定是否补进源仓库 |
| 退出码 2 | `~/.dsh` 或 `profiles/desktop/cordis.patch.yml` 不存在 → 确认 DSH 安装与 profile |
| 脚本调不通 | 路径是否写死成 WorkBuddy 路径；改用包根相对路径 |

---

## 九、历史沿革

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-29 | WorkBuddy 双副本同步规范（marketplace ↔ cache，事故复盘 + 强制同步序列） |
| **v2.0** | **2026-11-20** | **重写为 DSH 单向发布规范**：删除双副本/cache 概念，新增两个加载源对应关系、`verify_dsh_sync.py` 校验器、部署三步、WorkBuddy 遗留处置与六条红线 |

> 原 v1.0 正文（WorkBuddy 双副本事故复盘、Claw 会话重置、settings.json 反复丢失）
> 已归档到 `backup/dsh_arch_20261120/agents/references/dual_copy_sync.md`，
> 仅在回退 WorkBuddy 环境时参考。
