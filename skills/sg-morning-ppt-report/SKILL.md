---
owner: sg-gzprod
dispatch: true
name: sg-morning-ppt-report
description: |
  三钢数仓智脑·早会 PPT 报表批量导出（管枢主责）。从共享服务接口取报表路径结构表（D_A_SMBBZZ00_ZHPPTINFO），Playwright 逐页渲染导出 46 份单页 PDF（A2 横向 0.85 缩放），合并为 `早会PPT报表全部(YYYY-MM-DD).pdf` 并裁剪空白、删除 AI 声明、Ghostscript 压缩后投递企微群聊。触发："早会PPT报表/早会帆软报表导出/早会PPT报表生成/导出早会PPT全部报表"。
version: 3.0.0
tools_required: [exec]
---

# 早会 PPT 报表 · 批量导出

> **归属**：生产管制域 → **管枢 `sg-gzprod`** 主责
> **来源**：`C:\Users\lin\Downloads\personal\all-report-exporter`（skill name: `chat-report-exporter` v3，2026-11-20 并入）

---

## 一、产物

**`早会PPT报表全部(YYYY-MM-DD).pdf`** —— 一份合并好的完整 PDF（46 份单页合并）。

---

## 二、处理流程（7 步）

| # | 步骤 | 说明 |
|---|---|---|
| 1 | 取报表列表 | `D_A_SMBBZZ00_ZHPPTINFO` 接口 |
| 2 | 筛选排序 | 按 `SORT` 字段 |
| 3 | 拼 URL | 拼接 `p_date` 参数 |
| 4 | **Playwright 渲染** | 逐页导出 **46 份单页 PDF**（A2 横向 / 0.85 缩放） |
| 5 | 合并 + 裁剪 | 合成一份 PDF + 裁空白边距 + **删除 AI 声明** |
| 6 | **Ghostscript 压缩** | `/screen` 质量 |
| 7 | 企微投递 | `/cgi-bin/appchat/send`（群聊） |

---

## 三、执行

```bash
cd $env:DSH_HOME\dwb-team/skills/sg-morning-ppt-report/scripts

python3 export_reports.py                      # 默认导出昨天报表 → 默认群聊
python3 export_reports.py --date 2026-11-19    # 指定日期
python3 export_reports.py -c <chatid>          # 指定群聊
```

---

## 四、企微配置

| 项 | 值 |
|---|---|
| Token API | `http://eplat.fjsg.com/service/D_A_SMBBRAOC00_MRDJ_TOKEN` |
| 企业微信 | `https://wecom.fjsg.com.cn` |
| 默认群聊 ID | `MTk3MDMyNTYwMzAxNTYxMjpHygrR7KYUifUkH0BE_m4` |
| 发送方式 | 群聊 `appchat/send` |

---

## 五、依赖（不可省）

```bash
pip install requests playwright PyPDF2
playwright install chromium
# Ghostscript 需预装：apt install ghostscript / Windows 装 gs 并加 PATH
```

> ⚠️ **Playwright 浏览器必须已安装**，否则第 4 步渲染 0 页。
> 实测 2026-11-20：`playwright-core` 与 `ms-playwright` 浏览器均在位。

---

## 六、定时任务

```
15 7 * * * PYTHONUNBUFFERED=1 cd <skill>/scripts && python3 export_reports.py >> <skill>/logs/chat-report-*.log 2>&1
```

> 与 `sg-gzprod-etl-analyzer`（7:20 群聊）错峰：本技能 7:15 跑。

---

## 七、边界

- 只做**早会 PPT 报表批量导出 + 合并 + 投递**
- 单张管制报表 → `sg-gzprod-report`（管枢）
- 日成本报表 → `sg-cbprod-report`（成枢）
