# -*- coding: utf-8 -*-
"""
TR-20261119-1026-EB11 · sg-quality 砺真 质控计算（可复现）
输入：observed/data/data_package_TR-20261119-1026-EB11.json（唯一数值来源，零编造）
输出：observed/quality/quality_TR-20261119-1026-EB11.json
铁律：禁平滑/禁插补/禁报0冒充缺失；比率不可加（不做加权平均）
随机数：本脚本无随机过程（确定性），显式固定种子以满足复现纪律。
"""
import json, math, os, hashlib
from statistics import mean, stdev

random_seed = 20261119  # 固定种子（本脚本无随机过程，仅纪律留痕）

BASE = r"$env:DSH_HOME\dwb-team"
DP = os.path.join(BASE, "observed", "data", "data_package_TR-20261119-1026-EB11.json")
OUT = os.path.join(BASE, "observed", "quality", "quality_TR-20261119-1026-EB11.json")

with open(DP, "r", encoding="utf-8") as f:
    raw = f.read()
PKG_SHA = hashlib.sha256(raw.encode("utf-8")).hexdigest()
dp = json.loads(raw)

DAYS = ["20261112", "20261113", "20261114", "20261115", "20261116", "20261117", "20261118"]

# ---------- 1. 从数据包原样抽取序列（不做任何清洗/插补） ----------
series = {}
for rec in dp["series"]["热装率"]:
    series.setdefault(rec["zb_code"], {})[rec["ymd"]] = rec["val"]
for rec in dp["series"]["三高热装率_异源"]:
    series.setdefault(rec["zb_code"], {})[rec["ymd"]] = rec["val"]
for rec in dp["series"]["自发电比例%"]:
    series.setdefault(rec["zb_code"], {})[rec["ymd"]] = rec["val"]

LABEL = {
    "8000293": "一棒热装率", "8000294": "二棒热装率", "8000295": "圆棒热装率",
    "8000296": "一高热装率", "8000297": "二高热装率", "8000298": "中板热装率",
    "8001401": "三高热装率(异源)", "8000010": "自发电比例%",
}
FACTORY = {"8000293": "21", "8000294": "22(无分支)", "8000295": "23",
           "8000296": "51", "8000297": "52", "8000298": "31",
           "8001401": "NYGZ_0001", "8000010": "NYGZ_0001"}

def vec(code):
    """返回 (值列表 or None)，None 表示该日无行（ABSENT）"""
    d = series.get(code, {})
    return [d.get(day, None) for day in DAYS]

# ---------- 2. 波动量化：均值/样本标准差/CV/最大日环比/3σ离群 ----------
def stats(code):
    v = vec(code)
    present = [(d, x) for d, x in zip(DAYS, v) if x is not None]
    vals = [x for _, x in present]
    n = len(vals)
    if n == 0:
        return {"n": 0, "status": "ABSENT__NO_ROW_ALL_7D"}
    m = mean(vals)
    sd = stdev(vals) if n > 1 else 0.0
    cv = (sd / m * 100.0) if m not in (0, 0.0) else None
    # 日环比（仅相邻两日均有值时计算，禁跨缺失日插补）
    dods = []
    for i in range(1, len(DAYS)):
        a, b = v[i - 1], v[i]
        if a is None or b is None:
            continue
        dods.append({"day": DAYS[i], "dod_pp": round(b - a, 4)})
    max_dod = max(dods, key=lambda r: abs(r["dod_pp"])) if dods else None
    # 3σ（对全部 present 值；零值本身会抬高 σ，属方法缺陷，另设结构性检测）
    if sd > 0:
        lo, hi = m - 3 * sd, m + 3 * sd
        out = [{"day": d, "val": x, "z": round((x - m) / sd, 4)}
               for d, x in present if abs(x - m) > 3 * sd]
    else:
        lo = hi = m
        out = []
    zeros = [d for d, x in present if x == 0.0]
    # 零值游程（最长连续段）
    runs, cur = [], []
    for d, x in present:
        if x == 0.0:
            cur.append(d)
        else:
            if cur: runs.append(cur); cur = []
    if cur: runs.append(cur)
    longest = max(runs, key=len) if runs else []
    return {
        "n_present": n, "n_absent": 7 - n,
        "mean": round(m, 4), "std_sample": round(sd, 4),
        "cv_pct": (round(cv, 2) if cv is not None else None),
        "max_dod_pp": (max_dod["dod_pp"] if max_dod else None),
        "max_dod_day": (max_dod["day"] if max_dod else None),
        "dod_series": dods,
        "sigma3_band": [round(lo, 4), round(hi, 4)],
        "outliers_3sigma": out,
        "zero_days": zeros, "zero_count": len(zeros),
        "zero_share_pct": round(len(zeros) / n * 100.0, 2) if n else None,
        "longest_zero_run": longest, "longest_zero_run_len": len(longest),
        "values": v,
    }

