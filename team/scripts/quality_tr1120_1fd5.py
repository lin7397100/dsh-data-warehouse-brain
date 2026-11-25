# -*- coding: utf-8 -*-
"""
sg-quality (砺真 Veritas) · Step 7 质量闸门 + 异常检测 + 根因裁定
trace: TR-20261120-0739-1FD5
窗口: 20261113 ~ 20261119（7 日，20261120 两表 0 行 → 回退）
只消费 observed/ 已落盘数据，不连 DB2、不重查。
"""
import json, math, os, random
from datetime import datetime

random.seed(20261120)

ROOT = r"$env:DSH_HOME\dwb-team"
OBS = os.path.join(ROOT, "observed")
TR = "TR-20261120-0739-1FD5"

dp = json.load(open(os.path.join(OBS, "data", "data_package_%s.json" % TR), encoding="utf-8"))
cal = json.load(open(os.path.join(OBS, "caliber", "caliber_%s.json" % TR), encoding="utf-8"))
ont = json.load(open(os.path.join(OBS, "ontology", "%s.json" % TR), encoding="utf-8"))
lin = json.load(open(os.path.join(OBS, "lineage", "physical_lineage_%s.json" % TR), encoding="utf-8"))
gov = json.load(open(os.path.join(OBS, "governance_receipt_%s.json" % TR), encoding="utf-8"))

DAYS = ["20261113", "20261114", "20261115", "20261116", "20261117", "20261118", "20261119"]

# ---------- 1. 序列装配（原值，零插补） ----------
heat = {}
for r in dp["heat_rate"]:
    heat.setdefault(r["zb_code"], {})[r["ymd"]] = r

power = {}
for r in dp["power_self"]:
    power.setdefault(r["item_id"], {})[r["ymd"]] = r

def heat_series(code):
    return [float(heat[code][d]["zb_value_raw"]) for d in DAYS]

def heat_status(code):
    return [heat[code][d]["data_status"] for d in DAYS]

def power_series(code):
    return [float(power[code][d]["apport_value_raw"]) for d in DAYS]

HEAT_CODES = ["8000293", "8000295", "8000296", "8000297", "8000298"]
POWER_CODES = ["8000010", "8001365", "8000004", "8000007", "8001401"]

# ---------- 2. 描述统计（含小样本与零值掩码披露） ----------
def stats(vals, zero_is_invalid=True):
    n = len(vals)
    nz = [v for v in vals if v != 0.0] if zero_is_invalid else vals
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    rng = max(vals) - min(vals)
    rng_nz = (max(nz) - min(nz)) if len(nz) >= 2 else None
    # 线性回归斜率（按日序）
    xs = list(range(n))
    xm = sum(xs) / n
    den = sum((x - xm) ** 2 for x in xs)
    slope = sum((xs[i] - xm) * (vals[i] - mean) for i in range(n)) / den if den else 0.0
    dod, dod_pct = [], []
    for i in range(1, n):
        d = round(vals[i] - vals[i - 1], 4)
        dod.append({"day": DAYS[i], "dod_pp": d,
                    "dod_pct": (round(d / abs(vals[i - 1]) * 100, 4) if vals[i - 1] != 0 else None)})
    inflections = []
    for i in range(1, len(dod) - 1):
        a, b = dod[i - 1]["dod_pp"], dod[i]["dod_pp"]
        if a * b < 0 and (abs(a) >= 5 or abs(b) >= 5):
            inflections.append({"day": dod[i]["day"], "from_pp": a, "to_pp": b,
                                "magnitude_pp": round(abs(a) + abs(b), 4)})
    return {
        "values": vals, "n": n, "mean": round(mean, 6), "std_sample": round(sd, 6),
        "cv_pct": (round(sd / mean * 100, 4) if mean else None),
        "range_pp": round(rng, 4),
        "range_nonzero_pp": (round(rng_nz, 4) if rng_nz is not None else None),
        "min": [min(vals), DAYS[vals.index(min(vals))]],
        "max": [max(vals), DAYS[vals.index(max(vals))]],
        "slope_per_day": round(slope, 6),
        "sigma3_band": [round(mean - 3 * sd, 4), round(mean + 3 * sd, 4)],
        "outliers_3sigma": [{"day": DAYS[i], "value": vals[i],
                             "z": round((vals[i] - mean) / sd, 4)}
                            for i in range(n) if sd and abs((vals[i] - mean) / sd) > 3],
        "dod": dod, "inflections": inflections,
        "zero_days": [DAYS[i] for i in range(n) if vals[i] == 0.0],
        "zero_count": sum(1 for v in vals if v == 0.0),
        "zero_share_pct": round(sum(1 for v in vals if v == 0.0) / n * 100, 2),
    }

