-- =============================================================
-- EPLAT 5S 平台元数据 · 只读查询模板 Q00~Q15
-- 通道：mcp__eplat__oracle_query（仅 SELECT / WITH 单条语句；只读事务）
-- 参数：max_rows 默认 200（上限 2000）、timeout_ms 默认 30000
-- 占位符：:xxx 必须替换为字面量后再发送——MCP 只接收整条 SQL 文本，不做绑定变量
-- 纪律：不对 CLOB 用 TRIM()；数量结论一律 COUNT(*)；血缘统计一律 DISTINCT
-- =============================================================

-- -------------------------------------------------------------
-- Q00 开工自检（每次会话第一条；等价于 oracle_ping 的 SQL 版）
-- -------------------------------------------------------------
-- 注意：视图字典是 ALL_VIEWS（没有 ALL_TAB_VIEWS，写错会 ORA-00942）
SELECT SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS cur_schema,
       (SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = 'EPLAT') AS eplat_tables,
       (SELECT COUNT(*) FROM ALL_VIEWS WHERE OWNER = 'EPLAT') AS eplat_views
FROM DUAL;

-- -------------------------------------------------------------
-- Q01 资产规模实查（禁止用 ALL_TABLES.NUM_ROWS 作结论）
-- 实测 2026-11-25 基准值见 references/eplat_asset_map.md
-- -------------------------------------------------------------
SELECT 'TBEDF11_业务术语' AS item, COUNT(*) AS cnt FROM EPLAT.TBEDF11
UNION ALL SELECT 'TBEDF12_数据元', COUNT(*) FROM EPLAT.TBEDF12
UNION ALL SELECT 'TBEDF15_业务对象', COUNT(*) FROM EPLAT.TBEDF15
UNION ALL SELECT 'TBEDF33_业务过程', COUNT(*) FROM EPLAT.TBEDF33
UNION ALL SELECT 'TBEDG43_数据域', COUNT(*) FROM EPLAT.TBEDG43
UNION ALL SELECT 'TBEDG2101_数据资源', COUNT(*) FROM EPLAT.TBEDG2101
UNION ALL SELECT 'TBEDF51_业务指标', COUNT(*) FROM EPLAT.TBEDF51
UNION ALL SELECT 'TBEDF54_原子指标', COUNT(*) FROM EPLAT.TBEDF54
UNION ALL SELECT 'TBEDF5401_派生指标', COUNT(*) FROM EPLAT.TBEDF5401
UNION ALL SELECT 'TBEDF5403_复合指标', COUNT(*) FROM EPLAT.TBEDF5403
UNION ALL SELECT 'TBEDF5203_维度模型', COUNT(*) FROM EPLAT.TBEDF5203
UNION ALL SELECT 'TBEDF5204_事实模型', COUNT(*) FROM EPLAT.TBEDF5204
UNION ALL SELECT 'TBEDF5208_事实字段', COUNT(*) FROM EPLAT.TBEDF5208
UNION ALL SELECT 'TBEDF5207_维度字段', COUNT(*) FROM EPLAT.TBEDF5207
UNION ALL SELECT 'TBEDG91_表血缘_行数', COUNT(*) FROM EPLAT.TBEDG91
UNION ALL SELECT 'TBEDG91_表血缘_去重边', COUNT(DISTINCT SRC_TABLE_GUID || '|' || DEST_TABLE_GUID || '|' || DISPATCH_ID) FROM EPLAT.TBEDG91
UNION ALL SELECT 'TBEDG93_字段血缘_行数', COUNT(*) FROM EPLAT.TBEDG93
UNION ALL SELECT 'TBEDD05_质量规则', COUNT(*) FROM EPLAT.TBEDD05
UNION ALL SELECT 'TBEDM11_数据API', COUNT(*) FROM EPLAT.TBEDM11;