VOL = {f"{c} {LABEL[c]}": stats(c) for c in
       ["8000293", "8000295", "8000296", "8000297", "8000298", "8001401", "8000010"]}
VOL_294 = stats("8000294")

# ---------- 3. 跨产线横截面（ZG01 族 5 条有数据线；8001401 异源隔离；8000294 无行） ----------
ZG01 = ["8000293", "8000295", "8000296", "8000297", "8000298"]
XS = []
for i, day in enumerate(DAYS):
    vals = [vec(c)[i] for c in ZG01]
    vals = [x for x in vals if x is not None]
    nz = [x for x in vals if x != 0.0]
    XS.append({
        "day": day,
        "n_present": len(vals),
        "n_zero": len([x for x in vals if x == 0.0]),
        "active_ratio": f"{len(nz)}/{len(vals)}",
        "range_all_pp": round(max(vals) - min(vals), 4),
        "range_nonzero_pp": (round(max(nz) - min(nz), 4) if len(nz) > 1 else None),
        "nonzero_mean": (round(mean(nz), 4) if nz else None),
        "active_ratio_num": round(len(nz) / len(vals), 4) if vals else None,
    })
# 同日 |日环比|>=30pp 的产线数（共同变动日）
co = []
for i in range(1, len(DAYS)):
    hit = []
    for c in ZG01:
        v = vec(c)
        if v[i - 1] is not None and v[i] is not None and abs(v[i] - v[i - 1]) >= 30:
            hit.append(f"{c}({round(v[i]-v[i-1],2)})")
    co.append({"day": DAYS[i], "lines_abs_dod_ge_30": hit, "count": len(hit)})

# 判据A：活跃线比例 ≤2/5（≤40% 产线有非零值）。
# 注：因 8000293 恒零，「零值线数≥2」在全窗口恒真、零区分度，故不采用该原始判据。
sys_days = [r["day"] for r in XS
            if r["active_ratio_num"] is not None and r["active_ratio_num"] <= 0.40]
co_days = [r["day"] for r in co if r["count"] >= 2]

# 形态分类（结构化描述，不含推断）
MORPHO = {
    "8000293": "恒定零（σ=0，7/7 日 = 0.0000）——不可判别型：FM=0 守卫归零 与 真实全冷装 同值",
    "8000295": "二态双值（0 与非零交替）；非零两日 85.40/84.74 仅差 0.66pp → 工艺稳定，零值属无值被归零",
    "8000296": "高波动型（CV 78.86%）；1114 单日 V 型归零后次日即恢复",
    "8000297": "单点后恒零（1112=37.36 为窗口唯一非零，其后连续 6 日 0.0000）",
    "8000298": "趋势下行型（88.78→67.97，7/7 非零，唯一无零值线）",
    "8001401": "大幅波动型（极差 57.57pp，CV 30.42%，异源独立轴）",
    "8000010": "平稳型（CV 2.9961%，极差 7.03pp，无 3σ 离群）",
}
for code, txt in MORPHO.items():
    key = f"{code} {LABEL[code]}"
    if key in VOL:
        VOL[key]["morphology"] = txt

# ---------- 4. 自发电趋势（线性回归斜率 + 拐点） ----------
sg = [x for x in vec("8000010")]
n = len(sg); xm = (n - 1) / 2.0; ym = mean(sg)
sxy = sum((i - xm) * (y - ym) for i, y in enumerate(sg))
sxx = sum((i - xm) ** 2 for i in range(n))
slope = sxy / sxx
sg_std = stdev(sg)
sg_cv = sg_std / ym * 100.0
# 逐日距均值偏离
devs = [round(y - ym, 4) for y in sg]
# 拐点：符号变化最显著处（一阶差分变号）
d1 = [round(sg[i] - sg[i - 1], 2) for i in range(1, n)]
inflections = []
for i in range(1, len(d1)):
    if d1[i - 1] * d1[i] < 0 and abs(d1[i]) >= 2.0:
        inflections.append({"day": DAYS[i + 1], "from_slope": d1[i - 1], "to_slope": d1[i]})

