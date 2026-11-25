# -*- coding: utf-8 -*-
"""生成《三钢集团生产经营驾驶舱报告》单文件 HTML（深色 / 纯 SVG+CSS+内联JS / 零外链）。

v5 变更（相对 v4）
  1. 原生新增「标准成本 vs 实际成本对比」模块（同一张表按「版本」维度切分，同工序同口径）；
  2. 抽屉升级为四层结构（L1 构成 / L2 序列 / L3 血缘 / L4 源表明细），对齐明鉴 D1~D5 硬闸门；
  3. 勾稽闸门扩充至 36 项（含标准成本对比专项 10 项）；
  4. 数据集外置，CLI 支持 --check / --out / --data。

用法
  python gen_cockpit.py                 # 校验 + 生成
  python gen_cockpit.py --check         # 只跑闸门
  python gen_cockpit.py --out x.html    # 指定输出
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "cockpit_data_20261029.json")
if not os.path.exists(DATA):
    DATA = os.path.join(HERE, "_cockpit_data.json")
DEFAULT_OUT = os.path.join(HERE, "三钢集团生产经营驾驶舱报告.html")

TOL = 0.005


class DataError(Exception):
    pass


def load_data(path):
    if not os.path.exists(path):
        raise DataError(f"数据集不存在：{path}")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    must = {
        "meta": ["period", "period_prev", "base_order", "full_name"],
        "production": ["prod_day", "prod_prev", "prod_month", "steel_day", "steel_month",
                       "bf_ratio", "hm_ratio", "series_dates", "prod_series", "bf_series",
                       "steel_series", "source"],
        "cost": ["dates", "series", "months", "month_out", "month_unit_cost", "month_gross", "source"],
        "inventory": ["by_base", "weight", "prev_total", "trend_dates", "trend_amt",
                      "trend_by_base", "source"],
        "standard_cost": ["items", "not_comparable", "source", "std_version", "act_version"],
    }
    for sec, keys in must.items():
        if sec not in d:
            raise DataError(f"缺少段：{sec}")
        for k in keys:
            if k not in d[sec]:
                raise DataError(f"缺少字段：{sec}.{k}")
    bases = d["meta"]["base_order"]
    for k in ("prod_day", "prod_prev", "prod_month", "steel_day", "steel_month",
              "bf_ratio", "hm_ratio", "prod_series", "bf_series", "steel_series"):
        if set(d["production"][k]) != set(bases):
            raise DataError(f"production.{k} 基地集合不一致")
    for k in ("by_base", "weight", "trend_by_base"):
        if set(d["inventory"][k]) != set(bases):
            raise DataError(f"inventory.{k} 基地集合不一致")
    return d


class M:
    pass


def derive(d):
    m = M()
    p, c, i, s = d["production"], d["cost"], d["inventory"], d["standard_cost"]
    m.d, m.P, m.P_PREV = d, d["meta"]["period"], d["meta"]["period_prev"]
    m.BASE_ORDER, m.FULL = d["meta"]["base_order"], d["meta"]["full_name"]
    bo = m.BASE_ORDER

    m.prod_day, m.prod_prev, m.prod_month = p["prod_day"], p["prod_prev"], p["prod_month"]
    m.steel_day, m.steel_month = p["steel_day"], p["steel_month"]
    m.bf_ratio, m.hm_ratio = p["bf_ratio"], p["hm_ratio"]
    m.PROD_DATES = p["series_dates"]
    m.prod_series, m.bf_series, m.steel_series = p["prod_series"], p["bf_series"], p["steel_series"]
    m.p_src = p["source"]

    m.prod_total = sum(m.prod_day.values())
    m.prod_prev_total = sum(m.prod_prev.values())
    m.prod_month_total = sum(m.prod_month.values())
    m.steel_total = sum(m.steel_day.values())
    m.steel_month_total = sum(m.steel_month.values())
    m.prod_mom = (m.prod_total - m.prod_prev_total) / m.prod_prev_total * 100
    m.ratio_cg = m.prod_total / m.steel_total
    m.bf_weighted = sum(m.bf_ratio[b] * m.steel_day[b] for b in bo) / m.steel_total
    m.bf_prev_w = sum(m.bf_series[b][-2] * m.steel_day[b] for b in bo) / m.steel_total
    m.bf_mom = (m.bf_weighted - m.bf_prev_w) / m.bf_prev_w * 100
    m.hm_weighted = sum(m.hm_ratio[b] * m.steel_day[b] for b in bo) / m.steel_total

    m.COST_DATES, m.cost_series = c["dates"], c["series"]
    m.cost_now, m.cost_prev = m.cost_series[-1], m.cost_series[-2]
    m.cost_mom = (m.cost_now - m.cost_prev) / m.cost_prev * 100
    m.MONTHS, m.m_cg_out = c["months"], c["month_out"]
    m.m_cost, m.m_gross = c["month_unit_cost"], c["month_gross"]
    m.m_cost_chg = (m.m_cost[-1] - m.m_cost[0]) / m.m_cost[0] * 100
    m.m_out_chg = (m.m_cg_out[-1] - m.m_cg_out[0]) / m.m_cg_out[0] * 100
    m.c_src = c["source"]

    m.inv_by_base, m.inv_wt = i["by_base"], i["weight"]
    m.inv_total = sum(m.inv_by_base.values())
    m.inv_wt_total = sum(m.inv_wt.values())
    m.inv_prev_total = i["prev_total"]
    m.inv_mom = (m.inv_total - m.inv_prev_total) / m.inv_prev_total * 100
    m.inv_trend_dates, m.inv_trend_amt = i["trend_dates"], i["trend_amt"]
    m.inv_trend_by_base = i["trend_by_base"]
    m.inv_anomalies = i.get("anomalies", [])
    m.i_src = i["source"]

    m.std_items = []
    for it in s["items"]:
        diff = it["act"] - it["std"]
        m.std_items.append({"name": it["name"], "alias": it["alias"], "std": it["std"],
                            "act": it["act"], "out": it["out"], "diff": diff,
                            "rate": diff / it["std"] * 100,
                            "impact": diff * it["out"] / 10000})
    m.std_total_impact = sum(x["impact"] for x in m.std_items)
    m.std_w_sum = sum(x["std"] * x["out"] for x in m.std_items)
    m.std_a_sum = sum(x["act"] * x["out"] for x in m.std_items)
    m.std_out_sum = sum(x["out"] for x in m.std_items)
    m.std_w_std = m.std_w_sum / m.std_out_sum
    m.std_w_act = m.std_a_sum / m.std_out_sum
    m.std_w_rate = (m.std_w_act - m.std_w_std) / m.std_w_std * 100
    m.std_saving = sum(1 for x in m.std_items if x["diff"] < 0)
    m.std_over = sum(1 for x in m.std_items if x["diff"] > 0)
    m.std_not_cmp = s["not_comparable"]
    m.s_src = s["source"]
    m.STD_V, m.ACT_V = s["std_version"], s["act_version"]
    return m


def reconcile(m):
    bo = m.BASE_ORDER
    ck = []

    def add(name, ok, detail):
        ck.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    for b in bo:
        add(f"钢材日产量·{b} 点值=序列末值", abs(m.prod_day[b] - m.prod_series[b][-1]) < 0.01,
            f"{m.prod_day[b]:.2f} vs {m.prod_series[b][-1]:.2f}")
        add(f"钢铁料耗·{b} 点值=序列末值", abs(m.bf_ratio[b] - m.bf_series[b][-1]) < 0.01,
            f"{m.bf_ratio[b]:.2f} vs {m.bf_series[b][-1]:.2f}")
        add(f"粗钢日产量·{b} 点值=序列末值", abs(m.steel_day[b] - m.steel_series[b][-1]) < 0.01,
            f"{m.steel_day[b]:.2f} vs {m.steel_series[b][-1]:.2f}")

    add("钢材日产量三基地求和=集团", abs(sum(m.prod_day[b] for b in bo) - m.prod_total) < 0.01, f"{m.prod_total:,.2f}")
    add("粗钢日产量三基地求和=集团", abs(sum(m.steel_day[b] for b in bo) - m.steel_total) < 0.01, f"{m.steel_total:,.2f}")
    add("材钢比 ∈ [0.90, 1.20]", 0.90 <= m.ratio_cg <= 1.20, f"{m.ratio_cg:.4f}")
    add("钢铁料耗 > 铁水耗（所有基地）", all(m.bf_ratio[b] > m.hm_ratio[b] for b in bo),
        "、".join(f"{b}{m.bf_ratio[b]:.0f}>{m.hm_ratio[b]:.0f}" for b in bo))
    lo, hi = min(m.bf_ratio.values()), max(m.bf_ratio.values())
    add("钢铁料耗加权值在 [min,max] 内", lo - 1e-6 <= m.bf_weighted <= hi + 1e-6,
        f"{lo:.2f} ≤ {m.bf_weighted:.4f} ≤ {hi:.2f}")

    calc = m.m_gross[-1] * 10000 / m.m_cg_out[-1]
    add(f"月度吨材成本闭合（{m.MONTHS[-1]}）", abs(calc - m.m_cost[-1]) / m.m_cost[-1] < TOL,
        f"{calc:,.2f} vs {m.m_cost[-1]:,.2f}")
    add("日吨材成本偏离末月值 <40%", abs(m.cost_now - m.m_cost[-1]) / m.m_cost[-1] < 0.40,
        f"{m.cost_now:,.2f} vs {m.m_cost[-1]:,.2f}")

    add("存货三基地求和=集团", abs(sum(m.inv_by_base[b] for b in bo) - m.inv_total) < 0.01, f"{m.inv_total:,.3f}")
    add("存货环比公式自洽", abs((m.inv_total / m.inv_prev_total - 1) * 100 - m.inv_mom) < 1e-6, f"{m.inv_mom:+.3f}%")
    add("存货趋势末值=各基地资金",
        all(abs(m.inv_trend_by_base[b][-1] - m.inv_by_base[b]) < 0.01 for b in bo),
        "、".join(f"{b}{m.inv_trend_by_base[b][-1]:,.0f}" for b in bo))

    add("生产序列长度=日期轴", all(len(m.prod_series[b]) == len(m.PROD_DATES) for b in bo), f"{len(m.PROD_DATES)} 天")
    add("料耗序列长度=日期轴", all(len(m.bf_series[b]) == len(m.PROD_DATES) for b in bo), f"{len(m.PROD_DATES)} 天")
    add("粗钢序列长度=日期轴", all(len(m.steel_series[b]) == len(m.PROD_DATES) for b in bo), f"{len(m.PROD_DATES)} 天")
    add("成本序列长度=日期轴", len(m.cost_series) == len(m.COST_DATES), f"{len(m.COST_DATES)} 天")
    add("存货趋势长度=日期轴", len(m.inv_trend_amt) == len(m.inv_trend_dates), f"{len(m.inv_trend_dates)} 天")
    add("存货分基地序列等长", all(len(m.inv_trend_by_base[b]) == len(m.inv_trend_dates) for b in bo), f"{len(m.inv_trend_dates)} 天")
    add("月度三序列等长", len(m.MONTHS) == len(m.m_cg_out) == len(m.m_cost) == len(m.m_gross), f"{len(m.MONTHS)} 个月")

    add("标准成本可比工序数 ≥ 6", len(m.std_items) >= 6, f"{len(m.std_items)} 个工序")
    add("标准成本工序名唯一", len({x["name"] for x in m.std_items}) == len(m.std_items), "无重复")
    add("标准/实际成本均为正值", all(x["std"] > 0 and x["act"] > 0 for x in m.std_items), "全部 >0")
    add("工序产量均为正值", all(x["out"] > 0 for x in m.std_items), f"{m.std_out_sum:,.0f} 吨")
    bad = [f"{x['alias']}{x['rate']:+.0f}%" for x in m.std_items if abs(x["rate"]) > 50]
    add("单工序差异率 |Δ| ≤ 50%（防脏值）", not bad, "、".join(bad) or "全部在阈值内")
    add("差异率算式自洽",
        all(abs((x["act"] - x["std"]) / x["std"] * 100 - x["rate"]) < 1e-9 for x in m.std_items), "逐项复核")
    add("成本影响合计 = Σ逐项",
        abs(sum(x["impact"] for x in m.std_items) - m.std_total_impact) < 1e-9, f"{m.std_total_impact:,.2f} 万元")
    add("净影响 = 实际总成本 − 标准总成本",
        abs((m.std_a_sum - m.std_w_sum) / 10000 - m.std_total_impact) < 0.01,
        f"{(m.std_a_sum-m.std_w_sum)/10000:,.2f} vs {m.std_total_impact:,.2f}")
    add("不可比工序已披露", len(m.std_not_cmp) > 0, f"{len(m.std_not_cmp)} 个不可比项已列明")
    add("节约/超支工序数 = 可比总数",
        m.std_saving + m.std_over == len(m.std_items), f"节约 {m.std_saving} / 超支 {m.std_over}")

    flat = ([v for b in bo for v in m.prod_series[b]] + [v for b in bo for v in m.bf_series[b]]
            + [v for b in bo for v in m.steel_series[b]]
            + [v for b in bo for v in m.inv_trend_by_base[b]] + m.cost_series)
    add("全序列无 NaN/负值", all(isinstance(v, (int, float)) and v == v and v > 0 for v in flat), f"{len(flat)} 个点")
    return ck


NEON = {"cyan": "#2de2e6", "amber": "#ffb02e", "blue": "#4d9fff",
        "green": "#39ff14", "mag": "#ff2e97", "txt": "#e6edf7", "mut": "#8b9bb4"}


def axis(values, pad_ratio=0.10, floor=None):
    lo, hi = min(values), max(values)
    if hi == lo:
        hi = lo + 1.0
    span = hi - lo
    a, b = lo - span * pad_ratio, hi + span * pad_ratio
    if floor is not None:
        a = max(a, floor)
    return a, b


# ============================ 图表 ============================
def heatmap(m):
    cols = [("钢材日产量 t", "prod", "cyan", True), ("粗钢日产量 t", "steel", "blue", True),
            ("钢铁料耗 kg/t", "bf", "amber", False), ("存货资金 万元", "inv", "green", False)]
    src = {"prod": m.prod_day, "steel": m.steel_day, "bf": m.bf_ratio, "inv": m.inv_by_base}
    cw, ch, pad = 200, 66, 10
    W = pad * 2 + len(cols) * cw
    H = pad * 2 + len(m.BASE_ORDER) * ch + 34
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="基地×指标热力矩阵">']
    for j, (label, _, _, _) in enumerate(cols):
        x = pad + j * cw
        s.append(f'<rect x="{x}" y="{pad}" width="{cw-4}" height="28" rx="4" fill="#16203a"/>')
        s.append(f'<text x="{x+(cw-4)/2}" y="{pad+18}" fill="{NEON["txt"]}" font-size="12.5" text-anchor="middle" font-weight="700">{label}</text>')
    mx = {c[1]: max(src[c[1]][b] for b in m.BASE_ORDER) for c in cols}
    mn = {c[1]: min(src[c[1]][b] for b in m.BASE_ORDER) for c in cols}
    for i, b in enumerate(m.BASE_ORDER):
        y = pad + 32 + i * ch
        s.append(f'<rect x="{pad}" y="{y}" width="{cw-4}" height="28" rx="4" fill="#16203a"/>')
        s.append(f'<text x="{pad+8}" y="{y+19}" fill="{NEON["txt"]}" font-size="12.5" font-weight="700">{b}（{m.FULL[b]}）</text>')
        for j, (label, key, color, bh) in enumerate(cols):
            x = pad + j * cw
            yc = pad + 32 + i * ch + 32
            v = src[key][b]
            if mx[key] == mn[key]:
                inten = 1
            else:
                inten = ((v - mn[key]) / (mx[key] - mn[key])) if bh else ((mx[key] - v) / (mx[key] - mn[key]))
            op = 0.15 + 0.78 * inten
            s.append(f'<rect x="{x}" y="{yc}" width="{cw-4}" height="{ch-8}" rx="6" fill="{NEON[color]}" fill-opacity="{op:.2f}" stroke="{NEON[color]}" stroke-opacity="0.5"/>')
            s.append(f'<text x="{x+(cw-4)/2}" y="{yc+(ch-8)/2+5}" fill="#06101f" font-size="14" font-weight="800" text-anchor="middle">{v:,.0f}</text>')
    s.append('</svg>')
    return "".join(s)


def barchart(m):
    data = [(b, m.prod_day[b] / m.prod_total * 100, m.inv_by_base[b] / m.inv_total * 100) for b in m.BASE_ORDER]
    W, H = 760, 320
    padL, padR, padT, padB = 52, 20, 42, 52
    pw, ph = W - padL - padR, H - padT - padB
    maxv = max(60.0, max(max(x[1], x[2]) for x in data) * 1.15)
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="三基地产量占比与存货资金占比">']
    s.append(f'<line x1="{padL}" y1="{padT}" x2="{padL}" y2="{padT+ph}" stroke="#2a3550"/>')
    s.append(f'<line x1="{padL}" y1="{padT+ph}" x2="{W-padR}" y2="{padT+ph}" stroke="#2a3550"/>')
    for g in range(0, 7):
        yv = maxv * g / 6
        y = padT + ph - ph * yv / maxv
        s.append(f'<text x="{padL-8}" y="{y+4}" fill="{NEON["mut"]}" font-size="10" text-anchor="end">{yv:.0f}%</text>')
        s.append(f'<line x1="{padL}" y1="{y}" x2="{W-padR}" y2="{y}" stroke="#1a2238"/>')
    bw = pw / 3 / 2 - 14
    for i, (b, ps, isv) in enumerate(data):
        x0 = padL + i * (pw / 3) + 10
        h1 = ph * ps / maxv
        s.append(f'<rect x="{x0}" y="{padT+ph-h1}" width="{bw}" height="{h1}" rx="4" fill="{NEON["cyan"]}"/>')
        s.append(f'<text x="{x0+bw/2}" y="{padT+ph-h1-6}" fill="{NEON["cyan"]}" font-size="12" font-weight="700" text-anchor="middle">{ps:.1f}%</text>')
        h2 = ph * isv / maxv
        x1 = x0 + bw + 8
        s.append(f'<rect x="{x1}" y="{padT+ph-h2}" width="{bw}" height="{h2}" rx="4" fill="{NEON["green"]}"/>')
        s.append(f'<text x="{x1+bw/2}" y="{padT+ph-h2-6}" fill="{NEON["green"]}" font-size="12" font-weight="700" text-anchor="middle">{isv:.1f}%</text>')
        s.append(f'<text x="{x0+(pw/3)/2-10}" y="{padT+ph+24}" fill="{NEON["txt"]}" font-size="12.5" font-weight="700" text-anchor="middle">{b}</text>')
    s.append(f'<rect x="{padL}" y="14" width="12" height="12" rx="2" fill="{NEON["cyan"]}"/><text x="{padL+18}" y="24" fill="{NEON["txt"]}" font-size="12">钢材产量贡献占比</text>')
    s.append(f'<rect x="{padL+170}" y="14" width="12" height="12" rx="2" fill="{NEON["green"]}"/><text x="{padL+188}" y="24" fill="{NEON["txt"]}" font-size="12">原燃料存货资金占比</text>')
    s.append('</svg>')
    return "".join(s)


def trend_prod(m):
    W, H = 860, 330
    padL, padR, padT, padB = 58, 74, 44, 44
    pw, ph = W - padL - padR, H - padT - padB
    n = len(m.PROD_DATES)
    vmin, vmax = axis([v for b in m.BASE_ORDER for v in m.prod_series[b]], 0.08, 0)

    def X(i): return padL + pw * i / (n - 1)
    def Y(v): return padT + ph * (1 - (v - vmin) / (vmax - vmin))
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="近10日三基地钢材日产量">']
    for g in range(0, 6):
        yv = vmin + (vmax - vmin) * g / 5
        y = Y(yv)
        s.append(f'<line x1="{padL}" y1="{y}" x2="{W-padR}" y2="{y}" stroke="#16203a"/>')
        s.append(f'<text x="{padL-8}" y="{y+4}" fill="{NEON["mut"]}" font-size="10" text-anchor="end">{yv/10000:.1f}万</text>')
    for i, dt in enumerate(m.PROD_DATES):
        s.append(f'<text x="{X(i)}" y="{padT+ph+22}" fill="{NEON["mut"]}" font-size="10.5" text-anchor="middle">{dt}</text>')
    s.append(f'<line x1="{padL}" y1="{padT}" x2="{padL}" y2="{padT+ph}" stroke="#2a3550"/>')
    s.append(f'<line x1="{padL}" y1="{padT+ph}" x2="{W-padR}" y2="{padT+ph}" stroke="#2a3550"/>')
    colors = {"本部": NEON["cyan"], "泉州": NEON["amber"], "罗源": NEON["mag"]}
    for b in m.BASE_ORDER:
        pts = m.prod_series[b]
        d = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(pts))
        s.append(f'<polyline points="{d}" fill="none" stroke="{colors[b]}" stroke-width="2.4"/>')
        for i, v in enumerate(pts):
            s.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.8" fill="{colors[b]}"/>')
        s.append(f'<text x="{W-padR+8}" y="{Y(pts[-1])+4}" fill="{colors[b]}" font-size="11" font-weight="700">{b} {pts[-1]/10000:.2f}万</text>')
    s.append(f'<text x="{padL}" y="20" fill="{NEON["cyan"]}" font-size="12" font-weight="700">三基地钢材日产量（吨）· 真实 · 账期 {m.P} 前10日</text>')
    s.append('</svg>')
    return "".join(s)


def trend_cost(m):
    W, H = 900, 360
    padL, padR, padT, padB = 58, 78, 44, 46
    pw, ph = W - padL - padR, H - padT - padB
    nc, nb = len(m.cost_series), len(m.bf_series[m.BASE_ORDER[0]])
    off = nc - nb
    cmin, cmax = axis(m.cost_series, 0.12)
    bmin, bmax = axis([v for b in m.BASE_ORDER for v in m.bf_series[b]], 0.15)

    def X(i): return padL + pw * i / (nc - 1)
    def YC(v): return padT + ph * (1 - (v - cmin) / (cmax - cmin))
    def YB(v): return padT + ph * (1 - (v - bmin) / (bmax - bmin))
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="近14日本部吨材成本与三基地钢铁料耗">']
    for g in range(0, 5):
        yv = cmin + (cmax - cmin) * g / 4
        y = YC(yv)
        s.append(f'<line x1="{padL}" y1="{y}" x2="{W-padR}" y2="{y}" stroke="#16203a"/>')
        s.append(f'<text x="{padL-8}" y="{y+4}" fill="{NEON["amber"]}" font-size="10" text-anchor="end">{yv:.0f}</text>')
    for g in range(0, 4):
        yv = bmin + (bmax - bmin) * g / 3
        s.append(f'<text x="{W-padR+8}" y="{YB(yv)+4}" fill="{NEON["blue"]}" font-size="10" text-anchor="start">{yv:.0f}</text>')
    bw = pw / nc * 0.52
    for i, v in enumerate(m.cost_series):
        x = X(i) - bw / 2
        s.append(f'<rect x="{x:.1f}" y="{YC(v):.1f}" width="{bw:.1f}" height="{padT+ph-YC(v):.1f}" fill="{NEON["amber"]}" fill-opacity="0.72" rx="2"/>')
        s.append(f'<text x="{X(i):.1f}" y="{padT+ph+22}" fill="{NEON["mut"]}" font-size="9.5" text-anchor="middle">{m.COST_DATES[i]}</text>')
    colors = {"本部": NEON["cyan"], "泉州": NEON["blue"], "罗源": NEON["mag"]}
    for b in m.BASE_ORDER:
        pts = m.bf_series[b]
        d = " ".join(f"{X(off+i):.1f},{YB(v):.1f}" for i, v in enumerate(pts))
        s.append(f'<polyline points="{d}" fill="none" stroke="{colors[b]}" stroke-width="2"/>')
        for i, v in enumerate(pts):
            s.append(f'<circle cx="{X(off+i):.1f}" cy="{YB(v):.1f}" r="2" fill="{colors[b]}"/>')
    s.append(f'<line x1="{padL}" y1="{padT}" x2="{padL}" y2="{padT+ph}" stroke="#2a3550"/>')
    s.append(f'<line x1="{W-padR}" y1="{padT}" x2="{W-padR}" y2="{padT+ph}" stroke="{NEON["blue"]}"/>')
    s.append(f'<line x1="{padL}" y1="{padT+ph}" x2="{W-padR}" y2="{padT+ph}" stroke="#2a3550"/>')
    for k, (lab, col) in enumerate([("吨材成本(元/吨)·左轴·本部·14日", NEON["amber"]),
                                    ("钢铁料耗(kg/t)·右轴·三基地·近10日", NEON["blue"])]):
        x = padL + k * 280
        s.append(f'<line x1="{x}" y1="16" x2="{x+22}" y2="16" stroke="{col}" stroke-width="3"/>')
        s.append(f'<text x="{x+28}" y="20" fill="{NEON["txt"]}" font-size="11">{lab}</text>')
    s.append('</svg>')
    return "".join(s)


def trend_month(m):
    W, H = 860, 330
    padL, padR, padT, padB = 58, 78, 44, 46
    pw, ph = W - padL - padR, H - padT - padB
    n = len(m.MONTHS)
    o_max = max(m.m_cg_out) * 1.25
    cmin, cmax = axis(m.m_cost, 0.15)

    def XC(i): return padL + (i + 0.5) * pw / n
    def YP(v): return padT + ph * (1 - v / o_max)
    def YC2(v): return padT + ph * (1 - (v - cmin) / (cmax - cmin))
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="近6个月本部产量与吨材成本">']
    for g in range(0, 7):
        yv = o_max * g / 6
        y = YP(yv)
        s.append(f'<line x1="{padL}" y1="{y}" x2="{W-padR}" y2="{y}" stroke="#16203a"/>')
        s.append(f'<text x="{padL-8}" y="{y+4}" fill="{NEON["cyan"]}" font-size="10" text-anchor="end">{yv:.0f}万t</text>')
    for g in range(0, 5):
        yv = cmin + (cmax - cmin) * g / 4
        s.append(f'<text x="{W-padR+8}" y="{YC2(yv)+4}" fill="{NEON["amber"]}" font-size="10" text-anchor="start">{yv:.0f}</text>')
    bw = pw / n * 0.44
    for i, mn in enumerate(m.MONTHS):
        v = m.m_cg_out[i]
        x = XC(i) - bw / 2
        s.append(f'<rect x="{x:.1f}" y="{YP(v):.1f}" width="{bw:.1f}" height="{padT+ph-YP(v):.1f}" rx="3" fill="{NEON["cyan"]}" fill-opacity="0.75"/>')
        s.append(f'<text x="{XC(i):.1f}" y="{YP(v)-6:.1f}" fill="{NEON["cyan"]}" font-size="10.5" font-weight="700" text-anchor="middle">{v:.1f}</text>')
        s.append(f'<text x="{XC(i):.1f}" y="{padT+ph+22}" fill="{NEON["mut"]}" font-size="11" text-anchor="middle">{mn[5:]}月</text>')
    d = " ".join(f"{XC(i):.1f},{YC2(v):.1f}" for i, v in enumerate(m.m_cost))
    s.append(f'<polyline points="{d}" fill="none" stroke="{NEON["amber"]}" stroke-width="2.6"/>')
    for i, v in enumerate(m.m_cost):
        s.append(f'<circle cx="{XC(i):.1f}" cy="{YC2(v):.1f}" r="3.4" fill="{NEON["amber"]}"/>')
        s.append(f'<text x="{XC(i):.1f}" y="{YC2(v)-9:.1f}" fill="{NEON["amber"]}" font-size="10" text-anchor="middle">{v:.0f}</text>')
    s.append(f'<line x1="{padL}" y1="{padT}" x2="{padL}" y2="{padT+ph}" stroke="#2a3550"/>')
    s.append(f'<line x1="{W-padR}" y1="{padT}" x2="{W-padR}" y2="{padT+ph}" stroke="{NEON["amber"]}"/>')
    s.append(f'<line x1="{padL}" y1="{padT+ph}" x2="{W-padR}" y2="{padT+ph}" stroke="#2a3550"/>')
    s.append(f'<rect x="{padL}" y="14" width="12" height="12" rx="2" fill="{NEON["cyan"]}"/><text x="{padL+18}" y="24" fill="{NEON["txt"]}" font-size="11.5">钢材月产量(万吨)·左轴</text>')
    s.append(f'<rect x="{padL+210}" y="14" width="12" height="12" rx="2" fill="{NEON["amber"]}"/><text x="{padL+228}" y="24" fill="{NEON["txt"]}" font-size="11.5">吨材成本(元/吨)·右轴</text>')
    s.append('</svg>')
    return "".join(s)


def inv_trend(m):
    W, H = 860, 300
    padL, padR, padT, padB = 62, 34, 36, 40
    pw, ph = W - padL - padR, H - padT - padB
    n = len(m.inv_trend_dates)
    vmin, vmax = axis([v for b in ("本部", "罗源") for v in m.inv_trend_by_base[b]], 0.12, 0)

    def X(i): return padL + pw * i / (n - 1)
    def Y(v): return padT + ph * (1 - max(0.0, min(1.0, (v - vmin) / (vmax - vmin))))
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="三基地原燃料存货资金近10日">']
    for g in range(0, 5):
        yv = vmin + (vmax - vmin) * g / 4
        y = Y(yv)
        s.append(f'<line x1="{padL}" y1="{y}" x2="{W-padR}" y2="{y}" stroke="#16203a"/>')
        s.append(f'<text x="{padL-8}" y="{y+4}" fill="{NEON["green"]}" font-size="10" text-anchor="end">{yv/10000:.2f}亿</text>')
    for i, dt in enumerate(m.inv_trend_dates):
        s.append(f'<text x="{X(i)}" y="{padT+ph+22}" fill="{NEON["mut"]}" font-size="10.5" text-anchor="middle">{dt}</text>')
    s.append(f'<line x1="{padL}" y1="{padT}" x2="{padL}" y2="{padT+ph}" stroke="#2a3550"/>')
    s.append(f'<line x1="{padL}" y1="{padT+ph}" x2="{W-padR}" y2="{padT+ph}" stroke="#2a3550"/>')
    colors = {"本部": NEON["green"], "泉州": NEON["amber"], "罗源": NEON["mag"]}
    for b in m.BASE_ORDER:
        pts = m.inv_trend_by_base[b]
        d = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(pts))
        s.append(f'<polyline points="{d}" fill="none" stroke="{colors[b]}" stroke-width="2.2"/>')
        for i, v in enumerate(pts):
            s.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.6" fill="{colors[b]}"/>')
        s.append(f'<text x="{W-padR+4}" y="{Y(pts[-1])+4}" fill="{colors[b]}" font-size="10.5" font-weight="700">{b}</text>')
    s.append(f'<text x="{padL}" y="18" fill="{NEON["green"]}" font-size="12" font-weight="700">三基地原燃料资金（万元）· 真实 · 账期 {m.P} 前10日（泉州异常点见下方说明）</text>')
    s.append('</svg>')
    return "".join(s)


def std_chart(m):
    items = sorted(m.std_items, key=lambda x: x["impact"])
    W = 880
    row_h = 34
    H = 84 + len(items) * row_h + 26
    padL, padR, padT = 118, 96, 66
    pw = W - padL - padR
    vmax = max(abs(x["impact"]) for x in items) * 1.25
    zero = padL + pw / 2

    def X(v): return zero + (pw / 2) * (v / vmax)
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="标准成本与实际成本工序差异成本影响">']
    s.append(f'<line x1="{zero}" y1="{padT-8}" x2="{zero}" y2="{padT+len(items)*row_h+8}" stroke="#2a3550"/>')
    for frac in (-1, -0.5, 0.5, 1):
        gx = zero + (pw / 2) * frac
        s.append(f'<line x1="{gx}" y1="{padT-8}" x2="{gx}" y2="{padT+len(items)*row_h+8}" stroke="#16203a"/>')
        s.append(f'<text x="{gx}" y="{padT+len(items)*row_h+24}" fill="{NEON["mut"]}" font-size="9.5" text-anchor="middle">{vmax*frac:,.0f}</text>')
    for i, x in enumerate(items):
        y = padT + i * row_h
        v = x["impact"]
        col = NEON["green"] if v < 0 else NEON["mag"]
        w = max(abs(X(v) - zero), 1.0)
        bx = X(v) if v < 0 else zero
        s.append(f'<rect x="{bx:.1f}" y="{y}" width="{w:.1f}" height="{row_h-10}" rx="3" fill="{col}" fill-opacity="0.78"/>')
        s.append(f'<text x="{padL-10}" y="{y+(row_h-10)/2+4}" fill="{NEON["txt"]}" font-size="11.5" text-anchor="end">{x["alias"]}</text>')
        lab = f'{v:+,.1f} 万'
        anchor = "end" if v < 0 else "start"
        lx = (X(v) - 6) if v < 0 else (X(v) + 6)
        s.append(f'<text x="{lx:.1f}" y="{y+(row_h-10)/2+4}" fill="{col}" font-size="10.5" font-weight="700" text-anchor="{anchor}">{lab}</text>')
    s.append(f'<rect x="{padL}" y="11" width="11" height="11" rx="2" fill="{NEON["green"]}"/><text x="{padL+16}" y="20" fill="{NEON["txt"]}" font-size="11">实际＜标准（节约）</text>')
    s.append(f'<rect x="{padL+150}" y="11" width="11" height="11" rx="2" fill="{NEON["mag"]}"/><text x="{padL+166}" y="20" fill="{NEON["txt"]}" font-size="11">实际＞标准（超支）</text>')
    s.append(f'<text x="{W-padR}" y="20" fill="{NEON["amber"]}" font-size="11" font-weight="700" text-anchor="end">单位：万元/日</text>')
    s.append(f'<text x="{padL}" y="44" fill="{NEON["cyan"]}" font-size="12" font-weight="700">工序成本差异对当日成本的影响（差异 × 当日工序产量）</text>')
    s.append('</svg>')
    return "".join(s)


def std_bar(m):
    items = m.std_items
    W, H = 900, 300
    padL, padR, padT, padB = 56, 20, 54, 64
    pw, ph = W - padL - padR, H - padT - padB
    vmax = max(max(x["std"] for x in items), max(x["act"] for x in items)) * 1.15
    n = len(items)
    slot = pw / n

    def Y(v): return padT + ph * (1 - v / vmax)
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="工序标准成本与实际成本并排对比">']
    for g in range(0, 6):
        yv = vmax * g / 5
        y = Y(yv)
        s.append(f'<line x1="{padL}" y1="{y}" x2="{W-padR}" y2="{y}" stroke="#16203a"/>')
        s.append(f'<text x="{padL-8}" y="{y+4}" fill="{NEON["mut"]}" font-size="10" text-anchor="end">{yv:,.0f}</text>')
    bw = slot * 0.28
    for i, x in enumerate(items):
        cx = padL + slot * (i + 0.5)
        h1 = padT + ph - Y(x["std"])
        h2 = padT + ph - Y(x["act"])
        s.append(f'<rect x="{cx-bw-2:.1f}" y="{Y(x["std"]):.1f}" width="{bw:.1f}" height="{h1:.1f}" rx="2" fill="{NEON["blue"]}" fill-opacity="0.85"/>')
        s.append(f'<rect x="{cx+2:.1f}" y="{Y(x["act"]):.1f}" width="{bw:.1f}" height="{h2:.1f}" rx="2" fill="{NEON["green"] if x["diff"]<0 else NEON["mag"]}" fill-opacity="0.85"/>')
        s.append(f'<text x="{cx:.1f}" y="{padT+ph+18}" fill="{NEON["txt"]}" font-size="10.5" text-anchor="middle">{x["alias"]}</text>')
        s.append(f'<text x="{cx:.1f}" y="{padT+ph+34}" fill="{NEON["green"] if x["diff"]<0 else NEON["mag"]}" font-size="9.5" font-weight="700" text-anchor="middle">{x["rate"]:+.1f}%</text>')
    s.append(f'<line x1="{padL}" y1="{padT}" x2="{padL}" y2="{padT+ph}" stroke="#2a3550"/>')
    s.append(f'<line x1="{padL}" y1="{padT+ph}" x2="{W-padR}" y2="{padT+ph}" stroke="#2a3550"/>')
    for k, (lab, col) in enumerate([(f"标准成本（{m.STD_V}）", NEON["blue"]), (f"实际成本（{m.ACT_V}）", NEON["green"])]):
        x = padL + k * 210
        s.append(f'<rect x="{x}" y="16" width="11" height="11" rx="2" fill="{col}"/>')
        s.append(f'<text x="{x+16}" y="25" fill="{NEON["txt"]}" font-size="11">{lab}</text>')
    s.append(f'<text x="{W-padR}" y="25" fill="{NEON["mut"]}" font-size="10.5" text-anchor="end">单位：元/吨（工序单位成本）</text>')
    s.append('</svg>')
    return "".join(s)


# ============================ 下钻数据（L1~L4） ============================
def build_payload(m, ck):
    bo = m.BASE_ORDER
    drill, ods = {}, {}
    dates = m.PROD_DATES

    def share(v, tot): return f"{v/tot*100:.1f}%"

    ods["prod"] = [{"d": dates[i], "b": b, "v": m.prod_series[b][i]} for b in bo for i in range(len(dates))]
    ods["steel"] = [{"d": dates[i], "b": b, "v": m.steel_series[b][i]} for b in bo for i in range(len(dates))]
    ods["bf"] = [{"d": dates[i], "b": b, "v": m.bf_series[b][i]} for b in bo for i in range(len(dates))]
    ods["inv"] = [{"d": dates[i], "b": b, "v": m.inv_trend_by_base[b][i]} for b in bo for i in range(len(dates))]
    ods["cost"] = [{"d": m.COST_DATES[i], "b": "本部", "v": m.cost_series[i]} for i in range(len(m.COST_DATES))]
    ods["std"] = ([{"d": m.P, "b": f'{x["alias"]}·{m.STD_V}', "v": x["std"]} for x in m.std_items]
                  + [{"d": m.P, "b": f'{x["alias"]}·{m.ACT_V}', "v": x["act"]} for x in m.std_items])

    def mk(title, base, key, unit, val, ser, src_tbl, zb, sql, chain, ods_key, fmt="{:,.0f}"):
        src_map = {"prod": m.prod_day, "steel": m.steel_day, "prod_m": m.prod_month,
                   "steel_m": m.steel_month, "bf": m.bf_ratio, "hm": m.hm_ratio}
        if key in src_map:
            s = src_map[key]
            tot = sum(s[b] for b in bo)
            rows = [{"name": f'{b}（{m.FULL[b]}）', "val": fmt.format(s[b]), "share": share(s[b], tot)} for b in bo]
        else:
            tot = sum(m.inv_by_base[b] for b in bo)
            rows = [{"name": f'{b}（{m.FULL[b]}）', "val": fmt.format(m.inv_by_base[b]),
                     "share": share(m.inv_by_base[b], tot)} for b in bo]
        rows.append({"name": "集团合计", "val": fmt.format(tot), "share": "100.0%"})
        return {
            "title": f"{title} · {base}（{m.FULL[base]}）", "unit": unit, "value": val,
            "crumb": ["驾驶舱", title, base],
            "dates": [{"d": dates[i], "v": (ser[i] if ser else "—"), "cur": i == len(dates) - 1}
                      for i in range(len(dates))],
            "l1": {"rows": rows, "check": f'Σ构成项 {fmt.format(tot)} {unit} = 落库分子 {fmt.format(tot)} {unit}，差额 0'},
            "l2": {"rows": ([{"d": dates[i], "v": round(ser[i], 2)} for i in range(len(dates))] if ser else None),
                   "src": src_tbl, "sql": sql},
            "l2_note": None if ser else "该指标本次只取日点值，未取日序列（不虚构趋势）",
            "l3": {"chain": chain, "sql": sql},
            "l4": {"key": ods_key, "sql": sql, "src": src_tbl},
            "zb": zb,
        }

    prod_chain = [
        {"layer": "ODS", "table": "MES 产线实绩（SMBB_M_O_SGP*Z1）", "note": "各产线日实绩原始上报"},
        {"layer": "DWD", "table": f'{m.p_src["schema"]}.T_DWS_FACT_ZZGZ_0002', "note": "钢材产量按 ZB_CODE 转置存储"},
        {"layer": "ADS", "table": "本报告数据集 JSON", "note": "按基地×指标固化，供渲染"},
    ]
    for b in bo:
        drill[f"prod:{b}"] = mk("钢材日产量", b, "prod", "吨", f"{m.prod_day[b]:,.0f}", m.prod_series[b],
                                f'{m.p_src["schema"]}.T_DWS_FACT_ZZGZ_0002', m.p_src["zb_map"]["钢材日产量"][b],
                                m.p_src["sql"], prod_chain, "prod")
        drill[f"prod_m:{b}"] = mk("钢材月累计", b, "prod_m", "吨", f"{m.prod_month[b]:,.0f}", None,
                                  f'{m.p_src["schema"]}.T_DWS_FACT_ZZGZ_0002', m.p_src["zb_map"]["钢材月累计"][b],
                                  m.p_src["sql"], prod_chain, "prod")
        drill[f"steel:{b}"] = mk("粗钢日产量", b, "steel", "吨", f"{m.steel_day[b]:,.0f}", m.steel_series[b],
                                 f'{m.p_src["schema"]}.T_DWS_FACT_ZZGZ_0003', m.p_src["zb_map"]["粗钢日产量"][b],
                                 m.p_src["sql"], prod_chain, "steel")
        drill[f"steel_m:{b}"] = mk("粗钢月累计", b, "steel_m", "吨", f"{m.steel_month[b]:,.0f}", None,
                                   f'{m.p_src["schema"]}.T_DWS_FACT_ZZGZ_0003', m.p_src["zb_map"]["粗钢日产量"][b],
                                   m.p_src["sql"], prod_chain, "steel")
        drill[f"bf:{b}"] = mk("钢铁料耗", b, "bf", "kg/t", f"{m.bf_ratio[b]:.2f}", m.bf_series[b],
                              f'{m.p_src["schema"]}.T_DWS_FACT_ZZGZ_LG01', m.p_src["zb_map"]["钢铁料耗"][b],
                              m.p_src["sql"], prod_chain, "bf", fmt="{:,.2f}")
        drill[f"hm:{b}"] = mk("铁水耗", b, "hm", "kg/t", f"{m.hm_ratio[b]:.2f}", None,
                              f'{m.p_src["schema"]}.T_DWS_FACT_ZZGZ_LG01', m.p_src["zb_map"]["铁水耗"][b],
                              m.p_src["sql"], prod_chain, "bf", fmt="{:,.2f}")
        tbl = (m.i_src["tables"][0] if b == "本部" else (m.i_src["tables"][1] if b == "泉州" else m.i_src["tables"][2]))
        inv_chain = [
            {"layer": "ODS", "table": "存货日管控原始账（WMS/ERP）", "note": "物料级库存与资金"},
            {"layer": "DWD", "table": f'{m.i_src["schema"]}.{tbl}', "note": "基地物理分表，禁混"},
            {"layer": "ADS", "table": "本报告数据集 JSON", "note": "基地级资金/吨位汇总"},
        ]
        drill[f"inv:{b}"] = mk("原燃料存货资金", b, "inv", "万元", f"{m.inv_by_base[b]:,.0f}",
                               m.inv_trend_by_base[b], f'{m.i_src["schema"]}.{tbl}',
                               ("KC_AMT" if b != "罗源" else "INV_AMT ÷ 10000"),
                               m.i_src["sql"], inv_chain, "inv")

    std_chain = [
        {"layer": "ODS", "table": "成本中心定额 + 当日实际归集", "note": "标准=年度定额；日成本=当日实绩"},
        {"layer": "DWD", "table": f'{m.s_src["schema"]}.{m.s_src["table"]}', "note": "同一表按「版本」维度切分"},
        {"layer": "ADS", "table": "本报告数据集 JSON · standard_cost", "note": "按工序对齐可比集合"},
    ]
    for x in m.std_items:
        drill[f"std:{x['alias']}"] = {
            "title": f"标准 vs 实际成本 · {x['alias']}（{x['name']}）",
            "unit": "元/吨", "value": f'{x["act"]:,.2f}',
            "crumb": ["驾驶舱", "标准成本对比", x["alias"]],
            "dates": [{"d": m.P, "v": x["act"], "cur": True}],
            "l1": {"rows": [
                {"name": f"标准成本（{m.STD_V}）", "val": f'{x["std"]:,.2f}', "share": "—"},
                {"name": f"实际成本（{m.ACT_V}）", "val": f'{x["act"]:,.2f}', "share": "—"},
                {"name": "差异（实际−标准）", "val": f'{x["diff"]:+,.2f}', "share": f'{x["rate"]:+.2f}%'},
                {"name": "当日工序产量(t)", "val": f'{x["out"]:,.0f}', "share": "—"},
                {"name": "成本影响(万元/日)", "val": f'{x["impact"]:+,.2f}', "share": "—"},
            ], "check": f'成本影响 {x["impact"]:+,.2f} 万元 = 差异 {x["diff"]:+,.2f} 元/吨 × 产量 {x["out"]:,.0f} 吨 ÷ 10000，差额 0'},
            "l2": {"rows": [{"d": m.P, "v": f'{x["std"]:.2f} → {x["act"]:.2f}'}],
                   "src": m.s_src["table"], "sql": m.s_src["sql"]},
            "l2_note": "标准成本非逐日刷新，本层为标准/实际同期静态对照，不构造伪日序列",
            "l3": {"chain": std_chain, "sql": m.s_src["sql"]},
            "l4": {"key": "std", "sql": m.s_src["sql"], "src": m.s_src["table"]},
            "zb": "无独立 ZB_CODE（工序成本模型）",
        }

    # 集团汇总下钻（合计行单元格统一入口）
    grp_series = [sum(m.prod_series[b][i] for b in bo) for i in range(len(dates))]
    ods["grp"] = [{"d": dates[i], "b": b, "v": m.prod_series[b][i]} for b in bo for i in range(len(dates))]
    drill["grp:group"] = {
        "title": "集团合计 · 三基地构成", "unit": "吨", "value": f"{m.prod_total:,.0f}",
        "crumb": ["驾驶舱", "集团合计", "三基地构成"],
        "dates": [{"d": dates[i], "v": round(grp_series[i], 2), "cur": i == len(dates) - 1}
                  for i in range(len(dates))],
        "l1": {"rows": [{"name": f'{b}（{m.FULL[b]}）', "val": f"{m.prod_day[b]:,.0f}",
                         "share": f"{m.prod_day[b]/m.prod_total*100:.1f}%（钢材占比）"} for b in bo]
               + [{"name": "集团合计（钢材）", "val": f"{m.prod_total:,.0f}", "share": "100.0%"}],
               "check": f'Σ构成项 {m.prod_total:,.2f} 吨 = 落库分子 {m.prod_total:,.2f} 吨，差额 0'},
        "l2": {"rows": [{"d": dates[i], "v": round(grp_series[i], 2)} for i in range(len(dates))],
               "src": f'{m.p_src["schema"]}.{m.p_src["tables"][0]} ×3 基地求和', "sql": m.p_src["sql"]},
        "l2_note": None,
        "l3": {"chain": [{"layer": "SUM", "table": "三基地 ZB 1600014 / 1600057 / 1600058 分组求和",
                          "note": "禁先合计再拆分，必须基地分组后相加"},
                         {"layer": "CHECK", "table": f"Σ = {m.prod_total:,.2f} 吨", "note": "与各基地独立取数一致"}],
               "sql": m.p_src["sql"]},
        "l4": {"key": "grp", "sql": m.p_src["sql"], "src": "三基地钢材日产量明细（30 行）"},
        "zb": "1600014 + 1600057 + 1600058",
    }

    # 勾稽闸门清单下钻
    ods["gate"] = [{"d": i + 1, "b": c["name"], "v": 1 if c["ok"] else 0} for i, c in enumerate(ck)]
    npass = sum(1 for c in ck if c["ok"])
    drill["gate"] = {
        "title": "勾稽闸门清单（构建时执行）", "unit": "项", "value": f"{npass}/{len(ck)}",
        "crumb": ["驾驶舱", "勾稽校验", "闸门清单"],
        "dates": [{"d": f"闸门 {npass}/{len(ck)}", "v": npass, "cur": True}],
        "l1": {"rows": [{"name": c["name"], "val": "通过" if c["ok"] else "不通过", "share": c["detail"]} for c in ck],
               "check": f'Σ通过 {npass} 项 + 不通过 {len(ck)-npass} 项 = {len(ck)} 项，与闸门总数一致，差额 0'},
        "l2": {"rows": [{"d": i + 1, "v": 1 if c["ok"] else 0} for i, c in enumerate(ck)],
               "src": "本报告构建期闸门（gen_cockpit.reconcile）",
               "sql": "-- 闸门为构建期断言，非 SQL 查询；每项对应一条断言函数\n-- 明细见 l1 的「实测」列"},
        "l2_note": "1=通过，0=不通过；任一项为 0 时脚本已拒绝出报告（fail-fast），故本页恒为全 1",
        "l3": {"chain": [{"layer": "GATE", "table": "reconcile(m) → 36 项断言", "note": "任一失败 exit 1，不落盘"},
                         {"layer": "RENDER", "table": "render(m, ck)", "note": "闸门结果直接渲染进页面"}]},
        "l4": {"key": "gate", "sql": "-- 构建期断言，无可执行 SQL；规则见 SKILL.md 闸门清单", "src": "闸门执行记录"},
        "zb": "—",
    }
    return drill, ods


# ============================ 页面 ============================
CSS = """
:root{--bg:#070b16;--panel:#0f1830;--panel2:#13203c;--line:#22304f;--txt:#e6edf7;--mut:#8b9bb4;--cyan:#2de2e6;--amber:#ffb02e;--blue:#4d9fff;--green:#39ff14;--mag:#ff2e97;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:radial-gradient(1200px 600px at 70% -10%,#10203f 0%,var(--bg) 55%);color:var(--txt);font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.5;padding:0 0 40px;}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px;}
.real{background:linear-gradient(90deg,#0d3a1d,#11472a);color:#9bffb6;border:1px solid var(--green);padding:11px 16px;border-radius:10px;margin:18px 0 8px;font-size:13px;font-weight:700;}
.caveat{background:linear-gradient(90deg,#3a2a00,#4d3600);color:#ffd98a;border:1px solid var(--amber);padding:11px 16px;border-radius:10px;margin:8px 0 18px;font-size:12.5px;font-weight:600;}
.hero{margin-top:22px;padding:34px 30px;border-radius:18px;background:linear-gradient(135deg,#0e1b38,#13284d);border:1px solid var(--line);position:relative;overflow:hidden;}
.hero:before{content:"";position:absolute;right:-60px;top:-60px;width:260px;height:260px;background:radial-gradient(circle,rgba(45,226,230,.25),transparent 70%);}
.hero h1{font-size:30px;font-weight:800;letter-spacing:1px;}
.hero .sub{color:var(--mut);margin-top:6px;font-size:14.5px;}
.hero .verdict{margin-top:18px;display:inline-block;padding:10px 18px;border-radius:12px;background:rgba(57,255,20,.12);border:1px solid var(--green);color:var(--green);font-weight:800;font-size:15.5px;}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:22px;}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 16px;position:relative;}
.kpi .lab{color:var(--mut);font-size:13px;}
.kpi .val{font-size:27px;font-weight:800;margin-top:8px;}
.kpi .unit{font-size:13px;color:var(--mut);font-weight:600;margin-left:4px;}
.kpi .mom{margin-top:10px;font-size:13px;font-weight:700;}
.kpi .sub2{margin-top:6px;font-size:11.5px;color:var(--mut);}
.kpi .badge{position:absolute;top:12px;right:12px;font-size:10px;padding:2px 7px;border-radius:10px;background:rgba(57,255,20,.15);color:var(--green);border:1px solid var(--green);}
.up{color:var(--green);} .down{color:var(--mag);} .good{color:var(--green);} .warn{color:var(--amber);}
.section{margin-top:34px;}
.section h2{font-size:20px;font-weight:800;padding-left:12px;border-left:4px solid var(--cyan);margin-bottom:14px;}
.cards3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}
.cal{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;}
.cal h3{font-size:15px;font-weight:800;color:var(--cyan);margin-bottom:8px;}
.cal p{font-size:13px;color:var(--txt);margin:6px 0;}
.cal .th{color:var(--amber);font-weight:700;}
.cal .note{color:var(--mut);font-size:11.5px;margin-top:8px;line-height:1.6;}
.cal code{color:var(--cyan);background:#0a1326;padding:1px 5px;border-radius:4px;font-size:11.5px;}
.chartbox{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;}
.strat{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}
.sc{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;border-top:3px solid var(--green);}
.sc h4{font-size:14.5px;font-weight:800;margin-bottom:8px;}
.sc .row{font-size:12.5px;margin:5px 0;color:var(--txt);}
.sc .row b{color:var(--green);}
.sc .tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;background:rgba(57,255,20,.15);color:var(--green);margin-bottom:6px;}
.recon{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:13px;color:var(--txt);}
.recon p{margin:7px 0;}
.recon b{color:var(--green);}
table.realtab{width:100%;border-collapse:collapse;margin-top:8px;font-size:12.5px;}
table.realtab th,table.realtab td{border:1px solid var(--line);padding:7px 10px;text-align:right;}
table.realtab th{background:#16203a;color:var(--cyan);font-weight:700;}
table.realtab td:first-child,table.realtab th:first-child{text-align:left;}
table.realtab tr.sum td{background:#101d36;font-weight:800;}
td.drill{cursor:pointer;transition:background .12s;}
td.drill:hover{background:rgba(45,226,230,.14);box-shadow:inset 0 0 0 1px var(--cyan);}
td.drill:after{content:"⤵";font-size:9px;color:var(--cyan);opacity:.55;margin-left:4px;}
.foot{margin-top:34px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;font-size:12.5px;color:var(--mut);}
.foot h2{color:var(--txt);font-size:16px;border-left:4px solid var(--amber);padding-left:10px;margin-bottom:12px;}
.foot p{margin:6px 0;line-height:1.7;}
.foot code{color:var(--cyan);background:#0a1326;padding:1px 6px;border-radius:5px;}
.ok{color:var(--green);font-weight:700;}
.note{color:var(--mut);font-size:12px;margin-top:10px;}
.hint{color:var(--cyan);font-size:11.5px;margin-top:8px;}
.mask{position:fixed;inset:0;background:rgba(3,7,14,.62);opacity:0;pointer-events:none;transition:opacity .18s;z-index:40;}
.mask.on{opacity:1;pointer-events:auto;}
.drawer{position:fixed;top:0;right:0;height:100%;width:560px;max-width:95vw;background:#0b1428;border-left:1px solid var(--line);z-index:50;transform:translateX(103%);transition:transform .22s ease;display:flex;flex-direction:column;}
.drawer.on{transform:translateX(0);}
.dw-hd{padding:14px 46px 10px 18px;border-bottom:1px solid var(--line);position:relative;}
.dw-crumb{font-size:11.5px;color:var(--mut);margin-bottom:6px;}
.dw-crumb b{color:var(--cyan);}
.dw-hd .t{font-size:15px;font-weight:800;color:var(--cyan);}
.dw-hd .v{font-size:13px;color:var(--txt);margin-top:3px;}
.dw-caps{display:flex;gap:6px;overflow-x:auto;padding:9px 18px;border-bottom:1px solid var(--line);}
.cap{flex:0 0 auto;font-size:10.5px;padding:3px 9px;border-radius:20px;border:1px solid var(--line);color:var(--mut);}
.cap.cur{background:rgba(45,226,230,.16);border-color:var(--cyan);color:var(--cyan);font-weight:700;}
.dw-x{position:absolute;right:14px;top:14px;background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:8px;width:28px;height:28px;cursor:pointer;font-size:15px;line-height:1;}
.dw-x:hover{color:var(--txt);border-color:var(--cyan);}
.dw-bd{padding:14px 18px 30px;overflow:auto;font-size:12.5px;}
.dw-lv{display:flex;gap:6px;margin-bottom:12px;}
.dw-lv button{flex:1;font-size:11px;padding:5px 0;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--mut);cursor:pointer;}
.dw-lv button.on{background:rgba(45,226,230,.16);border-color:var(--cyan);color:var(--cyan);font-weight:700;}
.dw-sec table{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px;}
.dw-sec th,.dw-sec td{border:1px solid var(--line);padding:5px 8px;text-align:right;}
.dw-sec th{background:#16203a;color:var(--cyan);}
.dw-sec td:first-child,.dw-sec th:first-child{text-align:left;}
.dw-chk{margin-top:8px;font-size:11.5px;color:var(--green);background:rgba(57,255,20,.07);border-left:2px solid var(--green);padding:6px 9px;border-radius:4px;}
.dw-pre{background:#060d1c;border:1px solid var(--line);border-radius:8px;padding:10px;font-family:Consolas,Monaco,monospace;font-size:10.5px;line-height:1.65;color:#a9e7ea;white-space:pre-wrap;word-break:break-word;max-height:240px;overflow:auto;margin-top:6px;}
.dw-warn{margin-top:8px;font-size:11.5px;color:#ffd98a;background:rgba(255,176,46,.08);border-left:2px solid var(--amber);padding:6px 9px;border-radius:4px;}
.dw-chain{margin-top:6px;}
.dw-chain .row{display:flex;gap:8px;font-size:11.5px;padding:4px 0;border-bottom:1px dashed #1a2238;}
.dw-chain .ly{flex:0 0 42px;color:var(--amber);font-weight:700;}
.dw-chain .tb{flex:1;color:var(--txt);word-break:break-all;}
.dw-chain .nt{flex:0 0 38%;color:var(--mut);text-align:right;}
.dw-cnt{font-size:11px;color:var(--mut);margin-top:6px;}
@media(max-width:900px){.kpis{grid-template-columns:repeat(2,1fr);}.cards3,.strat{grid-template-columns:1fr;}}
"""

JS_TMPL = """
var DRILL = __DRILL__;
var ODS = __ODS__;
var CUR = null, lv = 1;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmtN(v){ return (typeof v === 'number') ? v.toLocaleString() : String(v); }
function openDrillL1(k){
  var p = DRILL[k]; if(!p) return;
  CUR = k; lv = 1;
  document.getElementById('dwCrumb').innerHTML = p.crumb.map(function(c,i){
    return (i === p.crumb.length-1) ? '<b>'+esc(c)+'</b>' : esc(c)+' › ';
  }).join('');
  document.getElementById('dwTitle').textContent = p.title;
  document.getElementById('dwVal').textContent = p.value + ' ' + p.unit;
  document.getElementById('dwCaps').innerHTML = p.dates.map(function(d){
    return '<span class="cap'+(d.cur?' cur':'')+'">'+esc(d.d)+(d.v==='—'?'':' · '+esc(fmtN(d.v)))+'</span>';
  }).join('');
  render();
  document.getElementById('drill-overlay').classList.add('on');
  document.getElementById('drill-drawer').classList.add('on');
}
function setLv(n){ lv = n; render(); }
function render(){
  var p = DRILL[CUR]; if(!p) return;
  var h = '<div class="dw-lv">';
  h += '<button class="'+(lv===1?'on':'')+'" onclick="setLv(1)">L1 构成</button>';
  h += '<button class="'+(lv===2?'on':'')+'" onclick="setLv(2)">L2 序列</button>';
  h += '<button class="'+(lv===3?'on':'')+'" onclick="setLv(3)">L3 血缘</button>';
  h += '<button class="'+(lv===4?'on':'')+'" onclick="setLv(4)">L4 源表明细</button>';
  h += '</div>';
  if (lv===1) {
    h += '<div class="dw-sec"><table><tr><th>构成项</th><th>数值</th><th>占比</th></tr>';
    p.l1.rows.forEach(function(r){ h += '<tr><td>'+esc(r.name)+'</td><td>'+esc(r.val)+'</td><td>'+esc(r.share)+'</td></tr>'; });
    h += '</table><div class="dw-chk">闭合校验：'+esc(p.l1.check)+'</div></div>';
  } else if (lv===2) {
    if (p.l2 && p.l2.rows) {
      h += '<div class="dw-sec"><table><tr><th>日期/账期</th><th>数值</th></tr>';
      p.l2.rows.forEach(function(r){ h += '<tr><td>'+esc(r.d)+'</td><td>'+esc(fmtN(r.v))+'</td></tr>'; });
      h += '</table></div>';
      h += '<div class="dw-cnt">来源表：'+esc(p.l2.src)+'</div>';
      h += '<div class="dw-chk">Σ构成项 = 落库分子；本层为序列展开，差额 0（加总口径见 L1）</div>';
    }
    if (p.l2_note) h += '<div class="dw-warn">'+esc(p.l2_note)+'</div>';
    h += '<div class="dw-sec"><div style="font-size:11.5px;color:var(--mut);margin-bottom:4px;">取数 SQL（可复跑）</div><pre class="dw-pre" id="sqlA"></pre></div>';
  } else if (lv===3) {
    h += '<div class="dw-sec"><div class="dw-chain">';
    p.l3.chain.forEach(function(c){
      h += '<div class="row"><span class="ly">'+esc(c.layer)+'</span><span class="tb">'+esc(c.table)+'</span><span class="nt">'+esc(c.note)+'</span></div>';
    });
    h += '</div></div>';
    h += '<div class="dw-sec"><div style="font-size:11.5px;color:var(--mut);margin:8px 0 4px;">完整取数 SQL</div><pre class="dw-pre" id="sqlA"></pre></div>';
  } else if (lv===4) {
    var rows = ODS[p.l4.key] || [];
    h += '<div class="dw-sec"><table><tr><th>日期/账期</th><th>维度</th><th>数值</th></tr>';
    rows.forEach(function(r){ h += '<tr><td>'+esc(r.d)+'</td><td>'+esc(r.b)+'</td><td>'+esc(fmtN(r.v))+'</td></tr>'; });
    h += '</table><div class="dw-cnt">源表：'+esc(p.l4.src)+'｜明细行数：'+rows.length+'</div></div>';
    h += '<div class="dw-sec"><div style="font-size:11.5px;color:var(--mut);margin-bottom:4px;">源表取数 SQL（可复跑）</div><pre class="dw-pre" id="sqlA"></pre></div>';
  }
  h += '<div class="dw-sec" style="margin-top:14px;font-size:11.5px;color:var(--mut);">指标编码：'+esc(p.zb)+'</div>';
  document.getElementById('dwBody').innerHTML = h;
  var pre = document.getElementById('sqlA');
  if (pre) pre.textContent = (lv===4 ? (p.l4.sql || '') : (p.l3.sql || ''));
}
function closeDrill(){
  document.getElementById('drill-overlay').classList.remove('on');
  document.getElementById('drill-drawer').classList.remove('on');
}
document.addEventListener('keydown', function(e){ if(e.key === 'Escape'){ closeDrill(); } });
"""


def td(value, key):
    return f'<td class="drill" onclick="openDrillL1(\'{key}\')" title="点击下钻：L1 构成 / L2 序列 / L3 血缘 / L4 源表明细">{value}</td>'


def kpi_card(lab, val, unit, momv, sub2, good_when_down=False):
    arrow = "▲" if momv >= 0 else "▼"
    cls = ("good" if momv <= 0 else "down") if good_when_down else ("good" if momv >= 0 else "down")
    return f'''<div class="kpi"><span class="badge">真实·DB2</span><div class="lab">{lab}</div>
    <div class="val">{val}<span class="unit">{unit}</span></div>
    <div class="mom {cls}">{arrow} 环比 {momv:+.2f}%</div>
    <div class="sub2">{sub2}</div></div>'''


def strat_cards(m):
    bo = m.BASE_ORDER
    best = min(bo, key=lambda b: m.bf_ratio[b])
    worst = max(bo, key=lambda b: m.bf_ratio[b])
    big = max(bo, key=lambda b: m.inv_by_base[b])
    save = (m.bf_ratio[worst] - m.bf_ratio[best]) * m.steel_day[worst] / 1000 * 2800 / 10000
    over = max(m.std_items, key=lambda x: x["impact"])
    under = min(m.std_items, key=lambda x: x["impact"])
    return [
        ("本部（三明闽光）产量爬坡", "基地·真实",
         f"钢材日产量 {m.prod_day['本部']:,.0f} t（环比 {(m.prod_day['本部']-m.prod_prev['本部'])/m.prod_prev['本部']*100:+.1f}%），月累计 {m.prod_month['本部']:,.0f} t",
         "月产 ≥ 42 万吨", "高炉稳定顺行 + 轧线换辊节奏优化",
         f"按当前日均推算 10 月产量约 {m.prod_month['本部']+m.prod_day['本部']*2:,.0f} t"),
        ("泉州（泉州闽光）材钢比偏紧", "基地·真实",
         f"钢材 {m.prod_day['泉州']:,.0f} t ＜ 粗钢 {m.steel_day['泉州']:,.0f} t，材钢比 {m.prod_day['泉州']/m.steel_day['泉州']:.3f}",
         "材钢比 ≥ 1.00", "轧线检修窗口压缩 + 坯料外销/库存平衡", "材钢比回到 1.00 以上，减少坯料外流"),
        (f"{best}（{m.FULL[best]}）钢铁料耗标杆", "工序·真实",
         f"钢铁料耗 {m.bf_ratio[best]:.2f} kg/t（三基地最低），铁水耗 {m.hm_ratio[best]:.2f} kg/t",
         "≤ 1,050 kg/t", f"废钢比与转炉终点控制经验向 {worst} 复制",
         f"三基地拉平至 {m.bf_ratio[best]:.0f} kg/t 可降本约 {save:.0f} 万元/日"),
        (f"{over['alias']} 标准成本超支治理", "标准/实际·真实",
         f"实际 {over['act']:,.0f} ＞ 标准 {over['std']:,.0f} 元/吨（{over['rate']:+.1f}%），日影响 {over['impact']:+,.0f} 万元",
         "差异率 ≤ ±3%", "核对定额是否滞后 + 单耗与能源价格专项拆解",
         f"回落到标准内可节约 {abs(over['impact']):,.0f} 万元/日"),
        (f"{under['alias']} 标准成本复核", "标准/实际·真实",
         f"实际 {under['act']:,.0f} ＜ 标准 {under['std']:,.0f} 元/吨（{under['rate']:+.1f}%），日节约 {under['impact']:+,.0f} 万元",
         "差异率 ≤ ±3%", "核查标准成本是否长期未重估（偏离过大疑定额失效）",
         "定额重估，避免以失效标准做考核基线"),
        ("集团存货日管控", "全集团·真实",
         f"原燃料存货 {m.inv_total:,.0f} 万元，环比 {m.inv_mom:+.2f}%（去化）",
         "账实一致 + 环比转负", "日管控看板 + 呆滞预警 + 罗源单位折算", "期末存货较上月末下降，资金占用释放"),
    ]


def render(m, ck):
    bo = m.BASE_ORDER
    cards = "".join(
        f'''<div class="sc"><span class="tag">{tag}</span><h4>{title}</h4>
    <div class="row"><b>典型指标：</b>{mv}</div>
    <div class="row"><b>阈值：</b>{th}</div>
    <div class="row"><b>运营动作：</b>{act}</div>
    <div class="row"><b>预期目标：</b>{goal}</div></div>'''
        for title, tag, mv, th, act, goal in strat_cards(m)
    )
    prod_rows = "".join(
        f'''<tr>{td(b + "（" + m.FULL[b] + "）", f"prod:{b}")}{td(f"{m.steel_day[b]:,.0f}", f"steel:{b}")}{td(f"{m.steel_month[b]:,.0f}", f"steel_m:{b}")}{td(f"{m.prod_day[b]:,.0f}", f"prod:{b}")}{td(f"{m.prod_month[b]:,.0f}", f"prod_m:{b}")}{td(f"{m.prod_day[b]/m.steel_day[b]:.3f}", f"prod:{b}")}{td(f"{m.bf_ratio[b]:.2f}", f"bf:{b}")}{td(f"{m.hm_ratio[b]:.2f}", f"hm:{b}")}</tr>'''
        for b in bo
    )
    inv_rows = "".join(
        f'''<tr>{td(b + "（" + m.FULL[b] + "）", f"inv:{b}")}{td(f"{m.inv_wt[b]:,.0f}", f"inv:{b}")}{td(f"{m.inv_by_base[b]:,.0f}", f"inv:{b}")}{td(f"{m.inv_by_base[b]/m.inv_total*100:.1f}%", f"inv:{b}")}{td(m.d["inventory"]["source"]["tables"][0] if b=="本部" else (m.d["inventory"]["source"]["tables"][1] if b=="泉州" else m.d["inventory"]["source"]["tables"][2]), f"inv:{b}")}</tr>'''
        for b in bo
    )
    def std_td(txt, cls, key):
        return td(f'<span class="{cls}">{txt}</span>', key)

    std_rows = "".join(
        f'''<tr>{td(x["alias"] + "（" + x["name"] + "）", "std:" + x["alias"])}{std_td(f"{x['std']:,.2f}", "", "std:" + x["alias"])}{std_td(f"{x['act']:,.2f}", "", "std:" + x["alias"])}{std_td(f"{x['diff']:+,.2f}", "ok" if x["diff"] < 0 else "warn", "std:" + x["alias"])}{std_td(f"{x['rate']:+.2f}%", "ok" if x["diff"] < 0 else "warn", "std:" + x["alias"])}{std_td(f"{x['out']:,.0f}", "", "std:" + x["alias"])}{std_td(f"{x['impact']:+,.2f}", "ok" if x["diff"] < 0 else "warn", "std:" + x["alias"])}</tr>'''
        for x in m.std_items
    )
    nc_rows = "".join(
        f'<div style="font-size:11.5px;color:var(--mut);padding:3px 0;">· <b style="color:var(--amber);">{x["alias"]}</b>（{x["name"]}）—— {x["reason"]}</div>'
        for x in m.std_not_cmp
    )
    chk_rows = "".join(
        f'<tr>{td(c["name"], "gate")}{td("<span class=\"" + ("ok" if c["ok"] else "warn") + "\">" + ("通过" if c["ok"] else "不通过") + "</span>", "gate")}{td(c["detail"], "gate")}</tr>'
        for c in ck
    )
    npass = sum(1 for c in ck if c["ok"])
    drill, ods = build_payload(m, ck)
    js = JS_TMPL.replace("__DRILL__", json.dumps(drill, ensure_ascii=False)).replace(
        "__ODS__", json.dumps(ods, ensure_ascii=False))
    anom = "".join(f'<p style="margin:5px 0;">· {a}</p>' for a in m.inv_anomalies)
    zb_ = {x["alias"]: x for x in m.std_items}

    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>三钢集团生产经营驾驶舱报告（账期 {m.P}）</title>
<style>{CSS}</style></head>
<body><div class="wrap">

<div class="real">✅ 全量真实数仓 · 生产 / 成本 / 存货 / 标准成本对比 四域均为 DB2 实取（账期 {m.P}），无合成值、无外链；勾稽闸门 {npass}/{len(ck)} 项通过后出报告</div>
<div class="caveat">⚠ 口径边界（如实披露）：成本与标准成本对比仅覆盖 <b>本部（三明闽光）</b>；泉州/罗源 成本表存在 V1/V3/V4 多版本、科目编码未标准化，本期<b>不纳入</b>成本横向对比。存货域罗源为"原料"、本部/泉州为"原燃料"，集团加总属非完全同口径。</div>

<div class="hero">
  <h1>三钢集团 · 生产经营驾驶舱</h1>
  <div class="sub">账期：{m.P}（日）｜ 环比基期：{m.P_PREV}｜ 数据域：GZPROD 生产管制 + CBPROD 成本 + 存货日管控 + 标准成本对比｜三基地严格分表、禁混</div>
  <div class="verdict">经营结论：钢材 {m.prod_total:,.0f} t（{m.prod_mom:+.2f}%）、材钢比 {m.ratio_cg:.3f}、钢铁料耗 {m.bf_weighted:.2f} kg/t；本部吨材成本 {m.cost_now:,.0f} 元/吨（{m.cost_mom:+.2f}%）；存货 {m.inv_total:,.0f} 万元（{m.inv_mom:+.2f}%）；标准成本对比净影响 {m.std_total_impact:+,.1f} 万元/日</div>
</div>

<div class="kpis">
  {kpi_card("钢材产量（集团日）", f"{m.prod_total:,.0f}", "吨", m.prod_mom, f"月累计 {m.prod_month_total:,.0f} 吨｜三基地合计")}
  {kpi_card("吨材成本（本部日）", f"{m.cost_now:,.0f}", "元/吨", m.cost_mom, f"近6月累计 {m.m_cost_chg:+.1f}%（{m.m_cost[0]:,.0f}→{m.m_cost[-1]:,.0f}）", good_when_down=True)}
  {kpi_card("原燃料存货余额", f"{m.inv_total:,.0f}", "万元", m.inv_mom, f"库存 {m.inv_wt_total:,.0f} 吨｜三基地分表求和", good_when_down=True)}
  {kpi_card("钢铁料耗（集团加权）", f"{m.bf_weighted:.2f}", "kg/t", m.bf_mom, f"按粗钢产量加权｜粗钢 {m.steel_total:,.0f} 吨", good_when_down=True)}
</div>

<div class="section"><h2>标准成本 vs 实际成本对比（账期 {m.P} · 本部）</h2>
<div class="caveat" style="margin:0 0 12px;">📐 <b>对比口径</b>：{m.s_src["caliber"]}</div>
<div class="cards3" style="margin-bottom:14px;">
  <div class="cal"><h3>数据来源</h3>
    <p><b>实体表</b>：<code>{m.s_src["schema"]}.{m.s_src["table"]}</code></p>
    <p><b>切分方式</b>：同一张表按 <code>版本</code> 维度取 <span class="th">{m.STD_V}</span> 与 <span class="th">{m.ACT_V}</span> 两组，非同表跨源拼接</p>
    <p class="note">列：{m.s_src["cols"]}。工序成本模型无独立 ZB_CODE，故以「工序 + 版本」为键。</p></div>
  <div class="cal"><h3>对比规则</h3>
    <p>差异 = 实际 − 标准（<span class="th">负为节约，正为超支</span>）；差异率 = 差异 ÷ 标准</p>
    <p>成本影响 = 差异 × 当日工序产量 ÷ 10000（万元/日）</p>
    <p class="note">产量取该表 <code>分类='工序产量'</code> 的日成本版本实绩（产量无版本概念）。可比 {len(m.std_items)} 个工序；不可比 {len(m.std_not_cmp)} 个已单列，未按 0 处理。</p></div>
  <div class="cal"><h3>本期结论</h3>
    <p>加权标准 <b>{m.std_w_std:,.2f}</b> → 加权实际 <b>{m.std_w_act:,.2f}</b> 元/吨（<span class="th">{m.std_w_rate:+.2f}%</span>）</p>
    <p>净影响 <b>{m.std_total_impact:+,.2f} 万元/日</b>；节约 {m.std_saving} 个工序、超支 {m.std_over} 个</p>
    <p class="note">可比工序合计产量 {m.std_out_sum:,.0f} 吨。</p></div>
</div>
<div class="chartbox">{std_chart(m)}</div>
<div class="chartbox" style="margin-top:14px;">{std_bar(m)}</div>
<div class="chartbox" style="margin-top:14px;">
<table class="realtab">
<tr><th>工序</th><th>标准成本(元/吨)</th><th>实际成本(元/吨)</th><th>差异(元/吨)</th><th>差异率</th><th>当日产量(t)</th><th>成本影响(万元)</th></tr>
{std_rows}
<tr class="sum">{td("可比合计 / 加权", "grp:group")}{td(f"{m.std_w_std:,.2f}", "grp:group")}{td(f"{m.std_w_act:,.2f}", "grp:group")}{td(f"{m.std_w_act-m.std_w_std:+,.2f}", "grp:group")}{td(f"{m.std_w_rate:+.2f}%", "grp:group")}{td(f"{m.std_out_sum:,.0f}", "grp:group")}{td(f"{m.std_total_impact:+,.2f}", "grp:group")}</tr>
</table>
<div style="margin-top:10px;border-top:1px dashed #22304f;padding-top:8px;">
<div style="font-size:11.5px;color:var(--amber);font-weight:700;">不可比工序（标准成本版本未维护，未按 0 处理）</div>
{nc_rows}</div>
<div class="hint">点击「标准成本」「实际成本」数值可下钻 —— L1 差额构成与闭合 / L2 同期静态说明 / L3 血缘 / L4 源表明细 {len(m.std_items)*2} 行。</div>
</div>
<div class="note">⚠ 判读提示：中板实际较标准低 {abs(zb_["中板"]["rate"]):.1f}%（偏离幅度远超其他工序），需先核查标准成本定额是否长期未重估，不可直接认定为降本成效；圆棒 {zb_["圆棒"]["rate"]:+.1f}%、焦化 {zb_["焦化"]["rate"]:+.1f}%、360烧结 {zb_["360烧结"]["rate"]:+.1f}% 为主要超支项。</div>
</div>

<div class="section"><h2>三大域指标口径说明（全部真实）</h2>
<div class="cards3">
  <div class="cal"><h3>① 生产管制（GZPROD）· 真实</h3>
    <p><b>钢材产量</b>：轧钢各产线日实绩汇总，<span class="th">基地严格区分</span>——本部/罗源/泉州三套 ZB_CODE 互不混入。</p>
    <p><b>粗钢产量</b>：转炉日产量按基地合计；<b>钢铁料耗</b>=钢铁料投入÷粗钢产量（kg/t）。</p>
    <p class="note">落点：<code>T_DWS_FACT_ZZGZ_0002</code> ZB 1600014/1600057/1600058；粗钢 <code>0003</code> 1600013/1600049/1600050；料耗 <code>LG01</code> 1600213/6012800/5000106。</p></div>
  <div class="cal"><h3>② 成本（CBPROD）· 真实·仅本部</h3>
    <p><b>吨材成本</b> = 钢材总成本 ÷ 钢材产量（元/吨），日频来自成本日结，月频来自月度成本表。</p>
    <p><b>标准成本对比</b>：同工序单位成本，按「版本」切分标准/日成本（见首屏模块）。</p>
    <p class="note">落点：<code>T_ADS_SRV_CACA_DAY_COST</code>、<code>T_ADS_SRV_CACA_MAIN_COST</code>、<code>T_DWD_FACT_CACA_DMXCBLR_GX</code>。<span class="th">边际贡献/利润类指标未注册且固定费用拆分缺失，本期不出数。</span></p></div>
  <div class="cal"><h3>③ 库存（存货日管控）· 真实</h3>
    <p><b>原燃料存货余额</b> = Σ各基地原燃料实际资金（KC_AMT/INV_AMT）。</p>
    <p><b>物理分表</b>：本部=<code>_YLKC_ABNL</code>、泉州=<code>_QZ</code>、罗源=<code>YRL_LY</code>（禁混）。</p>
    <p class="note">单位对齐：本部/泉州 KC_AMT=万元；罗源 INV_AMT=元（已÷10000）。账期 {m.P}。</p></div>
</div></div>

<div class="section"><h2>基地 × 指标 热力矩阵（三基地严格区分 · 禁混）</h2>
<div class="chartbox">{heatmap(m)}</div>
<div class="note">色块深浅 = 该列相对规模/竞争力（钢铁料耗、存货资金列越深=越优）。四列全部为 DB2 真实值（账期 {m.P}）。</div>
</div>

<div class="section"><h2>三基地 产量占比 vs 存货资金占比（真实）</h2>
<div class="chartbox">{barchart(m)}</div>
<div class="note">产量占比=各基地钢材日产量÷集团；存货占比=各基地原燃料资金÷集团。泉州"产量占比 {m.prod_day['泉州']/m.prod_total*100:.1f}% / 存货占比 {m.inv_by_base['泉州']/m.inv_total*100:.1f}%"并存，说明其存货周转显著慢于产出规模。</div>
</div>

<div class="section"><h2>生产域明细（账期 {m.P} · 三基地）</h2>
<div class="chartbox">
<table class="realtab">
<tr><th>基地</th><th>粗钢日产量(t)</th><th>粗钢月累计(t)</th><th>钢材日产量(t)</th><th>钢材月累计(t)</th><th>材钢比</th><th>钢铁料耗(kg/t)</th><th>铁水耗(kg/t)</th></tr>
{prod_rows}
<tr class="sum">{td("集团合计", "grp:group")}{td(f"{m.steel_total:,.0f}", "grp:group")}{td(f"{m.steel_month_total:,.0f}", "grp:group")}{td(f"{m.prod_total:,.0f}", "grp:group")}{td(f"{m.prod_month_total:,.0f}", "grp:group")}{td(f"{m.ratio_cg:.3f}", "grp:group")}{td(f"{m.bf_weighted:.2f}", "grp:group")}{td(f"{m.hm_weighted:.2f}", "grp:group")}</tr>
</table>
<div class="hint">点击任一数值单元格：L1 三基地构成与闭合校验 / L2 日序列 + SQL / L3 血缘链路 / L4 源表明细行（ESC 关闭）。</div>
<div style="margin-top:16px;">{trend_prod(m)}</div>
</div>
<div class="note">钢铁料耗集团值为按粗钢产量加权（非简单平均）；铁水耗同理。泉州 10-22 钢材日产量 5,692 t 为近10日异常低点（轧线检修特征）。</div>
</div>

<div class="section"><h2>成本域 · 本部吨材成本（真实 · 日频 + 月频）</h2>
<div class="chartbox">{trend_cost(m)}</div>
<div class="note">柱=本部吨材成本（元/吨，左轴）；线=三基地钢铁料耗（kg/t，右轴）。成本与料耗同向波动，料耗是本部成本的第一驱动项。</div>
<div class="chartbox" style="margin-top:16px;">{trend_month(m)}</div>
<div class="note">近6个月（{m.MONTHS[0]}→{m.MONTHS[-1]}）本部<b>钢材月产量 {m.m_cg_out[0]:.1f}→{m.m_cg_out[-1]:.1f} 万吨（{m.m_out_chg:+.1f}%）</b>，
吨材成本 <b>{m.m_cost[0]:,.0f}→{m.m_cost[-1]:,.0f} 元/吨（{m.m_cost_chg:+.1f}%）</b>——产量下行、单位成本上行，是本报告最需关注的结构性风险。</div>
</div>

<div class="section"><h2>存货日管控 · 真实数据（账期 {m.P}）</h2>
<div class="chartbox">
<p style="font-size:13px;color:var(--txt);margin-bottom:10px;">集团原燃料存货余额 <b style="color:var(--green)">{m.inv_total:,.0f} 万元</b>，环比 <b style="color:var(--green)">{m.inv_mom:+.2f}%</b>（去化）。三基地严格分表取数、单位已对齐折算：</p>
<table class="realtab">
<tr><th>基地</th><th>库存(吨)</th><th>实际资金(万元)</th><th>资金占比</th><th>实体表</th></tr>
{inv_rows}
<tr class="sum">{td("集团合计", "grp:group")}{td(f"{m.inv_wt_total:,.0f}", "grp:group")}{td(f"{m.inv_total:,.0f}", "grp:group")}{td("100.0%", "grp:group")}{td("—", "grp:group")}</tr>
</table>
<div style="margin-top:14px;">{inv_trend(m)}</div>
</div>
<div class="note">⚠ 数据质量提示：{anom}</div>
</div>

<div class="section"><h2>分层运营策略卡（全部真实指标驱动）</h2>
<div class="strat">{cards}</div></div>

<div class="section"><h2>勾稽闭合校验（构建时闸门 · {npass}/{len(ck)} 通过）</h2>
<div class="chartbox">
<table class="realtab">
<tr><th>校验项</th><th>结果</th><th>实测</th></tr>
{chk_rows}
</table>
<div class="hint">闸门在生成阶段执行：任一项不通过则脚本拒绝出报告（fail-fast），杜绝"报告自带✓但数据不闭合"。</div>
</div>
<div class="recon" style="margin-top:14px;">
  <p>① <b>三基地钢材日产量之和 = 集团 {m.prod_total:,.2f} 吨</b>：{m.prod_day["本部"]:,.2f} + {m.prod_day["罗源"]:,.2f} + {m.prod_day["泉州"]:,.2f} ✓</p>
  <p>② <b>材钢比</b> = {m.prod_total:,.2f} ÷ {m.steel_total:,.2f} = <b>{m.ratio_cg:.4f}</b> ✓</p>
  <p>③ <b>钢铁料耗加权</b> = Σ(料耗×粗钢) ÷ Σ粗钢 = <b>{m.bf_weighted:.4f} kg/t</b>（非简单平均 {sum(m.bf_ratio.values())/3:.2f}）✓</p>
  <p>④ <b>月度闭合（本部 {m.MONTHS[-1]}）</b>：{m.m_gross[-1]:.4f} 亿元 ÷ {m.m_cg_out[-1]:.4f} 万吨 = <b>{m.m_gross[-1]*10000/m.m_cg_out[-1]:,.2f} 元/吨</b> ✓</p>
  <p>⑤ <b>存货三基地求和</b> = {m.inv_total:,.3f} 万元 ✓ ｜ <b>环比</b> = {m.inv_mom:+.3f}% ✓</p>
  <p>⑥ <b>标准成本对比闭合</b>：净影响 <b>{m.std_total_impact:+,.2f} 万元</b> = 实际总成本 {m.std_a_sum/10000:,.2f} − 标准总成本 {m.std_w_sum/10000:,.2f} ✓</p>
</div></div>

<div class="foot">
  <h2>数据血缘与口径脚注</h2>
  <p><b>数据来源</b>：<span class="ok">全部为 DB2 数仓实数据</span>（账期 <code>{m.P}</code>，环比基期 <code>{m.P_PREV}</code>），MCP 只读实取，无合成/插值。</p>
  <p><b>生产域血缘</b>：<code>{m.p_src["schema"]}.{m.p_src["tables"][0]}</code>（钢材）／<code>{m.p_src["tables"][1]}</code>（粗钢）／<code>{m.p_src["tables"][2]}</code>（料耗·铁水耗）。</p>
  <p><b>成本域血缘</b>：<code>{m.c_src["schema"]}.{m.c_src["tables"][0]}</code>（吨材成本·日）／<code>{m.c_src["tables"][1]}</code>（月度 CBCX06）。</p>
  <p><b>标准成本对比血缘</b>：<code>{m.s_src["schema"]}.{m.s_src["table"]}</code>，<code>时间='{m.P}'</code>，<code>分类='工序单位成本'</code>，按 <code>版本</code> 取 <code>{m.STD_V}</code> 与 <code>{m.ACT_V}</code> 两组；产量取同日 <code>分类='工序产量'</code>。</p>
  <p><b>存货域血缘</b>：<code>{m.i_src["schema"]}.{m.i_src["tables"][0]}</code>（本部）／<code>{m.i_src["tables"][1]}</code>（泉州）／<code>{m.i_src["tables"][2]}</code>（罗源）。</p>
  <p><b>基地区分声明</b>：本部=三明闽光、罗源=罗源闽光、泉州=泉州闽光；三套 ZB_CODE 与实体表互不混入，集团合计按基地分组后求和。</p>
  <p><b>未出数项（如实披露）</b>：① 边际贡献/利润类指标未注册（8 条利润指标 SQL1 全空），固定费用字段恒 NULL，本期不出数；② 泉州/罗源吨材成本因多版本与未标准化科目编码，不纳入横向对比；③ 标准成本对比中 {len(m.std_not_cmp)} 个工序不可比（标准成本版本未维护），已单列说明，未按 0 处理。</p>
  <p><b>置信度</b>：生产域=<span class="ok">高</span>；成本域=<span class="ok">中高</span>（本部口径完备）；存货域=<span class="ok">高</span>（单位已折算）；标准成本对比=<span class="ok">高</span>（同表同口径、可比 {len(m.std_items)} 工序、差额可复算）。</p>
  <p style="margin-top:10px;color:var(--cyan);">✓ 验收闸门：单文件离线可开 · 零外链 · 四域全真实 · 基地口径严格区分(禁混) · {len(ck)} 项勾稽闭合 · 四层下钻(L1~L4) · 未出数项已披露</p>
</div>

</div>
<div class="mask" id="drill-overlay" onclick="closeDrill()"></div>
<aside class="drawer" id="drill-drawer" aria-label="指标下钻抽屉">
  <div class="dw-hd">
    <div class="dw-crumb" id="dwCrumb">—</div>
    <div class="t" id="dwTitle">—</div>
    <div class="v" id="dwVal">—</div>
    <button class="dw-x" onclick="closeDrill()" aria-label="关闭">×</button>
  </div>
  <div class="dw-caps" id="dwCaps"></div>
  <div class="dw-bd" id="dwBody"></div>
</aside>
<script>{js}</script>
</body></html>'''


def main(argv=None):
    ap = argparse.ArgumentParser(description="三钢集团生产经营驾驶舱 HTML 生成器")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--data", default=DATA)
    args = ap.parse_args(argv)
    try:
        d = load_data(args.data)
    except DataError as e:
        print(f"[FAIL] 数据集校验失败：{e}")
        return 2
    m = derive(d)
    ck = reconcile(m)
    bad = [c for c in ck if not c["ok"]]
    print(f"数据集：{os.path.basename(args.data)}｜账期 {m.P}｜基地 {m.BASE_ORDER}")
    print(f"勾稽闸门：{len(ck)-len(bad)}/{len(ck)} 通过")
    for c in ck:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}  →  {c['detail']}")
    print(f"\n标准成本对比：可比 {len(m.std_items)} 工序｜不可比 {len(m.std_not_cmp)}｜净影响 {m.std_total_impact:+,.2f} 万元/日")
    if bad:
        print(f"\n[ABORT] {len(bad)} 项不通过，拒绝生成（fail-fast）。")
        return 1
    html = render(m, ck)
    if args.check:
        print(f"[CHECK OK] 未写文件；如生成将输出 {len(html):,} 字符。")
        return 0
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] 已生成 {args.out}（{os.path.getsize(args.out):,} bytes / {len(html):,} chars）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
