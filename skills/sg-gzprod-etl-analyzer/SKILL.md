---
owner: sg-gzprod
dispatch: true
name: sg-gzprod-etl-analyzer
description: |
  三钢数仓智脑·管控抽数（ETL 抽数日志）性能分析（管枢主责）。从 ETL 日志 API 拉取生产管制域（GZ4/GZ5/GZ6 等模块）抽数记录，按 MODULE_TYPE / SRC_OBJECT_NAME 做多维耗时分析，产出 9 图 7 表交互式 HTML 报告并投递企微群聊。ETL 日志 API `http://eplat.fjsg.com/service/D_A_SMBBCS01_JOBLOGS_LD1D_X`（clientId=sgdw-cs01）。触发："分析ETL日志/生成ETL报告/ETL性能分析/抽数分析/管控抽数/抽取日志分析"。
version: 2.4.0
tools_required: [exec]
---

# 管控抽数（ETL 抽数日志）性能分析

> **归属**：生产管制域 → **管枢 `sg-gzprod`** 主责
> **来源**：`C:\Users\lin\Downloads\personal\etl-performance-analyzer` v2.4.0（2026-11-20 并入）

---

## 一、数据源（实测可用 2026-11-20）

| 项 | 值 |
|---|---|
| **API** | `http://eplat.fjsg.com/service/D_A_SMBBCS01_JOBLOGS_LD1D_X` |
| **方法** | POST `application/json;charset=UTF-8` |
| **认证** | `clientId=sgdw-cs01` · `clientSecret=${EPLAT_CLIENT_SECRET_CS01}` |
| **默认模块** | `GZ4,GZ5,GZ6`（逗号分隔可覆盖） |
| **默认时间窗** | `05:30`–`07:00`（ETL_TIME） |
| **单模块上限** | 2000 条 |

**请求体**：
```json
{"clientId":"sgdw-cs01","clientSecret":"${EPLAT_CLIENT_SECRET_CS01}",
 "params":{"etlTime":"YYYY-MM-DD","moduleType":"GZ4"},
 "showCount":"true","offset":"0","limit":2000}
```

**响应**：`__sys__.status == 0` 为成功；数据在 `__blocks__.result.{meta.columns, rows}`。
**15 个字段**：`DATECODE / SRCSYSTEMID / SRCOBJECTNAME / DESSYSTEMID / DESOBJECTNAME / ISSUCCESSFUL / MINS / ETLTIME / LASTUPDATE / MODULETYPE / JOBSEQ / CONDITIONORACLE / JOBNAME / CONDITION / SRCOBJECTDESC`

> ⚠️ **MINS 是分钟**（不是秒）；`ETLTIME`/`LASTUPDATE` 为 `YYYY-MM-DD HH:MM:SS` 字符串。

---

## 二、分析维度

| 维度 | 说明 |
|---|---|
| **MODULE_TYPE 总耗时** | 各模块总耗时 + 耗时占比 |
| **SRC_OBJECT_NAME 耗时** | 前 20 耗时最长源表 |
| **抽数明细** | 全量按 `ETL_TIME` 升序 |
| **时间窗筛选** | 默认 05:30–07:00 可覆盖 |
| **异常任务** | 3σ 原则检测 + `ISSUCCESSFUL='F'` |

**9 图**：模块耗时饼图 / 模块总耗时柱状 / 模块平均耗时 / 前 15 源表 / 前 10 作业类型 / 执行时间分布 / 源系统任务数 / 耗时直方图 / 异常模块分布
**7 表**：核心指标汇总 / 模块总耗时 / 源表耗时 Top20 / 异常任务详情 / 主要模块统计 / 源表耗时全量 / 抽数明细全量

---

## 三、执行

```bash
cd $env:DSH_HOME\dwb-team/skills/sg-gzprod-etl-analyzer

python script.py                                  # 当天 05:30-07:00 的 GZ4,GZ5,GZ6
python script.py -d "2026-11-19"                  # 指定日期
python script.py -m "GZ4"                         # 单模块
python script.py -m "GZ5,GZ6"                     # 多模块
python script.py --time-start "06:00" --time-end "08:00"
python script.py -s "桌面/ETL.xlsx"               # 本地文件兜底
python script.py --no-send                        # 仅生成不发企微
```

| 参数 | 简写 | 默认 |
|---|---|---|
| `--source` | `-s` | `etl_api` |
| `--date` | `-d` | 当天 |
| `--module` | `-m` | `GZ4,GZ5,GZ6` |
| `--time-start` / `--time-end` | | `05:30` / `07:00` |
| `--chatid` | `-t` | 内置群 |
| `--output` | `-o` | 桌面 |
| `--no-send` | | False |

**依赖**：`pip install openpyxl requests`（均已装）

---

## 四、与闸门 6 的关系（重要）

本技能的 API **正是闸门 6「埋点时点」的 ETL 层数据源**。
`tools/freshness_gate.py --fetch` 直接复用本技能的 API 契约拉取 `ETL_TIME` / `LAST_UPDATE` / `MINS`。

**分工**：
- **闸门 6** 只取「时点」，判**时序是否倒挂、DWS 快照是否落后**
- **本技能** 做**性能分析**（谁慢、慢多少、异常任务）

> 🔴 **铁律**：不得用本技能的分析结论去推翻数据正确性判断 —— 抽数慢 ≠ 数据错，抽数时点不同 ≠ 数据错（见 `knowledge/design/policy/data_freshness_rules.md`）。

---

## 五、边界

- 只做**抽数日志分析**，不生产数据口径
- 存储过程执行记录 → 走 `sg-cbprod-procedure-analyzer`（成枢）
- 报表导出 → `sg-gzprod-report`（管制）/ `sg-cbprod-report`（成本）