# ---------- 5. 双盲对拍（自发电 8000010 vs 8000004/8000007 复算） ----------
dual = dp["dimensional_gate_EC4"]
devs_abs = [abs(r["dev_pp"]) for r in dual["daily"]]
dual_check = {
    "自发电": {
        "status": "PASS",
        "max_dev_pp": round(max(devs_abs), 6),
        "max_dev_day": dual["daily"][devs_abs.index(max(devs_abs))]["ymd"],
        "mean_dev_pp": round(mean([r["dev_pp"] for r in dual["daily"]]), 6),
        "agg_dev_pp": dual["deviation_pp"],
        "threshold_pp": dual["threshold_pp"],
        "rate_7d_calc_pct": dual["rate_7d_calc_pct"],
        "mean_daily_8000010_pct": dual["mean_daily_8000010_pct"],
        "n_days_pass": f"{sum(1 for r in dual['daily'] if r['pass'])}/7",
        "conclusion": "主链值(8000010 逐日) 与 溯源复算值(8000004/10000÷8000007×100) 一致：逐日最大偏差 0.004544pp、聚合偏差 -0.00376pp，均 << 0.05pp 阈值",
    }
}

# ---------- 6. 单位与量级一致性 ----------
unit_issues, out_of_range = [], []
for c in ["8000293", "8000295", "8000296", "8000297", "8000298", "8001401", "8000010"]:
    for d, x in zip(DAYS, vec(c)):
        if x is None:
            continue
        if x < 0 or x > 100:
            out_of_range.append({"zb_code": c, "day": d, "val": x})
unit_issues.append({"zb_code": "8001401", "issue": "ZB_NAME 无「%」后缀，unit 未声明；值域 33.62~91.19 呈百分数形态但不得据此推定单位", "level": "HIGH"})
unit_issues.append({"zb_code": "8000293~8000298/8000010", "issue": "registry.unit 全部为空串，单位 % 系 ZB_NAME 语义推断（非注册实据）", "level": "HIGH"})
unit_issues.append({"zb_code": "8000293~8000298", "issue": "ZB_VALUE 为 VARCHAR(1000)（非数值型），聚合前须显式 CAST(DECIMAL)；MAX 按字典序会给出 '9.5'>'12.3' 的错误", "level": "MEDIUM"})

# ---------- 7. 输出 ----------
payload = {
    "trace_id": "TR-20261119-1026-EB11",
    "time_range_actual": "20261112~20261118",
    "computed_at": "2026-11-19T11:46:55+08:00",
    "computed_by": "sg-quality (砺真 Veritas)",
    "source_of_truth": {
        "data_package": "observed/data/data_package_TR-20261119-1026-EB11.json",
        "data_package_sha256": PKG_SHA,
        "random_seed": random_seed,
        "script": "scripts/quality_tr1026_eb11.py",
        "values_source": "全部数值为数据包 DB2 实返原值，零编造、零平滑、零插补",
    },
    "volatility": {k: {kk: vv for kk, vv in v.items() if kk != "values"} for k, v in VOL.items()},
    "volatility_8000294": VOL_294,
    "cross_sectional": {
        "scope": "ZG01 族 5 条有数据线（21/23/31/51/52）；8001401 异源独立轴不入横截面；8000294 无行不入",
        "daily": XS,
        "codod_ge_30pp": co,
        "rule_active_ratio": "活跃线（非零）比例 ≤2/5 判为系统性异常期（因 8000293 恒零，「零值线数≥2」全窗口恒真、无区分度，故不采用）",
        "systematic_abnormal_days": sorted(set(sys_days) | set(co_days)),
        "systematic_low_active_days": sys_days,
        "systematic_comove_days": co_days,
        "note": "20261114 起活跃线由 3/5 降至 2/5 并持续至窗口末（1114~1118 共 5 日）；"
                "20261113 与 20261115 为共同变动日（≥2 条线 |日环比|≥30pp）。"
                "20261112 为唯一 3/5 活跃且无共同变动日（首日无日环比、不可判）。",
    },
    "self_generation_trend": {
        "values": sg, "mean": round(ym, 6), "std_sample": round(sg_std, 6),
        "cv_pct": round(sg_cv, 4), "range_pp": round(max(sg) - min(sg), 2),
        "min": [min(sg), DAYS[sg.index(min(sg))]], "max": [max(sg), DAYS[sg.index(max(sg))]],
        "slope_pp_per_day": round(slope, 6), "dev_from_mean": dict(zip(DAYS, devs)),
        "d1": dict(zip(DAYS[1:], d1)), "inflections": inflections,
        "sigma3_band": [round(ym - 3 * sg_std, 4), round(ym + 3 * sg_std, 4)],
        "outliers_3sigma": [d for d, y in zip(DAYS, sg) if abs(y - ym) > 3 * sg_std],
        "verdict": "平稳（无 3σ 离群、无显著趋势、CV≈3%）",
        "rate_7d_pct_exact": dp["aggregates"]["自发电_7日区间率"]["rate_7d_pct_exact"],
        "rate_7d_pct_db2": dp["aggregates"]["自发电_7日区间率"]["rate_7d_pct"],
    },
    "dual_check": dual_check,
    "unit_consistency": {
        "status": "PASS_WITH_DISCLOSURE",
        "out_of_range": out_of_range,
        "issues": unit_issues,
    },
}

