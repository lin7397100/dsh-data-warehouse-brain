# 数据分析模型驱动规范（P2 强制 · 函数实算→结论→图表）

> 生效：2026-11-15 ｜ 触发：IntentContract `deliverable.analysis_required=true` 或任务型 Q2(含趋势/对比)/Q3(归因)/含"分析/预测/相关/检验/异常"词。
> 目的：落实用户诉求「一定要利用数据分析的各个模型和函数等手段进行分析，最终生成可视化数据分析报告」，禁止"只做 SQL 取数 + 画图"的浅层交付。

## 一、为什么需要（根因）
原分析引擎 `sg-data-analysis-engine` 是共享规范，`analysis-patterns.md` 列了方法选型，但**无强制派发、无函数实算门禁**——P2 阶段常退化为"SQL 出数 → 前端画折线"，没有统计检验/归因分解/模型计算的参与，结论停留在数字罗列。

## 二、P2 计算阶段强制六步链（缺一即 P2 闸门不过，禁止进 P3 报告）

| 步 | 动作 | 主责专家 | 工具/函数 | 产物 |
|---|---|---|---|---|
| 1 | **数据画像** | 砺真 sg-quality | `scripts/data_profiler.py`（行数/类型/空值率/基数/分布/异常值） | `<workspace>/artifacts/analysis/<trace>_profile.json` |
| 2 | **方法选型** | 砺真 sg-quality | `analysis-patterns.md` 问题→方法表 | `analysis_plan.json`（问题→方法→理由） |
| 3 | **函数实算** | 砺真 sg-quality | Python（venv `default`，`random_state=42`）：pandas/numpy/scipy/statsmodels/sklearn | `analysis_result.json`（函数签名+参数+返回值） |
| 4 | **结论提炼** | 砺真 sg-quality | 显著性/效应量/置信区间判读 | `findings[]`（含 [已证实]/[证据不足] 标注） |
| 5 | **图表规格** | 明鉴 sg-insight | 消费 findings 生成 charts_spec（图型/字段/标注） | `data_package.json.charts_spec` |
| 6 | **报告渲染** | 明鉴/若溪/达仕 | 契约冻结后渲染，数值字面一致 | HTML（四层下钻 + 内联 SVG/ECharts） |

**禁止**：① 跳过 2/3 直接画图；② 结论无函数证据（"看着像上升"）；③ 主理人内联做函数实算（必须派砺真）。

## 三、方法→函数映射（强制选型表）

| 分析诉求 | 方法 | Python 函数（示例） | 输出判据 |
|---|---|---|---|
| 两组均值差异 | 独立样本 t 检验 / Mann-Whitney U | `scipy.stats.ttest_ind` / `mannwhitneyu` | p<0.05 + 效应量 Cohen's d |
| 多组比较 | 单因素 ANOVA | `scipy.stats.f_oneway` | p 值 + 事后检验 |
| 相关性 | Pearson / Spearman | `scipy.stats.pearsonr` / `spearmanr` | r + p；注明相关≠因果 |
| 趋势 | 移动平均/指数平滑/季节分解 | `statsmodels.tsa.*` | 置信区间 + 假设条件 |
| 异常检测 | 3σ / IQR / isolate forest | `numpy` 分位 / `sklearn.ensemble.IsolationForest` | 异常点清单 + 阈值 |
| 成本归因 | 量-价-结构三因子 / 连环替代 | 自写分解函数（落盘可复现） | 残差=0 闭合校验 |
| 贡献度 | 分项对总差异贡献 | 分解函数 + 归一化 | Σ贡献=总差异 |
| 多维聚类/分型 | KMeans / 层次聚类 | `sklearn.cluster.KMeans` | 轮廓系数 + 分型解释 |

**铁律**：样本不足不给显著性结论；预测必给置信区间与假设；相关不等于因果；随机种子固定 `random_state=42`，脚本落盘可复现。

## 四、图表驱动契约（P2→P3）
`data_package.json`（由主理人组装，明鉴/若溪消费）必须含：

```json
{
  "caliber": {"domain":"","period":"","factory":"","version":""},
  "data": {"rows":[], "source":""},
  "profile": {"profile_path":"","null_rate":{},"outliers":[]},
  "analysis": {"plan":"","functions":[],"results":{},"findings":[]},
  "charts_spec": [{"type":"line|bar|scatter|heatmap","title":"","x":"","y":"","annotate":["<finding ref>"]}],
  "lineage": {"data_gates":"pass/fail","indicator_level":"L?"}
}
```

明鉴/若溪**禁止各自取数或查 DB2**，只消费本数据包；图表的每个标注点须能对应到 `findings[]` 的某条函数结论。

## 五、质量门（P2 退出 G2 追加断言）
- □ `analysis_profile.json` 存在（画像已做）
- □ `analysis_result.json` 存在且含函数签名与返回值（实算已做）
- □ `findings[]` 非空且每条有函数证据
- □ `charts_spec` 每条 annotate 指向 finding
- 任一缺 → G2 不过，退回 P2 补做，禁止进 P3。

## 六、适用范围与豁免
- **快车道**（Q1 纯数值、fast_lane=true）：豁免函数实算链，但仍出数值三查（零值/量级/离群）。
- **T2a 趋势速览**：1 条区间 SQL + 7 条断言即可，不强制统计模型；用户点开下钻仍走完整血缘（第零铁律推论4）。
- **Q3/Q2-分析型/L2+**：强制全链，无豁免。
