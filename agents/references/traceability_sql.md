### 数据溯源与口径核查（生产管制指标专用）

> 本节是问数正确性 ≥95% 的**取证底座**：生产管制指标的数据与业务逻辑，一律经 `SMBB_M_A_GZ01.T_PM_KPI` / `SMBB_M_A_GZ01.T_ADS_DIM_GZ01` / `SMBB_M_A_GZ01` 下相关 ADS 表取得；来源与过程经 **SQL1/SQL2 直接溯源** 与 **CREATER→存储过程** 两条路径交叉确认。所有 DB2 取数走 DB2 MCP 或 REST 接口（只读）。

**⓪ 厂别识别（根因分析前置 · 2026-10-13 定稿 · 由专家驱动，禁止硬编码）**

> 触发：2026-10-13 罗源钢铁料耗/铁水耗根因分析中，编排器未激活 sg-ontology/sg-supervisor，凭 schema 名称误判厂别。此后所有基地区分的分析必须走专家驱动流程。

**厂别识别由 sg-ontology 主导**，通过解析 CREATER 存储过程的 SQL 来确定，不可凭 schema 名称或炉座号臆断：

```sql
-- ① sg-semantic 取注册信息（T_ADS_DIM_GZ01）
SELECT ZB_CODE, FACTORY_DIV, ZB_NAME, SQL1, CREATER
FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01 WHERE ZB_CODE = '<编码>';

-- ② sg-ontology 实时拉取存储过程（SYSCAT.ROUTINES）
SELECT SUBSTR(TEXT, 1, 30000) FROM SYSCAT.ROUTINES
WHERE ROUTINESCHEMA='<schema>' AND ROUTINENAME='<CREATER>';
-- 解析 SQL 中的 FACTORY_DIV 过滤条件和 schema 使用方式

-- ③ sg-metadata 探测 ODS 表列结构（SYSCAT.COLUMNS）
SELECT TABNAME, COLNAME FROM SYSCAT.COLUMNS
WHERE TABSCHEMA LIKE 'SMBB_M_O_SGP%' AND COLNAME LIKE '%FACTORY%'
  AND TABNAME IN ('<涉及的表名>');
-- 确认哪些表有 FACTORY_DIV 列，哪些通过 schema 隐式区分

-- ④ 对有 FACTORY_DIV 列的表取分布快照（可选，验证厂别一致性）
-- 注意：并非所有 ODS 表都有 FACTORY_DIV 列（如 T_ODS_BASICM21），
-- 此时厂别由 schema 隐式确定，需与存储过程解析结果交叉验证。
```

**厂别判定优先级**（由高到低）：
1. 存储过程中显式的 FACTORY_DIV 过滤条件（如 `WHERE FACTORY_DIV='14'`）
2. 存储过程中 FROM 子句的 schema 选择（如 `FROM SGP3Z1.T_ODS_TMMSM21` → 对应罗源）
3. T_ADS_DIM_GZ01 中的 FACTORY_DIV 注册值（可能是文字名如"罗源闽光"）
4. ODS 表 GROUP BY FACTORY_DIV 的分布快照

> ⚠️ **严禁行为**：凭炉座号（Y/Z/M/S）或 heat_no 前缀硬编码映射。严禁跳过 SYSCAT.ROUTINES 查询直接下结论。sg-supervisor 必须在场监控无跨厂污染。

---

**① 取指标口径与溯源线索（T_ADS_DIM_GZ01）**

```sql
SELECT ZB_CODE, ZB_NAME, ZB_TYPE, UNIT, IS_VALID, SQL1, SQL2, CREATER
FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01
WHERE ZB_CODE = '<指标编码>' AND IS_VALID = '3';
```