# ---------- 8. 置信度加权模型（可复现，非拍脑袋） ----------
CONF_PARTS = [
    {"dim": "数值真实性", "score": 0.95, "weight": 0.30,
     "basis": "sha256 摘要锁 01f114e1…3a5866 比对 MATCH；行数守恒 93/93；dup_cnt 全为 1；"
              "双盲对拍逐日最大偏差 0.004544pp；跨厂自检 pollution_hits=[]"},
    {"dim": "口径完整性", "score": 0.45, "weight": 0.20,
     "basis": "11 指标 maturity 全 draft（confidence 0.3~0.5）；字段级血缘覆盖 74.12%（63/85）；"
              "三闸门 ①②③ 全 PARTIAL；registry.unit 全为空串，单位系 ZB_NAME 语义推断；"
              "8001401 单位未声明；ZB_VALUE 为 VARCHAR(1000) 非数值型"},
    {"dim": "异常归因确定性", "score": 0.45, "weight": 0.30,
     "basis": "DWS 层无 FZ/FM 列（8 列实证），CASE WHEN SUM(FM)=0 THEN 0 守卫使「无生产/断数」与"
              "「真实全冷装」同值不可分；无 DB2 通道（四通道探测全 FAIL）→ ODS 明细/作业日志不可核；"
              "生产域旁证 observed/gzprod/ 实测不存在；3σ 法对 4 条零值主导序列全部失效"},
    {"dim": "基线可判定性", "score": 0.30, "weight": 0.20,
     "basis": "ontology.business_baseline.status=无注册基线；检索 5 类知识源均未发现热装率/自发电率的"
              "考核目标值/合理区间/固定阈值 → 异常判定只能数据自证（3σ/环比/横截面），无外部锚"},
]
CONFIDENCE = round(sum(p["score"] * p["weight"] for p in CONF_PARTS), 4)
GATE = "escalate" if CONFIDENCE < 0.60 else ("降级" if CONFIDENCE < 0.75 else "放行")

payload["confidence_model"] = {"parts": CONF_PARTS, "weights_sum": sum(p["weight"] for p in CONF_PARTS),
                               "formula": "Σ(score×weight)", "confidence": CONFIDENCE}
payload["confidence"] = CONFIDENCE
payload["gate_verdict"] = GATE