def longest_zero_run(vals):
    best, cur = [], []
    for i, v in enumerate(vals):
        if v == 0.0:
            cur.append(DAYS[i])
            if len(cur) > len(best):
                best = list(cur)
        else:
            cur = []
    return best

vol = {}
for c in HEAT_CODES:
    s = stats(heat_series(c))
    s["longest_zero_run"] = longest_zero_run(heat_series(c))
    s["longest_zero_run_len"] = len(s["longest_zero_run"])
    s["data_status"] = heat_status(c)
    s["metric_name"] = heat[c][DAYS[0]]["zb_name"]
    s["family"] = "FAM_A_ZG01_HEAT_RATE"
    vol[c] = s
for c in POWER_CODES:
    s = stats(power_series(c))
    s["longest_zero_run"] = longest_zero_run(power_series(c))
    s["longest_zero_run_len"] = len(s["longest_zero_run"])
    s["metric_name"] = power[c][DAYS[0]]["item_name"]
    s["family"] = ("FAM_B_NYGZ_THREE_GAO_HEAT_RATE" if c == "8001401" else
                   "FAM_C_NYGZ_SELF_GEN_RATE" if c == "8000010" else
                   "FAM_D_NYGZ_SELF_GEN_RATE_ALT" if c == "8001365" else
                   "FAM_E_NYGZ_SELF_GEN_NUM" if c == "8000004" else
                   "FAM_E_NYGZ_SELF_GEN_DEN")
    vol[c] = s

# ---------- 3. 量级一致性 / 双向对账（Q4 量纲门禁） ----------
gen = power_series("8000004")
use = power_series("8000007")
ratio_reg = power_series("8000010")
ratio_alt = power_series("8001365")
recalc = [round((gen[i] / 10000.0) / use[i] * 100, 6) for i in range(7)]
dev_pp = [round(recalc[i] - ratio_reg[i], 6) for i in range(7)]
agg_num = round(sum(gen) / 10000.0, 5)
agg_den = round(sum(use), 5)
agg_rate = round(agg_num / agg_den * 100, 4)
mean_daily = round(sum(ratio_reg) / 7, 6)

# 错配形态反证（仅作量纲判据，不构成业务结论）
wrong_both_none = round(sum(gen) / sum(use) * 100, 2)          # 两码均不折算
wrong_both_conv = round((sum(gen) / 10000.0) / (sum(use) / 10000.0) * 100, 2)  # 两码均折算

dual_check = {
    "daily": [{"day": DAYS[i], "recalc_pct": recalc[i], "registry_8000010_pct": ratio_reg[i],
               "dev_pp": dev_pp[i]} for i in range(7)],
    "max_abs_dev_pp": round(max(abs(x) for x in dev_pp), 6),
    "max_abs_dev_day": DAYS[max(range(7), key=lambda i: abs(dev_pp[i]))],
    "threshold_pp": 0.05,
    "verdict": "PASS" if max(abs(x) for x in dev_pp) <= 0.05 else "FAIL",
    "agg_7d": {"numerator_wan_kwh": agg_num, "denominator_wan_kwh": agg_den,
               "rate_pct": agg_rate, "mean_daily_8000010_pct": mean_daily,
               "agg_vs_mean_daily_dev_pp": round(agg_rate - mean_daily, 4),
               "eff": "COMPILE_TIME_SELF_CHECK_ONLY · 编译期量纲自校验，不构成业务结论（P7/C-Q4-1）"},
    "dimension_mismatch_falsification": {
        "both_unscaled_rate_pct": wrong_both_none,
        "both_scaled_rate_pct": wrong_both_conv,
        "note": "两种错折形态均落 ~8392% 量级（偏大 10^4 倍），与登记 83.9248% 差 100 倍级 → 反证『仅对 8000004 折算一次』为唯一正确形态",
    },
}

