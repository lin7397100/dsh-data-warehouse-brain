---
owner: sg-gzprod
dispatch: true
name: sg-gzprod-report
description: |
  三钢数仓智脑·生产管制域报表导出（管枢主责）。导出帆软 FineReport 管制/生产/ERP 报表 `GZ01/ZZGZ.cpt`（默认前一天），自动修复 Excel 已知格式缺陷，投递企微个人（默认工号 230012）与 AI赋能群。报表服务地址 `http://172.16.100.25:8080/webroot/decision/view/report`。触发："导出管制报表/生产管制报表/ZZGZ/生产报表/查管制报表发给我"。
version: 1.0.0
tools_required: [exec]
---

# 生产管制域报表导出（sg-gzprod-report）

> **归属**：生产管制域（GZPROD）→ **管枢 Nexus（`sg-gzprod`）主责**
> **执行器**：`skills/sg-report-delivery/scripts/finereport_export.py`（单一实现，本技能只做域路由与口径校验，不复制脚本）
> **变更**：2026-11-20 按用户要求，管制报表从「翰枢代管」改回**域专家主责**；翰枢退化为纯投递通道。

---

## 一、什么时候用

| 触发 | 示例 |
|---|---|
| 「导出 / 下载 / 生成」+ **管制报表 / 生产管制报表 / ZZGZ / 生产报表** | 「导出昨天的管制报表」「查 20261119 的 ZZGZ 发我」 |
| 「报表发给我 / 发到群里 / 查报表并发给我」+ 生产域语义 | 「生产报表发 AI赋能群」 |

**不适用**：日成本 / 边际贡献 / 工序成本 / CBMS → 走 `sg-cbprod-report`（成枢）。

---

## 二、报表服务（铁律）

| 项 | 值 |
|---|---|
| **服务地址** | **`http://172.16.100.25:8080/webroot/decision/view/report`** |
| 报表模板 | `GZ01/ZZGZ.cpt`（帆软 FineReport） |
| 默认日期 | 前一天 |
| 环境变量覆盖 | `FINEREPORT_URL` / `FINEREPORT_VIEWLET` |

> 该地址为内网，需三钢内网/VPN。实测 2026-11-20 返回 **HTTP 200**。

---

## 三、执行（一条命令）

```bash
cd $env:DSH_HOME\dwb-team/skills/sg-report-delivery/scripts

python finereport_export.py                          # 默认：个人 230012 + AI赋能群
python finereport_export.py -d 2026-11-19            # 指定报表日期
python finereport_export.py -u 230012                # 指定个人
python finereport_export.py -u 230012|127761         # 多人工号（| 分隔）
python finereport_export.py --chatid <CHATID>        # 覆盖默认群聊
python finereport_export.py --skip-chat              # 只发个人
python finereport_export.py --skip-user              # 只发群聊
python finereport_export.py --export-only            # 仅导出本地，不发送
```

**参数**：`-u/--user/--emp-id` `--chatid` `-d/--date` `--text` `--content` `--skip-chat` `--skip-user` `--export-only`

---

## 四、自动格式修复（脚本内置，不改）

| 工作簿 | 缺陷 | 修正 |
|---|---|---|
| 三钢集团生产信息总览 | K42 底部多余内容 | 合并修正为 `K28:V44`；「十一、昨日质量」区修正为 `K32:V48` |
| 三明闽光生产经营日报（2） | 备注区越界 | `K27:W34`→`K27:W39`，`A29:A34`→`A29:A35` |

---

## 五、执行纪律

1. **禁止解释、禁止询问**：命中触发词即直接执行脚本，不临时改脚本"修复"。
2. **成功标志**：`[OK] 成功！报表已发送到企微。`；仅导出时 `[OK] 成功！报表已导出（未发送）。`
3. **失败保留现场**：`[FAIL]` 打印异常并清理临时文件，退出码 1。
4. **通道隔离铁律**：HTTP 上传的 `media_id` **只能**经 HTTP 通道发送；经 WebSocket robot 发送会报 `40007`，二者不得混用。
5. 临时产物落 `scripts/tmp/`，发送成功后自动清理。

---

## 六、导出前的口径核查（不可跳过）

1. 经 `sg-db2-executor` 查 `SMBB_M_A_GZ01.T_ADS_DIM_GZ01` 实表取该 `ZB_CODE` 的 `SQL1`
2. Grep 三份指标血缘文档：`knowledge/kb/ZZGZ_指标血缘.md`、`ZZGZ_JD02_指标血缘.md`、`GZJD02LDY_指标血缘.md`
3. Read 管枢域知识：`knowledge/kb/管枢_生产管制域GZPROD_知识库文档.md`
4. **口径确认后再导出**；口径有疑义→退回主理人，**不得凭印象出数**

---

## 七、依赖

```bash
pip install requests openpyxl
```
（实测 2026-11-20 两包均已安装）
