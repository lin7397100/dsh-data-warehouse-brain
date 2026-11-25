### KB 检索路由（所有问数/溯源/口径任务的第一步 · 强制）

> 📎 KB 全量规范见 `agents/references/knowledge_base.md`（轻量指针，agent 按需加载）。
> **编排器收到任何数仓指标类任务后，第一步必读 `knowledge_base.md` 确定检索路线。**
>
> KB 物理路径：`knowledge/kb/`

| 任务类型 | KB 查找策略 |
|---|---|
| **本体/语义/同义词/维度/ind-指标/血缘/规范类知识（第 0 优先 · 2026-10-27）** | **`mcp__weknora-1ba3462b__search_knowledge`** 按前缀定向检索（`ONT-本体-*` / `SEM-语义-*` / `IND-指标-*` / `DOM-域-血缘-*` / `REF-规范-*`），命中后引用并标注「口径来源：weknora KB」；**禁止**把本体语义知识硬编码作答。编码/表名用 `mode=keyword`，口径定义用 `mode=semantic`，深度问答用 `ask` |
| **表结构/字段类型/主键/中文名（第 0 优先 · 2026-10-27）** | **weknora `DDL-表结构-<SCHEMA>`**：`search_knowledge`（query=`<表名>`，mode=`keyword`）→ 取字段列表（字段名/中文名/类型/长度/精度/可空/默认值）+ 主键。覆盖 96 schema / 9,167 表。**禁止凭记忆答字段，禁止 `SELECT *` 试探** |
| **存储过程/函数源码与加工逻辑（第 0 优先 · 2026-10-27）** | **weknora `PROC-过程-<域>-<过程名>`**：`search_knowledge`（query=`<过程名>`，mode=`keyword`）→ 取完整 DDL/SQL 源码。覆盖 GZPROD 55 + CBPROD 49 + OTHERPROD 1 + GZ01PROD 60 = 165 脚本 |
| 已知 ZB_CODE 的单指标问数 | ① weknora `keyword` 查 `ind-<ZB_CODE>`（全量 3,253 条指标信息）→ ② 经 `sg-db2-executor` 执行 DB2 SQL 精确查询 `T_ADS_DIM_GZ01`（取实时 SQL1/CREATER 对拍） |
| 已知中文指标名的问数 | ① weknora `keyword` 查同义词映射归一问法 → ② DB2 SQL 模糊查找 `T_ADS_DIM_GZ01` → ③ Grep 血缘文档 |
| 根因分析/溯源 | ① DB2 SQL 查 T_ADS_DIM_GZ01 取 SQL1+CREATER → ② Grep 血缘文档取完整链路 SQL → ③ Read 管枢/成枢域知识文档取加工逻辑 |
| **成本域问数（2026-10-27 修订）** | **① 首查 `knowledge/domains/cbprod/CBPROD_指标配置清单.md`**（269 指标，16 字段元数据：业务定义/统计口径/取数逻辑/血缘/归属部门，按 T1-T9 九大主题分组）→ ② 取「指标编码 + 统计口径 + 取数逻辑 + 血缘链路」→ ③ 交 `sg-db2-executor` 取数 → ④ **必读**《三钢成本域与利润域_数据口径与计算链路权威手册》校验口径六要素 → ⑤ 交付。⚠️ **成本域指标不在 `T_ADS_DIM_GZ01` 中**（实测 0 条），禁止只查 GZ01 就判定"无数据" |
| **跨域共有业务词（2026-10-27 新增 · 强制双域并行）** | 命中 `产量`/`用量`/`消耗`/`料耗`/`库存`/`单耗`/`成本`/`单价` 等跨域共有词时，**必须双域并行检索，不得只返回单域**：<br>**① 生产域**：`sg-db2-executor` 查 `T_ADS_DIM_GZ01`（ZB_NAME LIKE）→ 生产口径指标<br>**② 成本域**：查 `CBPROD_指标配置清单.md` + `SMBB_M_A_CB01.T_ADS_SRV_CACA_DAY_COST` / `SMBB_M_S_CB00.T_DWS_FACT_CBZX_CACA_CENTER_COST` → 成本口径指标<br>**③ 双域对拍**：产量/消耗若两域不一致，按权威手册 §14 标注「生产口径 vs 成本口径」差异原因，禁止择一隐藏 |
| 报表导出前口径确认 | DB2 SQL 查 T_ADS_DIM_GZ01 + Grep 血缘文档确认指标口径（翰枢专属步骤）；成本报表另需读 `CBPROD_指标配置清单.md` |

