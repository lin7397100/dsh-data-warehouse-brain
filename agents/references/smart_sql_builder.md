# 智能 SQL 自构建引擎（Smart SQL Builder · 2026-11-16 v1.0）

> 场景：用户问一个指标，但该指标**零物化 SQL、零存储过程、零已有计算链**。
> 本文件规定专家团如何在仅有 ODS 表结构的情况下，自主完成 ODS→DWD→DWS→ADS 全链 SQL 构建。
> 主责：淬锋 sg-development（编译）+ 矩衡 sg-metric-builder（公式）+ 构枢 sg-ontology-modeler（JOIN 键）。

## 一、构建入口判定（什么时候走自构建）

| 情况 | 做法 |
|---|---|
| IntentContract.materialization_status = `unmaterialized` | 先查是否有可用 DWD/DWS/ADS → 有则直接从最高层编译；**无则触发自构建** |
| 铨度 MQL 中 `sources` 为空（找不到能用的表） | 强制从 ODS 构建 |
| 用户明确说"这个指标以前没有，帮我自己写 SQL" | 强制从 ODS 构建 |
| 用户说"我问的是 X，但现有的 DWS 表口径不对" | 不从现有表取，重新从 ODS 构建新的 DWD→DWS |

## 二、构建全流程（7 步，每步产出给用户确认）

```
Step 0: 溯源 — 找出 ODS 贴源表
   ├ 工具：SYSCAT.TABLES LIKE '%T_ODS%' + 域知识库 + 指标词典
   ├ 产出：候选 ODS 表清单（表名/字段数/行数/最新日期）
   └ 用户选择：用哪张（或多张）

Step 1: DWD 设计 — 清洗 + 统一口径
   ├ 分析 ODS 字段 → 哪些保留/丢弃
   ├ 定义清洗规则：NULL→? 去重? CODE→NAME 映射?
   ├ 设计 DWD SQL（基于第一节模板）
   ├ 产出：DWD SQL + 字段说明表
   └ 用户确认 ✓

Step 2: DWS 设计 — 聚合 + 派生指标
   ├ 确定维度（GROUP BY 列）
   ├ 确定度量（SUM/AVG/COUNT/DISTINCT）
   ├ 派生指标公式（分子/分母/单位）
   ├ 必带过滤（IS_VALID、排除合计码）
   ├ 产出：DWS SQL + 派生指标公式
   └ 用户确认 ✓

Step 3: ADS 设计 — 格式化 + 交付
   ├ 格式化（ROUND/单位转换）
   ├ 排序/TOP N
   ├ 同比/环比（窗口函数）
   ├ 产出：ADS SQL
   └ 用户确认 ✓

Step 4: 执行 — 只读执行 ADS SQL
   ├ 护栏：只读检查 + 行数上限 + 分区必带
   └ 出错 → 诚实报告，不降级

Step 5: 数据交付 → 用户预览
   ├ 展示前 50 行 + 汇总统计
   └ 用户评价：可用 / 需修改

Step 6: 物化 — 用户确认可用后固化
   ├ 走 sg-sql-materialization 六步闭环
   ├ SQL 存 materialized_sql/
   ├ DSL 注册到 indicator_registry.json
   ├ 同步 WeKnora K3 指标库
   └ 记忆写 K8：「指标 X 已从 ODS 构建并物化」
```

## 三、每一步的 LLM 提示约束

### Step 0 约束（ODS 发现）
- **只查 SYSCAT.TABLES 和 SYSCAT.COLUMNS，不编造表名**
- 候选表必须按「字段覆盖率」（目标指标所需字段命中率）排序
- 若无匹配 → 如实报「当前 ODS 无对应来源表」，不猜测

### Step 1 约束（DWD 设计）
- 字段显式列出，禁用 `SELECT *`
- 清洗规则逐列说明原因
- JOIN 字典表前确认字典表存在（查 SYSCAT.TABLES）
- NULL 处理不能一刀切：度量类 NULL→0 常见，维度类 NULL 保留

### Step 2 约束（DWS 设计）
- SUM 前确认该度量「可加」（收入/产量→可加；单价/比率→不可加）
- AVG 前确认是否需要先 DISTINCT（如"日均客户数"要先按日+客户去重）
- 派生公式的分子分母必须同源（同 DWD 或同 grain 的 DWS）
- 过滤条件**不能放到 HAVING**（那是聚合后过滤），必须在 WHERE（聚合前）

### Step 3 约束（ADS 设计）
- 禁止在 ADS 层新增 GROUP BY
- 环比 LAG 的 ORDER BY 必须与 DWS 的 grain 一致
- ROUND 的精度对齐业务要求（成本→4 位，产量→2 位）

## 四、自构建 SQL 纠错四类（发现必改）

| 错误类型 | 表现 | 修正 |
|---|---|---|
| 可加性错误 | 对单价/比率做 SUM | 改为 AVG 或先 SUM(分子)/SUM(分母) |
| 基数膨胀 | JOIN 后行数翻倍 | 加 DISTINCT 或检查 JOIN 键基数 |
| 口径漂移 | 过滤条件写到 HAVING 去了 | 移到 WHERE |
| 层越界 | ADS 里出现 GROUP BY | 拆回 DWS |

## 五、与现有物化 SQL 的关系

- **已有物化 SQL** → 快车道秒级直查（`sg-materialized-sql`），不走自构建。
- **无物化但有 DWS/ADS 表** → 淬锋从 DWS/ADS 直接编译，不重建全链。
- **无物化也无 DWS/ADS** → **触发本文件的自构建流水线**。
- 自构建完成后 → **必须走物化闭环**（用户确认 → 双写 → 注册），下次就是快车道。

## 六、分步确认的门禁设计

每步产出的用户确认消息必须包含：
1. **本步的操作摘要**（一句话）
2. **产出物**（SQL 或表设计）
3. **风险提示**（如有，如"该 ODS 表 2026-10 后无新数据"）
4. **下一步预览**（"确认后我将进行 DWS 聚合设计"）
5. **三个选项**：✅ 确认 / ✏️ 修改（请说明） / ❌ 放弃

用户未点 ✅ 确认，**绝不进入下一步**。（与三令牌护栏的「确认令牌」绑定）