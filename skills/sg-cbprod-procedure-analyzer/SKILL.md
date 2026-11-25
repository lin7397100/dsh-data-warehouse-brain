---
owner: sg-cbprod
dispatch: true
name: sg-cbprod-procedure-analyzer
description: |
  三钢数仓智脑·日成本存储过程执行记录性能分析（成枢主责）。从 CBMS PJJOB API 拉取日成本域存储过程执行记录，按数据仓库分层（ODS/DWD/DWS/ADS/DIM）分类统计耗时、成功率、异常作业，产出 6 图 + 搜索式明细 HTML 报告并投递企微群聊。过程日志 API `http://eplat.fjsg.com/service/D_A_SMBBCB00_PJJOB`（clientId=sgdw-cb01）。触发："存储过程执行记录/过程性能分析/PJJOB/日成本过程分析/存储过程跑没跑"。
version: 2.0.0
tools_required: [exec]
---

# 日成本存储过程执行记录 · 性能分析

> **归属**：日成本域 → **成枢 `sg-cbprod`** 主责
> **来源**：`C:\Users\lin\Downloads\personal\cbms-procedure-performance-analyzer` v2.0.0（2026-11-20 并入）

---

## 一、数据源（实测可用 2026-11-20）

| 项 | 值 |
|---|---|
| **API** | `http://eplat.fjsg.com/service/D_A_SMBBCB00_PJJOB` |
| **方法** | POST `application/json;charset=UTF-8` |
| **认证** | `clientId=sgdw-cb01` · `clientSecret=537410A26EC7FE29B7258A7861D1C59F` |
| **日期参数** | `params.startTimestamp`，`YYYY-MM-DD` |
| **默认时间窗** | `05:00`–`07:00`（按 `START_TIMESTAMP` 的 HHMM 过滤） |
| **上限** | 2000 条 |

**请求体**：
```json
{"clientId":"sgdw-cb01","clientSecret":"537410A26EC7FE29B7258A7861D1C59F",
 "params":{"startTimestamp":"YYYY-MM-DD"},
 "showCount":"true","offset":"0","limit":2000}
```

**9 个返回列**：`JOB_NAME / MODULE_TYPE / IS_SUCCESSFUL / START_TIMESTAMP / LAST_TIMESTAMP / XHTIME / REMARK1 / PARAM_INFO / ERROR_DESC`

> ⚠️ **`XHTIME` 是秒**（不是分钟，与 ETL 的 `MINS` 相反）；`START_TIMESTAMP`/`LAST_TIMESTAMP` 为 `YYYYMMDDHH24MISS` 14 位字符串。

---

## 二、分层识别（按过程名前缀）

| 前缀 | 分层 |
|---|---|
| `P_ODS_` | ODS 原始层 |
| `P_DWD_` | DWD 明细层 |
| `P_DWS_` | DWS 汇总层 |
| `P_ADS_` | ADS 应用层 |
| `P_DIM_` | DIM 维度层 |
| 其他 | 未识别 |

**6 图**：分层耗时环形 / 分层执行次数环形 / Top20 高耗时过程（横向柱） / 耗时分布柱 / 执行时间分布折线 / 分层平均耗时
**5 表**：整体概况（8 指标卡） / 分层统计对比 / 分层明细（按总耗时降序） / Top20 高耗时 / 异常作业（3σ） / 执行明细（全量 + 搜索框）

**分析指标**：执行总数、成功数、失败数、成功率、总/平均/最长/最短耗时、3σ 异常检测、分层统计、按过程名聚合、耗时分布（0-5s / 5-10s / 10-30s / 30-60s / 1-2min / 2-5min / 5min+）、按分钟执行分布

---

## 三、执行

```bash
cd $env:DSH_HOME\dwb-team/skills/sg-cbprod-procedure-analyzer

python script.py -d "2026-11-19"                        # 指定日期
python script.py                                        # 当天
python script.py -d "2026-11-19" --no-send              # 仅生成
python script.py -d "2026-11-19" -c "<chatid>"          # 指定群聊
python script.py -d "2026-11-19" -o "D:/reports"        # 指定输出
python script.py -d "2026-11-19" --time-start "05:00" --time-end "07:00"
```

| 参数 | 说明 | 默认 |
|---|---|---|
| `-d/--date` | 查询日期 `YYYYMMDD` 或 `YYYY-MM-DD` | 当天 |
| `-c/--chatid` | 目标群聊 | 内置 |
| `-o/--output` | 输出目录 | 桌面 |
| `--no-send` | 不发送企微 | false |
| `--time-start` / `--time-end` | 时间范围 | `05:00` / `07:00` |

**依赖**：`pip install requests`（已装）

---

## 四、与闸门 6 的关系（重要）

本技能的 API **正是闸门 6「埋点时点」的过程执行层数据源**。
`tools/freshness_gate.py --fetch` 直接复用本技能 API 契约拉取 `START_TIMESTAMP` / `LAST_TIMESTAMP` / `XHTIME` / `IS_SUCCESSFUL`。

**分工**：
- **闸门 6** 只判「过程跑没跑 / 成功没 / 时点是否倒挂」
- **本技能** 做**性能分析**（谁慢、慢多少、3σ 异常）

> 🔴 **铁律**：`IS_SUCCESSFUL='F'` 才是**真失败**；`XHTIME` 偏高只是**慢**，不等于数据错。

---

## 五、边界

- 只做**过程执行记录分析**，不生产口径
- ETL 抽数日志 → 走 `sg-gzprod-etl-analyzer`（管枢）
- 日成本报表导出 → `sg-cbprod-report`（成枢）
