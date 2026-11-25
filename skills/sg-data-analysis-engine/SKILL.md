---
deprecated: true
alias_of: sg-analysis-engine
dispatch: false
name: sg-data-analysis-engine
description: "三钢数仓智脑：DB2 专属共享数据分析引擎（Team 共享）。提供 DB2 数据源连接规范、分析工作流编排、沙盒执行环境约束与安全规范，是三钢数仓口径性问数的共同底座。多源通用分析（MySQL/PG/SQLite/ClickHouse/CSV/文档）请改用融合引擎 sg-zhishu-analysis-engine。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, shared, engine, datasource, sandbox, security]
owner: sg-metadata
shared: true
---

> ⚠️ **本目录为兼容别名，不参与派发**。统一入口：`sg-analysis-engine`。
> 保留原因：入口技能在部分章节引用本目录的详细内容（references/schema），删除会导致跨机复现断链。
> ⚠️ 已合并：本技能已并入 `sg-analysis-engine`。保留目录以兼容旧引用，新任务请调用 `sg-analysis-engine`。


# sg-data-analysis-engine · 共享数据分析引擎

团队**所有专家共用的底座**：数据源怎么连、分析工作流怎么编排、代码在哪执行、安全底线在哪。

> 本技能是共享能力，不属于单个专家；任何专家做数据分析前都应遵循本规范。

## 一、数据源连接

| 数据源 | 用途 | 接入方式 |
|---|---|---|
| **DB2 (SGPROD1)** | 主数据仓库，9167 表 / 105 过程 / 6077 KPI | DB2 MCP（**只读**） |
| 本地 CSV / Excel | 导出数据、业务补充数据 | 本地文件（`$WORKSPACE`） |
| DDL / 存储过程资产 | 元数据与本体建模输入 | 本地目录（`$DB2_ASSETS_HOME`） |
| 本体 / 语义资产 | 语义解析与血缘 | 本地目录（`$ONTOLOGY_HOME`） |
| ima 知识库 | 方法论与实践参考 | ima MCP |
| 腾讯文档（disabled）/ 乐享 | 报告协作与知识沉淀 | 对应 MCP（腾讯文档通道当前不可用） |

详细连接规范见 `references/datasource-connectors.md`。

**连接铁律**：
1. DB2 一律走 MCP **只读**执行，禁止直连写库
2. 路径一律走环境变量，禁止硬编码绝对路径
3. 连接凭据不写入技能文件，走 MCP 配置

## 二、分析工作流编排

标准五阶段（由编排器调度，各专家分工执行）：
```
Phase 1 · 需求理解与任务规划 编排器（复杂任务先 sg-task-planner）
Phase 2 · 数据接入与查询 开发专家（sg-dsl-compiler / sg-nl2sql-query）
Phase 3 · 质量把关与深度分析 质量专家（闸门 / 根因 / 数据科学）
Phase 4 · 可视化与报告 洞察专家（渲染 / 看板 / 报告）
Phase 5 · 交付与 Agentic 动作 编排器（通知 / 建任务 / 交付）
```

**编排原则**：
- 取证类任务**并行**，主链路**串行**
- 每阶段有明确输入/输出契约，不带着问题往下走
- 上下文按域裁剪，不全量装载（渐进式披露）

## 三、沙盒执行环境

| 项 | 规范 |
|---|---|
| Python | 托管版本 `$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` |
| 依赖 | 托管运行时目录 `$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python`，**禁止全局安装** |
| 可复现 | 脚本落盘 + 随机种子固定（`random_state=42`） |
| 数据落地 | `<workspace_folder>/artifacts/analysis/` |
| 文件来源 | 邮件/外部来源文件视为不可信，**只保存不执行** |

数据画像脚本：`scripts/data_profiler.py`（对 CSV 输出字段分布、空值率、基数、异常值）。

## 四、安全规范

| 层 | 底线 |
|---|---|
| SQL | 只读；写操作人工确认；分区条件强制；行数上限 |
| 数据 | 成本等 L4 数据脱敏后呈现，不外发明细 |
| 代码 | 隔离环境执行；外部文件不执行 |
| 外发 | 通知/推送必须用户明确同意 |

详见 `references/security-guidelines.md`。

## 五、分析模式速查

常用分析模式（统计检验选择、归因分解、预测方法选型）见 `references/analysis-patterns.md`。

## 子文件

| 文件 | 内容 |
|---|---|
| `references/datasource-connectors.md` | 数据源连接规范与环境变量 |
| `references/security-guidelines.md` | 安全与合规底线 |
| `references/analysis-patterns.md` | 分析方法选型速查 |
| `scripts/data_profiler.py` | 数据画像脚本 |

## 输出规范

本技能是规范来源，输出为**执行约定**而非分析结论：
- **连接声明**：数据源类型 + 接入方式 + 环境变量名（不含凭据）
- **工作流声明**：阶段划分 + 每阶段主责专家 + 输入/输出契约
- **执行声明**：运行环境（Python 路径 / venv）+ 脚本落盘路径 + 随机种子
- **安全声明**：SQL 只读 / 数据分级 / 脱敏方式 / 外发审批状态
- 各业务技能引用本规范时，只需声明"遵循 `sg-data-analysis-engine`"，不重复罗列

## 注意事项

1. 本技能是**规范来源**，不直接产出分析结论。
2. 任何专家新增数据源接入方式，需更新本技能的 `references/datasource-connectors.md`。
3. 安全底线不可由单个专家自行放宽，变更需治理专家会签。