- `IS_VALID`(VARCHAR1, col7)：**启用状态标志，仅 `IS_VALID = '3'` 为启用/有效指标**。实测分布：T_ADS_DIM_GZ01 共 6023 行，其中 `IS_VALID='3'` 仅 **3801** 行（`'0'`=20、`'1'`=60、空=4、NULL=2138 均非启用）。问数取数与对拍**必须加 `IS_VALID='3'` 过滤**，禁用态指标一律不参与计算，否则会引入脏数据拉低正确率。
- `SQL1`(VARCHAR500, col9) / `SQL2`(VARCHAR500, col10)：**指标真实计算 SQL**，是权威溯源依据；`SQL2` 常为占位 `' '` 或 `'无'`，仅 SQL1 有效时以 SQL1 为准。实测 **3801 个启用指标 100% 含有效 SQL1**，故 SQL1 直溯对拍对启用指标全覆盖、可行。
- `CREATER`(VARCHAR50, col11)：写入该指标的**存储过程线索**（详见 ③）。
- 实测：T_ADS_DIM_GZ01 共 **6023 行，其中 1972 行 CREATER 为空**，且 CREATER 形态混杂（见 ③ 容错）；故**绝不可单凭 CREATER 判定来源**，必须以 SQL1/SQL2 直溯为主、CREATER 为辅。

**② SQL1/SQL2 直接溯源与对拍（淬锋/sg-development 主责）**

- 替换日期 token 后**独立执行 SQL1**，将其结果作「溯源值」与主链计算值对拍：
 - `$TD$` → 当日 `YYYYMMDD`（如 20260930）；`$D4$` → 前 4 日；`$D7$` → 前 7 日（其余 `$Dn$` 按语义偏移）。
 - 注意 SQL 内可能含 `PROD_ITEM_VALUE * 10` 等倍数因子、NVL/SUM 聚合，对拍须保持同口径。
- 溯源目标表多为 `SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_*`、`SMBB_M_S_CG00.T_DWS_FACT_CGGZ_*` 等 DWS 过程表；其写入来源由 ③ 的存储过程进一步确认。
- 取实时真值：`SMBB_M_A_GZ01.T_PM_KPI` 经 `KPI_ID = ZB_CODE` 关联 T_ADS_DIM_GZ01（实测命中 **4,375,414** 行），`KPI_VAL`(DOUBLE) 为已落库值，可作对拍第三方基准。**注意 T_PM_KPI 无 KPI_NAME 字段**，名称须由 T_ADS_DIM_GZ01.ZB_NAME 经关联补全。

**③ CREATER → 存储过程（容错版，主理人裁决）**

CREATER 真实形态（实测样本）分为四类，**必须分类处理**：
| 形态 | 样例 | 处理 |
|---|---|---|
| 裸过程名（无 schema） | `P_DWS_FACT_ZZGZ_0003` | 假定默认 schema `SMBB_M_S_ZZ00`，TRIM 后查 SYSCAT.ROUTINES |
| schema 前缀过程 | `SMBB_M_S_NY00.P_DWS_FACT_NYGZ_0001` | 按点切分 schema/proc，精确查 |
| **表名（非过程！）** | `SMBB_M_A_GZ01.T_ADS_WH0004`、`SMBB_M_A_GZ01.T_ADS_LY_ENERGY` | 这是 ADS 结果表，**不是过程**；回退 ② SQL1/SQL2 直接溯源 |
| 自由文本/带脏字符 | `SMBB_M_S_NY00.P_DWS_FACT_NYGZ_0001\n`、`,\n` 结尾 | **先 TRIM + 去尾部换行/逗号/空格**，再分类；仍不可解析则回退 ② |

容错流程：
1. `TRIM(CREATER)` → 去除首尾空白、换行、`\r`、`\n`、尾部 `,`。
2. 含 `.` → `schema = 前缀`、`proc = 后缀`；不含 `.` → `schema=SMBB_M_S_ZZ00`、`proc=CREATER`。
3. 用用户给定**语句①**探活；跨 schema 回查：若默认 schema 未命中，依次回查 `SMBB_M_A_GZ01` / `XSMBB_M_S_ZZ00` / `SMBB_M_S_CG00` / `SMBB_M_S_NY00` 等。
4. 命中且 `ROUTINETYPE='P'` → 进入 ④ 取 TEXT 复核；若解析为表名（`T_` 前缀或 `SYSCAT.TABLES` 命中）→ 判为结果表，回退 ②；若仍不可解析（自由文本、空）→ **回退 ② SQL1/SQL2 直接溯源**，并在血缘摘要标注「来源：SQL1 直溯（CREATER 不可解析）」。

