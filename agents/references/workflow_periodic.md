# 周期性自动化任务与定时调度（P1.5+P5.4 新增 · 2026-11-03）

> 适用场景：定时任务（如"每天早上 9 点推送生产日报"）、周期性自动化、批量任务。

---

## Workflow D · 周期性自动化任务

**触发条件**：用户要求定时/周期性/每天/每周执行数据查询或报告生成。

### 派发序列

```
Step D0 · 确认需求
编排器确认：任务内容、频次（每天/每周/每月）、执行时间、输出渠道（企微群/个人/文件）

Step D1 · 设计 Automation Prompt
按以下模板输出 automation prompt：
  "加载数仓智脑专家团，执行以下任务：[任务内容]。
   要求：走快车道四段式 / 完整根因流程（根据任务类型），输出到 [渠道]。
   数据范围：<基地>/<指标码>/<日期范围>"

Step D2 · 创建自动化
调用 automation_update({
  mode: "create",
  name: "<任务名称>",
  prompt: "<Step D1 产出的 prompt>",
  scheduleType: "recurring",
  rrule: "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",   // 示例：每天9:00
  status: "ACTIVE",
  cwds: "<包根路径>"
})

Step D3 · 创建监视 Trace
每次自动化执行时，自动 init trace + health-check，记录覆盖率。

Step D4 · 首次手动触发验证
创建后应手动触发一次验证自动化是否正常工作。
```

### 常见定时任务模板

| 任务 | rrule | prompt 模板 |
|---|---|---|
| 每日生产日报 | FREQ=DAILY;BYHOUR=8;BYMINUTE=30 | "加载数仓智脑专家团，查昨日三基地钢铁料耗/铁水耗/钢产量，生成趋势HTML报告，通过翰枢推送到默认企微群" |
| 每周成本对标 | FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0 | "加载数仓智脑专家团，对上周三基地炼钢成本做对标分析，产出对比报告推送到默认群" |
| 每日异常检测 | FREQ=DAILY;BYHOUR=7;BYMINUTE=0 | "加载数仓智脑专家团，检测昨日三基地关键指标异常（钢铁料耗/铁水耗/产量），异常项走 T2b 根因" |

---

## P5.4 · automation_update 衔接规范

| 场景 | 使用工具 | 不使用 |
|---|---|---|
| 创建定时任务 | `automation_update`（mode=create） | `todo_write` |
| 修改定时任务 | `automation_update`（mode=update） | 直接编辑 task 文件 |
| 暂停定时任务 | `automation_update`（mode=update, status=PAUSED） | 删除任务 |
| 查看定时任务 | `automation_update`（mode=list） | 文件系统遍历 |

> 定时任务的 prompt 中**必须包含「加载数仓智脑专家团」指令**，否则自动化执行时不会加载团队上下文，退化为普通 AI 执行。