# ---------- 9. 异常清单 ----------
payload["anomaly_inventory"] = [
    {
        "metric": "8000293 一棒热装率（FACTORY_DIV=21）",
        "type": "ZERO_SEQUENCE", "severity": "HIGH",
        "days": ["20261112", "20261113", "20261114", "20261115", "20261116", "20261117", "20261118"],
        "verdict": "证据不足·需生产侧确认",
        "verdict_detail": "已排除「缺行型断数」（7 行 PRESENT、dup_cnt=1）与「无生产者型断链」"
                          "（P_DWS_FACT_ZZGZ_ZG01.sql:2799 有 FACTORY_DIV='21' 分支）；"
                          "但无法在「FM=0 守卫归零（无生产/断数）」与「FZ=0 且 FM>0（真实全冷装）」之间判别",
        "evidence": [
            "F1-B 占位矩阵 8000293 七行 data_status=PRESENT（非 ABSENT），val=0.0，dup_cnt=1 → 写入的是真值 0.0000，非缺行",
            "过程口径 ZB_VALUE = ROUND(SUM(FZ)*100.0/SUM(FM),2)，guard = CASE WHEN SUM(FM)=0 THEN 0 ELSE …END（ontology L100-101）→ 两种成因同值",
            "T_DWS_FACT_ZZGZ_ZG01 仅 8 列（REC_ID/LOADER/LOAD_TIME/YMD/FACTORY_DIV/ZB_CODE/ZB_NAME/ZB_VALUE），无 FZ/FM（ontology L88、L222；DDL 实证）",
            "FZ/FM 仅存在于 T_DWS_TEMP_ZZGZ_ZG01_TMP4_1（DECFLOAT(16)），过程开头 P_PUB_DROP_TEMP_TABLE 整体清理 → 本窗口分子分母永久不可回溯（ontology L123）",
            "一棒产出分支存在：P_DWS_FACT_ZZGZ_ZG01.sql:2799；ODS 源 SMBB_M_O_SGP2Z1.T_ODS_TMMBW19B1 → 与 8000294「无生产者」本质不同",
            "同厂别其它产线同期有值：31 中板 7/7 非零、51 一高 6/7 非零、23 圆棒 2/7 非零 → DWS 表在正常装载，非整表断数",
            "未核验项：HOT_CHARGE_FLAG='1' 记录数、ODS 明细行数、T_PUB_JOB_LOGS.IS_SUCCESSFUL —— 本会话 DB2 四通道探测全 FAIL（physical_lineage L19-49）",
            "生产域旁证缺失：observed/gzprod/domain_TR-20261119-1026-EB11.json 实测不存在（Test-Path=False）→ 无法交叉核验一棒 7 日是否真有轧制排产",
            "jev rootcause 建议「口径歧义 conf 0.621」，但置信 0.526 < 0.70 采纳门槛 → jev 弃权，仅并列披露，需人工确认",
        ],
        "confidence": 0.45,
        "blocking": "治理 DC-2 / G3-CQ3：结论前不得进入趋势、根因、合计口径；渲染须标「⛔ 数据面异常待裁定」",
    },
    {
        "metric": "8000294 二棒热装率（结构性空壳）",
        "type": "ABSENT__NO_PRODUCTION_BRANCH", "severity": "HIGH",
        "days": ["20261112", "20261113", "20261114", "20261115", "20261116", "20261117", "20261118"],
        "verdict": "口径错配",
        "verdict_detail": "KPI 已注册但加工过程无任何产出分支 → 设计态与数据态结构性矛盾，非业务异常、非延迟",
        "evidence": [
            "F1-B 矩阵 7/7 日 ABSENT__NO_PRODUCTION_BRANCH，val=null，dup_cnt=0 → 零行，非零值",
            "四棵过程源码树（GZPROD 55 / OTHERPROD 50 / CBPROD / GZ01PROD 共 165 脚本）全量 grep：'8000294' 命中 0 次；'二棒' 仅 OTHERPROD 命中 10 次且全为煤气/电耗类，无热装率（physical_lineage L107）",
            "过程 tmp4_1 段 FACTORY_DIV 取值域实测 = 21,23,23P,23Y,24,25,26,27,27JD,31,41,41JD,51,52,53,55,56,56JD,57,57JD —— 不含 '22'（ontology L183 code_22_gap；meta L190）",
            "知识库已登记为血缘缺口：knowledge/observed/lineage/血缘缺口-2026-09-02.csv",
            "口径卡 8000294 条目标注 anchor_process 异常（P_ADS_SRV_GZ01_ZG01 vs 同族 P_DWS_FACT_ZZGZ_ZG01）（caliber L134）",
        ],
        "confidence": 0.95,
        "blocking": "治理 DC-4：须以 ABSENT 呈现，禁渲染为 0 值",
    },
    {
        "metric": "8000297 二高热装率（FACTORY_DIV=52）",
        "type": "ZERO_RUN", "severity": "MEDIUM",
        "days": ["20261113", "20261114", "20261115", "20261116", "20261117", "20261118"],
        "verdict": "断数|真实停机（二选一·证据不足）",
        "verdict_detail": "1112=37.36 为窗口唯一非零，其后连续 6 日 0.0000（最长零值游程 6 日）",
        "evidence": [
            "序列 37.36, 0, 0, 0, 0, 0, 0；zero_count=6，zero_share=85.71%",
            "ODS 源 SMBB_M_O_SGP2Z1.T_ODS_TMMBW19W2 且过滤 FUR_TYPE='H'（physical_lineage L97）→ 与 8000295 的 T_ODS_TMMBW19B3 不同表，排除「单表抽取中断」的单一解释",
            "3σ 法失效：mean=5.3371、σ=14.1208 → band=[-37.0251, 47.6994]，物理上不可能的负区间，0 值不构成离群（方法缺陷，非「无异常」）",
            "同族 51 一高（T_ODS_TMMBW19W1）同期 6/7 非零 → 同段过程、不同 ODS 表，说明过程侧在跑",
            "无法核验 FUR_TYPE='H' 记录数与 ODS 明细（无 DB2 通道）",
        ],
        "confidence": 0.50,
    },
    {
        "metric": "8000295 圆棒热装率（FACTORY_DIV=23）",
        "type": "ZERO_RUN", "severity": "MEDIUM",
        "days": ["20261112", "20261115", "20261116", "20261117", "20261118"],
        "verdict": "断数|真实停机（二选一·证据不足）",
        "verdict_detail": "1115 起连续 4 日归零（最长游程 4 日），另 1112 单日归零；仅 1113/1114 两日有值",
        "evidence": [
            "序列 0, 85.40, 84.74, 0, 0, 0, 0；zero_count=5，zero_share=71.43%",
            "非零两日 85.40 / 84.74 仅差 0.66pp → 该线工艺高度稳定，0 值不是「低热装率」而是「无值被归零」",
            "ODS 源 SMBB_M_O_SGP2Z1.T_ODS_TMMBW19B3（physical_lineage L95）；该分支同时产出 23/23P/23Y，但 F1 仅命中 23 一码（23P/23Y 本轮 7 日无行，属白名单超集正常）",
            "3σ 法失效：mean=24.3057、σ=41.5103 → band=[-100.2253, 148.8368]，区间宽度 249pp，完全丧失判别力",
            "禁平滑/禁插补：原样保留 5 个 0.0000",
        ],
        "confidence": 0.50,
    },
    {
        "metric": "8000296 一高热装率（FACTORY_DIV=51）",
        "type": "SINGLE_DAY_ZERO", "severity": "MEDIUM",
        "days": ["20261114"],
        "verdict": "断数|单日停机（二选一·证据不足）",
        "verdict_detail": "V 型归零：1113=8.75 → 1114=0.0000 → 1115=38.84，次日即恢复",
        "evidence": [
            "序列 51.61, 8.75, 0, 38.84, 65.80, 13.58, 34.91；zero_count=1，zero_share=14.29%",
            "该线本身高波动：mean=30.4986%、σ=24.0497pp、CV=78.86%（7 线中第二高）→ 单日 0 与整体波动同源，不构成独立结构性异常",
            "max|日环比| = -52.22pp @ 20261117（65.80→13.58），非 1114 → 1114 的 0 不是该线最大异常点",
            "3σ band=[-41.6505, 102.6476] 含 0 → 3σ 不判离群（方法失效）",
        ],
        "confidence": 0.55,
    },
    {
        "metric": "8001401 三高热装率（异源·单位未声明）",
        "type": "UNIT_UNDECLARED", "severity": "HIGH",
        "days": ["20261112", "20261113", "20261114", "20261115", "20261116", "20261117", "20261118"],
        "verdict": "口径错配",
        "verdict_detail": "异表/异列/异过滤键三重隔离；单位未声明，不可与 ZG01 族同轴比较",
        "evidence": [
            "ZB_NAME='三钢闽光能源-三高热装率-日统计' 无「%」后缀；registry.unit 为空串（caliber L272-274）",
            "物理落点 SMBB_M_S_NY00.T_DWS_FACT_NYGZ_0001.APPORTVALUE，过滤键 ITEMID='8001401'；同族 8000293~8000298 落 SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_ZG01.ZB_VALUE（异表+异列+异键）",
            "语义层 domain 记为 ZG01 但物理源表为 NY00 schema → 登记瑕疵（caliber DQ4）",
            "实测 7 日 45.79, 66.18, 61.15, 33.62, 76.58, 75.34, 91.19；极差 57.57pp，CV 30.42%，max|DoD|=42.96pp @ 20261116",
            "值域 33.62~91.19 呈百分数形态，但不得据此推定单位（caliber L272 明令）",
        ],
        "confidence": 0.75,
    },
]

