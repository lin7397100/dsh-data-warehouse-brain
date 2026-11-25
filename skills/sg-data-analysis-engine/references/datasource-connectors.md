# 数据源连接规范

## 环境变量

| 变量 | 含义 | 默认值 |
|---|---|---|
| `$DB2_ASSETS_HOME` | DB2 资产目录（DDL / PROD / CBPROD） | 用户在部署时设置 |
| `$ONTOLOGY_HOME` | 本体与语义资产目录 | 用户在部署时设置 |
| `$WORKSPACE` | 当前工作区（产物落盘位置） | DSH 工作区 |

> 技能文件中**禁止硬编码绝对路径**，一律用变量 + 部署说明。

## DB2（主数据源）

| 项 | 规范 |
|---|---|
| 连接方式 | DB2 MCP（只读服务账号） |
| 数据库 | SGPROD1 |
| 层次 | ODS `SMBB_M_O_XXX` / DWS `SMBB_M_S_XXX` / ADS `SMBB_M_A_XXX` |
| 典型 Schema | `SMBB_M_S_ZZ00`（制造总表）/ `SMBB_M_S_CB00`（成本域）/ `SMBB_M_A_GZ01`（指标配置） |
| 方言要点 | `FETCH FIRST n ROWS ONLY` 分页、`NULLIF` 保护除法、分区条件强制 |
| 只读约束 | 禁止 INSERT/UPDATE/DELETE/DDL，写操作需人工确认 |

## 本地文件

| 类型 | 用途 | 位置 |
|---|---|---|
| CSV / Excel | 导出数据、业务补充数据 | `$WORKSPACE` 或用户指定 |
| DDL 文件 | 表结构检索（9167 个） | `$DB2_ASSETS_HOME/DDL` |
| 存储过程 | 业务逻辑解析（105 个） | `$DB2_ASSETS_HOME/PROD` / `CBPROD` |
| 执行日志 | 成本批处理监控 | `C.xlsx` / `T_DWD_WH_CACC_PNC0` |

## 知识库

| 源 | 用途 | 接入 |
|---|---|---|
| ima 知识库 | 方法论、行业实践 | ima MCP |
| 腾讯文档（通道 disabled） | 报告协作（回退本地 MD / 企微） | 腾讯文档 MCP（当前不可用） |
| 乐享知识库 | 团队知识沉淀 | 乐享 MCP |

## 产物落盘

统一目录：`<workspace_folder>/artifacts/analysis/`

| 产物 | 命名 |
|---|---|
| 报告 Markdown | `{主题}-{日期}.md` |
| 报告 HTML | `{主题}-{日期}.html` |
| docx | `{主题}-{日期}.docx` |
| 看板 | `kanban-{主题}-{日期}.html` |
| 分析脚本 | `{分析名}.py` |
| 数据快照 | `{数据集}-{日期}.csv` |
