---
name: sg-adhoc-indicator
description: "三钢数仓智脑：即席指标构建引擎。当用户临时询问指标体系（indicator_registry / indicator_system）之外的指标时，先读取业务存储过程、DDL 表结构与 ODS 源表：已有 DWD/DWS 则直接引用，否则重写 DSL 与 SQL 构建对应 DWD/DWS（必要时用 ADS）；先以可视化方式向用户展示计算结果，再并行调度各专家把该指标固化为本体/语义层/指标体系资产。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, adhoc, indicator-build, dwd, dws, on-demand]
owner: sg-memory
---

# sg-adhoc-indicator · 即席指标构建（体系外指标兜底）

## 定位

指标体系（`indicator_registry.json`，6155 指标）与语义层、`ind-<ZB_CODE>` 封装技能**覆盖不到**的用户临时问数，
由本技能兜底。**首查可接受较慢（实时编译 + 按需建表），但二次命中须转直查。**

> 优先级链（见 `sg-memory-engine`）：① 既有技能 `ind-<ZB_CODE>` → ② `sg-materialized-sql` 物化直查 →
> ③ `sg-dsl-compiler` 实时编译 → ④ **本技能 sg-adhoc-indicator（即席构建）**。

## 触发条件

进入本技能前，**必须**先判优先级：
1. 问数意图抽出的业务词 → 查 `indicator_registry.json`（按 `zb_name`/`zb_code`/`alias`）→ 命中 → 转 `sg-materialized-sql`。
2. 查 `knowledge/design/skill_inventory.json` → 命中 `ind-<ZB_CODE>` 或领域技能 → 直接调用。
3. 仅语义层（`sg-semantic`）注册但无物化 SQL → 转 `sg-dsl-compiler`（mode B 实时编译）。
4. **以上都不中** → 进入本技能（体系外指标）。

## 即席构建流程（八步）

```
1. 资产盘点（只读 RAG + 本地）
   - 业务存储过程：本包 knowledge/design/indicator/source/procs/ 下的 GZPROD/CBPROD/OTHERPROD/*.sql
   - DDL 表结构：本包 knowledge/design/indicator/source/ddl/ 下的表结构
   - ODS 源表：SMBB_M_O_*（生产管制 ODS）的物理字段与口径
   - 知识库：knowledge/observed/{schema,procedures,lineage}
2. 指标定义澄清
   - 用 sg-semantic 的口径/同义词能力，把用户口语映射为业务实体 + 度量 + 维度 + 时间粒度
   - 若口径模糊，向用户澄清（不臆测）
3. 复用判定
   - 目标指标能否由**已有 DWD/DWS 表**直接算出？→ 是 → 跳到 5（直接引用）
   - 否 → 进入 4（按需建表）
4. 按需构建 DWD/DWS（必要时 ADS）— **SQL 准确性护栏（2026-11-02 · E11 强制）**
   - **只允许写 DSL（声明式）**：模型产出「源 ODS / JOIN / 聚合 / 分区键 / 时间窗口」的 DSL 描述
   - **禁止裸写裸出**：最终可执行 SQL **必须**由 `sg-dsl-compiler`（mode B）编译生成，**禁止模型直接产出 SQL 文本并执行**
   - **三查强制（缺一不可）**：① 语法（DB2 方言合法性）② 表存在性（对照 9167 DDL 校验表与字段）③ 合理性（分区条件注入 + 返回量级）
     → **任一不通过：修正后重编译，不得产出「看起来能用」的 SQL**
   - 过 `sg-quality` 可靠性闸门（非空 / 量级合理 / 同比环比可解释）→ **不通过不得交付**
   - 优先级：复用 DWS > 新建 DWD > 落 ADS 临时表（不污染主模型，命名带 _ADHOC 后缀）
   - 仅只读/建临时表，过 sg-governance 护栏
5. 计算执行
   - 交 sg-db2-executor 执行（DB2 MCP 优先，REST 需用户自备 token）（或建临时表后查询）
   - sg-quality 可靠性闸门对账（非空/量级合理/同比环比可解释）
6. 优先可视化展示（首查即给用户看）
   - 先用 sg-insight 把结果渲染为**数据表 + 轻量图表/口诀卡**直接展示给用户
   - **强制标注（三标签齐全，缺一不得交付）**：**「即席构建·未注册·待实据核验」**
     → 含义：该数值**未经反向实据血缘核验**，不得当作确定值引用；固化并核验后方可按确定值口径呈现
   - 同时标注"本次为实时编译 + 按需建表，下次将转为固化指标"
7. 并行固化（把即席沉淀为永久资产，下一次直查）
   并行调度：
   - 鼎元 sg-ontology：补本体子图 + 业务逻辑（存储过程/计算链）
   - 铨度 sg-semantic：注册语义口径（certified/draft）
   - 矩衡 sg-metric-builder + sg-indicator-system/engine/import_gz01.py：
       * 若可纳入 T_ADS_DIM_GZ01 → 补 SQL1/SQL2 重新固化
       * 否则写入 knowledge/design/indicator 的本地扩展指标（indicator_system.json 的 extended[]）
   - 铭枢 sg-memory：触发封装 `ind-<临时CODE>` 技能 + 登记 skill_inventory.json
8. 回写与通知
   - 把新指标登记进 indicator_registry（local-extended 区，区别于全量固化）
   - 报告：本次构建的 DWD/DWS 表名、SQL 路径、已沉淀的本体/语义/指标资产、下次直查路径
```