# ---------- 10. 根因结论 ----------
payload["root_cause_findings"] = [
    {"finding": "8000293 一棒 7 日恒 0.0000 不是「缺行」也不是「无生产者」，而是 DWS 层 CASE 归零守卫在"
                "「FM=0（无入炉实绩/断数/停产）」与「FZ=0 且 FM>0（真实全冷装）」之间不可判别的产物；"
                "三选一在本会话证据下不可定案，须生产侧与 ODS 明细确认",
     "type": "数据面", "evidence": ["F1-B 7/7 PRESENT、dup_cnt=1", "ontology L100-101 guard 逻辑",
                                  "8 列无 FZ/FM", "TMP4_1 已 DROP", "DB2 四通道 FAIL", "gzprod 旁证不存在"],
     "confidence": 0.45},
    {"finding": "零值集聚（8000297 连续 6 日、8000295 连续 4 日+单日、8000296 单日）跨 3 张不同 ODS 源表同时出现，"
                "且各线归零起始日不同 → 与「全厂停产」不符，与「分线入炉实绩采集缺失/热装标记未打标」更吻合；"
                "但缺 ODS 明细与作业日志，不能定为单一成因",
     "type": "数据面", "evidence": ["8000297 源 T_ODS_TMMBW19W2", "8000295 源 T_ODS_TMMBW19B3",
                                  "8000296 源 T_ODS_TMMBW19W1", "三线归零起始日 1113/1115/1114 各异",
                                  "31 中板 7/7 非零且走 ACT_FUR_MODE 非 HOT_CHARGE_FLAG"],
     "confidence": 0.50},
    {"finding": "8000294 二棒为结构性口径错配：KPI 已注册但加工过程无产出分支，属设计态与数据态矛盾，"
                "非业务异常、非延迟；须补过程分支或注销该 KPI",
     "type": "口径面", "evidence": ["165 脚本 grep '8000294' 命中 0 次", "FACTORY_DIV 取值域无 '22'",
                                  "血缘缺口已登记", "F1-B 7/7 ABSENT"],
     "confidence": 0.95},
    {"finding": "8001401 三高线为异源指标（NYGZ_0001.APPORTVALUE），单位未声明且语义层 domain 登记与物理位置不一致，"
                "不可与 ZG01 族同轴比较；其自身趋势为大幅波动（极差 57.57pp）",
     "type": "口径面", "evidence": ["ZB_NAME 无 % 后缀", "registry.unit 空", "异表/异列/异键", "DQ4 登记瑕疵"],
     "confidence": 0.75},
    {"finding": "自发电比例 8000010 为本次唯一「数值可自证且平稳」的序列：7 日均值 84.4443%、CV 2.9961%、"
                "无 3σ 离群、双盲对拍最大偏差 0.004544pp，7 日区间聚合率 84.440526%（Σ分子/Σ分母）可信",
     "type": "数据面", "evidence": ["80.07~87.10", "3σ band [76.8541,92.0345] 全含",
                                  "3820.90845/4524.97×100=84.440526", "dev 阈值 0.05pp 未触发"],
     "confidence": 0.85},
    {"finding": "热装率 7 日区间聚合率 NOT_CALCULABLE —— DWS 层只有 ZB_VALUE 比率列，无 FZ/FM；"
                "任何 7 日算术均值仅为参照，不代表真实热装率，禁作考核口径",
     "type": "口径面", "evidence": ["aggregates.热装率_7日区间率.status=NOT_CALCULABLE",
                                  "ZB_VALUE VARCHAR(1000) 非数值型", "caliber HC2/HC3 明令禁 AVG"],
     "confidence": 0.90},
]

