# -*- coding: utf-8 -*-
"""
Step 7 可靠性闸门 · 统计/异常校验
trace_id = TR-20261119-1631-62A2
输入：observed/data/data_TR-20261119-1631-62A2.json（DB2 实取原值，零改写）
禁止重查 DB2；本脚本只做本地统计，不连库。
random_seed 固定（本脚本无随机过程，仅登记）。
"""
import json, math
from decimal import Decimal

SEED = 20261119
SRC = r"$env:DSH_HOME\dwb-team/observed/data/data_TR-20261119-1631-62A2.json"
OUT = r"$env:DSH_HOME\dwb-team/observed/quality/_stats_TR-20261119-1631-62A2.json"

d = json.load(open(SRC, encoding="utf-8"))
S1 = [r for r in d["statements"][0]["rows"]]

DAYS = ["20261113", "20261114", "20261115", "20261116", "20261117", "20261118"]
SERIES = {}
STATUS = {}
for r in S1:
    code = r["ZB_CODE"]
    SERIES.setdefault(code, {})[r["YMD"]] = (None if r["METRIC_VALUE"] is None else float(r["METRIC_VALUE"]))
    STATUS.setdefault(code, {})[r["YMD"]] = r["DATA_STATUS"]

def stats(vals):
    n = len(vals)
    if n == 0:
        return None
    mu = sum(vals) / n
    if n == 1:
        return dict(n=n, mean=mu, sd_pop=0.0, sd_sample=None, cv_pct=None, rng=0.0,
                    outliers_2s=[], outliers_3s=[], iqr_fence=None)
    var_p = sum((x - mu) ** 2 for x in vals) / n
    sd_p = math.sqrt(var_p)
    var_s = sum((x - mu) ** 2 for x in vals) / (n - 1)
    sd_s = math.sqrt(var_s)
    s = sorted(vals)
    # Tukey Q1/Q3 (method: median of halves, n even -> exact halves)
    def med(a):
        m = len(a)
        return sum(a) / m if m % 2 else (a[m // 2 - 1] + a[m // 2]) / 2
    q1 = med(s[:n // 2]); q3 = med(s[(n + 1) // 2:])
    iqr = q3 - q1
    return dict(n=n, mean=mu, sd_pop=sd_p, sd_sample=sd_s,
                cv_pct=(None if mu == 0 else sd_p / abs(mu) * 100),
                rng=max(vals) - min(vals),
                q1=q1, q3=q3, iqr=iqr,
                iqr_fence=[q1 - 1.5 * iqr, q3 + 1.5 * iqr],
                outliers_2s=[(i, v) for i, v in enumerate(vals) if abs(v - mu) > 2 * sd_p],
                outliers_3s=[(i, v) for i, v in enumerate(vals) if abs(v - mu) > 3 * sd_p])

report = {}
for code, m in SERIES.items():
    days = [d_ for d_ in DAYS if m.get(d_) is not None]
    vals = [m[d_] for d_ in days]
    st = stats(vals)
    dod = []
    for i in range(1, len(days)):
        a, b = m[days[i - 1]], m[days[i]]
        dod.append(dict(day=days[i], prev=days[i - 1], delta_pp=round(b - a, 4),
                        pct=(None if a == 0 else round((b - a) / a * 100, 2))))
    report[code] = dict(product_line=S1[[r["ZB_CODE"] for r in S1].index(code)]["PRODUCT_LINE"],
                        status=STATUS[code], n_present=len(vals), n_null=6 - len(vals),
                        days=days, values=vals,
                        stats=None if st is None else {k: v for k, v in st.items()},
                        dod=dod)

# ---- S2 自发电率区间重算校验 ----
S2 = d["statements"][1]["rows"]
num6 = float([r for r in S2 if r["SCOPE"] == "RANGE_6D"][0]["NUM_WAN_KWH"])
den6 = float([r for r in S2 if r["SCOPE"] == "RANGE_6D"][0]["DEN_WAN_KWH"])
range_rate = num6 / den6 * 100
daily = {r["YMD"]: (float(r["NUM_WAN_KWH"]), float(r["DEN_WAN_KWH"]), float(r["RECALC_RATE_PCT"]))
         for r in S2 if r["SCOPE"] == "DAILY"}
precise = [daily[d_][0] / daily[d_][1] * 100 for d_ in DAYS]
mean_daily = sum(precise) / 6
dens = [daily[d_][1] for d_ in DAYS]
dmu = sum(dens) / 6
dsd = math.sqrt(sum((x - dmu) ** 2 for x in dens) / 6)
selfgen = dict(sum_num_wan_kwh=num6, sum_den_wan_kwh=den6,
               range_rate_pct=round(range_rate, 6), mean_of_daily_pct=round(mean_daily, 6),
               deviation_pp=round(range_rate - mean_daily, 6),
               relative_dev_pct=round((range_rate - mean_daily) / mean_daily * 100, 6),
               den_mean=dmu, den_sd_pop=dsd, den_cv_pct=dsd / dmu * 100,
               daily_precise=[round(x, 4) for x in precise],
               daily_recalc_rounded=[daily[d_][2] for d_ in DAYS])

# ---- 一高线 ODS 6 日区间重算（本体 A5 实据，非本次新查） ----
oh = dict(code="8000296", fz_6d=2594.903, fm_6d=9325.269,
          range_rate_pct=round(2594.903 / 9325.269 * 100, 4),
          mean_of_daily_pct=round(report["8000296"]["stats"]["mean"], 4))
oh["deviation_pp"] = round(oh["range_rate_pct"] - oh["mean_of_daily_pct"], 4)

# ---- 零值 / 状态分布 ----
zdi = {}
for code, m in SERIES.items():
    zdi[code] = dict(
        zero_cells=[d_ for d_ in DAYS if m.get(d_) == 0],
        zero_status=[STATUS[code][d_] for d_ in DAYS if m.get(d_) == 0],
        null_cells=[d_ for d_ in DAYS if m.get(d_) is None],
        ok_cells=[d_ for d_ in DAYS if STATUS[code][d_] == "OK"],
        true_zero=[d_ for d_ in DAYS if STATUS[code][d_] == "TRUE_ZERO"],
        false_zero=[d_ for d_ in DAYS if STATUS[code][d_] == "FALSE_ZERO"])

out = dict(trace_id="TR-20261119-1631-62A2", seed=SEED,
           series=report, selfgen_range_check=selfgen, yigao_range_check=oh,
           zero_diagnosis=zdi, status_distribution=d["data_status_distribution"])
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# 控制台摘要
print(json.dumps(dict(
    per_line={k: dict(n=v["n_present"], mean=None if not v["stats"] else round(v["stats"]["mean"], 4),
                      sd_pop=None if not v["stats"] else round(v["stats"]["sd_pop"], 4),
                      cv=None if not v["stats"] or v["stats"]["cv_pct"] is None else round(v["stats"]["cv_pct"], 2),
                      rng=None if not v["stats"] else round(v["stats"]["rng"], 4),
                      o2=None if not v["stats"] else v["stats"]["outliers_2s"],
                      o3=None if not v["stats"] else v["stats"]["outliers_3s"],
                      iqr_fence=None if not v["stats"] else v["stats"].get("iqr_fence"))
               for k, v in report.items()},
    dod={k: v["dod"] for k, v in report.items()},
    selfgen=selfgen, yigao=oh, zero=zdi), ensure_ascii=False, indent=1))