## 资产读取路径（真实落地）

| 资产 | 路径 | 用途 |
|---|---|---|
| 业务存储过程 | 本包 `knowledge/design/indicator/source/procs/{GZPROD,CBPROD,OTHERPROD}/*.sql` | 业务逻辑 / 计算口径 / 建表顺序 |
| DDL 表结构 | 本包 `knowledge/design/indicator/source/ddl/` | 96 张表字段、主键、分区 |
| ODS 源表 | DB2 `SMBB_M_O_*` | 最细粒度原始数据 |
| 语义注册 | `knowledge/design/semantic/` | 已有口径/同义词 |
| 指标注册 | `knowledge/design/indicator/indicator_registry.json` | 复用判定 |

> 本包内置 `knowledge/design/indicator/source/` 为权威业务资产基线（DB2_ASSETS_HOME 可覆盖）；DB2 MCP 为实时核验通道。

## 输出规范

```json
{"mode": "adhoc-build",
 "indicator_name": "用户描述的指标",
 "reuse_decision": "reuse_dws | build_dwd | build_dws | build_ads_temp",
 "built_objects": [
   {"type": "DWS", "table": "SMBB_M_S_XX.T_DWS_。.", "sql_file": "。."},
   {"type": "ADS_TEMP", "table": "SMBB_M_A_XX.T_ADS_。._ADHOC", "sql_file": "。."}
 ],
 "visualization": {"type": "table+chart", "rendered_by": "sg-insight"},
 "固化资产": {"ontology": true, "semantic": true, "indicator_registry": "local-extended", "skill": "ind-<CODE>"},
 "next_query_path": "materialized | ind-skill",
 "compile_log": {"template": "live", "checks": {"syntax":"pass","table_exists":"pass","reasonable":"pass"}, "compiled_by": "sg-dsl-compiler(mode B)", "quality_gate": "sg-quality pass"},
 "annotation": "即席构建·未注册·待实据核验",
 "confidence_note": "设计态推导，置信度低于反向实据血缘；固化 + 实据核验后方可按确定值引用"}
```

## 与智能问数的衔接

- 本技能产物（DWD/DWS 表 + 固化 SQL）**必须**回流到 `indicator_registry` / `ind-<CODE>` 技能，
  使该指标从"即席慢查"升级为"物化直查"。
- 回流后，编排器下次遇到相同问数 → ①/② 命中 → 不再进入本技能。

## 注意事项

1. **可视化优先**：首查也必须先给用户看结果，不憋到最后；标注即席性质。
2. **不污染主模型**：即席建表仅限 `_ADHOC` 后缀临时表或本地 extended 区，禁止改写既有 ODS/DWD/DWS 生产表。
3. **护栏不可绕过**：建表/查询仍过 `sg-governance` 四层护栏 + `sg-quality` 闸门（卡点）。
4. **资产必须回流**：即席结果不沉淀等于重复劳动；固化失败也须登记 `unresolved` 并回执用户。
5. **双重保真**：口径以真实资产（DDL/存储过程/ODS）为准，不臆测；与数据态冲突时升级编排器。
6. **禁止裸写裸出（2026-11-02 · E11）**：即席场景模型只能产出的**DSL 声明**，SQL 必须经 `sg-dsl-compiler` 编译并过「三查」+ `sg-quality` 闸门；禁止直接写出并执行未经编译校验的 SQL。
7. **交付三标签（2026-11-02 · E11）**：即席结果交付**必须**带「即席构建·未注册·待实据核验」，禁止以确定值口径呈现。
8. **确定性编译张力消解（2026-11-02）**：即席 ≠ 允许临场发挥 SQL。模型发挥空间**仅限于 DSL 声明**（选表 / 定聚合 / 定维度），**SQL 文本本身仍由编译器确定性生成**——以此保证准确率不崩塌，契合 `sg-dsl-compiler`「确定性编译」铁律。