**④ 存储过程业务逻辑核验（SYSCAT.ROUTINES，用户给定语句原样）**

取过程清单与正文，复核指标写入逻辑：
```sql
-- 语句①：过程清单（生产管制过程多在 SMBB_M_S_ZZ00）
SELECT ROUTINESCHEMA, ROUTINENAME, SPECIFICNAME, CREATE_TIME, OWNER, PARM_COUNT
FROM SYSCAT.ROUTINES
WHERE ROUTINETYPE = 'P' AND ROUTINESCHEMA = 'SMBB_M_S_ZZ00'
ORDER BY ROUTINENAME;

-- 语句②：过程正文（业务逻辑溯源；TEXT 为 CLOB，实测 P_DWS_FACT_ZZGZ_0003 长约 276,772 字符）
SELECT TEXT
FROM SYSCAT.ROUTINES
WHERE ROUTINESCHEMA = 'SMBB_M_S_ZZ00'
 AND ROUTINENAME = 'P_DWS_FACT_ZZGZ_0003'
 AND ROUTINETYPE = 'P';
```

- 语句①实测返回 SMBB_M_S_ZZ00 下 **72 个存储过程**（如 `P_DWS_FACT_ZZGZ_0001/0002/0003/0006/HY01/LG01/LT01/...`）；语句②实测可取，首行即 `CREATE or replace PROCEDURE SMBB_M_S_ZZ00.P_DWS_FACT_ZZGZ_0003(IN P_YMD VARCHAR(8))`，印证过程由日期参数 `P_YMD` 驱动 —— 与 SQL1 中 `$TD$` 日期 token 一致。
- **TEXT 为超大 CLOB**：实际溯源用 `SUBSTR(TEXT,1,N)` 或 `LENGTH(TEXT)` 检视，避免一次拉取 27 万字符撑爆响应；需完整逻辑时按 `SPECIFICNAME` + 分段 `SUBSTR` 抽取关键 INSERT/UPDATE 段。
- **已知落地过程（跨 schema 补充，`SMBB_M_A_GZ01`）**：罗源闽光 / 泉州闽光的**能源数据**经 `SMBB_M_A_GZ01.P_PRIV_TEMP_KPI` 写入 `T_PM_KPI`。实测登记：`ROUTINESCHEMA=SMBB_M_A_GZ01, ROUTINETYPE='P', PARM_COUNT=1, TEXT 长 2424`；正文首行 `CREATE or replace PROCEDURE SMBB_M_A_GZ01.P_PRIV_TEMP_KPI(IN DAY_TIME VARCHAR(50))`，含注释 `--获取基地能源数据` 与 `DELETE FROM SMBB_M_A_GZ01.T_PM_KPI WHERE TO_CHAR(KPI_TIME,'YYYY-MM-DD')=...`，印证其按日清空并重写 `T_PM_KPI`（基地能源 KPI）。该过程位于 `SMBB_M_A_GZ01`（**非** SMBB_M_S_ZZ00），正是 ③ 容错"跨 schema 回查 SMBB_M_A_GZ01"的典型命中；溯源能源类（尤其罗源/泉州）指标、且 CREATER 为空或指向不明时，应优先核查此过程，再经 `KPI_ID=ZB_CODE` 关联 T_ADS_DIM_GZ01 取 `ZB_NAME`（T_PM_KPI 无 KPI_NAME）。
- 过程正文可进一步经 `SYSCAT.ROUTINEDEP` 取依赖（源表/临时表），作溯源边界证据；边界外（动态 SQL/临时表静态依赖残缺）须如实标注，不得补造。

**⑤ 下钻到 ODS 最源头并展示全明细（溯源铁律）**

溯源不止于 DWS，必须沿血缘**一直追到指标数值的最源头 ODS 层**，并把每一层下钻命中的**所有明细数据行**完整展示（不能只给聚合值或抽样），让用户能逐行复核到原始凭证。链路通用模板：

`T_ADS_DIM_GZ01.ZB_CODE → SQL1（直查 DWS） → CREATER（存储过程） → 过程体映射块 → ODS 明细源表`