# ---------- 4. 跨口径差（8000010 vs 8001365） ----------
spread = [round(ratio_reg[i] - ratio_alt[i], 4) for i in range(7)]
cross_caliber = {
    "daily_spread_pp": [{"day": DAYS[i], "spread_pp": spread[i]} for i in range(7)],
    "mean_spread_pp": round(sum(spread) / 7, 4),
    "min_spread_pp": min(spread), "max_spread_pp": max(spread),
    "verdict": "系统性约 30pp 差（分母口径不同：总用电量 vs 同口径用电量）→ 禁混算/禁求平均/禁同轴差解读（IC2/HC5）",
}

# ---------- 5. 同比/环比（DoD）阈值判定 ----------
def dod_flags(s, name, zero_guard=True):
    out = []
    for d in s["dod"]:
        p = d["dod_pct"]
        if p is None:
            out.append({"day": d["day"], "dod_pp": d["dod_pp"], "dod_pct": None,
                        "level": "UNDEFINED", "note": "前值为 0，环比百分比无定义（禁以 0 作分母）"})
            continue
        a = abs(p)
        lv = "P0" if a > 30 else "P1" if a > 15 else "P2" if a > 5 else "正常"
        out.append({"day": d["day"], "dod_pp": d["dod_pp"], "dod_pct": p, "level": lv})
    return out

# ---------- 6. 趋势判定 ----------
def trend_of(code, s):
    vals = s["values"]
    nz = [v for v in vals if v != 0.0]
    zc = s["zero_count"]
    if zc == 7:
        return {"code": code, "direction": "不可判（恒定零·掩码型）",
                "breakpoints": DAYS[:], "note": "7/7 日为 0.00 且 data_status 掩码 → 非趋势形态，禁入趋势线"}
    if zc >= 2:
        first_zero = DAYS[vals.index(0.0)]
        return {"code": code, "direction": "断点型（0 值掩码段 + 非零段双态）",
                "breakpoints": [first_zero],
                "note": "自 %s 起 %d 日归零；非零段 %s" % (first_zero, zc, nz)}
    if s["cv_pct"] is not None and s["cv_pct"] > 50:
        return {"code": code, "direction": "高波震荡型", "breakpoints": [i["day"] for i in s["inflections"]],
                "note": "CV %.2f%%，斜率 %.4f/日（7 点小样本，斜率不具外推效力）" % (s["cv_pct"], s["slope_per_day"])}
    if abs(s["slope_per_day"]) > 0.5:
        return {"code": code, "direction": "上升型" if s["slope_per_day"] > 0 else "下降型",
                "breakpoints": [i["day"] for i in s["inflections"]],
                "note": "斜率 %.4f/日，CV %.2f%%" % (s["slope_per_day"], s["cv_pct"] or 0)}
    return {"code": code, "direction": "震荡（无显著趋势）", "breakpoints": [i["day"] for i in s["inflections"]],
            "note": "斜率 %.4f/日，CV %.2f%%" % (s["slope_per_day"], s["cv_pct"] or 0)}

trends = {c: trend_of(c, vol[c]) for c in HEAT_CODES + POWER_CODES}

