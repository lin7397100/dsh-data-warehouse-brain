---
name: sg-semantic-modeler
description: "三钢数仓智脑：语义层自动化建模引擎。从 DB2 SYSCAT、T_ADS_DIM_GZ01、WeKnora 和用户文档中自动抽取字段/指标/口径信息，经 sentence-transformers 向量化存入 Milvus/Qdrant，聚类生成同义词与标准名，注册到语义层并同步 WeKnora K3。支持增量更新与用户反馈触发。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, semantic, modeling, vector, milvus, embedding]
owner: sg-semantic-modeler
---

# sg-semantic-modeler · 语义层自动化建模引擎

## 定位
把 DB2 的物理结构（表/列/指标）与业务语义（口径/同义词/别名）之间的映射 **自动向量化 + 聚类 + 注册**，使 NL 查询能通过语义匹配秒级命中指标。与铨度（sg-semantic）分工：铨度设计语义层架构与口径核查，本技能执行自动化建模。

### v1.1 厚语义层四支柱自动抽取（2026-11-16 · 源自语义层调研）
权威规则：`agents/references/thick_semantic_layer.md`。本技能的抽取不能只做"表字段+同义词"，须覆盖四支柱：

| 支柱 | 自动抽取动作 | 数据源 |
|---|---|---|
| 关联体系 | 从 `SYSCAT.REFERENCES`/`ROUTINEDEP`/SQL JOIN 抽取关系 + 基数（1:1/1:N/N:M），产出 `relations.join_key` | DB2 元数据 + K2 过程 |
| 维度体系 | 抽取层级（年季月日/厂别/产线）、代码↔名称映射、计算维度、grain | SYSCAT.COLUMNS + K1 + K3 |
| 指标体系 | 抽取 family/version、计算表达式、`do_not` 反面说明（如"不要直接 AVG"） | T_ADS_DIM_GZ01.SQL1 + K3 |
| 业务词典 | 抽取 8 类词（实体/字段/聚合/比较/宏/字段簇/动词/常数词），每词指向已注册对象/指标，禁悬空 | 用户文档 + WeKnora SEM + 聚类同义词 |

**向量化策略升级**：除原 `指标名|口径|字段名|备注` 外，拼接 `同义词簇 + 维度层级路径 + 关系链路`，使向量空间承载厚语义（不仅字面相似）。
**确定性优先**：向量匹配只做"召回候选"，最终口径裁决归铨度按本体规则确定——**召回可概率，裁决必确定**。
**边用边建**：从高频指标+核心表开始，配置一个→验证一个→上线一个；每批触发 `sg-eval-harness` 回归，准确率下降 >2pp 回退。

## Pipeline 四步（不可跳过）

### Step 1 · 数据源抽取
```python
# DB2 字段抽取（ibm_db 直连，见 references/db2_extract.py）
SELECT TABNAME, COLNAME, TYPENAME, LENGTH, REMARKS
FROM SYSCAT.COLUMNS WHERE TABSCHEMA='SMBB_M_A_GZ01' — 生产域列

# 指标注册抽取
SELECT ZB_CODE, ZB_NAME, FACTORY_DIV, SQL1, CREATER
FROM T_ADS_DIM_GZ01 WHERE ZB_CODE IS NOT NULL  — 指标基线

# WeKnora 已有语义知识检索
mcp__weknora-admin__hybrid_search("SEM-语义-*")  — 已有同义词/口径

# 用户上传文档解析（MinerU API 10.233.2.32:8112）
POST /parse {file: "口径维护手册.pdf"} → 结构化文本
```
- **铁律**：域前置分流——成本域先查 CBPROD schema（`SMBB_M_S_CB00`），生产域先查 GZPROD。
- 大表分批抽取，每批 ≤500 行，避免 DB2 超时。

### Step 2 · 向量化
```python
# sentence-transformers（已安装 5.6.0）
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-large-zh-v1.5', cache_folder='/data/models')
embeddings = model.encode(texts, batch_size=64, normalize_embeddings=True)
```
- 模型首次下载约 1.3GB，缓存在 `/data/models/`。
- 每 batch 64 条，可并行。三类文本字段拼接：`"指标名 | 口径描述 | 字段名 | 备注"`。