- **铁（P_DWS_FACT_ZZGZ_0001，schema=SMBB_M_S_ZZ00）**：过程经 GTT 装配（UNION ALL 三基地 ODS `T_ODS_TMMIS21`@ SMBB_M_O_SGP4Z1/SGP6Z1/SGP8Z1），再到映射块（过滤明细码 + remap + 置'铁产量日实绩值'）。过程对 ODS **1:1 透传**，每 BFxxDPS001 → 一行 DWS；BF10 = BF11+BF12+BF16 系 ODS 数据属性（非过程计算），下钻到 ODS 须列出三基地当日全部 BFxxDPS001 明细码与数值。
- **钢（P_DWS_FACT_ZZGZ_0003，DWS=LG01）**：熔炼号/物料重量（MAT_WT）模型。ODS `T_ODS_TMMSM21` → 临时表 → RIGHT JOIN `T_ODS_TMMSM01`/`HMMSM01`（过滤 `COMPLEX_DECIDE_CODE NOT IN('2','4')` 剔除不合格/废品）[SGP1→11, SGP2→12, SGPD→13, SGP3→14] → +冶废（AI_WT_1×-1）→ UNION 去重 → GROUP BY FACTORY_DIV SUM(MAT_WT)。下钻到 ODS 须列出各基地当日全部熔炼号/物料重量明细。
- **钢材（P_DWS_FACT_ZZGZ_0002）**：ODS `SMBB_M_O_SGM1M1.T_ODS_TMMBW01`(+`HMMBW01` 本部+泉州，FACTORY_DIV 21/22/23/51/52/31 本部、25/26/55 泉州) 与 `SMBB_M_O_SGP3Z1.T_ODS_TMMBW01`(罗源) → SUM(MAT_WT) GROUP BY FACTORY_DIV。下钻到 ODS 须列出各轧线当日全部物料重量明细。

**schema 备忘录**（溯源落地必带）：

| 表 | schema |
|---|---|
| T_ADS_DIM_GZ01 | SMBB_M_A_GZ01 |
| T_DWS_FACT_ZZGZ_0001（铁 DWS） | SMBB_M_S_ZZ00 |
| T_DWS_FACT_ZZGZ_LG01（钢 DWS，YMD+ZB_CODE+ZB_VALUE(VARCHAR 需 CAST)+FACTORY_CODE） | SMBB_M_S_ZZ00 |
| T_DWS_FACT_ZZGZ_0002（钢材 DWS，YMD+ZB_NAME+ZB_VALUE） | SMBB_M_S_ZZ00 |
| T_ODS_TMMIS21（铁 ODS 三基地） | SMBB_M_O_SGP4Z1 / SMBB_M_O_SGP6Z1 / SMBB_M_O_SGP8Z1 |
| T_ODS_TMMSM21/TMMSM01/HMMSM01（钢 ODS） | SMBB_M_O_SGP1Z1(→11)/SGP2Z1(→12)/SGPDZ1(→13)/SGP3Z1(→14) |
| T_ODS_TMMBW01/HMMBW01（钢材 ODS 本部+泉州） | SMBB_M_O_SGM1M1 |
| T_ODS_TMMBW01（钢材 ODS 罗源） | SMBB_M_O_SGP3Z1 |

**溯源六步（已固化为团队默认动作）**：① 取 T_ADS_DIM_GZ01 的 ZB_CODE/SQL1/CREATER；② 直执行 SQL1 得 DWS 归集值；③ 按 CREATER 取存储过程 TEXT，定位映射块；④ 逆推 ODS 源表与过滤/remap 逻辑；⑤ 实查 ODS 列出**所有**明细行；⑥ 逐层对账（ODS 之和 = DWS = ADS）。

---

## 通用三层血缘下钻模板（2026-11-02 泛化 · E4）

> **目标**：上述铁/钢/钢材三例只是**实例**。本模板将其泛化为**任意指标 (ZB_CODE, 日期)** 的三层下钻引擎，
> 严格对应 **第一层 T_ADS 应用展示层 → 第二层 T_DWD/T_DWS 的 CDM 层（含 tmp 临时表）→ 第三层 T_ODS 贴源层**。
> 主责：`sg-data-lineage`（反向）/ `sg-metric-builder`（正向兜底）；消费：`sg-insight` 渲染**四层抽屉**（L1 构成 / L2 序列 / L3 tmp / L4 ODS）。
> 📎 下钻规则唯一权威源：`knowledge/kb/数据下钻规则_权威手册.md`

