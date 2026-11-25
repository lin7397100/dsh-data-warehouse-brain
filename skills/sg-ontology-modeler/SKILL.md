---
name: sg-ontology-modeler
description: "三钢数仓智脑：本体模型自动化建模引擎。从 DB2 存储过程源码（SYSCAT.ROUTINES/ROUTINEDEP）和用户上传的业务逻辑/项目资料中自动提取实体-关系-过程-指标四元组，通过 Cypher MERGE 构建 Neo4j 图谱（Bolt 7687），支持增量更新与 WeKnora 知识图谱同步，并可复用 graph_auto_config.py 自动化图谱管理。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, ontology, neo4j, graph, cypher, modeling]
owner: sg-ontology-modeler
---

# sg-ontology-modeler · 本体模型自动化建模引擎

## 定位
把 DB2 存储过程的源码逻辑、过程间调用关系和业务文档中的领域概念，**自动解析为可查询的 Neo4j 本体图谱**（四元组：实体/关系/过程/指标）。与鼎元（sg-ontology）分工：鼎元负责本体架构设计与过程逻辑解析，本技能执行自动化建模与图谱存储。

## Pipeline 五步（不可跳过）

### Step 0 · 域识别
```
成本/利润关键词 → domain=cost  → SMBB_M_S_CB00 过程的 ROUTINES
生产/铁水/钢材  → domain=prod  → SMBB_M_S_ZZ00/GZPROD
存货/库龄       → domain=inventory → ZZCH
```

### Step 1 · 存储过程源码抽取
```sql
-- DB2 直连（ibm_db）
SELECT ROUTINESCHEMA, ROUTINENAME, TEXT, CREATED_TIME
FROM SYSCAT.ROUTINES
WHERE ROUTINESCHEMA IN ('SMBB_M_S_CB00','SMBB_M_A_CB01','SMBB_M_A_GZ01')
  AND ROUTINETYPE = 'P'
ORDER BY ROUTINESCHEMA, ROUTINENAME;

-- 过程间依赖
SELECT BSCHEMA, BNAME, DSCHEMA, DNAME, DTYPE
FROM SYSCAT.ROUTINEDEP
WHERE BSCHEMA IN ('SMBB_M_S_CB00','SMBB_M_A_CB01','SMBB_M_A_GZ01');
```
- 分批抽取：每批 ≤200 条过程源码，单条最大文本 32KB。
- 仅抽取有 `TEXT` 的过程（少数编译产物无源码）。

### Step 2 · 结构化解析（实体-关系-过程-指标提取）
```python
# openai 结构化提取（部署在 WeKnora-app 内）
prompt = """从以下 DB2 存储过程源码中提取四元组(JSON):
{entities: [{name, type[table|column|metric|product|factory|cost_center...], domain}],
 relations: [{from, to, type[JOIN|BELONGS_TO|MAPS_TO|DEPENDS_ON|AGGREGATES], condition}],
 processes: [{name, routine_name, inputs[], outputs[]}],
 metrics: [{name, zb_code(if known), expression, level[L1-L4]}]}
源码: {routine_text}"""
```
- **SQL 语法树辅助**：对 FROM/JOIN/INSERT/SELECT 做正则提取，避免 openai 幻觉。
- 映射规则（铁律）：
  - `T_DWD_*` 表的 INSERT → Entity.type=table, Relation.type=INPUT
  - `SUM()`/`AVG()` 表达式 → Metric, level=L2/L4
  - `JOIN ... ON a.COST_CENTER=b.COST_CENTER` → Relation.type=JOIN