-- -------------------------------------------------------------
-- Q02 UUID 前缀 -> 物理位置（跨表定位；WARN: 全表 UNION 有成本，先判前缀只跑对应分支）
-- DY_IN_BS_00_ -> TBEDF51      DY_IN_TC_00_ -> TBEDF54/5401/5403
-- DY_MO_FM_00_ -> TBEDF5208    DY_MO_DM_00_ -> TBEDF5207
-- DY_MO_ER_00_ -> TBEDF5209    DY_EL_00_00_ -> TBEDF11
-- DY_FD_00_00_ -> TBEDF12      DY_NO_00_00_ -> TBEDF33
-- DY_BO_00_00_ -> TBEDF15      DY_TB_TN_00_ -> TBEDG2101（表/数据资源）
-- DS_TK_DQ_00_ -> TBEDD05      DS_TK_SQ_00_ -> TBEDD0105（ETL 步骤）
-- DY_TB_TF_00_ -> TBEDG2102（物理数据资源字段；与模型字段 TBEDF5208 是两套）
-- -------------------------------------------------------------
SELECT 'TBEDF51' AS src, UUID, INDEX_0_ENAME AS ename, INDEX_0_CNAME AS cname FROM EPLAT.TBEDF51 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDF54', UUID, INDEX_1_ENAME, INDEX_1_CNAME FROM EPLAT.TBEDF54 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDF5401', UUID, INDEX_2_ENAME, INDEX_2_CNAME FROM EPLAT.TBEDF5401 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDF5403', UUID, INDEX_3_ENAME, INDEX_3_CNAME FROM EPLAT.TBEDF5403 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDF5208', UUID, FIELD_ENAME, MEMO FROM EPLAT.TBEDF5208 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDF5207', UUID, FIELD_ENAME, MEMO FROM EPLAT.TBEDF5207 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDG2102', UUID, FIELD_ENAME, MEMO FROM EPLAT.TBEDG2102 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDG2101', UUID, TABLE_ENAME, TABLE_CNAME FROM EPLAT.TBEDG2101 WHERE UUID = ':uuid'
UNION ALL SELECT 'TBEDD0105', STEP_UUID, STEP_ALIAS, STEP_TYPE FROM EPLAT.TBEDD0105 WHERE STEP_UUID = ':uuid';

-- -------------------------------------------------------------
-- Q03 业务指标 -> 技术指标（原子/派生）完整链路
-- -------------------------------------------------------------
SELECT b.UUID AS biz_uuid,
       b.INDEX_0_ENAME AS biz_ename,
       b.INDEX_0_CNAME AS biz_cname,
       t.TECHNOLOGY_INDEX_UUID AS tech_uuid,
       c.INDEX_TYPE AS tech_type,            -- 1原子 2派生 3复合
       a.UUID AS atomic_uuid,
       a.INDEX_1_ENAME AS atomic_ename,
       a.EXPRESSION AS atomic_expression,
       d.UUID AS derived_uuid,
       d.INDEX_2_ENAME AS derived_ename,
       d.INDEX_2_TABLE_JSON AS derived_logic
FROM EPLAT.TBEDF5406 t
JOIN EPLAT.TBEDF51 b ON b.UUID = t.BUSINESS_INDEX_UUID
LEFT JOIN EPLAT.TBEDF5404 c ON c.INDEX_UUID = t.TECHNOLOGY_INDEX_UUID
LEFT JOIN EPLAT.TBEDF54 a ON a.UUID = t.TECHNOLOGY_INDEX_UUID
LEFT JOIN EPLAT.TBEDF5401 d ON d.UUID = t.TECHNOLOGY_INDEX_UUID
WHERE b.INDEX_0_CNAME LIKE '%:keyword%'
   OR b.INDEX_0_ENAME LIKE '%:keyword%';

-- -------------------------------------------------------------
-- Q04 原子指标表达式里的字段 UUID -> 字段名 + 所属事实模型
-- ⚠ ${DY_MO_FM_00_xxx} 是字段 UUID，不是指标 UUID
-- -------------------------------------------------------------
SELECT f.UUID AS field_uuid,
       f.FIELD_ENAME,
       f.MEMO AS field_cname,
       f.FIELD_DESC,
       f.IS_PK,
       f.FACT_UUID,
       m.MODEL_ENAME AS fact_model_ename,
       m.MODEL_CNAME AS fact_model_cname,
       m.PHYSICAL_STATE,
       m.SAFETY_CODE_RANK