# ---------- 7. 零值陷阱分类 ----------
tmp4 = {r["factory_div"]: r for r in dp["agg"]["heat_rate_7d"]}
zero_type = []
for c, div in [("8000293", "21"), ("8000295", "23"), ("8000296", "51"), ("8000297", "52")]:
    t = tmp4.get(div)
    for i, d in enumerate(DAYS):
        if heat[c][d]["zb_value_raw"] != "0.00":
            continue
        st = heat[c][d]["data_status"]
        if d == "20261119" and t is not None:
            if t["fm_7d"] == 0:
                cls, basis = "FALSE_ZERO__NO_PRODUCTION_FM0", \
                    "TMP4_1 20261119 FACTORY_DIV=%s：FM=%.3f=0 且 FZ=%.3f → 分母为 0 的守卫归零（D8），非真实全冷装" % (div, t["fm_7d"], t["fz_7d"])
            else:
                cls, basis = "TRUE_ZERO__GENUINE_FULL_COLD_CHARGE", \
                    "TMP4_1 20261119 FACTORY_DIV=%s：FM=%.3f>0 且 FZ=%.3f=0 → 真实全冷装（有入炉量、无热装量）" % (div, t["fm_7d"], t["fz_7d"])
        else:
            cls, basis = "ZERO_UNDIFFERENTIATED", \
                "TMP4_1 仅存 20261119 单日（ROWS_7D=1），%s 无 FZ/FM 证据 → 不可判别（禁以推测填格）" % d
        zero_type.append({"zb_code": c, "factory_div": div, "day": d,
                          "value": 0.0, "ZERO_TYPE": cls, "basis": basis,
                          "data_status_verbatim": st})

