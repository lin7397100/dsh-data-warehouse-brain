---
owner: sg-wecom-doc
deprecated: true
alias_of: sg-wecom-doc
dispatch: false
name: sg-report-delivery
description: |
  【兼容别名·勿直接派发】三钢数仓智脑：报表导出与企微投递统一技能。导出两类报表——① CBMS 成本管理系统的 15 种工序成本报表（工序指标/边际贡献/焦化·烧结·球团·炼铁/长材·板材炼钢/一棒·圆棒·中大棒/一高·二高·三高/中板）；② 帆软 FineReport 管制/生产/ERP 报表（ZZGZ.cpt）并自动修复 Excel 已知格式缺陷。修复后上传企微临时素材，投递至企微个人（默认工号 230012）和/或群聊（默认「AI赋能群」）。触发："导出CBMS报表/工序指标表/边际贡献表/炼钢工序成本表/成本管理报表/导出管制报表/查生产管制报表发给我/查ERP报表/把报表发到企微/发报表到AI赋能群"。
version: 1.0.0
tools_required: [exec]
---
> ⚠️ 已合并：本技能已并入 `sg-wecom-doc`。保留目录以兼容旧引用，新任务请调用 `sg-wecom-doc`。

> 🔀 **2026-11-20 路由变更（按域拆回）**：报表导出**不再统一走翰枢**，改回域专家主责 ——
> - **生产管制报表**（ZZGZ / 生产报表）→ **管枢 `sg-gzprod`** → 技能 `sg-gzprod-report`
> - **日成本报表**（CBMS / 边际贡献 / 工序成本）→ **成枢 `sg-cbprod`** → 技能 `sg-cbprod-report`
> - **翰枢 `sg-wecom-doc`** 退化为**纯投递通道**
> 本目录 `scripts/` 仍是**唯一执行器实现**（`finereport_export.py` / `cbms_report.py`），两个域技能直接引用，**不复制脚本**。


<!-- SG-SWIFT-MERGED-INTO-HANSHU v1 -->
> **owner 变更**：（原 owner 迅达 sg-report-delivery 已退役，能力并入 翰枢 sg-wecom-doc）

> **归属变更**：本技能原属「原迅达（`sg-report-delivery`）」专家。该专家已退役，其能力全量并入「翰枢 Hanshu（`sg-wecom-doc`）」。**本技能保留可用**，由翰枢调度执行；调度入口一律走 `sg-wecom-doc`。

# 报表导出与企微投递（sg-report-delivery）

把「报表导出 → 格式修复 → 企微素材上传 → 个人/群聊投递」收敛为一条命令。含两条独立产线，统一默认投递目标。

## 一、默认投递目标（铁律）

| 通道 | 默认值 | 说明 |
|------|--------|------|
| 个人 | 工号 `230012` | `message/send`，`touser` 为具体工号，**严禁 `@all`** |
| 群聊 | 从智能表格读取 |

两者**默认同时投递**；用 `--skip-user` / `--skip-chat` 关闭其中之一，`-u` / `--chatid` 可覆盖。

## 二、企微通道配置

> 2026-09-19 起统一使用「每日点检」应用；原「驾驶舱」`D_A_SMBBRAOC00_TOKEN` 已停用。

| 配置项 | 值 |
|--------|-----|
| TOKEN_API_URL | `http://eplat.fjsg.com/service/D_A_SMBBRAOC00_MRDJ_TOKEN` |
| TOKEN_CLIENT_ID | `sgoc-oc01` |
| TOKEN_CLIENT_SECRET | `${WECOM_TOKEN_CLIENT_SECRET}` |
| WECOM_BASE_URL | `https://wecom.fjsg.com.cn` |
| WECOM_AGENT_ID | `1000078`（每日点检） |

接口分工：个人 → `/cgi-bin/message/send`（touser + agentid）；群聊 → `/cgi-bin/appchat/send`（chatid）；素材 → `/cgi-bin/media/upload`（type=file）。两个通道共用同一个每日点检 Token。

## 三、产线 A：CBMS 日成本报表（`cbms_report.py`）

支持 15 种工序成本报表：

| 编号 | 报表名称 |
|------|----------|
| 1 | 工序指标表 |
| 2 | 边际贡献表 |
| 3-6 | 焦化/烧结/球团/炼铁工序成本表 |
| 7-8 | 长材/板材炼钢工序成本表 |
| 9-11 | 一棒/圆棒/中大棒工序成本表 |
| 12-14 | 一高/二高/三高工序成本表 |
| 15 | 中板工序成本表 |