### 通用流程（七步 · 支持「无 ADS」分支）

```
① 定指标     T_ADS_DIM_GZ01 取 ZB_CODE / ZB_NAME / SQL1 / CREATER / FACTORY_DIV
             └ 未注册 → 走 caliber_check.md L4 + lineage_fallback.md 正向建模
② 判有无ADS  有 ADS → 取 ADS 层归集值（SQL1 直执行）
             无 ADS → 【合法终点】直接用 CDM(DWD/DWS) 展示，标注 has_ads=false 后继续③
③ 解过程     SYSCAT.ROUTINES 取 CREATER 正文（CLOB 用 SUBSTR(TEXT,1,N) 分段，禁一次拉全）
             └ 解析：源表 / JOIN / WHERE 过滤 / remap / 聚合方式
④ 提tmp链    SYSCAT.ROUTINEDEP 取依赖 + 正文 Grep 'tmp|TMP|GTT|SESSION.' 提取临时表链
             （tmp 是合法一环，必须纳入；静态依赖残缺如实标注，不得补造）
⑤ 定ODS源表  从过程 FROM/UNION ALL 子句提取 T_ODS_* 与其 schema（见 schema 备忘录）
⑥ 实查明细   对 T_ODS_* 按当日全条件实查，列出【所有】明细行（禁抽样、禁只给聚合值）
⑦ 逐层对账   ODS 之和 = CDM = ADS（或 = CDM，当 has_ads=false）；对不平 → 标 [对账差异]
```

### 关键 SQL 模板

```sql
-- 【T1】ADS/指标注册定位（口径最终事实源，不依赖 weknora）
SELECT ZB_CODE, ZB_NAME, FACTORY_DIV, UNIT, SQL1, CREATER
FROM SMBB_M_A_GZ01.T_ADS_DIM_GZ01
WHERE ZB_CODE = '<ZB_CODE>';

-- 【T2】判定有无 ADS 层 + 取 CDM 归集值
-- 有 ADS：直执行 SQL1（注意 $TD$ 日期 token 替换为 YYYYMMDD）
-- 无 ADS：直查 DWS/DWD
SELECT YMD, ZB_CODE, CAST(ZB_VALUE AS DECIMAL(18,4)) AS ZB_VALUE
FROM <CDM_SCHEMA>.<T_DWS_xxx>
WHERE ZB_CODE = '<ZB_CODE>' AND YMD = '<YYYYMMDD>';

-- 【T3】过程正文分段检视（CLOB 防溢出）
SELECT ROUTINESCHEMA, ROUTINENAME, LENGTH(TEXT) AS TEXT_LEN,
       SUBSTR(TEXT, 1, 8000) AS TEXT_PART1
FROM SYSCAT.ROUTINES
WHERE ROUTINENAME = '<CREATER>';
-- 续段：SUBSTR(TEXT, 8001, 8000) AS TEXT_PART2 ... 逐段推进

-- 【T4】tmp 临时表链提取（依赖 + 正文双路）
SELECT BSCHEMA, BNAME, BTYPE
FROM SYSCAT.ROUTINEDEP
WHERE ROUTINESCHEMA = '<PROC_SCHEMA>' AND ROUTINENAME = '<CREATER>';
-- 正文侧：Grep 'TMP|tmp|GTT|SESSION\.|DECLARE GLOBAL TEMPORARY'

-- 【T5】ODS 贴源层【全明细】实查（溯源铁律：列出所有明细行）
SELECT *
FROM <ODS_SCHEMA>.<T_ODS_xxx>
WHERE <日期字段> = '<YYYYMMDD>'    -- 或 BETWEEN '<START>' AND '<END>'
  AND <过程内同款过滤条件>          -- 必须与过程体一致（如 COMPLEX_DECIDE_CODE NOT IN('2','4')）
ORDER BY <主键/时间>;
-- ⚠ 禁止 FETCH FIRST n ROWS ONLY（5sApi 自动追加 20000，自定义会报 SQLCODE=-104）

-- 【T6】逐层对账
SELECT '<ODS>' AS LAYER, COUNT(*) AS N, SUM(<度量>) AS TOTAL FROM <ODS_SCHEMA>.<T_ODS_xxx> WHERE <同款条件>
UNION ALL SELECT 'CDM', COUNT(*), SUM(<度量>) FROM <CDM_SCHEMA>.<T_DWS_xxx> WHERE ZB_CODE='<ZB_CODE>' AND YMD='<YYYYMMDD>'
UNION ALL SELECT 'ADS', COUNT(*), SUM(<度量>) FROM <ADS层或SQL1结果集>;
```

