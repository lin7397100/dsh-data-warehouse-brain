---
owner: sg-cbprod
dispatch: true
name: sg-cbprod-report
description: |
  三钢数仓智脑·成本域报表导出（成枢主责）。导出 CBMS 成本管理系统 15 种工序成本报表（工序指标表/边际贡献表/焦化·烧结·球团·炼铁/长材·板材炼钢/一棒·圆棒·中大棒/一高·二高·三高/中板），投递企微个人（默认工号 230012）与 AI赋能群。报表服务地址 `http://172.16.100.25:8080/webroot/decision/view/report`。触发："导出日成本报表/CBMS报表/工序指标表/边际贡献表/炼钢工序成本表/成本管理报表"。
version: 1.0.0
tools_required: [exec]
---

# 成本域报表导出（sg-cbprod-report）

> **归属**：日成本域（CBPROD）→ **成枢 Ledger（`sg-cbprod`）主责**
> **执行器**：`skills/sg-report-delivery/scripts/cbms_report.py`（单一实现，本技能只做域路由与口径校验，不复制脚本）
> **变更**：2026-11-20 按用户要求，日成本报表从「翰枢代管」改回**域专家主责**；翰枢退化为纯投递通道。

---

## 一、什么时候用

| 触发 | 示例 |
|---|---|
| 「导出 / 下载 / 生成」+ **日成本 / CBMS / 成本报表 / 工序成本 / 边际贡献 / 工序指标** | 「导出昨天的日成本报表」「算一下边际贡献表发我」 |
| 「成本管理报表 / 成本报表发群里」 | 「15 张工序成本表发 AI赋能群」 |

**不适用**：管制报表 / 生产报表 / ZZGZ → 走 `sg-gzprod-report`（管枢）。

---

## 二、支持的 15 种报表

| 编号 | 报表名称 | 编号 | 报表名称 |
|---|---|---|---|
| 1 | 工序指标表 | 9 | 一棒工序成本表 |
| 2 | 边际贡献表 | 10 | 圆棒工序成本表 |
| 3 | 焦化工序成本表 | 11 | 中大棒工序成本表 |
| 4 | 烧结工序成本表 | 12 | 一高工序成本表 |
| 5 | 球团工序成本表 | 13 | 二高工序成本表 |
| 6 | 炼铁工序成本表 | 14 | 三高工序成本表 |
| 7 | 长材炼钢工序成本表 | 15 | 中板工序成本表 |
| 8 | 板材炼钢工序成本表 | | |

---

## 三、报表服务（铁律）

| 项 | 值 |
|---|---|
| **服务地址** | **`http://172.16.100.25:8080/webroot/decision/view/report`** |
| 引擎 | CBMS 成本管理系统（帆软封装） |
| 默认日期 | 前一天 |
| 环境变量覆盖 | `FINEREPORT_BASE_URL` |

> 该地址为内网，需三钢内网/VPN。

---

## 四、执行（一条命令）

```bash
cd $env:DSH_HOME\dwb-team/skills/sg-report-delivery/scripts

python cbms_report.py                        # 全部 15 张 → 个人 230012 + AI赋能群
python cbms_report.py -r 1,2,9               # 指定报表编号（工序指标/边际贡献/一棒）
python cbms_report.py -u 230012              # 指定个人收件人
python cbms_report.py -u 230012 -d 2026-11-19
python cbms_report.py --chatid <CHATID>      # 仅发群聊（配合 --skip-user）
python cbms_report.py --send-xlsx-each       # 15 个 xlsx 逐个单独发送
python cbms_report.py --export-only          # 仅导出本地，不发送
```

**参数**：`-r/--reports` `-u/--user` `-d/--date` `--chatid` `--send-xlsx-each` `--export-only` `--save-path`

---

## 五、执行纪律

1. **禁止解释、禁止询问**：命中触发词即直接执行脚本。
2. **成功标志**：`[OK] 成功！报表已发送到企微。`；仅导出时 `[OK] 成功！报表已导出（未发送）。`
3. **失败保留现场**：`[FAIL]` 打印异常并清理临时文件，退出码 1。
4. **HTML 合并失败不删 xlsx**：用 `--send-xlsx-each` 兜底。
5. **通道隔离铁律**：HTTP 上传的 `media_id` **只能**经 HTTP 通道发送（WebSocket 会报 `40007`）。

---

## 六、导出前的口径核查（不可跳过）

1. 先加载 `sg-cbprod-warehouse` v2.0 技能，取**口径决策树 + SQL 模板**
2. 成本域**六要素**必须齐备：`ACCOUNT_PERIOD`（版本 Vn）+ `DATA_SOURCE`/`DATA_TYPE×RC_TYPE` + `COST_CENTER` + `FACTORY_CODE` + `COMPANY_CODE='100'` + `COMPARE_CHK`，**缺一作废**
3. 经 `sg-db2-executor` 查 `SMBB_M_A_GZ01.T_ADS_DIM_GZ01` 实表取 `SQL1` 对拍
4. **口径确认后再导出**；口径有疑义→退回主理人，**不得凭印象出数**

---

## 七、依赖

```bash
pip install requests openpyxl
```
（实测 2026-11-20 两包均已安装）