### Step 3 · 向量存储与聚类
```python
# Milvus 批量插入（pymilvus 3.0.0, host=10.233.2.32:19530）
from pymilvus import Collection, connections
connections.connect(host='10.233.2.32', port=19530)
collection = Collection('semantic_indicators')
collection.insert(records)  # [{id, zb_code, zb_name, embedding, ...}]
collection.flush()
collection.create_index('embedding', index_type='IVF_FLAT', metric_type='COSINE')

# 语义聚类（余弦距离）
from sklearn.cluster import DBSCAN
clusters = DBSCAN(eps=0.15, metric='cosine').fit_predict(embeddings)

# Qdrant 混合检索辅助（gRPC 6334）
from qdrant_client import QdrantClient
qdrant = QdrantClient(host='10.233.2.32', port=6334)
qdrant.upsert('semantic_cache', points)
```
- **铁律**：Milvus 是主存储，Qdrant 是检索加速缓存；禁止跳过 Milvus 直写 Qdrant。
- 聚类阈值 eps 可调（0.10=严格 / 0.20=宽松），默认 0.15。

### Step 4 · 语义注册与同步
```python
# 同义词自动生成规则
for cluster in clusters:
    canonical = cluster[0].zb_name  # 最长/最规范的那个
    synset = [c.zb_name for c in cluster]
    # 注册到 indicator_registry.json
    registry[canonical.zb_code]['synonyms'] = synset
    
# 写回本地语义层 CSV
semantic_csv.append({zb_code, canonical_name, synset, domain})

# WeKnora K3 同步
mcp__weknora-admin__create_knowledge_from_text(
    kb_id='227f0a01-c36b-488a-8049-5b5869175782',
    title='SEM-语义-{domain}-{zb_code}',
    content=json.dumps(semantic_entry)
)
```
- openai 辅助校验仅在同义词群 confidence<0.7 时调用，减少 API 开销。
- 增量：只处理新增/修改的指标，已注册的不覆盖。

## 增量更新触发条件
| 触发 | 动作 |
|---|---|
| `knowledge/observed/schema/` 有新快照 | 全量增量对账（新表→向量化→注册） |
| 用户说「XX 的同义词应该是 YY」 | 追加 synset → upsert Milvus/Qdrant → 注册表更新 |
| WeKnora 新增 SEM-语义-* 文档 | 解析 → 合并到对应 ZB_CODE synset |
| 铨度修正了某个指标口径 | 全量重跑该 ZB_CODE 的向量聚类 |

## 工具连接速查
| 工具 | 地址 | 凭据 | 备注 |
|---|---|---|---|
| DB2 | SGPROD1 | ibm_db + 5sApi token（从企微智能表格取） | 只读 SELECT |
| Milvus | 10.233.2.32:19530 | WeKnora-milvus（docker 内网） | pymilvus 3.0.0 |
| Qdrant | 10.233.2.32:6333/6334 | WeKnora-qdrant | 混合检索辅助 |
| WeKnora API | 10.233.2.32:9081 | 同 K3 kb_id | 知识库同步 |
| MinerU | 10.233.2.32:8112 | 无 | 文档解析 |
| s-bert | 本地 | 无 | BAAI/bge-large-zh-v1.5 |
| openai | WeKnora-app 内 | WeKnora 已配置 | 辅助校验 |

## 输出规范
- 主产物：语义注册 PDF 报告（含新注册指标数/同义词数/聚类覆盖率）
- 持久化：`knowledge/design/semantic/semantic-{domain}.csv` 更新
- 同步：WeKnora K3 新/改文档数

## 注意事项
1. 本技能与 `sg-semantic` 铨度的分工：铨度定义语义层架构与口径规则，你执行向量化与自动注册。
2. 首次全量跑建议分批（每域 30 分钟），持续增量秒级。
3. 模型下载失败或 Milvus 不可达时，降级到本地 FAISS 内存索引，标注 [降级矢量索引]。
4. 禁止把 AI 推断的同义词当作确定口径——conf<0.8 的同义词标注 [AI推断-待人工确认]。