### 正向建模取证模板（断链兜底 · 从 ODS 起建指标）

> 触发：SQL1 空 / CREATER 取不到 / 加工文档缺失。详见 `agents/references/lineage_fallback.md`。

```sql
-- 【F1】找候选事实明细表（ODS 贴源，按业务域关键词探）
SELECT TABSCHEMA, TABNAME FROM SYSCAT.TABLES
WHERE TABSCHEMA LIKE 'SMBB_M_O_%'      -- ODS 贴源层统一前缀
  AND TABNAME LIKE '%<业务关键词>%';

-- 【F2】看字段，定位度量列与维度列
SELECT COLNAME, TYPENAME, LENGTH, SCALE, REMARKS
FROM SYSCAT.COLUMNS
WHERE TABSCHEMA='<ODS_SCHEMA>' AND TABNAME='<T_ODS_xxx>'
ORDER BY COLNO;

-- 【F3】定原子指标（来源于 T_DWD 事实明细）：度量列的原子聚合
--      派生 = 原子 + 度量单位 + 统一口径(维度) + 通用限定条件 + 计算逻辑 + 计算方式
--      复合 = 派生指标 加减乘除
SELECT <维度列>, COUNT(*) AS N,
       SUM(<度量列>)   AS ATOMIC_SUM,      -- 计算方式：求和
       AVG(<度量列>)   AS ATOMIC_AVG,      -- 计算方式：求平均
       COUNT(DISTINCT <键>) AS ATOMIC_CNT  -- 计算方式：统计
FROM <ODS_SCHEMA>.<T_ODS_xxx>
WHERE <日期> = '<YYYYMMDD>' AND <通用限定条件>
GROUP BY <维度列>;

-- 【F4】维度表关联（T_DIM_* 横切：厂别/产线/钢种/日期）
SELECT d.<维度名>, f.<度量>
FROM <T_DWD_xxx> f JOIN <T_DIM_xxx> d ON f.<维度键> = d.<维度键>
WHERE f.<日期> = '<YYYYMMDD>';

-- 【F5】实据核验（正向建模产物必做，决定能否摘掉 [正向建模·待实据核验]）
-- 用 F3 结果 与 已知归集值/主表对账，差值为 0 或可解释方可摘标
```

### 标准血缘 JSON 输出（全团唯一交换格式）

```json
{
  "zb_code": "<ZB_CODE>", "indicator_name": "<名称>", "date": "<YYYYMMDD>",
  "level": "L4业务|L3复合|L2派生|L1原子",
  "layers": {
    "ADS": {"table": "<T_ADS_xxx 或 null>", "source": "T_ADS_DIM_GZ01.SQL1", "has_ads": true},
    "CDM": {"tables": ["T_DWD_*","T_DWS_*"], "tmp_chain": ["TMP1_1","TMP1_2"], "procedure": "<CREATER>"},
    "ODS": {"tables": ["T_ODS_*"], "schema": "SMBB_M_O_SGP1Z1", "detail_rows_n": 71}
  },
  "lineage_mode": "reverse|forward",
  "gates": {"structure":"pass|fail", "continuity":"pass|fail", "design_vs_data":"pass|fail"},
  "reconcile": {"ods_sum": 0, "cdm_sum": 0, "ads_sum": 0, "diff": 0},
  "confidence": 0.95,
  "annotation": ""
}
```

**输出纪律**：`lineage_mode=forward` 时 `annotation` 必须含 `[正向建模·待实据核验]`，`confidence ≤ 0.60`；三者 gates 不全 pass 时必须标 `[血缘不完整·数据存疑]` 并在交付文本披露缺哪一环。

