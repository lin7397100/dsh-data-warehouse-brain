# 技能 owner 生命周期治理规范（P3 · 2026-10-30 生效）

> 定位：专家团「职责-技能-成员」三者一致性的制度保障。
> 背景：2026-10-30 审查发现——成枢/管枢作为在册主责却 0 技能，根因是某次"退役迁移"只迁走了技能 owner、未随复职归位，且"已退役"措辞与"在册主责"散布冲突。
> 铁律级：与 `iron_rules.md` 同级；本文档为技能归属的唯一权威。

---

## 一、三条铁律

### T1 · 新技能按"使用者主责"归属

- 新建技能时，`owner` 必须指向**该技能的实际使用主责专家**，而非"顺手开发它的人"。
- 若技能由 A 开发、由 B 长期使用并主责，`owner` 应设为 B；开发者在 `SKILL.md` 内以 `author:` 记录，不影响归属。
- 判定口径：**谁对该技能的口径正确性、可用性、更新维护负最终责任，谁就是 owner。**

### T2 · 专家退役必须"同步回收"技能

- 专家退役时，**必须同一步完成**其名下全部技能的 owner 转移，转给接任的在册专家，并在 `SKILL.md` 顶部写入「owner 变更」记录（含日期、原 owner、新 owner、接任原因）。
- **禁止**出现"成员已退役、技能 owner 仍指向退役者"或"技能 owner 转走、但退役动作与复职动作不同步"的半成品状态。

### T3 · 专家复职必须"同步归位"技能

- 退役专家恢复在册时，其此前被转走的技能 owner 必须**同步归位**。
- 归位时同样写入「owner 归位」记录。

---

## 二、owner 生命周期状态机

```
                    ┌──────────────────────┐
   新建技能 ────────►│  owner = 使用者主责    │
                    └──────────┬───────────┘
                               │ 使用者退役（T2）
                               ▼
                    ┌──────────────────────┐
                    │  owner 转接任者 + 记录  │◄─────────┐
                    └──────────┬───────────┘           │
                               │ 接任者复职/归位（T3）      │
                               ▼                        │
                    ┌──────────────────────┐           │
                    │  owner 归位 + 记录      │───────────┘
                    └──────────────────────┘
```

**每一步都必须：**
1. 改 `SKILL.md` 的 `owner:` 字段
2. 在 `SKILL.md` 顶部加变更记录（日期 + 方向 + 责任人）
3. 同步所有引用该技能归属的文档（routing / members_guidance 能力载体表 / SOP 角色表 / 架构文档）
4. 同步双副本（marketplace → cache）
5. 执行 `validate_expert.py` + `register_expert.py`（expert-manager 规范）

---

## 三、共享技能例外（避免误拆）

以下技能属**能力平台型**，owner 归"平台方"，使用者通过加载共享技能使用，**不视为"使用者名下 0 技能缺陷"**：

| 技能 | 平台 owner | 说明 |
|---|---|---|
| `sg-analysis-engine`（及别名 `sg-zhishu-analysis-engine`/`sg-data-analysis-engine`） | `sg-metadata` | 分析引擎统一入口，多专家共享 |
| `sg-report-composer`、`sg-kanban-builder` | `sg-insight` | 交付平台技能，若溪/达仕等按插槽使用 |
| `sg-multi-agent-coordination`、`sg-task-planner`、`sg-agentic-decision` | `data-warehouse-brain-team-lead` | 编排平台技能 |

**判断标准**：若一个技能被 ≥3 位专家使用、且无单一"业务域主责"，它就是共享平台技能，owner 归平台方；反之若技能强绑定某业务域（如成本域/生产域），owner 必须归该域主责专家。

> 反例（本次已纠正）：`sg-cbprod-warehouse`、`sg-gzprod-warehouse`、`sg-cost-ops` 曾挂在 `sg-metadata` 名下，但它们**强绑定成本域/生产域**，不属于共享平台技能 → 已归位成枢/管枢。

---

## 四、每次改包后的强制校验

改包（尤其涉及成员增删、退役、复职、新建技能）后，必须运行：

```bash
python scripts/check_skill_ownership.py --root <包根>
```

脚本检查以下不变量（任一失败即退回重做）：

| # | 不变量 | 期望 |
|---|---|---|
| C1 | 每个技能 `owner` 非空且指向存在的成员 | 0 悬空 owner |
| C2 | 退役成员名下 0 个主技能 | 秦逸/赛奇/瑞卡/迅达 = 0 |
| C3 | 转实域专家名下技能数符合预期 | 成枢 ≥2、管枢 ≥1 |
| C4 | 共享技能白名单与 owner 一致 | 见第三节 |
| C5 | 无"在册成员却 0 技能"的非白名单情况 | 仅允许若溪/达仕（共享交付角色）为 0 |
| C6 | 双副本（marketplace/cache）关键文件摘要一致 | MD5 一致 |

---

## 五、与 expert-manager 的配合

- 成员退役/复职、新建技能，均属"修改已有专家"，走 expert-manager 场景 C：编辑 → `validate_expert.py` → `register_expert.py`。
- **严禁**只改文件跳过校验与注册；**严禁**直接手改 `marketplace.json` 绕过注册脚本。
- 退役成员**不删除**其 `agents/*.md`（历史留痕与审计需要），仅在成员清单标注退役，并执行 T2 回收技能。

---

## 六、退役成员当前清单（与 members_guidance 同步维护）

| 退役成员 | 并入专家 | 名下应余技能数 |
|---|---|---|
| `sg-zhishu-sql-analyst` 秦逸 | `sg-development` 淬锋 | 0 |
| `sg-zhishu-data-scientist` 赛奇 | `sg-quality` 砺真 | 0 |
| `sg-zhishu-knowledge-researcher` 瑞卡 | `sg-semantic` 铨度 | 0 |
| `sg-report-delivery` 迅达 | `sg-wecom-doc` 翰枢 | 0 |

> 成员新增退役时，**必须同步更新本节清单与 `check_skill_ownership.py` 的 `RETIRED` 常量**，两处不一致即视为制度未落地。