```bash
cd <skill>/scripts

python cbms_report.py                       # 全部报表 → 默认个人230012 + AI赋能群
python cbms_report.py -r 1,3,5              # 指定报表编号
python cbms_report.py -u 230012             # 指定个人收件人
python cbms_report.py -u 230012 -d 2026-03-15
python cbms_report.py --chatid <CHATID>     # 仅发群聊（配合 --skip-user）
python cbms_report.py --send-xlsx-each      # 15个xlsx逐个单独发送（HTML合并失败时不删除xlsx）
python cbms_report.py --export-only         # 仅导出本地，不发送
```

参数：`-r/--reports` `-u/--user` `-d/--date` `--chatid` `--send-xlsx-each` `--export-only` `--save-path`

## 四、产线 B：帆软管制/生产/ERP 报表（`finereport_export.py`）

导出 `GZ01/ZZGZ.cpt`（默认前一天），并自动修复 FineReport 已知格式缺陷：

1. 工作簿「三钢集团生产信息总览」：K42 底部多余内容 → 合并修正为 `K28:V44`；「十一、昨日质量」区域修正为 `K32:V48`
2. 工作簿「三明闽光生产经营日报（2）」：备注区 `K27:W34`→`K27:W39`，`A29:A34`→`A29:A35`

```bash
python finereport_export.py                          # 默认：个人230012 + AI赋能群
python finereport_export.py -u 230012                # 指定个人（--emp-id 同义）
python finereport_export.py -u 230012|127761         # 多人工号用 | 分隔
python finereport_export.py -d 2026-03-15            # 指定报表日期
python finereport_export.py --chatid <CHATID>        # 覆盖默认群聊
python finereport_export.py --skip-chat              # 只发个人
python finereport_export.py --skip-user              # 只发群聊
python finereport_export.py --text --content "。."   # 发文本通知而非文件
python finereport_export.py --export-only            # 仅导出本地
```

参数：`-u/--user/--emp-id` `--chatid` `-d/--date` `--text` `--content` `--skip-chat` `--skip-user` `--export-only`

## 五、执行纪律

1. **禁止解释、禁止询问**：命中触发词即直接执行脚本，不用 cronjob 工具，不临时改脚本"修复"。
2. 成功标志：日志出现 `[OK] 成功！报表已发送到企微。`；仅导出时为 `[OK] 成功！报表已导出（未发送）。`
3. 失败时保留现场：`[FAIL]` 打印异常并清理临时文件，退出码 1。
4. 临时产物落在 `scripts/tmp/`（`.gitignore` 忽略），发送成功后自动清理。

## 六、依赖

```bash
pip install requests openpyxl
```

## 七、边界

- 本技能（由翰枢 `sg-wecom-doc` 调度执行）只做**报表文件导出与消息投递**，不生产数据口径（口径由数仓成员负责）。
- 企微**文档/智能表格**的读写落表走 `sg-wecom-doc`（翰枢），本技能不碰 wedoc 接口。

### 触发路由（主理人/翰枢调度）

<!-- SG-REPORT-ROUTE v1 -->

命中以下意图时**必须**调用本技能：

- 「导出/下载/生成 + 生产管制报表 / 管制报表 / 生产报表 / ZZGZ」
- 「导出/下载/生成 + 成本报表 / 日成本 / 边际贡献 / 工序成本 / CBMS」
- 「报表发给我 / 推送 / 投递 / 发到群里」
- 「查 XX 报表并发给我」

**默认投递通道**（用户未指定时）：默认个人 = 工号 `230012`；默认群聊 = `AI赋能群`（从智能表格读取）。

**执行链路不可跳步**：报表定位 → 取数渲染（DB2 MCP 优先，REST 需用户自备 lightcodegtw-token）→ 导出落盘（xlsx/html）→ 格式修复 → `media/upload` 取 media_id → 个人 `send_file_to_user` / 群 `send_file_to_group`。

**通道隔离铁律**：HTTP 上传的 media_id 只能经 HTTP 通道发送；经 WebSocket robot 发送会报 `40007`（app token 不同），二者不得混用。

**导出前协同核查**：先查知识库目录 `C:\Users\lin\WorkBuddy\2026-09-05-09-44-33\指标血缘报告` 下的 `T_ADS_DIM_GZ01.csv`、三份指标血缘文档（`ZZGZ_指标血缘.md` / `ZZGZ_JD02_指标血缘.md` / `GZJD02LDY_指标血缘.md`）、以及管枢/成枢域知识文档，确认指标口径后再导出。