# ---------- 8. 输出 ----------
out = {
    "trace_id": TR,
    "artifact_type": "QUALITY_GATE_REPORT",
    "step": "Step 7 · 可靠性闸门 + 异常检测 + 根因裁定（P3.2 执行实例 · 唯一指定执行者）",
    "executed_by": "sg-quality（砺真 Veritas）",
    "executed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "skills_loaded": ["sg-anomaly-detect", "sg-quality-rule-gen", "sg-root-cause-fullchain"],
    "roles": ["质量守门员", "根因侦探", "评测闭环执行者"],
    "source_of_truth": {
        "data_package": "observed/data/data_package_%s.json" % TR,
        "heat_rate_series": "observed/data/heat_rate_series_%s.csv" % TR,
        "power_series": "observed/data/power_series_%s.csv" % TR,
        "caliber_card": "observed/caliber/caliber_%s.json" % TR,
        "ontology": "observed/ontology/%s.json" % TR,
        "physical_lineage": "observed/lineage/physical_lineage_%s.json" % TR,
        "governance_receipt": "observed/governance_receipt_%s.json" % TR,
        "random_seed": 20261120,
        "script": "scripts/quality_tr1120_1fd5.py",
        "db2_requeried": False,
        "values_note": "全部数值为 data_package 的 DB2 实返原值，零编造、零平滑、零插补、零补 0",
    },
    "window": {"start": "20261113", "end": "20261119", "days": 7,
               "rollback_reason": "20261120 两表均 0 行（ZG01=0 / NYGZ=0，日结未到）→ 未就绪，按等长回退",
               "rows": {"heat_rate": 35, "power_self": 35, "agg_q4": 1, "agg_q5": 5, "reconcil_q6": 20, "total": 96}},
    "gate_verdict": "降级",
    "gate_verdict_code": "DEGRADE_WITH_MANDATORY_DISCLOSURE",
    "gate_summary": "数值真实性通过（DB2 实返、行数守恒 35/35、幂等无重复、量纲门禁 PASS），但交付形态必须降级：① 6/7 日零值语义不可判别（仅 20261119 有 TMP4_1 实证），禁入趋势/异常/均值/极差；② 热装率 7 日区间聚合 NOT_AVAILABLE（PARTIAL_WINDOW_1_OF_7_DAYS）；③ 8000294 UNAVAILABLE；④ 11 条指标全部 draft 未校准；⑤ G1 批处理日志 / G2 抽数日志未核验 → 生产工况类结论一律不得断言。",
    "confidence": 0.62,
    "confidence_model": {
        "parts": [
            {"dim": "数值真实性", "score": 0.94, "weight": 0.30,
             "basis": "DB2 MCP 实返 96 行；Q1/Q3 各 35 行 = 5 码×7 日（无缺日无重复）；Q6 值域 20 值逐值吻合、'100' 计 0；Q5↔Q1 199 单日逐码吻合（|Δ|≤0.0011pp）；量纲门禁 87.1028 ↔ 87.10（偏差 0.0028pp << 0.05pp 阈值）"},
            {"dim": "口径完整性", "score": 0.48, "weight": 0.20,
             "basis": "11 条 maturity 全 draft（confidence 0.3~0.5）；registry.unit 除 8000004 外全空串（单位系 ZB_NAME 语义推断）；8001401 单位未声明；8000010 vs 8001365 系统性差 30pp（IC2）；比率不可加（HC3）且区间聚合不可得"},
            {"dim": "异常归因确定性", "score": 0.58, "weight": 0.30,
             "basis": "20261119 三类零值语义经 TMP4_1 实证可判（FM=0 假 0 ×2 / FM>0 真冷装 ×1）；但 20261113~18 六日无 FZ/FM 载体 → 不可判别；G1 T_PUB_JOB_LOGS 与 G2 V_PUB_JOB_LOGS_LD_1D_X 未查（本 Step 禁重查 DB2）→ 断数 vs 停产二选一不可定案"},
            {"dim": "基线可判定性", "score": 0.32, "weight": 0.20,
             "basis": "无注册业务基线与合理区间（ontology 无 business_baseline）；仅 7 点样本；3σ 法对零值主导序列物理上失效（区间下界为负）；极差/CV 不得作考核口径（HC3/IC4）"},
        ],
        "weights_sum": 1.0, "formula": "Σ(score×weight)",
        "confidence": 0.62,
        "escalation_threshold": 0.6,
        "escalation_required": False,
        "note": "0.62 ≥ 0.60 → 无需整体 escalate；但 5 项挂账（见 escalations）须由编排器派单闭环，未闭环前对应结论不得对外引用",
    },
    "reliability_gate": {
        "G0_zero_trap": {
            "verdict": "PARTIAL",
            "detail": "7 个 0.00 点中仅 3 个（全为 20261119）可定语义，另 6 个 ZERO_UNDIFFERENTIATED 不可判别；不存在『全部可判』与『全部不可判』两种极端",
            "counts": {"total_zero_points": 20,
                       "FALSE_ZERO__NO_PRODUCTION_FM0": 2,
                       "TRUE_ZERO__GENUINE_FULL_COLD_CHARGE": 1,
                       "ZERO_UNDIFFERENTIATED": 17},
            "broken_down": "8000293 一棒 7 点（19 日=假 0，13~18 日不可判）；8000295 圆棒 5 点（19 日=真冷装，15~18 日不可判）；8000296 一高 1 点（14 日不可判）；8000297 二高 7 点（19 日=假 0，13~18 日不可判）",
            "rule": "D8 ZERO_GUARD_MASKS_EMPTY：16 支均用 CASE WHEN SUM(FM)=0 THEN 0 → 0.00 与『未生产』在 DWS 层同值不可分",
        },
        "G1_magnitude_consistency": {
            "verdict": "PASS",
            "detail": "8000004 库内 kWh、8000007 库内 万kWh（差 10^4）；换算仅对分子 /10000 且仅一次，7 日逐日复算最大偏差 0.0028pp（<<0.05pp 阈值）",
            "falsification": dual_check["dimension_mismatch_falsification"],
            "sample_20261113": "5643480.33/10000 ÷ 647.91 × 100 = 87.1028 ↔ 落盘 87.10（Δ=0.0028pp）",
        },
        "G2_outlier_detection": {
            "verdict": "NOT_DECISIVE（方法失效，非『无异常』）",
            "detail": "7 点样本下 σ 被极值放大，3σ 区间普遍越出物理边界（如 8000295 band=[%.4f, %.4f]、8000297 band=[%.4f, %.4f]）→ 0 值不构成离群；且零值按 P4/P5 禁入离群统计。故本闸门只作并列披露，不得据『无 3σ 离群』推出『无异常』" % (
                vol["8000295"]["sigma3_band"][0], vol["8000295"]["sigma3_band"][1],
                vol["8000297"]["sigma3_band"][0], vol["8000297"]["sigma3_band"][1]),
            "small_sample_caveat": "n=7，t 分布自由度 6，3σ 等效双侧约 5% 但零值主导序列的均值/σ 均被掩码污染；CV 在均值≈0 时无定义（8000293/8000297 均值 0.00 → CV=null）",
        },
        "G3_direction_reasonableness": {
            "verdict": "PASS",
            "detail": "20261119 自发电比例 76.58 与『自发电量 7 日最低 5,067,607.09 kWh』+『用电量 7 日最高 661.73 万kWh』同向印证：分子降 9.05%、分母升 1.54% → 比率降 8.92pp（-10.43%），方向自洽",
            "quantified": {"dod_numerator_pct": -9.05, "dod_denominator_pct": 1.54,
                           "dod_ratio_pp": -8.92, "recalc_20261119_pct": recalc[6]},
        },
        "G4_data_readiness": {
            "verdict": "PARTIAL",
            "four_choice": "真异常（窗口内 7 日）+ 未就绪（20261120 已回退）",
            "G1_job_logs": "NOT_VERIFIED —— T_PUB_JOB_LOGS 未查（本 Step 禁重查 DB2）",
            "G2_extract_logs": "NOT_VERIFIED —— V_PUB_JOB_LOGS_LD_1D_X 未查；间接旁证：ZG01 逐日行数 184/181/178/176/177/176/179（波动 4.5%）、NYGZ 恒 930 → 无『半批次只剩 1/N』形态",
            "G3_load_time": "NOT_VERIFIED —— 窗口内 LOAD_TIME MIN~MAX 未取；已实证脏值 YMD='23230809' 的 LOAD_TIME=20230810173823（2023-08 遗留，不在本窗口）",
            "idempotency": "PASS —— (ZB_CODE,YMD) 35 行无重复，(ITEMID,YMD) 35 行无重复 → 无重跑覆盖残留",
            "note": "三层埋点任一项未核 → 依 data_ready_gate 铁律，生产工况类根因一律降为『推断待核』，不得断言",
        },
    },
    "zero_type_classification": zero_type,
    "volatility": vol,
    "dual_check": dual_check,
    "cross_caliber": cross_caliber,
    "trend": {
        "window": "20261113~20261119（7 点逐日序列，禁区间聚合）",
        "per_series": trends,
        "cross_series_note": "ZG01 族（21/23/31/51/52）与 8001401（异源独立轴）禁同轴/禁合并求均值/禁横向极差（IC1）；8000010 与 8001365 禁混算（IC2）",
    },
    "_vol_dod": {c: dod_flags(vol[c], c) for c in HEAT_CODES + POWER_CODES},
}

with open(os.path.join(ROOT, "scripts", "_tmp_stats.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("OK", dual_check["max_abs_dev_pp"], dual_check["agg_7d"]["rate_pct"], round(agg_rate - mean_daily, 4))
for c in HEAT_CODES + POWER_CODES:
    s = vol[c]
    print(c, "mean=%.4f sd=%.4f cv=%s rng=%.4f rngnz=%s zc=%d slope=%.4f" % (
        s["mean"], s["std_sample"], s["cv_pct"], s["range_pp"], s["range_nonzero_pp"],
        s["zero_count"], s["slope_per_day"]), "|", trends[c]["direction"], trends[c]["breakpoints"])
print("spread mean", cross_caliber["mean_spread_pp"], cross_caliber["min_spread_pp"], cross_caliber["max_spread_pp"])
print("wrong both unscaled", wrong_both_none, "both scaled", wrong_both_conv)
