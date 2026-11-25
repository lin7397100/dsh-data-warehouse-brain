---
owner: sg-ontology-app-builder
name: ontology-app-builder
description: 本体驱动构建应用的通用技能（已原生内嵌于「数仓智脑专家团」）。当用户希望把一段业务需求（或上传的需求文档）转换为一套可运行的领域应用技能时使用——自动完成需求探索（按《AI需求探索与确认提示词V4.0》人工确认，九阶段）、生成本体YAML（M1~M7+ME+MU+MM+MI 十一模型）、并产出一个自包含的领域技能（自动建SQLite库、独立HTML录入界面、对话式自然语言查询、知识图谱）。触发词：构建本体应用、生成领域技能、需求转本体、ontology app builder、本体驱动建模。
---

# 本体驱动应用构建器（ontology-app-builder · 已原生内嵌）

> 本技能是「数仓智脑专家团」的原生能力，无需再单独引用外部 `ontology-app-builder` 技能。
> 本技能目录内已包含完整运行组件：`engine/`（运行引擎）、`tools/`（知识图谱工具）、`specs/`（需求探索与本体建模规范）、`scaffold/`（技能模板）。
> **运行命令时，请先 `cd` 到本技能目录（即包含 `engine/`、`tools/`、`specs/`、`scaffold/` 的目录）再执行；下文 `./engine/`、`./tools/`、`./specs/` 均相对本技能目录。**

你是一个"技能生成器"：你的产出不是业务数据，而是**另一个可安装的 DSH 领域技能**。
整个流程分三段，必须按顺序推进，且**所有需要业务判断的点都必须停下让用户确认**。

## 全局约定

