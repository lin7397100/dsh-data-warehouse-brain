# KB-First 协议 · 知识库优先搜索与物化SQL直用

> **生效日期**：2026-11-13 | **定位**：GATE-0.5 门禁（GATE-0 健康自检后、GATE-1 判型前执行）
> **原则**：任何 DB2 SQL 到达数据库之前，必须先完成 KB 召回 → 物化 SQL 判定 → 回退 DSL 编译的**三层决策**。

---

## 三层决策模型

```
用户问数
  │
  ▼
L0 · KB 召回（WeKnora + 本地 indicator_registry.json）
  ├─ 命中且 materialized_sql_file 非空 → 直接执行物化 SQL（省 DSL+编译）
  ├─ 命中且 sql1 有内容 → 使用 sql1（替换时间占位符后执行，免实时编译）
  └─ 未命中 → 转入 L1
      │
      ▼
L1 · DB2 实表查询（T_ADS_DIM_GZ01）
  ├─ 找到 ZB_CODE → DSL 声明 → 淬锋编译 → 执行
  └─ 未找到 → L2 回退（caliber_check.md 五级回退链）
```

## 知识库清单（WeKnora MCP 可检索）

| kb_id | 名称 | 内容 | knowledge_count |
|-------|------|------|-----------------|
| `227f0a01-c36b-488a-8049-5b5869175782` | 数仓智脑专家团-指标体系库 | 6182 条指标注册记录 + 物化 SQL | 大量 |
| `存储过程库` | 数仓智脑专家团-存储过程 | 253 个 DB2 存储过程源码 + 知识图谱 | 253 |
| `表结构库` | 数仓智脑专家团-表结构 | 9167 张表 DDL + schema 信息 | 大量 |
| `d12f3c32-bf50-41cc-8be8-77af4c45bb35` | 5S 知识库（K7） | 5S 平台操作知识 | 待确认 |

## L0 · KB 召回执行步骤（Agent prompt 中必须包含）

### Step 0.1：WeKnora 混合检索

使用 `mcp__weknora-admin__hybrid_search` 在指标体系库中检索：

```json
{
  "kb_id": "227f0a01-c36b-488a-8049-5b5869175782",
  "query": "<业务术语 + 用户原话，如：'三明闽光 热装率 ZB_CODE 日统计'>",
  "match_count": 10
}
```

### Step 0.2：本地 indicator_registry.json 精确匹配

读取 `<包根>/knowledge/design/indicator/indicator_registry.json`，Grep 匹配 ZB_CODE 或 ZB_NAME：

```bash
# 方式1：Bash Grep 精确匹配（推荐，快）
python -c "
import json
with open('<包根>/knowledge/design/indicator/indicator_registry.json', encoding='utf-8') as f:
    reg = json.load(f)
matches = [i for i in reg['indicators']['indicators'] if '<关键词>' in i.get('zb_name','')]
for m in matches:
    print(f\"ZB_CODE={m['zb_code']} | {m['zb_name']} | sql1={'有' if m.get('sql1') else '无'} | materialized={'有' if m.get('materialized_sql_file') else '无'}\")
"
```

### Step 0.3：判定分支

| 条件 | 动作 | 省去步骤 |
|------|------|----------|
| `materialized_sql_file` 非空 | 读 `<包根>/knowledge/design/indicator/materialized_sql/<ZB_CODE>.sql`，替换时间占位符后直投 DB2 | **DSL + 编译** |
| `materialized_sql_file` 为空但 `sql1` 有内容 | 使用 `sql1` 替换 `$TD$`/`$D4$` 等占位符后执行 | **编译** |
| `sql1` 也为空 | 转入 L1：查 T_ADS_DIM_GZ01 → DSL 声明 → 淬锋编译 | 无，走完整链路 |

### Step 0.4：双码体系交叉核验

⚠️ 部分指标存在两套 ZB_CODE 体系（如热装率 1600xxx vs 8000xxx）。KB 检索时必须：
1. 分别用两套编号体系检索
2. 对比 `zb_name` 和 `factory_div` 确认是否为同一指标的不同编码
3. 标注编码体系来源："本部经营日报(160xxx)" vs "三钢闽光能源(800xxx)"

## L1 · DB2 实表查询（仅当 L0 未命中时）

当 KB 和 registry 都未命中时，转入 DB2 查询：

```sql
-- 注意：PROD_UNIT_CODE 需限定本部范围（不含泉州/罗源）
SELECT ZB_CODE, PROD_ITEM_CODE, PROD_ITEM_NAME, PROD_UNIT_CODE, TABLE_NAME, SQL1
FROM <schema>.T_ADS_DIM_GZ01
WHERE PROD_ITEM_NAME LIKE '%<关键词>%'
```

## 编排器派发 Agent 时的强制指令

编排器在派发取数 Agent 时，**prompt 中必须包含以下 KB-First 指令**：

```
### KB-First 强制前置步骤（不可跳过）

在执行任何 DB2 查询之前，必须先完成：

1. **WeKnora 检索**：调用 hybrid_search(kb_id="227f0a01-...", query="<业务描述>") 
   在指标体系库中搜索指标 ZB_CODE、口径定义

2. **本地 Registry 匹配**：读取 indicator_registry.json，Grep 匹配指标名称
   - 命中 materialized_sql_file → 直接使用物化 SQL（替换 $TD$ 后执行）
   - 命中 sql1 → 使用 sql1 执行（免编译）
   - 未命中 → 才能去 DB2 查 T_ADS_DIM_GZ01

3. **多码体系交叉核验**：如存在 16xxxx 和 80xxxx 两套编码，均检索并对比

4. **返回格式**：必须报告 KB 检索结果（命中/未命中、使用的 SQL 来源）
```

## 违规检测（编排器自检）

派发 Agent 前自查：
- □ Agent prompt 中是否含 "WeKnora hybrid_search" 或 "indicator_registry.json"？
  - 否 → **标 [KB-First 缺失]**，禁止派发
- □ 如果 KB 已命中物化 SQL，Agent 是否仍然去 DB2 查 T_ADS_DIM_GZ01？
  - 是 → **标 [冗余 DB2 查询]**，记录但不阻断