FROM EPLAT.TBEDF5208 f
LEFT JOIN EPLAT.TBEDF5204 m ON m.UUID = f.FACT_UUID
WHERE f.UUID = ':fact_field_uuid';

-- -------------------------------------------------------------
-- Q05 维度模型字段解析（DY_MO_DM_00_）
-- -------------------------------------------------------------
SELECT f.UUID AS field_uuid,
       f.FIELD_ENAME,
       f.MEMO AS field_cname,
       f.DIMENSION_UUID,
       m.MODEL_ENAME AS dim_model_ename,
       m.MODEL_CNAME AS dim_model_cname,
       m.DIMENSION_TYPE
FROM EPLAT.TBEDF5207 f
LEFT JOIN EPLAT.TBEDF5203 m ON m.UUID = f.DIMENSION_UUID
WHERE f.UUID = ':dim_field_uuid';

-- -------------------------------------------------------------
-- Q06 表级血缘 -> ETL 加工步骤（DISPATCH_ID = STEP_UUID，已实测自证）
-- ⚠ 必须 DISTINCT：同 src/dest/dispatch 存在重复行
-- -------------------------------------------------------------
SELECT DISTINCT
       s.TABLE_ENAME AS src_table,
       d.TABLE_ENAME AS dest_table,
       l.DISPATCH_ID,
       st.STEP_ALIAS,
       st.PROJECT_NAME,
       DBMS_LOB.SUBSTR(st.STEP_DEFINITION, 2000, 1) AS step_sql_head
FROM EPLAT.TBEDG91 l
LEFT JOIN EPLAT.TBEDG2101 s ON s.UUID = l.SRC_TABLE_GUID
LEFT JOIN EPLAT.TBEDG2101 d ON d.UUID = l.DEST_TABLE_GUID
LEFT JOIN EPLAT.TBEDD0105 st ON st.STEP_UUID = l.DISPATCH_ID
WHERE d.TABLE_ENAME = ':table_name';

-- -------------------------------------------------------------
-- Q07 字段级血缘 -> ETL 步骤
-- ⚠ TBEDG93.SRC/DEST_COLUMN_NAME 存的是 UUID（DY_TB_TF_00_），不是字段名：
--   DY_TB_TF_00_ -> TBEDG2102（物理字段，FIELD_ENAME/MEMO）
--   DY_TB_TN_00_ -> TBEDG2101（表级，少数整表流转行）
--   只 JOIN TBEDG2102 会漏掉表级行，故用 COALESCE 双解析
-- -------------------------------------------------------------
SELECT DISTINCT
       s.TABLE_ENAME AS src_table,
       d.TABLE_ENAME AS dest_table,
       COALESCE(fs.FIELD_ENAME, s.TABLE_ENAME) AS src_col,
       fs.MEMO AS src_col_cname,
       COALESCE(fd.FIELD_ENAME, d.TABLE_ENAME) AS dest_col,
       fd.MEMO AS dest_col_cname,
       g.SRC_COLUMN_NAME,
       g.DEST_COLUMN_NAME,
       g.DISPATCH_ID,
       st.STEP_ALIAS
FROM EPLAT.TBEDG93 g
LEFT JOIN EPLAT.TBEDG2101 s ON s.UUID = g.SRC_TABLE_GUID
LEFT JOIN EPLAT.TBEDG2101 d ON d.UUID = g.DEST_TABLE_GUID
LEFT JOIN EPLAT.TBEDG2102 fs ON fs.UUID = g.SRC_COLUMN_NAME
LEFT JOIN EPLAT.TBEDG2102 fd ON fd.UUID = g.DEST_COLUMN_NAME
LEFT JOIN EPLAT.TBEDD0105 st ON st.STEP_UUID = g.DISPATCH_ID
WHERE d.TABLE_ENAME = ':table_name';
-- 需要只看某字段时追加：AND fd.FIELD_ENAME = ':column_name'