### 其他分支路由
| 诉求关键词 | 路由 |
|---|---|
| **驾驶舱报告 / 生产经营驾驶舱 / cockpit / 集团经营总览 / 一屏经营** | **强制 `sg-insight` + `sg-cockpit-report`**：四域（生产/成本/存货/标准成本对比）+ 36 项勾稽闸门 + 四层下钻 + 39 项验收；**禁止走 `sg-kanban-builder`（无闸门）或 `sg-report-composer`（无四域口径）** |
| 看板/仪表盘（**不含"驾驶舱"字样**） | sg-insight `sg-kanban-builder` |
| **双盲交叉验证 / A-B 路对拍** | 按 `agents/references/disciplines.md §13.2` 配对（**均为在册专家**）：SQL 验证 `sg-development` ↔ `sg-metadata`；数据分析 `sg-quality` ↔ `sg-cbprod`／`sg-gzprod`；知识检索 `sg-semantic` ↔ `sg-metadata`。**禁止派退役成员（秦逸/赛奇/瑞卡/迅达）** |
| 5S 平台建数 / 维度建模 / 任务编排 | sg-5s-dev `sg-5s-dw-modeling`（16 步 ODS→CDM→ADS→API） |
| 5S 平台报错 / 页面导航 / 规范合规 | sg-5s-qa `sg-5s-qa-assistant` |
| **ECharts 不可用 / 要求零依赖 / 内网无 CDN / 纯 SVG 报告** | `sg-insight` 走 **纯 SVG 降级**，样式与图元复用 `sg-cockpit-report`（见该技能 `references/纯SVG降级规范.md`）；**禁止因缺图表库退化为"纯数据表格报告"** |
| 报告/docx/HTML 报告 | sg-insight `sg-report-composer` |
| 成本/利润/边际贡献/保本线/科目构成/吨材成本/工序成本 | **强制 `sg-cbprod-warehouse` v2（成本域口径决策树）**：利润/边际贡献→`SMBB_M_A_CB01.T_ADS_SRV_CACA_SIDE_COST`（V1+DT4+RC2），成本→PRODUCT_COST÷PRODUCT_EARN（V1+DS3）；**禁止查 T_ADS_DIM_GZ01 判定无数据** |
| 库存/存货/存货日管控/库龄/周转天数/合理·异常库存/资金占用 | **存货日管控域**：K7 指标口径 + K2 加工逻辑 + K1 表结构（T_DWD/DWS_FACT_ZZCH_ZH_*）；**禁止查 T_ADS_DIM_GZ01 判定无数据** |
| 数据类问数/取数（**非成本/存货域**的数据任务） | **先走「KB 检索路由」取口径卡**，再 **sg-insight（明鉴）+ sg-zhishu-report-composer（若溪）联合**：任务最终结果产出后，**优先以 HTML 可视化分析报告交付**（富交互：趋势图 + 多图表组件 + 分析文案 + 点击下钻；并按用户提问内容自动叠加分基地柱状/堆叠、占比饼环、贡献度拆解、帕累托、异常检测、多厂对标、同比环比等多种图表组件）；下钻须追到最源头 ODS 并展示该层所有下钻明细数据行 |
| 日报/成本日报 | sg-insight `sg-production-report-auto` / `sg-cost-ops` |
| 数据不对/为什么/追根溯源/看明细 | **先走「KB 检索路由」取完整血缘链路**，再 **sg-quality `sg-root-cause-fullchain`**：用数据链路下钻（T_ADS_DIM_GZ01→SQL1→CREATER→存储过程→ODS）溯源到指标数据值最源头，并展示所有下钻数据的所有明细数据行 |
| 成本异常/批处理 | sg-quality `sg-cost-ops` / `sg-cost-ops` |
| 库存/存货/存货日管控/库存周转天数/库龄/合理库存/异常库存/资金占用/库区分布 | **先走「KB 检索路由」：** weknora **K2** 检索「存货日管控：*」（加工逻辑 P_DWD_FACT_ZZCH_ZH_* + 查询SQL），**K1** 查目标表结构 T_DWD/DWS_FACT_ZZCH_ZH_*；口径核验派 sg-semantic，加工逻辑/血缘派 sg-metadata；取数经 sg-db2-executor；详见 `knowledge/kb/库存管理_存货日管控_知识库文档.md` |
| SQL/存储过程/优化 | sg-development |
| 表结构/字段/血缘 | sg-metadata |
| 口径/语义/指标定义 | sg-semantic（**铨度先 weknora `SEM-语义-*` 检索取口径卡，再查 T_ADS_DIM_GZ01 实表**） |
| 业务逻辑/本体/计算过程 | sg-ontology（**鼎元先 weknora `ONT-本体-*` 检索实体与关系，本体内容一律走知识库**） |
| 权限/安全/分级 | sg-governance |
| 经常做/固化成技能 | sg-skill-evolution |
| 评测/回归 | sg-quality `sg-eval-harness` |
| 资产漂移/变更清单 | sg-metadata `sg-metadata-core` |
| 批量注册/指标分级 | sg-semantic `sg-semantic-batch-register` |
| 本体资产初始化/契约 | sg-ontology `sg-ontology-asset-bootstrap` |
| 做领域技能/需求转本体 | **sg-ontology-app-builder** |
| 指标体系/指标构建/补建指标/血缘定义 | **sg-metric-builder** `sg-indicator-system` |
| 生产管制域表结构/血缘/加工逻辑/JOIN/指标全链路 | **先走「KB 检索路由」：** Read `管枢_生产管制域GZPROD_知识库文档.md`（生产域主责管枢的域知识）；细粒度检索派 **sg-gzprod 管枢**，复用其域技能 `sg-gzprod-warehouse` |
| 成本域表结构/血缘/加工逻辑/JOIN/指标/期间口径 | **先走「KB 检索路由」：** Read `成枢_成本域CBPROD_知识库文档.md`（成本域主责成枢的域知识）；细粒度检索派 **sg-cbprod 成枢**，复用其域技能 `sg-cbprod-warehouse` |
| 报表导出/下载/发我/发到群里（生产管制报表 ZZGZ / 成本报表 CBMS 等） | **先走「KB 检索路由」确认口径**，再派 **sg-wecom-doc 翰枢**（已并入原迅达 Swift 的报表导出与企微投递能力），详见「报表导出与投递路由（强制）」 |
| 命中已固化指标直查（免编译，秒级） | **sg-materialized-sql** |
| 记忆备份/预编译缓存/技能封装/清单维护 | **sg-memory** `sg-memory-engine` |
| 体系外指标/即席建表问数（兜底） | **sg-memory** → `sg-adhoc-indicator` |
| 调用链复盘/性能纪律/健康度 | **sg-supervisor** `sg-task-flow-report` |
| 多源SQL/数据库连接/文件取数 | **sg-development 淬锋**（承接原秦逸 Quinn 的多源 SQL 分析）`sg-analysis-engine` |
| Python统计/ML/数据科学分析 | **sg-quality 砺真**（承接原赛奇 Sage 的统计/数据科学分析）`sg-analysis-engine` |
| 文档问答/知识检索/RAG | **sg-semantic 铨度**（承接原瑞卡 Rika 的知识检索）`sg-analysis-engine` |
| 图表/数据画像/可视化 | **sg-zhishu-dashboard-designer** `sg-analysis-engine` |
| 多源综合分析/正式报告 | **sg-zhishu-report-composer** `sg-analysis-engine` |

<!-- SG-KB-ROUTE v1 · 2026-10-10 -->
<!-- SG-REPORT-ROUTE v1 -->
