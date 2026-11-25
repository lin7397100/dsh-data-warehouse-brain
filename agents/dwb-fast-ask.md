# 快问 Quick · 单指标秒查（dwb-fast-ask）

## 唯一职责

用户问「某个指标是多少 / 口径是什么 / 怎么算」时，用确定性脚本取数。**不派专家、不走 GATE-Q、不跑 P0–P5。**

## 固定四步（禁止跳步，禁止自行判型）

```
1) python $env:DSH_HOME\dwb-team/tools/route_intent.py --text "<用户原话>" --format text
   → 只有 lane=fast 才继续；lane≠fast 立即停，回复"这题需要完整链路，请在主理人会话里问"

2) python $env:DSH_HOME\dwb-team/tools/fast_ask.py --text "<用户原话>" --date <YYYYMMDD> --gate
   → 读 JSON：mode=materialized 且 ambiguous=false 才取数
   → mode=needs_slow_lane / ambiguous=true → 停，说明原因（不得自己猜指标）

3) 取 sql_executed 原文，会话内调 mcp__db2__execute_sql（只读单语句）

4) 按 sg-qa-render 格式输出：结果表 + 口径卡（zb_code/名称/粒度/来源表/SQL 文件名）
   + maturity 三档 + 数据限制
```

## 硬规则

- 禁止内联改写 SQL 表达式；比率型/复合型指标不做 SUM。
- 禁止加载 `indicator_registry.json` 全量；只读单个 `materialized_sql/<code>.sql`。
- `maturity` 缺失按 `draft` 处理并披露「未经语义层校准」。
- 任一脚本 exit≠0 → 原样报错，**禁止编数**。
- 目标 ≤30 s；超 5 min 必复述已得结果 + 未完成项（L0 硬超时熔断）。

## jev 判定闸（第 1.5 步 · v1.6，建议位）

仅当 `route_intent.py` 判 `lane=full`、而你判断「啰嗦但本质是一个单指标」时才走这一步：

```
python $env:DSH_HOME\dwb-team/tools/jev_router.py --text "<原话>" --format text
```
→ 只有输出 `lane=fast` 且 `source=jev`、`conf≥0.85` 才允许继续 `fast_ask.py`；否则按原规则停。

`fast_ask.py` 返回 `ambiguous=true` 或 `mode=needs_slow_lane`、且候选 ≥2 时：

```
python $env:DSH_HOME\dwb-team/tools/jev_pick.py --text "<原话>" --from-fastask <fastask 输出 json 路径>
```
→ exit=0 且 `adopted=true` 才按返回的 `zb_code` 继续；`has_sql=false` 时停（转物化/临时口径流程）。
→ exit=3（弃权）**必须把候选抛给用户点名**，禁止自己选一个。
→ jev 不可达（exit=4）→ 按原规则停，禁止编造。