-- -------------------------------------------------------------
-- Q08 数据质量规则（强弱规则 + 分类 + 启用/审批状态）
-- CLOB：RULE_CONTENT 用 DBMS_LOB.SUBSTR，禁止 TRIM()
-- -------------------------------------------------------------
SELECT UUID,
       RULE_NAME,
       TABLE_NAME,
       SCHEMA_NAME,
       TABLE_UUID,
       QUALITY_CODE_CLASSIFY,   -- accuracy / integrity / authenticity / timeliness
       BLOCK_TYPE,              -- 1=强规则(拦截) 0=弱规则
       IS_ENABLE,
       APPROVAL_STATUS,
       STEP_UUID,
       DBMS_LOB.SUBSTR(RULE_CONTENT, 2000, 1) AS rule_content_head
FROM EPLAT.TBEDD05
WHERE TABLE_NAME = ':table_name'
   OR RULE_NAME LIKE '%:keyword%';

-- -------------------------------------------------------------
-- Q09 安全 / 重要 / 风险等级字典（EPLAT L1~L3 ≠ 本团 L1~L4）
-- -------------------------------------------------------------
SELECT '安全等级' AS kind, SAFETY_CODE_RANK AS code, SAFETY_NAME AS name FROM EPLAT.TBEDF6101
UNION ALL
SELECT '重要等级', IMPORTANT_CODE_RANK, IMPORTANT_NAME FROM EPLAT.TBEDF6102
UNION ALL
SELECT '风险等级', RISK_CODE_RANK, RISK_NAME FROM EPLAT.TBEDF6103;

-- -------------------------------------------------------------
-- Q10 数据资源实体的安全/血缘属性（表级锚点）
-- -------------------------------------------------------------
SELECT TABLE_ENAME,
       TABLE_CNAME,
       SAFETY_CODE_RANK,
       IMPORTANT_CODE_RANK,
       RISK_CODE_RANK,
       HAS_BLOOD,
       HAS_FIELD_BLOOD,
       ROW_COUNT,
       UPDATE_FREQUENCY,
       MODEL_UUID,
       RELEASE_STATUS
FROM EPLAT.TBEDG2101
WHERE TABLE_ENAME = ':table_name';

-- -------------------------------------------------------------
-- Q11 D_A API + M_ 服务单元 + 配置 SQL（CLOB 截断读取）
-- ⚠ DBMS_LOB.SUBSTR 的 amount 不要超过 2000：AL32UTF8 下 4000 字符会超字节缓冲 → ORA-06502
-- -------------------------------------------------------------
SELECT a.API_ID,
       a.API_NAME,
       a.MODEL_ID AS service_unit,
       a.API_TYPE,
       a.API_STATUS,
       a.SAFETY_LEVEL,
       a.API_URL,
       DBMS_LOB.SUBSTR(a.API_SQL, 2000, 1) AS api_sql_head
FROM EPLAT.TBEDM11 a
WHERE a.API_NAME LIKE 'D_A%'
  AND a.MODEL_ID LIKE 'M_%'
  AND (a.API_NAME LIKE '%:keyword%' OR a.API_DESC LIKE '%:keyword%');

-- -------------------------------------------------------------
-- Q12 D_A API 参数
-- ⚠ API_ID 是复合键：MODEL_ID || '.' || API_NAME
--   例 M_DWD_FACT_CGJH_CLJH01_JX.D_A_CGJX_PSCS_BJK2_001
-- -------------------------------------------------------------
SELECT PARAM_ID,
       PARAM_NAME,
       API_ID,
       FIELD_NAME,
       FIELD_CNAME,
       OPERATOR,
       REQUIRED,
       PARAM_DESC,
       FIELD_UUID
FROM EPLAT.TBEDM12
WHERE API_ID = ':api_id';
-- 只知 API_NAME 时改用：
-- WHERE API_ID LIKE '%' || ':api_name' （API_ID 以 .API_NAME 结尾）

-- -------------------------------------------------------------
-- Q13 5S 落地查重（新建指标前必跑，四级一次查全）
-- ⚠ 别名不可叫 LEVEL：LEVEL 是 Oracle 伪列，会 ORA-00923
-- -------------------------------------------------------------
SELECT '业务指标' AS idx_level, UUID, INDEX_0_ENAME AS ename, INDEX_0_CNAME AS cname FROM EPLAT.TBEDF51
 WHERE INDEX_0_CNAME LIKE '%:keyword%' OR INDEX_0_ENAME LIKE '%:keyword%'