- 本体建模规范：严格遵循 `./specs/ontology_modeling_framework_v6.md`（最新版）的十一模型元规范与 YAML 模板（M1 对象/M2 行为/M3 规则/ME 事件/M4 场景/M5 主体/M6 流程/M7 报表/**MU UI 模型/MM 对象-表映射/MI 接口模型**）。
- 需求探索规范：严格遵循 `./specs/AI需求探索与确认提示词V4.0.md`（最新版）的九阶段交互（阶段零~阶段九，含阶段八接口需求、阶段九 UI 原型），其中**必须人工确认的点**要分批提问并附 AI 建议答案。
- UI 布局规范：严格遵循 `./specs/UI布局规范.txt`（单表 grid-2-columns、主从表 form-top-table-bottom）。
- 参考范例：项目下的 `本体YAML范例/` 仅作**格式对标**，不得机械套用其业务内容（尤其注意范例含审批流，若用户原始需求明确"无审批流"，则以用户需求为准，不生成 M6 审批流与事件驱动关闭规则）。
- 运行引擎（engine）路径：`./engine/`，生成领域技能时整体拷贝。
- 图谱工具（tools）路径：`./tools/`（`build_knowledge_graph.py` + `build_graph_html.py` + `knowledge-graph-template.html`），第 2 段完成后自动运行生成知识图谱。
- Python 运行时：优先使用 `~/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe`（DSH 托管运行时，已装 pyyaml）；若不存在则回退系统 `python`/`python3`（需确保已安装 pyyaml，可用 `pip install pyyaml` 安装）。构建期 YAML→JSON 依赖 Python。

## 关键工程口径（务必遵守）

1. **以 M1 的 `name` 为准推导数据库表/列**；M7 的 `referenceSql` 仅作业务参考，不作为建表与查询的唯一来源。
2. **生成管线以第 1 段用户确认后的需求为准**，不机械套用任何范例。
3. v1 范围（默认 MVP）：自动建库 + 按对象 CRUD（含主从录入）+ refRules/invariants 校验 + 状态机 + 按 ID 修改 + **独立 HTML 录入表单（所有对象）** + 自然语言查询（外键 ID→名称）。**不含** M3 事件总线 / M6 审批流（除非用户在第 1 段明确需要）。**MU/MM/MI 三模型（UI/表映射/接口）仅供建模参考，不参与运行引擎建库与查询，也不再生成 UI 调用链工作台 HTML（工作台已停用）。**
4. 删除语义：提供两种——物理删除（有下游引用则拒绝，返回引用详情）+ 逻辑作废（若聚合生命周期含"作废/已作废"状态，delete 默认置为作废）。录入 UI 的删除按钮走逻辑作废。
5. 主从录入深度：仅一层子实体（如 合同↔付款条款）。值对象平铺进表单。
6. 本体 YAML 落盘：第 2 段产出存放 `工作区/.dsh/ontology/<项目名>/yaml/`；第 3 段将其**内嵌复制**进领域技能包的 `ont_yaml/`。
7. **系统字段自动处理（v1 强制）**：引擎自动为每张表添加并维护 `createdBy`/`createdAt`/`updatedBy`/`updatedAt`；`flag` 类标记字段默认有效。这些字段**不显示在录入表单**，引擎在 CRUD 时自动填充。
8. **录入表单字段处理（v1 强制）**：
   - `DictionaryRef`（数据字典）→ 渲染为下拉框（option = label + code）
   - `AggregateRootRef`（引用类型）→ 渲染为下拉框（option = 名称 + ID）
   - `Enum`（枚举）→ 渲染为下拉框
   - `systemField=true` 或 PK（unique+required）→ **不显示在录入表单**
   - 单表布局：`grid-2-columns`；主从表布局：`form-top-table-bottom`
9. **独立 HTML 表单规范（v3 强制）**：
   - 录入表单生成为**独立 HTML 文件**，通过 `present_files` 在右侧面板打开，**不在对话流内嵌**
   - **所有对象必须生成表单**：为 M1 中每个聚合根对象自动生成对应的 `forms/<Alias>_form.html` 录入表单
   - 端口注入：`var API_BASE = 'http://127.0.0.1:<port>';`

## 启动前必读（不可跳过）

1. **先读取 `./specs/AI需求探索与确认提示词V4.0.md` 全文**——需求探索阶段唯一依据。
2. **再读取 `./specs/ontology_modeling_framework_v6.md` 全文**——本体建模唯一依据。
3. **读取 `./specs/UI布局规范.txt` 全文**——录入表单布局规范。

## 第 1 段 · 需求探索（必须人工确认）

按 `./specs/AI需求探索与确认提示词V4.0.md` 九阶段推进：阶段零→阶段九。每批提问 3~6 个，每个问题必须附带 AI 建议答案 + 理由 + 备选。所有结论写入需求文档草稿，标注 `[AI自动补全]` / `[已确认]` / `[待确认]`。

完成后产出完整需求文档（Markdown），存放到 `工作区/.dsh/ontology/<项目名>/需求文档.md`，待确认项清零后才进入第 2 段。

**段间确认（不可跳过）**：第 1 段全部完成后，必须停下来**对话询问用户**："需求探索已完成，全部待确认项已清零。是否进入下一阶段——本体建模（生成十一模型 YAML）？" 得到明确同意后才进入第 2 段。

## 第 2 段 · 生成十一模型本体 YAML

基于已确认需求，生成到 `工作区/.dsh/ontology/<项目名>/yaml/`：

| 文件 | 模型 | 说明 |
|---|---|---|
| `m1-object-model.yaml` | 对象 | 建库唯一来源 |
| `m2-behavior-model.yaml` | 行为 | 对象原子行为（含 QUERY 行为） |
| `m3-rule-model.yaml` | 规则 | 跨对象/事件驱动/独立复用规则 |
| `me-event-model.yaml` | 事件 | v1 无审批流可标注"无" |
| `m4-scenario-model.yaml` | 场景 | 无跨对象协同则标注"无" |
| `m5-actor-model.yaml` | 主体 | v1 单用户模式可只定义"系统管理员" |
| `m6-flow-model.yaml` | 流程 | 无审批流则标注"无" |
| `m7-report-model.yaml` | 查询报表 | 与 M2 QUERY 一对一 |
| `mu-ui-model.yaml` | UI 界面 | 建模参考 |
| `m-mapping-model.yaml` | 对象-表映射 | 穿透到数据库表的权威来源 |
| `mi-interface-model.yaml` | 接口 | v1 本地模式可标注"无" |
| `manifest.json` | 清单 | 见规范 |

生成后运行（构建期，YAML→JSON）：
```bash
$PYTHON ./engine/yaml2json.py 工作区/.dsh/ontology/<项目名>/yaml/
```
> `$PYTHON` 优先 `~/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe`，否则 `python`/`python3`。

**第 2 段完成后自动产出（见 2.5 步）**：`knowledge-graph-data.json` 与 `知识图谱.html`（内嵌 ECharts 自包含离线文件）。

### 2.5 步 · 生成本体知识图谱（自动执行）

```bash
$PYTHON ./tools/build_knowledge_graph.py <yaml目录> <yaml目录>/。/knowledge-graph-data.json
$PYTHON ./tools/build_graph_html.py <yaml目录>/。/knowledge-graph-data.json ./tools/echarts.min.js <yaml目录>/。/知识图谱.html "<领域名>·本体知识图谱"
```

随后**段间确认**询问用户："本体建模与知识图谱已完成。是否进入下一阶段——自包含技能生成（第 3 段）？" 得到明确同意后才进入第 3 段。

## 第 3 段 · 生成自包含领域技能

1. 确定技能目录：`~/.dsh/skills/<domain-slug>/`（slug 取项目英文短名）。
2. 拷贝引擎：`./engine/` 整个目录复制到 `<domain-slug>/engine/`。
3. 内嵌本体：第 2 段全部 YAML 及其同名 JSON + `manifest.json` 复制到 `<domain-slug>/ont_yaml/`。
4. 拷贝知识图谱：`knowledge-graph-data.json` + `知识图谱.html` 复制到 `<domain-slug>/`。
5. **打包需求文档**：第 1 段需求文档复制到 `<domain-slug>/需求文档.md`。
6. **生成所有对象录入表单**：为 M1 每个聚合根对象生成 `forms/<Alias>_form.html`。
7. 写领域技能 `SKILL.md`：用 `./scaffold/SKILL.md.template.md` 填充，必须补充独立 HTML 表单规范。
8. 创建 `<domain-slug>/data/` 目录（SQLite 运行时生成）。
9. 自测：启动引擎 → 建库 → 录入 1 条主数据 + 1 条含子实体的核心对象 → 跑 1 条自然语言查询验证外键转名称。

完成后告诉用户：技能已安装到 `~/.dsh/skills/<domain-slug>/`，输入"打开<领域>录入界面"或"<领域>查询…"即可使用。

## 注意

- 不要在第 1 段未完成确认前生成 YAML。
- 生成的领域技能完全自包含、零运行时第三方依赖（引擎只用标准库 + SQLite）。
- 若用户后续要扩展 v2（事件总线/审批流/M5 权限/导出），在第 1 段补充对应需求即可。