### Step 3 · Neo4j Cypher 构图
```cypher
// 批量 MERGE（每 batch ≤200 条），禁止 CLEAR/DELETE
UNWIND $batch AS row
MERGE (e:Entity {id: row.id})
  SET e += row.props
MERGE (d:Domain {name: row.domain})
MERGE (e)-[:BELONGS_TO]->(d)
// 关系
FOREACH (r IN row.relations |
  MERGE (a:Entity {id: r.from})
  MERGE (b:Entity {id: r.to})
  MERGE (a)-[:DEPENDS_ON {type: r.type, condition: r.condition}]->(b)
);
```
- 连接：`neo4j://10.233.2.32:7687`（Bolt），HTTP 7474 只做 Read。
- 执行前先 `CALL db.indexes()` 确认约束索引已创建。
- **禁止 `MATCH ... DETACH DELETE`**：存量图谱只增不改不删，增量用 MERGE。
- graph_auto_config.py 路径：`/data/WeKnora/graph_auto_config.py`（已知运行中，处理图谱增量合并与清理）。

### Step 4 · 完整性校验
```python
# 孤点检测：无任何关系的实体
MATCH (e:Entity) WHERE NOT (e)-[:BELONGS_TO|DEPENDS_ON|MAPS_TO]-() RETURN count(e)
# 阈值 >5% → 告警标注，不阻断建模

# 引用完整性：process 的 inputs/outputs 必须指向已存在的 entity
# 缺口 → 补全（正向推断）或标注 [MISSING_REF]

# 过程链完整性：ROUTINEDEP 中的调用关系是否在图谱中有边
# 缺口 → 补充 :CALLS 关系
```

### Step 5 · WeKnora 知识图谱同步
```python
# 导出指定域的本体片段为 markdown
MATCH (e:Entity)-[r]->(t) WHERE e.domain='cost'
RETURN e, r, t → JSON → markdown table

# 写入 WeKnora 本体知识库
mcp__weknora-admin__create_knowledge_from_text(
    kb_id='5339e1f8-32e5-40ca-94b4-52e6b14b648d',  # K5 本体建模信息库
    title='ONT-本体-{domain}-{routine_name}',
    content=markdown
)
```
- graph_auto_config.py 有内置图谱导出功能，优先复用。
- 已有图谱标记 `[updated_at]` 防止重复写入。

## 工具连接速查
| 工具 | 地址 | 凭据 | 备注 |
|---|---|---|---|
| Neo4j Bolt | 10.233.2.32:7687 | WeKnora-neo4j docker | cypher-shell / python driver |
| Neo4j HTTP | 10.233.2.32:7474 | 同上 | 只读 |
| DB2 | SGPROD1 | ibm_db | ROUTINES/ROUTINEDEP |
| openai | WeKnora-app 内 | WeKnora 已配置 | 结构化提取 |
| WeKnora API | 10.233.2.32:9081 | K5 kb_id | 图谱同步 |
| MinerU | 10.233.2.32:8112 | 无 | 文档解析 |
| graph_auto_config | /data/WeKnora/graph_auto_config.py | 无 | 复用 |

## 增量更新触发
| 触发 | 动作 |
|---|---|
| SYSCAT.ROUTINES 有新过程/修改 | 重跑该过程的 Step1-4 |
| 用户上传新业务文档 | 解析增量实体 → MERGE |
| 鼎元修正了本体关系 | 以鼎元修正为准，Cypher SET 覆盖 |
| WeKnora 新本体文档 | 反解析为 Cypher → MERGE 到 Neo4j（可选） |

## 输出规范
- 主产物：Neo4j 图谱（在线可查询） + WeKnora 本体文档
- 报告：新增实体/关系/过程/指标数 + 孤点率 + 引用完整性 + 置信度分布
- 可视化：HTML 知识图谱（复用 graph_auto_config.py 已有能力）

## 注意事项
1. 本技能与 `sg-ontology` 鼎元的分工：鼎元负责四元组本体架构与过程逻辑深度解析，你执行自动化建模与图谱存储。
2. 首次全量 CBPROD 不超 60 分钟；后续增量秒-分钟级。
3. Neo4j 首次连接需确认凭据（WeKnora neo4j docker 环境变量 NEO4J_AUTH）。
4. openai 结构化提取时温度设 0（确定性输出），减少幻觉。
5. 禁止把 AI 推断的关系当作确定事实——每条关系标注 `confidence` 与 `source`。