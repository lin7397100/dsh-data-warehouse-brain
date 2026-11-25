---
name: sg-db2-procedure-gen
description: "三钢数仓智脑：存储过程生成。参照 GZPROD 55 个生产与 CBPROD 50 个日成本过程的既有编码模式，生成符合规范的 DB2 存储过程（CTE 链、参数模式、日志写入、异常处理）。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, procedure, generation]
owner: sg-development
---

# sg-db2-procedure-gen · 存储过程生成

## 定位

数仓加工逻辑的**生成器**：产出符合三钢既有编码模式、可直接评审入库的 DB2 存储过程。

## 既有编码模式（参照基准）

| 域 | 目录 | 特征 |
|---|---|---|
| 生产 | `$DB2_ASSETS_HOME/PROD`（55 个） | `P_DWD_*` / `P_DWS_*` 命名，CTE 多步链，指标写入 DWS |
| 成本 | `$DB2_ASSETS_HOME/CBPROD`（50 个） | `C010A~H` / `C022~C072` 十步链，六参数，版本变体 `_5V`/`_7V`/`_9V` |

## 生成规范（八项）

### 1. 命名与归属

- 生产：`P_DWS_FACT_{域}_{粒度}` / `P_DWD_FACT_{域}_{粒度}`
- 成本：遵循十步链命名体系，新增步骤明确插入位置

### 2. 参数模式

```sql
CREATE PROCEDURE 过程名 (
  IN  P_YMD        VARCHAR(8),    -- 数据日期 YYYYMMDD
  IN  P_COMPANY    VARCHAR(10),   -- 公司代码（成本域）
  IN  P_USER       VARCHAR(20),   -- 执行用户
  OUT P_RETCODE    INTEGER,       -- 返回码 0 成功 / 非 0 失败
  OUT P_RETMSG     VARCHAR(500)   -- 返回信息
)
```

### 3. CTE 链风格

每个 CTE 必须带**业务注释**（做什么 + 为什么）：

```sql
WITH
-- T1: 关联轧制计划与钢种，确定每批次的目标规格
T1 AS (SELECT … FROM …),
-- T2: 按当日时间窗过滤，排除跨日数据
T2 AS (SELECT … FROM T1 WHERE …),
…
```

### 4. 分区与性能

- 大表必带分区条件（`YMD` 或分区键）
- 避免隐式类型转换
- 必要的 `RUNSTATS` 提示与索引建议

### 5. 空值与边界

- 除法 `NULLIF` 保护
- `COALESCE` 明确语义（是"当作 0"还是"保留空"）
- 跨月 / 跨班次边界显式处理

### 6. 日志写入

关键步骤写入执行日志（与 C.xlsx 日志体系对齐）：`JOB_NAME / START_TIMESTAMP / LAST_TIMESTAMP / ELAPSED / IS_SUCCESSFUL / PARAM_INFO / ERROR_DESC`

### 7. 异常处理

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
  GET DIAGNOSTICS EXCEPTION 1 P_RETMSG = MESSAGE_TEXT;
  SET P_RETCODE = SQLCODE;
  -- 写入失败日志
END;
```

### 8. 幂等性

- 重跑安全：先 `DELETE` 当日分区再 `INSERT`（写操作需审批）
- 或采用 `MERGE` 保证幂等

## 工作流

1. **需求确认**：输入输出表、加工逻辑、调度依赖、粒度
2. **参照选型**：找一个最接近的既有过程作模板
3. **生成过程体**：按八项规范编写
4. **自审清单**：分区条件 / 空值保护 / 日志 / 异常 / 幂等 / 注释
5. **评审交付**：输出过程体 + 参数说明 + 调用示例 + 回退方案

## 输出规范

- 完整过程体（含注释）
- 参数说明表
- 调用示例（含典型参数值）
- 自审清单结论（八项逐条）
- 回退方案（如何撤销本次变更）

## 注意事项

1. **写操作必须人工确认并审批** —— 生成 ≠ 直接执行，部署需走治理流程。
2. 新过程必须登记到元数据（表/字段/血缘）与本体（业务逻辑），否则后续无法解析。
3. 成本域过程必须遵循六参数与版本体系，不得私自简化。
4. 禁止在过程中硬编码公司代码、期间、版本号 —— 一律走参数。