UNION ALL
SELECT '原子指标', UUID, INDEX_1_ENAME, INDEX_1_CNAME FROM EPLAT.TBEDF54
 WHERE INDEX_1_CNAME LIKE '%:keyword%' OR INDEX_1_ENAME LIKE '%:keyword%'
UNION ALL
SELECT '派生指标', UUID, INDEX_2_ENAME, INDEX_2_CNAME FROM EPLAT.TBEDF5401
 WHERE INDEX_2_CNAME LIKE '%:keyword%' OR INDEX_2_ENAME LIKE '%:keyword%'
UNION ALL
SELECT '复合指标', UUID, INDEX_3_ENAME, INDEX_3_CNAME FROM EPLAT.TBEDF5403
 WHERE INDEX_3_CNAME LIKE '%:keyword%' OR INDEX_3_ENAME LIKE '%:keyword%';

-- -------------------------------------------------------------
-- Q14 术语 -> 数据元 -> 字段语义（语义专家用）
-- -------------------------------------------------------------
SELECT t.UUID AS term_uuid,
       t.ELEMENT_ENAME AS term_ename,
       t.ELEMENT_CNAME AS term_cname,
       t.ELEMENT_DESC,
       t.ELEMENT_DOMAIN,
       f.UUID AS data_element_uuid,
       f.FIELD_ENAME,
       f.FIELD_CNAME,
       f.MEASURE_UNIT,
       f.FIELD_DOMAIN,
       f.FIELD_SAFETY
FROM EPLAT.TBEDF11 t
LEFT JOIN EPLAT.TBEDF12 f
       ON f.FIELD_CNAME = t.ELEMENT_CNAME
       OR f.FIELD_ENAME = t.ELEMENT_ENAME
WHERE t.ELEMENT_CNAME LIKE '%:term%'
   OR t.ELEMENT_ENAME LIKE '%:term%';

-- -------------------------------------------------------------
-- Q15 业务对象 / 业务过程 / 数据域（本体专家用）
-- -------------------------------------------------------------
SELECT '业务对象' AS kind, UUID, OBJECT_ENAME AS ename, OBJECT_CNAME AS cname, NULL AS extra FROM EPLAT.TBEDF15
UNION ALL
SELECT '业务过程', UUID, PROCESS_CODE, PROCESS_NAME, AREA_UUID FROM EPLAT.TBEDF33
UNION ALL
SELECT '数据域', UUID, DOMAIN_ENAME, DOMAIN_CNAME, PARENT_DOMAIN_ID FROM EPLAT.TBEDG43;

-- -------------------------------------------------------------
-- Q16 物理字段 UUID（DY_TB_TF_00_）-> 字段名 + 所属表（血缘落地必用）
-- ⚠ 与模型字段 TBEDF5208/5207 是两套：血缘用 TBEDG2102，指标表达式用 TBEDF5208
-- -------------------------------------------------------------
SELECT f.UUID AS field_uuid,
       f.FIELD_ENAME,
       f.MEMO AS field_cname,
       f.FIELD_TYPE,
       f.DATA_ELEMENT,
       f.TABLE_UUID,
       t.TABLE_ENAME,
       t.TABLE_CNAME,
       t.SAFETY_CODE_RANK
FROM EPLAT.TBEDG2102 f
LEFT JOIN EPLAT.TBEDG2101 t ON t.UUID = f.TABLE_UUID
WHERE f.UUID = ':phys_field_uuid';

-- -------------------------------------------------------------
-- Q17 某表有哪些字段参与血缘（影响面/字段清单）
-- -------------------------------------------------------------
SELECT t.TABLE_ENAME,
       f.FIELD_ENAME,
       f.MEMO AS field_cname,
       COUNT(DISTINCT g.DISPATCH_ID) AS dispatch_cnt
FROM EPLAT.TBEDG93 g
JOIN EPLAT.TBEDG2102 f ON f.UUID = g.DEST_COLUMN_NAME
JOIN EPLAT.TBEDG2101 t ON t.UUID = f.TABLE_UUID
WHERE t.TABLE_ENAME = ':table_name'
GROUP BY t.TABLE_ENAME, f.FIELD_ENAME, f.MEMO;
