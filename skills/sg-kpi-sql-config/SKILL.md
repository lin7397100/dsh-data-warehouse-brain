---
name: sg-kpi-sql-config
description: "三钢数仓智脑：KPI 指标 SQL 配置。为 T_ADS_DIM_GZ01 配置 SQL1（数值计算）与 SQL2（字符格式），支持六种模板模式，含参数占位符规范与配置校验。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, db2, kpi, sql-config]
owner: sg-development
---

# sg-kpi-sql-config · KPI 指标 SQL 配置

## 定位

6077 个 KPI 的**配置工厂**：把指标定义固化为可执行的 SQL1/SQL2，写入指标配置表。

## 配置表

`SMBB_M_A_GZ01.T_ADS_DIM_GZ01` —— 指标配置主表，核心字段：

| 字段 | 说明 |
|---|---|
| `ZB_CODE` | 指标编码 |
| `ZB_NAME` | 指标名称 |
| `SQL1` | **数值计算逻辑**（取数 SQL） |
| `SQL2` | **字符格式逻辑**（格式化/单位/文案） |
| `UNIT` | 单位 |
| `FACTORY` | 厂部归属 |
| 其他 | 口径说明、版本、生效标志 |

## 六种 SQL1 模板模式

| # | 模式 | 适用 | 示例 |
|---|---|---|---|
| ① | 单值直取 | 单指标当前值 | `SELECT ZB_VALUE FROM … WHERE ZB_NAME=? AND YMD='$TD$'` |
| ② | 分组汇总 | 按维度聚合 | `SELECT FACTORY_DIV, SUM(ZB_VALUE) … GROUP BY FACTORY_DIV` |
| ③ | 时间序列 | 趋势 | `SELECT YMD, ZB_VALUE … WHERE YMD BETWEEN '$D30$' AND '$TD$'` |
| ④ | 同环比 | 对比 | `LAG(ZB_VALUE) OVER (ORDER BY YMD)` 或自关联同期 |
| ⑤ | 下钻 | 层级展开 | CTE 递归 / 层级字段分段 |
| ⑥ | 排名 TopN | 排名 | `ROW_NUMBER() OVER(ORDER BY ZB_VALUE DESC)` + `FETCH FIRST n` |

## 参数占位符规范

| 占位符 | 含义 |
|---|---|
| `$TD$` | 当日 |
| `$D1$` ~ `$D7$` | 前 1~7 日 |
| `$D30$` | 前 30 日 |
| `$YM$` | 当前会计期间 |
| `$FACTORY$` | 厂部（运行时注入） |

## SQL2（字符格式）规范

用于把数值渲染为业务文案：

```sql
SELECT CASE WHEN ZB_VALUE IS NULL THEN '—'
            WHEN ZB_VALUE >= 目标值 THEN '达标'
            ELSE '未达标' END AS ZB_TEXT
FROM (…SQL1 结果…)
```

常见格式：达标判定、同比箭头（↑/↓）、单位拼接、千分位、百分比、成本域**语义反转**（升为坏/降为好）。

## 工作流（五步）

### Step 1 · 指标定义确认

- 语义层是否已注册（未注册先走 `sg-semantic-layer`）
- 口径、单位、厂部、版本、粒度确认

### Step 2 · 选择模板

按查询形态六选一；复合形态拆分为多个 `ZB_CODE` 或嵌套 CTE。

### Step 3 · 编写并校验 SQL

- DB2 方言（`FETCH FIRST` / `NULLIF` / 分区条件）
- 表存在性（对照 9167 DDL）
- 参数占位符正确

### Step 4 · 试跑与回归

- 用历史日期试跑，核对结果量与业务合理性
- 与同类指标交叉验证（如"圆棒产量" vs "圆棒合格量"量级关系合理）

### Step 5 · 落配置与版本

- 写入配置表（写操作需治理专家审批 + 人工确认）
- 记录版本与生效日期，旧版本保留可回滚

## 输出规范

- SQL1 / SQL2 完整语句 + 模板编号
- 参数说明表（占位符 / 含义 / 默认值）
- 试跑结果（样本数据 + 合理性说明）
- 回归结论（与同类指标的一致性）

## 注意事项

1. **写操作必须人工确认** —— 配置写入属写操作，经治理专家审批级护栏。
2. 成本指标必须带三要素参数（CAL_DATE 版本 / DATE_TYPE / Y_EDITION）。
3. SQL2 的语义反转（成本升为坏）必须与指标域一致，禁止生产域误用反转。
4. 配置变更需同步语义层版本，避免口径与 SQL 脱节。