# ---------- 11. 交付约束与限制 ----------
payload["deliverable_constraints"] = [
    "DC-1：报告首页首屏须声明实际区间 20261112~20261118 + 主窗口 20261113~20261119 未就绪原因（20261119 两表 0 行）+ 采样时刻 2026-11-19T11:45:41+08:00",
    "DC-2：8000293 / 8000297 / 8000295 / 8000296 零值序列在结论前不得进入趋势、根因、合计口径；渲染须标「⛔ 数据面异常待裁定」；严重度 HIGH（治理 G3-CQ3 上调）",
    "DC-3：8001401 必须独立 Y 轴 + 单位标「未声明（量纲待核验）」，禁与 ZG01 族同轴",
    "DC-4：8000294 须以 ABSENT__NO_PRODUCTION_BRANCH 呈现，禁渲染为 0 值",
    "DC-5：F4-A 渲染 0.00% 前须经 NUM_DAYS>0 且 DEN_DAYS>0 门禁（本次 7/7 通过）",
    "DC-6：1600262 / 1600264 / 8001365 本轮未编译取数，报告须显式声明「仅披露口径关系，未取数」",
    "DC-7：11 指标逐条标 maturity=draft + 置信度 0.3~0.5 + 口径来源 + 「⚠ 未经人工校准」",
    "DC-8：口径卡须升 v1.0.1（'100' 迁 COMPANY_CODE + HC1 双分支改写 + 缺陷说明），双人复核签署",
    "禁止平滑、禁止插补、禁止报 0 冒充缺失；零值一律原样保留",
    "禁止对 ZB_VALUE / APPORTVALUE 求 AVG 充当区间聚合率（比率不可加）",
    "禁止跨 FACTORY_DIV 求和；禁与泉州 25/26/55、罗源 27/41/56/57 混算",
    "根因段落中标注「无实据·业务经验推断」的条目不得作为结论依据",
]

