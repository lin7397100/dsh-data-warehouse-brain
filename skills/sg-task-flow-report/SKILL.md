---
name: sg-task-flow-report
description: "三钢数仓智脑：任务流复盘与调用链可观测技能。追踪专家/技能调用链、生成每任务流报告、监控快车道纪律与长上下文腐化风险，定位性能瓶颈并产出改进建议。对应原 DATA AGENT data-agent-supervisor 的监管职能。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, supervision, observability, flow-report, performance]
owner: sg-supervisor
---

# sg-task-flow-report · 任务流复盘与调用链可观测

## 定位

专家团的"黑匣子"。把每一次问数/任务的**谁调了谁、花了多久、走了哪条路径**结构化落盘，用于复盘与性能优化。

## 调用链记录规范

每任务一条 trace：

```json
{"trace_id":"T-<timestamp>",
 "intent":"查本月圆棒产量及同比变化",
 "route_decision":"fast|live|adhoc",
 "chain":[{"from":"team-lead","to":"sg-materialized-sql","skill":"sg-materialized-sql",
           "start":0,"end":820,"latency_ms":820,"hit_path":"fast","confidence":0.95}],
 "total_latency_ms":1820,"open_issues":[]}
```

`route_decision` 取值：
- `fast`：命中 indicator_index → sg-materialized-sql 物化直查（**期望路径**，秒级）
- `live`：未命中但语义层注册 → sg-dsl-compiler 实时编译
- `adhoc`：体系外 → sg-adhoc-indicator 即席构建

## 每任务流报告

落 `knowledge/design/supervision/flow_<trace_id>.md`：

```
# 任务流报告 <trace_id>
- 意图：。
- 路由决策：fast / live / adhoc
- 调用拓扑：team-lead → sg-materialized-sql（单跳）
- 耗时分布：语义解析 0.8s / 执行 0.9s / 渲染 0.3s
- 命中路径审计：✅ 走快车道，未加载全量注册表
- 瓶颈：无
- 改进建议：无
```

## 性能纪律（快车道守卫）

| 反模式 | 判定 | 动作 |
|---|---|---|
| 单指标问数却组队多专家 + 三引擎 | 全量加载 indicator_registry.json (4.68MB) | **告警 + 记反模式** |
| 任何专家把全量注册表载入上下文 | 上下文 > 阈值 | 告警，要求改走 indicator_index.json |
| 单步 > 30s / 全任务 > 5min | 超时 | 标记瓶颈段，给优化建议 |
| 嵌套/过度派发（agent 调 agent 调 agent） | 调用深度 > 2 | 告警，建议压平 |

## 技能健康度

维护 `knowledge/design/supervision/health.json`：
```json
{"skills":{
  "sg-materialized-sql":{"calls":128,"avg_ms":900,"fail":2,"fast_hit_rate":0.93},
  "sg-dsl-compiler":{"calls":9,"avg_ms":12000,"fail":1,"fast_hit_rate":0.0}
}}
```
周期性识别零调用/高耗时/高失败技能，回执编排器与技能进化专家。

## 运行命令

```bash
# 汇总健康度（示例：统计 flow_*.md 的路由分布）
python - <<'PY'
import json,glob,os
from collections import Counter
c=Counter(); lat=[]
for f in glob.glob("knowledge/design/supervision/flow_*.json"):
    d=json.load(open(f,encoding="utf-8"))
    c[d.get("route_decision")]+=1; lat.append(d.get("total_latency_ms",0))
print("route:",dict(c),"avg_total_ms:",int(sum(lat)/max(1,len(lat))))
PY
```

## 注意事项

1. **只观测不干预**：不改 SQL、不篡改结果，只记录与告警。
2. **快车道纪律优先**：发现单指标走重链即告警，归档反模式。
3. **全量加载即事故**：注册表全量入上下文视为性能事故，必须改走轻量索引。