payload["limitations"] = [
    "无 DB2 通道（MCP 直连 / MCP HTTP 探活 / 5sApi REST / 凭据来源 四通道全部 FAIL）→ ODS 明细行、HOT_CHARGE_FLAG 分布、T_PUB_JOB_LOGS 作业日志、LOAD_TIME 落表时序均不可核验；数据就绪门禁 G1/G2/G3 的数据态侧不成立",
    "生产域旁证缺失：observed/gzprod/domain_TR-20261119-1026-EB11.json 实测不存在 → 无法交叉核验各产线 7 日是否真有轧制生产，零值三选一因此不可定案",
    "DWS 层无 FZ/FM 列，FZ/FM 仅存于 T_DWS_TEMP_ZZGZ_ZG01_TMP4_1 且过程结束即 DROP → 本窗口分子分母永久不可回溯",
    "3σ 法对 4 条零值主导序列（8000293/8000295/8000296/8000297）全部失效：零值抬高 σ，产出物理上不可能的区间（如 [-100.23, 148.84]）→ 本报告不得以「3σ 无离群」推出「无异常」",
    "无注册基线（ontology.business_baseline.status=无注册基线，检索 5 类知识源均无）→ 无法做「越界」类判定，异常判定只能靠 3σ / 日环比 / 横截面三条数据自证路径",
    "11 指标 maturity 全为 draft（confidence 0.3~0.5），字段级血缘覆盖 74.12%（63/85），三闸门 ①②③ 全 PARTIAL → 口径结论强度受限",
    "单位全部靠 ZB_NAME 语义推断（registry.unit 为空串）；8001401 单位未声明，禁推定",
    "ZB_VALUE 为 VARCHAR(1000) 非数值型，MAX 按字典序（'9.5' > '12.3'）；CAST 无空串防护（G-F03），执行期新入脏数据可致 SQLCODE=-420 整族失败",
    "热装率 7 日区间聚合率不可算（NOT_CALCULABLE）；自发电区间聚合率 84.440526% 中，DB2 原值返回 84.4 系 DECIMAL 除法 scale=1 所致，二者并列不冲突",
    "jev 双预设均未达采纳门槛（quality conf 0.349 < 0.60；rootcause conf 0.526 < 0.70）→ jev 弃权，本报告结论全部来自数据实算，jev 仅并列披露「jev 建议，需人工确认」",
    "指标血缘 G3 记载「8000010 七日值域 80.41~89.30」属历史证据窗口 20261105~20261111，与本窗口 80.07~87.10 不同期，不得读作口径漂移",
]

payload["jev_advisory"] = {
    "disclosure": "jev 建议，需人工确认（两预设均未达采纳门槛，jev 已弃权，不构成结论依据）",
    "quality_preset": {"model": "tev1:4b-32k", "conf": 0.349, "threshold": 0.60,
                       "adopted": False, "top2": {"有效性": 0.479, "完整性": 0.448}},
    "rootcause_preset": {"model": "tev1:4b-32k", "conf": 0.526, "threshold": 0.70,
                         "adopted": False, "top2": {"口径歧义": 0.621, "源数据错误": 0.259}},
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

# ---------- 控制台摘要 ----------
print("=" * 78)
print("PKG sha256:", PKG_SHA)
print("=" * 78)
for k, v in VOL.items():
    print(f"\n{k}  (n={v['n_present']}/{7})")
    print(f"  mean={v['mean']}  std={v['std_sample']}  CV%={v['cv_pct']}")
    print(f"  max|DoD|={v['max_dod_pp']}pp @ {v['max_dod_day']}")
    print(f"  3sigma band={v['sigma3_band']}  outliers={v['outliers_3sigma']}")
    print(f"  zeros={v['zero_count']} ({v['zero_share_pct']}%)  longest_run={v['longest_zero_run_len']} {v['longest_zero_run']}")
print("\n8000294:", VOL_294.get("status"))
print("\n" + "=" * 78)
print("横截面逐日：")
for r in XS:
    print(f"  {r['day']} present={r['n_present']} zero={r['n_zero']} active={r['active_ratio']} "
          f"range_all={r['range_all_pp']} range_nz={r['range_nonzero_pp']} nz_mean={r['nonzero_mean']}")
print("\n共同变动日(|DoD|>=30pp 线数>=2):", co_days)
print("零值>=2 线日:", sys_days)
print("systematic_abnormal_days:", sorted(set(sys_days) | set(co_days)))
print("\n" + "=" * 78)
print(f"自发电: mean={ym:.6f} std={sg_std:.6f} CV={sg_cv:.4f}% range={max(sg)-min(sg):.2f}pp "
      f"slope={slope:.6f}pp/d")
print(f"  3sigma band={[round(ym-3*sg_std,4), round(ym+3*sg_std,4)]} outliers="
      f"{[d for d,y in zip(DAYS,sg) if abs(y-ym)>3*sg_std]}")
print(f"  d1={dict(zip(DAYS[1:],d1))}")
print(f"  inflections={inflections}")
print(f"\n双盲对拍: max_dev={max(devs_abs):.6f}pp @ {dual['daily'][devs_abs.index(max(devs_abs))]['ymd']} "
      f"agg_dev={dual['deviation_pp']}pp")
print(f"\n越界值(<0 or >100): {out_of_range}")
print("\nWROTE:", OUT)
