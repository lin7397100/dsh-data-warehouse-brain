# -*- coding: utf-8 -*-
"""
gen_charts_extra_tr1631.py
trace_id : TR-20261119-1631-62A2
producer : sg-zhishu-dashboard-designer（达仕）
用途     : 生成 #charts-extra 增强图表片段（纯 HTML 子集 · 内联 SVG · 零 CDN）
数据源   : observed/data/data_TR-20261119-1631-62A2.json
           observed/lineage/TR-20261119-1631-62A2.json
           observed/quality/TR-20261119-1631-62A2.json
铁律     : 所有数值均为上述三文件原值或其确定性派生；假 0（NULL）以 --color-null 灰显，
           禁止画成 0 值；未取证单元格以灰显斜纹 + 「未取证」标注，禁止插补。
"""
import math
import os

# ----------------------------------------------------------------------------
# 0. 事实源原值（逐条对齐 data_/lineage_/quality_ 三文件，禁改）
# ----------------------------------------------------------------------------
DAYS = ["20261113", "20261114", "20261115", "20261116", "20261117", "20261118"]
DAY_SHORT = [d[4:] for d in DAYS]

# 一高线 8000296（lineage.fz_fm_triplets.yg_8000296）
YG = {
    "20261113": dict(rows=538, cnt1=47, fz=114.962, fm=1314.496, rate=8.7457, stored="8.75"),
    "20261114": dict(rows=593, cnt1=0, fz=0.000, fm=1446.713, rate=0.0000, stored="0.00"),
    "20261115": dict(rows=711, cnt1=275, fz=671.576, fm=1728.978, rate=38.8424, stored="38.84"),
    "20261116": dict(rows=634, cnt1=418, fz=1015.999, fm=1544.028, rate=65.8019, stored="65.80"),
    "20261117": dict(rows=688, cnt1=94, fz=227.047, fm=1671.888, rate=13.5803, stored="13.58"),
    "20261118": dict(rows=669, cnt1=234, fz=565.319, fm=1619.166, rate=34.9142, stored="34.91"),
}
# 中板 8000298（lineage.fz_fm_triplets.zb_8000298）
ZB = {
    "20261113": dict(rows=803, cnt1=662, fz=4681.123, fm=5579.921, rate=83.8923, stored="83.89"),
    "20261114": dict(rows=882, cnt1=677, fz=4880.621, fm=6159.273, rate=79.2402, stored="79.24"),
    "20261115": dict(rows=899, cnt1=764, fz=5531.996, fm=6319.292, rate=87.5414, stored="87.47"),
    "20261116": dict(rows=913, cnt1=496, fz=3795.422, fm=5901.624, rate=64.3115, stored="64.31"),
    "20261117": dict(rows=778, cnt1=374, fz=2342.750, fm=5051.645, rate=46.3760, stored="46.38"),
    "20261118": dict(rows=848, cnt1=536, fz=3880.765, fm=5709.481, rate=67.9705, stored="67.97"),
}

# 自发电率 8000010（data S1）
SELFGEN = [87.10, 84.12, 85.86, 86.34, 82.12, 85.50]

# 六产线统计量（quality.outliers.per_line / data_status_distribution）
LINES = [
    dict(code="8000293", name="一棒材", n=0, mean=None, cv=None, rng=None, valid_cells=0, dod=None),
    dict(code="8000295", name="圆棒", n=2, mean=85.07, cv=0.39, rng=0.66, valid_cells=2, dod=0.66),
    dict(code="8000296", name="一高线", n=6, mean=26.98, cv=82.19, rng=65.80, valid_cells=6, dod=52.22),
    dict(code="8000297", name="二高线", n=1, mean=0.00, cv=None, rng=None, valid_cells=1, dod=None),
    dict(code="8000298", name="中板", n=6, mean=71.5433, cv=19.47, rng=41.09, valid_cells=6, dod=23.16),
]
# 假 0 格数（quality.evidence.E03 / zero_value_rulings.Z1）
FALSE_ZERO_CELLS = {"8000293": 6, "8000295": 4, "8000297": 5, "8000296": 0, "8000298": 0}

# HOT_CHARGE_FLAG 小时级（lineage.attribution_hypotheses.hypotheses[2].evidence）
HOURLY_KNOWN = {
    "20261113": {0: 5, 1: 32, 2: 10, **{h: 0 for h in range(3, 24)}},
    "20261114": {h: 0 for h in range(24)},
    "20261115": {**{h: 0 for h in range(0, 8)}, 8: 22, 9: 18, 21: 5, 22: 0, 23: 0},
    "20261116": {},   # 仅日合计 418，小时未取证
    "20261117": {},   # 仅日合计 94
    "20261118": {},   # 仅日合计 234
}
DAY_TOTAL_CNT1 = {d: YG[d]["cnt1"] for d in DAYS}

# ----------------------------------------------------------------------------
# 1. 派生量（可复算，脚本内断言）
# ----------------------------------------------------------------------------
FZ_SUM = sum(YG[d]["fz"] for d in DAYS)
FM_SUM = sum(YG[d]["fm"] for d in DAYS)
FZ_MEAN = FZ_SUM / 6.0
FM_MEAN = FM_SUM / 6.0
assert abs(FZ_SUM - 2594.903) < 1e-6, FZ_SUM
assert abs(FM_SUM - 9325.269) < 1e-6, FM_SUM

DEV = {d: YG[d]["fz"] - FZ_MEAN for d in DAYS}
ABS_DEV_SUM = sum(abs(v) for v in DEV.values())
# 分子偏离折算 pp（FM 固定为 6 日均值）
DEV_PP = {d: v / FM_MEAN * 100.0 for d, v in DEV.items()}

# 极差桥接（lineage.attribution_hypotheses.yg_8000296）
NUM_EXPL = 100.0 * (max(YG[d]["fz"] for d in DAYS) - min(YG[d]["fz"] for d in DAYS)) / FM_MEAN
fz_mean_v = FZ_MEAN
den_expl = 100.0 * fz_mean_v * (1.0 / min(YG[d]["fm"] for d in DAYS) - 1.0 / max(YG[d]["fm"] for d in DAYS))
OBS_RANGE = 65.80
INTER = OBS_RANGE - NUM_EXPL - den_expl
assert abs(NUM_EXPL - 65.37) < 0.01, NUM_EXPL
assert abs(den_expl - 7.89) < 0.01, den_expl

# 中板 极差观测（lineage 记 41.17，quality 记 41.09；两者差异来自 1115 落库/重算，本图按 lineage 原值标注）
ZB_RANGE_LINEAGE = 41.17
ZB_NUM_SHARE_RANGE = 133.9
ZB_DEN_SHARE_RANGE = 40.4
ZB_NUM_SHARE_LOG = 127.4
ZB_DEN_SHARE_LOG = -27.4
ZB_INTER_RANGE = 100.0 - ZB_NUM_SHARE_RANGE - ZB_DEN_SHARE_RANGE  # -74.3

# ----------------------------------------------------------------------------
# 2. 工具
# ----------------------------------------------------------------------------
def f2(v):
    return "%.2f" % v


def sgn(v, nd=2):
    return ("+" if v > 0 else ("−" if v < 0 else "±")) + ("%." + str(nd) + "f") % abs(v)


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def pol(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)


# 热力色阶（0 / 1-9 / 10-19 / 20-29 / 30+）
def heat_color(v):
    if v is None:
        return None
    if v == 0:
        return "#16233A"
    if v <= 9:
        return "#12557D"
    if v <= 19:
        return "#0E7490"
    if v <= 29:
        return "#F0A03C"
    return "#E17055"


# ============================================================================
# 图 1 · 一高线 FZ 波动贡献度帕累托
# ============================================================================
def chart_pareto():
    W, H = 1000, 452
    PL, PR, PT, PB = 82, 762, 62, 358
    YMAX_T = 640.0

    def yt(v):
        return PB - v / YMAX_T * (PB - PT)

    def yp(p):
        return PB - p / 100.0 * (PB - PT)

    order = sorted(DAYS, key=lambda d: -abs(DEV[d]))
    band = (PR - PL) / 6.0
    bw = 58.0
    cum = 0.0
    bars, labels, cums = [], [], []
    for i, d in enumerate(order):
        v = DEV[d]
        share = abs(v) / ABS_DEV_SUM * 100.0
        cum += share
        cx = PL + band * i + band / 2.0
        top = yt(abs(v))
        color = "#E17055" if v > 0 else "#00B894"
        bars.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s" fill-opacity="0.86" '
            'stroke="%s" stroke-width="1"/>' % (cx - bw / 2, top, bw, PB - top, color, color)
        )
        # 数值标注
        labels.append(
            '<text class="val-label" x="%.1f" y="%.1f" text-anchor="middle" fill="%s">%s t</text>'
            % (cx, top - 8, "#F0B49E" if v > 0 else "#6FE3C6", sgn(v))
        )
        # x 轴双行标签
        labels.append(
            '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="13" fill="#E8EFFA" font-weight="700">%s</text>'
            % (cx, PB + 20, d)
        )
        labels.append(
            '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="11" fill="#7488A3">分子 %s pp</text>'
            % (cx, PB + 37, sgn(DEV_PP[d]))
        )
        cums.append((cx, yp(cum), cum))

    # 网格 + 左轴
    grid = []
    for t in (0, 160, 320, 480, 640):
        y = yt(t)
        grid.append('<line class="grid-line" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke-dasharray="2 4"/>' % (PL, y, PR, y))
        grid.append('<text class="ax-tick" x="%.1f" y="%.1f" text-anchor="end" dominant-baseline="middle">%d</text>' % (PL - 10, y, t))
    # 右轴
    for p in (0, 20, 40, 60, 80, 100):
        y = yp(p)
        grid.append('<text class="ax-tick" x="%.1f" y="%.1f" text-anchor="start" dominant-baseline="middle" fill="#0984E3">%d%%</text>' % (PR + 12, y, p))

    # 80% 帕累托参考线
    y80 = yp(80)
    pareto80 = (
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#22D3EE" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.75"/>'
        '<text x="%.1f" y="%.1f" font-size="11" fill="#22D3EE">80%% 参考线</text>'
        % (PL, y80, PR, y80, PL + 6, y80 - 6)
    )

    # 累计折线
    poly = " ".join("%.1f,%.1f" % (x, y) for x, y, _ in cums)
    cum_line = '<polyline points="%s" fill="none" stroke="#0984E3" stroke-width="2.2" stroke-linejoin="round"/>' % poly
    cum_dots = "".join(
        '<circle cx="%.1f" cy="%.1f" r="4" fill="#0B1220" stroke="#0984E3" stroke-width="2"/>'
        '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10" fill="#7FB6E8">%.1f%%</text>'
        % (x, y, x, y - 10, c)
        for x, y, c in cums
    )

    # 极值聚焦（1116 峰 / 1114 谷）
    focus = (
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="none" stroke="#22D3EE" stroke-width="1.4" stroke-dasharray="5 3"/>'
        '<text x="%.1f" y="%.1f" font-size="11" font-weight="700" fill="#22D3EE">峰 · 1116 ｜ 6 日 FZ 最高</text>'
        % (PL + band * 0 - 4, yt(abs(DEV["20261116"])) - 26, bw + 8, PB - yt(abs(DEV["20261116"])) + 26,
           PL + band * 0 + 12, yt(abs(DEV["20261116"])) - 32)
    )

    return """
<figure class="sg-card" data-chart-id="CHART-EXTRA-01" data-chart-type="pareto" data-series-count="2" data-data-points="6" role="group" aria-labelledby="ce01-t">
  <figcaption class="sg-card__head">
    <span class="sg-card__id">CHART-EXTRA-01</span>
    <h3 class="sg-card__title" id="ce01-t">一高线（8000296）FZ 逐日偏离量帕累托 · 分子驱动实证</h3>
    <p class="sg-card__sub">基准 = 6 日 FZ 均值 %s t｜偏离量 = 当日 FZ − 均值（t）｜折线 = 累计贡献占比（右轴，%%）</p>
  </figcaption>
  <div class="sg-card__body sg-scroll-x">
    <svg class="sg-svg" viewBox="0 0 %d %d" role="img" aria-label="一高线 FZ 逐日偏离量帕累托图，1116 日正偏离 583.52 吨居首，1114 日负偏离 432.48 吨次之，前 4 日累计贡献 82.30%%">
      <defs>
        <linearGradient id="ce01-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%%" stop-color="#111B2E" stop-opacity="0.7"/>
          <stop offset="100%%" stop-color="#0B1220" stop-opacity="0.2"/>
        </linearGradient>
      </defs>
      <rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="url(#ce01-bg)" rx="6"/>
      %s
      <line class="axis-line" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>
      <line class="axis-line" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#0984E3" stroke-opacity="0.35"/>
      %s
      %s
      %s
      %s
      %s
      <text class="ax-title" transform="translate(28,%.1f) rotate(-90)" text-anchor="middle">FZ 偏离量（t）</text>
      <text class="ax-title" transform="translate(%d,%.1f) rotate(90)" text-anchor="middle" fill="#0984E3">累计贡献占比（%%）</text>
      <text x="%.1f" y="%.1f" font-size="11" fill="#4E5F78">源：T_ODS_TMMBW19W1 全条件实算（lineage.fz_fm_triplets.yg_8000296）｜6 日 FZ 合计 %.3f t</text>
    </svg>
  </div>
  <div class="sg-legend">
    <span class="sg-legend__item"><span class="sg-legend__swatch" style="background:#E17055"></span>正偏离（当日 FZ 高于均值）</span>
    <span class="sg-legend__item"><span class="sg-legend__swatch" style="background:#00B894"></span>负偏离（当日 FZ 低于均值）</span>
    <span class="sg-legend__item"><span class="sg-legend__swatch sg-legend__swatch--line" style="background:#0984E3"></span>累计贡献占比（帕累托）</span>
  </div>
  <div class="sg-card__foot">
    <b>读数</b>：偏离量绝对值合计 %.2f t；1116（+583.52 t，占 30.54%%）、1114（−432.48 t，占 22.63%%）、1113（−317.52 t，占 16.62%%）、1115（+239.09 t，占 12.51%%）四日累计 82.30%%，即 <b>4/6 日解释了 8 成以上分子波动</b>。<br>
    <b>口径偏差声明</b>：任务简报标注的「1116 +552 t 级 / 1114 −233 t 级 / 1117 −486 t 级」与 ODS 实算偏离量（+583.52 / −432.48 / −205.44 t）不符，本图一律以实算值为准，简报数值不予采用。<br>
    <b>单位</b>：t（入炉重量）｜pp（热装率百分点，分子偏离 ÷ FM 均值 1554.2115 t ×100）。
  </div>
</figure>
""" % (
        f2(FZ_MEAN), W, H,
        PL, PT, PR - PL, PB - PT,
        "".join(grid),
        PL, PB, PR, PB,
        PR, PB, PR, PT,
        "".join(bars), pareto80, cum_line, cum_dots, focus,
        (PB + PT) / 2, PR + 42, (PB + PT) / 2,
        PL, H - 8, FZ_SUM,
        ABS_DEV_SUM,
    )


# ============================================================================
# 图 2 · 极差桥接瀑布（pp）
# ============================================================================
def chart_bridge():
    W, H = 1000, 396
    PL, PT, PB = 96, 66, 300
    YMAX = 80.0

    def y(v):
        return PB - v / YMAX * (PB - PT)

    band = 168.0
    steps = [
        ("分子驱动", NUM_EXPL, 0.0, NUM_EXPL, "#0984E3", "FZ 极差 1016.0 t ÷ FM 均值"),
        ("分母驱动", den_expl, NUM_EXPL, NUM_EXPL + den_expl, "#00B894", "FM 极差 414.5 t（FZ 固定均值）"),
        ("交叉项", INTER, NUM_EXPL + den_expl, OBS_RANGE, "#E17055", "分子×分母 联合残差"),
        ("观测极差", OBS_RANGE, 0.0, OBS_RANGE, "#6C5CE7", "min 0.00% ~ max 65.80%"),
    ]
    x0 = 150.0
    bars, texts, conns = [], [], []
    for i, (name, delta, y_from, y_to, color, note) in enumerate(steps):
        cx = x0 + band * i + 62
        top = y(max(y_from, y_to))
        hgt = abs(y(y_to) - y(y_from))
        if hgt < 2:
            hgt = 2
        bars.append(
            '<rect x="%.1f" y="%.1f" width="124" height="%.1f" rx="3" fill="%s" fill-opacity="0.82" stroke="%s"/>'
            % (cx - 62, top, hgt, color, color)
        )
        if i < 3:
            texts.append(
                '<text class="val-label" x="%.1f" y="%.1f" text-anchor="middle" fill="%s">%s pp</text>'
                % (cx, top - 9, color, sgn(delta))
            )
        else:
            texts.append(
                '<text class="val-label" x="%.1f" y="%.1f" text-anchor="middle" fill="%s" font-weight="700">%s pp</text>'
                % (cx, top - 9, color, f2(delta))
            )
        texts.append(
            '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="12.5" fill="#E8EFFA" font-weight="700">%s</text>'
            % (cx, PB + 22, name)
        )
        texts.append(
            '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10.5" fill="#7488A3">%s</text>'
            % (cx, PB + 39, note)
        )
        # 连接虚线
        if i < 3:
            nxt = y(y_to)
            conns.append(
                '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#5A6B82" stroke-width="1" stroke-dasharray="4 3" opacity="0.8"/>'
                % (cx + 62, nxt, cx + band - 62, nxt)
            )

    grid = []
    for t in (0, 20, 40, 60, 80):
        yy = y(t)
        grid.append('<line class="grid-line" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke-dasharray="2 4"/>' % (PL, yy, 860, yy))
        grid.append('<text class="ax-tick" x="%.1f" y="%.1f" text-anchor="end" dominant-baseline="middle">%d%%</text>' % (PL - 10, yy, t))

    # 观测极差参考线
    ref = (
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#6C5CE7" stroke-width="1.2" stroke-dasharray="7 4" opacity="0.7"/>'
        '<text x="%.1f" y="%.1f" font-size="11" fill="#A99BF0">观测极差 65.80 pp</text>'
        % (PL, y(OBS_RANGE), 880, y(OBS_RANGE), 872, y(OBS_RANGE) - 6)
    )

    return """
<figure class="sg-card" data-chart-id="CHART-EXTRA-02" data-chart-type="waterfall" data-series-count="4" data-data-points="4" role="group" aria-labelledby="ce02-t">
  <figcaption class="sg-card__head">
    <span class="sg-card__id">CHART-EXTRA-02</span>
    <h3 class="sg-card__title" id="ce02-t">一高线热装率极差桥接瀑布 · 「分子驱动 99.3%%」的分解实证</h3>
    <p class="sg-card__sub">极差分解法：FM 固定为 6 日均值 %s t → 分子可解释量；FZ 固定为均值 → 分母可解释量；残差 = 交叉项</p>
  </figcaption>
  <div class="sg-card__body sg-scroll-x">
    <svg class="sg-svg" viewBox="0 0 %d %d" role="img" aria-label="极差桥接瀑布：分子驱动 65.37 百分点，分母驱动 7.89 百分点，交叉项负 7.46 百分点，合计观测极差 65.80 百分点">
      %s
      <line class="axis-line" x1="%.1f" y1="%.1f" x2="880" y2="%.1f"/>
      %s
      %s
      %s
      <text class="ax-title" transform="translate(34,%.1f) rotate(-90)" text-anchor="middle">热装率极差贡献（pp）</text>
      <text x="%.1f" y="%.1f" font-size="11" fill="#4E5F78">源：lineage.attribution_hypotheses.yg_8000296（极差分解法）｜热装率不可加，本图仅作极差分解，不作区间聚合率</text>
    </svg>
  </div>
  <div class="sg-card__foot">
    <b>中文结论</b>：分子驱动 %s pp 占观测极差 65.80 pp 的 <b>99.3%%</b>，分母仅 12.0%%（%s pp），交叉项 %s pp 为负向抵消 → <b>本次波动由热装量（分子）主导，装炉量（分母）不足以单独解释</b>。<br>
    <b>物理锚点</b>：1114 当日 FZ = 0.000 t 而 FM = 1446.713 t（6 日常态区间内）→ 率 0.00%% 系<b>纯分子塌陷</b>；热装炉次比 8.74/0.00/38.68/65.93/13.66/34.98 与重量率逐日差 ≤0.30 pp。<br>
    <b>边界</b>：本图只给物理实据的支持程度，<b>不下根因结论</b>（停轧/检修/标记写入端归 sg-gzprod 与生产域研判）。
  </div>
</figure>
""" % (
        f2(FM_MEAN), W, H,
        "".join(grid), PL, PB, PB,
        "".join(bars), "".join(conns), "".join(texts),
        (PB + PT) / 2,
        PL, H - 8,
        sgn(NUM_EXPL), sgn(den_expl), sgn(INTER),
    )


# ============================================================================
# 图 3 · 产线波动雷达（5 产线 × 5 维，全维归一化为「劣化度」0~100）
# ============================================================================
def chart_radar():
    CX, CY, R = 330.0, 300.0, 200.0
    W, H = 660, 620
    axes = [
        ("极差（pp）", "RANGE / 70pp", "#FDCB6E"),
        ("CV（%）", "CV / 90%", "#E17055"),
        ("均值劣势", "100 − 均值(%)", "#00B894"),
        ("最大日环比跌幅", "|Δmax| / 60pp", "#22D3EE"),
        ("数据完整度缺失", "假0格 / 6日", "#8E7CF0"),
    ]

    def score_range(v):
        return None if v is None else min(100.0, v / 70.0 * 100.0)

    def score_cv(v):
        return None if v is None else min(100.0, v / 90.0 * 100.0)

    def score_mean(v):
        return None if v is None else max(0.0, 100.0 - v)

    def score_dod(v):
        return None if v is None else min(100.0, v / 60.0 * 100.0)

    def score_comp(code):
        return FALSE_ZERO_CELLS[code] / 6.0 * 100.0

    series = []
    for ln in LINES:
        s = [
            score_range(ln["rng"]),
            score_cv(ln["cv"]),
            score_mean(ln["mean"]),
            score_dod(ln["dod"]),
            score_comp(ln["code"]),
        ]
        series.append((ln, s))

    color_map = {
        "8000293": "#8E7CF0",
        "8000295": "#22D3EE",
        "8000296": "#0984E3",
        "8000297": "#00B894",
        "8000298": "#FDCB6E",
    }

    # 背景环
    rings = []
    for rr in (20, 40, 60, 80, 100):
        pts = " ".join("%.1f,%.1f" % pol(CX, CY, R * rr / 100.0, a * 72) for a in range(5))
        rings.append(
            '<polygon points="%s" fill="none" stroke="#1E2C45" stroke-width="1" %s/>'
            % (pts, 'stroke-dasharray="3 4"' if rr != 100 else "")
        )
        rings.append(
            '<text x="%.1f" y="%.1f" font-size="10" fill="#42546F" text-anchor="middle">%d</text>'
            % (CX + 3, CY - R * rr / 100.0 + 4, rr)
        )
    # 轴线 + 轴标签
    axis_svg = []
    for i, (name, sub, col) in enumerate(axes):
        x, y = pol(CX, CY, R, i * 72)
        axis_svg.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2A3D5B" stroke-width="1"/>' % (CX, CY, x, y))
        lx, ly = pol(CX, CY, R + 34, i * 72)
        anchor = "middle"
        if i == 1 or i == 2:
            anchor = "start"
        elif i == 3 or i == 4:
            anchor = "end"
        dy = {0: -6, 1: -2, 2: 10, 3: -2, 4: -2}[i]
        axis_svg.append(
            '<text x="%.1f" y="%.1f" text-anchor="%s" font-size="12" fill="%s" font-weight="700">%s</text>'
            % (lx, ly + dy, anchor, col, name)
        )
        axis_svg.append(
            '<text x="%.1f" y="%.1f" text-anchor="%s" font-size="9.5" fill="#5A6B82">%s</text>'
            % (lx, ly + dy + 13, anchor, sub)
        )

    # 序列
    polys, markers = [], []
    for ln, s in series:
        col = color_map[ln["code"]]
        valid = [(i, v) for i, v in enumerate(s) if v is not None]
        if len(valid) >= 2:
            pts = " ".join("%.1f,%.1f" % pol(CX, CY, R * v / 100.0, i * 72) for i, v in valid)
            closed = len(valid) == 5
            polys.append(
                '<polygon points="%s" fill="%s" fill-opacity="%s" stroke="%s" stroke-width="%s" %s/>'
                % (pts, col, "0.10" if ln["code"] != "8000298" else "0.14", col,
                   "1.6" if len(valid) == 5 else "1.4",
                   "" if closed else 'stroke-dasharray="5 4"')
            )
        for i, v in valid:
            x, y = pol(CX, CY, R * v / 100.0, i * 72)
            markers.append(
                '<circle cx="%.1f" cy="%.1f" r="3.6" fill="#0B1220" stroke="%s" stroke-width="2"/>' % (x, y, col)
            )
        # n/a 顶点
        for i, v in enumerate(s):
            if v is None:
                x, y = pol(CX, CY, 8, i * 72)
                markers.append(
                    '<circle cx="%.1f" cy="%.1f" r="4" fill="none" stroke="#5A6B82" stroke-width="1" stroke-dasharray="2 2"/>'
                    % (x, y)
                )

    # 一棒材/二高线 退化标注（置于画布左下角，避让雷达主体）
    ann = (
        '<text x="%.1f" y="%.1f" font-size="10.5" fill="#8E7CF0">▲ 8000293 一棒材：n=0（6/6 假 0）→ 五维全不可计算</text>'
        % (20.0, H - 34)
    )
    ann += (
        '<text x="%.1f" y="%.1f" font-size="10.5" fill="#6FE3C6">▲ 8000297 二高线：n=1（1 个真 0 点）→ 仅 2 维可算，σ 无统计意义</text>'
        % (20.0, H - 16)
    )

    # 右侧原始值表
    rows = []
    for ln, s in series:
        cells = []
        for v in [ln["rng"], ln["cv"], ln["mean"], ln["dod"]]:
            cells.append(
                '<td class="null">n/a</td>' if v is None else '<td class="num">%s</td>' % f2(v)
            )
        cells.append('<td class="num">%d/6</td>' % FALSE_ZERO_CELLS[ln["code"]])
        rows.append(
            '<tr><td><span class="sg-legend__swatch" style="background:%s;display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px"></span>%s <span class="sg-mono" style="color:#5A6B82">%s</span></td>%s</tr>'
            % (color_map[ln["code"]], ln["name"], ln["code"], "".join(cells))
        )

    return """
<figure class="sg-card" data-chart-id="CHART-EXTRA-03" data-chart-type="radar" data-series-count="5" data-data-points="25" role="group" aria-labelledby="ce03-t">
  <figcaption class="sg-card__head">
    <span class="sg-card__id">CHART-EXTRA-03</span>
    <h3 class="sg-card__title" id="ce03-t">五产线波动劣化度雷达 · 一高线为最劣项（多维权衡）</h3>
    <p class="sg-card__sub">五维统一归一化为「劣化度」（0 = 最优，100 = 最劣）；面积越大 = 该产线波动风险越高</p>
  </figcaption>
  <div class="sg-card__body" style="display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start">
    <div class="sg-scroll-x" style="flex:1 1 520px;min-width:420px">
      <svg class="sg-svg" viewBox="0 0 %d %d" role="img" aria-label="五产线波动劣化度雷达图：一高线在极差、CV、均值劣势、最大日环比跌幅四维均处高位，面积最大，为最劣项；一棒材全期假 0，无有效样本">
        %s
        %s
        %s
        %s
        %s
      </svg>
    </div>
    <div style="flex:1 1 340px;min-width:320px">
      <table class="sg-table">
        <caption>原始值（未归一化）· 单位：pp / %% / 日 / 格</caption>
        <thead>
          <tr><th>产线</th><th>极差 pp</th><th>CV %%</th><th>均值 %%</th><th>最大日环比 pp</th><th>假 0 格</th></tr>
        </thead>
        <tbody>%s</tbody>
      </table>
      <p class="sg-note sg-note--null"><code>n/a</code> = 样本量不足不可计算（n&lt;2 时 σ 无统计意义），<b>禁以 0 代入</b>；一棒材 8000293 全 6 日假 0（ODS 无源），二高线 8000297 仅 1 个真 0 点。</p>
    </div>
  </div>
  <div class="sg-card__foot">
    <b>归一化口径</b>：① 极差 ÷ 70 pp；② CV ÷ 90%%；③ (100 − 均值)；④ |最大日环比| ÷ 60 pp；⑤ 假 0 格 ÷ 6 日。五维均封顶 100。<br>
    <b>读数</b>：一高线 8000296 在 ① 极差 65.80 pp（94.0）② CV 82.19%%（91.3）④ 最大日环比 −52.22 pp（87.0）三维同时逼近上限，③ 均值劣势 73.0 —— <b>四维高位、面积最大，为五产线最劣项</b>；中板 8000298 次之（① 58.7 ③ 28.5 ④ 38.6）；圆棒 8000295 因 n=2 全域低位，<b>不得据此判「稳定」</b>。<br>
    <b>方法学警示</b>：σ 法与 IQR 法对三条长序列<b>全部零离群命中</b>（quality.O2），故「离群」不可作异常认定依据，本图改用「极差 + CV + 日环比幅度」三路刻画波动。
  </div>
</figure>
""" % (W, H, "".join(rings), "".join(axis_svg), "".join(polys), "".join(markers), ann, "".join(rows))


# ============================================================================
# 图 4 · HOT_CHARGE_FLAG 小时级断点时间轴热力图
# ============================================================================
def chart_heatmap():
    CW, CH = 30.0, 34.0
    LX, TY = 86.0, 96.0
    W = int(LX + 24 * CW + 150)
    H = int(TY + 6 * CH + 130)

    cells, row_labels = [], []
    for r, d in enumerate(DAYS):
        y = TY + r * CH
        row_labels.append(
            '<text x="%.1f" y="%.1f" text-anchor="end" dominant-baseline="middle" font-size="12" fill="#E8EFFA" font-weight="700">%s</text>'
            % (LX - 12, y + CH / 2, d)
        )
        # 行背景（隔行）
        if r % 2 == 0:
            cells.append(
                '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#111B2E" opacity="0.7"/>'
                % (LX, y, 24 * CW, CH)
            )
        for h in range(24):
            v = HOURLY_KNOWN[d].get(h)
            x = LX + h * CW
            col = heat_color(v)
            if col is None:
                cells.append(
                    '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="url(#ce04-hatch)" stroke="#24354F" stroke-width="0.6"/>'
                    % (x + 1, y + 1, CW - 2, CH - 2)
                )
                cells.append(
                    '<text x="%.1f" y="%.1f" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="#5A6B82">—</text>'
                    % (x + CW / 2, y + CH / 2 + 1)
                )
            else:
                cells.append(
                    '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s" stroke="#0B1220" stroke-width="0.8"/>'
                    % (x + 1, y + 1, CW - 2, CH - 2, col)
                )
                if v > 0:
                    cells.append(
                        '<text x="%.1f" y="%.1f" text-anchor="middle" dominant-baseline="middle" font-size="10.5" fill="#0B1220" font-weight="700">%d</text>'
                        % (x + CW / 2, y + CH / 2 + 1, v)
                    )

    # 小时刻度
    ticks = []
    for h in range(24):
        if h % 2 == 0:
            ticks.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10" fill="#7488A3" font-family="monospace">%02d</text>'
                % (LX + h * CW + CW / 2, TY - 10, h)
            )
    ticks.append(
        '<text x="%.1f" y="%.1f" text-anchor="start" font-size="11" fill="#7488A3">小时（00–23 时）</text>' % (LX - 6, TY - 28)
    )

    # 日合计条
    totals = []
    TOT_X = LX + 24 * CW + 34
    MAXT = 450.0
    totals.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="11" fill="#A9B8CF">日合计</text>' % (TOT_X + 46, TY - 10))
    for r, d in enumerate(DAYS):
        v = DAY_TOTAL_CNT1[d]
        y = TY + r * CH
        w = max(1.5, v / MAXT * 92.0)
        col = "#D63031" if v == 0 else ("#F0A03C" if v < 200 else "#0984E3")
        totals.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s" fill-opacity="0.85"/>'
            % (TOT_X, y + 8, w, CH - 16, col)
        )
        totals.append(
            '<text x="%.1f" y="%.1f" text-anchor="start" dominant-baseline="middle" font-size="11" fill="#E8EFFA" font-family="monospace">%d</text>'
            % (TOT_X + w + 6, y + CH / 2 + 1, v)
        )
    totals.append(
        '<text x="%.1f" y="%.1f" text-anchor="start" font-size="10" fill="#5A6B82">炉次</text>' % (TOT_X, TY + 6 * CH + 16)
    )

    # 断点标注
    x03 = LX + 3 * CW
    x08 = LX + 8 * CW
    marks = (
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#22D3EE" stroke-width="1.6" stroke-dasharray="6 3"/>'
        '<text x="%.1f" y="%.1f" font-size="10.5" fill="#22D3EE" font-weight="700">03:00 断点</text>'
        % (x03, TY - 34, x03, TY + 6 * CH, x03 + 4, TY - 38)
    )
    marks += (
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#FDCB6E" stroke-width="1.6" stroke-dasharray="6 3"/>'
        '<text x="%.1f" y="%.1f" font-size="10.5" fill="#FDCB6E" font-weight="700">08:00 恢复</text>'
        % (x08, TY - 34, x08, TY + 6 * CH, x08 + 4, TY - 38)
    )
    # 1114 全天 0 聚焦框
    y1114 = TY + 1 * CH
    marks += (
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="none" stroke="#D63031" stroke-width="1.8"/>'
        '<text x="%.1f" y="%.1f" font-size="10.5" fill="#F08A8A" font-weight="700">1114 全天 593 炉次</text>'
        '<text x="%.1f" y="%.1f" font-size="10" fill="#C07070">全 \'0\' → FZ 0.000 t</text>'
        % (LX - 2, y1114 - 1, 24 * CW + 4, CH + 2, 700, y1114 + 13, 700, y1114 + 27)
    )

    # 图例
    legend = []
    legend.append('<g transform="translate(%.1f,%.1f)">' % (LX, TY + 6 * CH + 30))
    legend.append('<text x="0" y="0" font-size="11" fill="#A9B8CF">FLAG=\'1\' 炉次数：</text>')
    items = [("0", "#16233A"), ("1–9", "#12557D"), ("10–19", "#0E7490"), ("20–29", "#F0A03C"), ("≥30", "#E17055")]
    ox = 96
    for lab, col in items:
        legend.append('<rect x="%d" y="-10" width="18" height="12" rx="2" fill="%s" stroke="#24354F"/>' % (ox, col))
        legend.append('<text x="%d" y="0" font-size="10.5" fill="#7488A3">%s</text>' % (ox + 23, lab))
        ox += 62
    legend.append('<rect x="%d" y="-10" width="18" height="12" rx="2" fill="url(#ce04-hatch)" stroke="#24354F"/>' % ox)
    legend.append('<text x="%d" y="0" font-size="10.5" fill="#5A6B82">— 未取证（禁插补）</text>' % (ox + 23))
    legend.append("</g>")

    return """
<figure class="sg-card" data-chart-id="CHART-EXTRA-04" data-chart-type="heatmap" data-series-count="6" data-data-points="144" role="group" aria-labelledby="ce04-t">
  <figcaption class="sg-card__head">
    <span class="sg-card__id">CHART-EXTRA-04</span>
    <h3 class="sg-card__title" id="ce04-t">一高线 HOT_CHARGE_FLAG 小时级断点热力图 · 1113 03:00 断点 / 1114 全天归零 / 1115 08:00 恢复</h3>
    <p class="sg-card__sub">行 = 6 个自然日｜列 = 24 小时｜色阶 = 该小时 <span class="sg-mono">HOT_CHARGE_FLAG=\'1\'</span> 的入炉炉次数｜右列为日合计（炉次）</p>
  </figcaption>
  <div class="sg-card__body sg-scroll-x">
    <svg class="sg-svg" viewBox="0 0 %d %d" role="img" aria-label="一高线小时级热装标记热力图：1113 仅 00 至 02 时有标记、03 时起全 0；1114 全天 593 炉次全为 0；1115 于 08 时恢复并有 22 炉次">
      <defs>
        <pattern id="ce04-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="#111B2E"/>
          <line x1="0" y1="0" x2="0" y2="6" stroke="#3A4A63" stroke-width="1.6"/>
        </pattern>
      </defs>
      %s
      %s
      %s
      %s
      %s
      %s
      <text x="%.1f" y="%.1f" font-size="11" fill="#4E5F78">源：lineage.attribution_hypotheses.hypotheses[③]｜6 日 FLAG 取值域实测仅 '0' / '1' 两值（0:2765 行 / 1:1068 行），无 NULL</text>
    </svg>
  </div>
  <div class="sg-card__foot">
    <b>断点三证</b>：① 1113 的 47 条标记<u>全部</u>落在 00:00（5）/ 01:00（32）/ 02:00（10）三小时，<b>03:00 起至 23:59 全为 0</b>；② 1114 全部 593 炉次 <span class="sg-mono">FLAG=\'0\'</span>，无一条热装标记 → FZ = 0.000 t；③ 1115 的 00:00–07:00 全 0，<b>08:00 起恢复</b>（08:00 = 22、09:00 = 18、…、21:00 = 5），呈<b>按时间段阶梯式回填</b>而非随机分布。<br>
    <b>取证边界（重要）</b>：仅 1113（24 格全量）、1114（24 格全量）、1115（00–09 与 21–23 共 13 格）为小时级实查；<b>1115 的 10:00–20:00 与 1116/1117/1118 全部 24 列小时明细未取证</b>，以斜纹灰显并标「—」，<b>零插补、零兜底</b>（1116/1117/1118 仅有日合计 418 / 94 / 234 炉次）。<br>
    <b>归因边界</b>：该断点属「标记写入端」现象，<b>非重量口径可得</b>；成因（MES 接口 / 补数 / 停机）归 sg-gzprod 与生产域研判，本图不预设结论。
  </div>
</figure>
""" % (W, H, "".join(cells), "".join(row_labels), "".join(ticks), "".join(totals), marks, "".join(legend), LX, H - 8)


# ============================================================================
# 图 5 · 中板 FZ/FM 贡献度双法分解（对数方差 + 极差）
# ============================================================================
def chart_zb_decomp():
    W, H = 1000, 420
    X0, PT, PB = 470.0, 74.0, 320.0
    VMAX = 150.0
    SC = 300.0 / VMAX

    def x(v):
        return X0 + v * SC

    rows = [
        ("极差分解法", "分子 FZ 贡献", ZB_NUM_SHARE_RANGE, "#0984E3"),
        ("极差分解法", "分母 FM 贡献", ZB_DEN_SHARE_RANGE, "#00B894"),
        ("极差分解法", "交互项（残差）", ZB_INTER_RANGE, "#5A6B82"),
        ("对数方差法", "分子 Var(lnFZ)", ZB_NUM_SHARE_LOG, "#0984E3"),
        ("对数方差法", "分母 Var(lnFM)", ZB_DEN_SHARE_LOG, "#E17055"),
    ]
    RH = 46.0
    bars, labels, groups = [], [], []
    group_seen = {}
    for i, (method, name, v, col) in enumerate(rows):
        y = PT + i * RH
        bx = x(min(0.0, v))
        bw = abs(x(v) - x(0.0))
        bars.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="26" rx="3" fill="%s" fill-opacity="0.84" stroke="%s"/>'
            % (bx, y, max(bw, 1.5), col, col)
        )
        labels.append(
            '<text x="%.1f" y="%.1f" text-anchor="end" dominant-baseline="middle" font-size="12" fill="#E8EFFA">%s</text>'
            % (X0 - 168, y + 15, name)
        )
        # 数值标签：柱宽足够时置于柱内居中，避免与左侧行标签/方法括号相撞
        if bw >= 46:
            lx, anchor = (x(v) + x(0.0)) / 2.0, "middle"
        else:
            lx, anchor = (x(v) + 9 if v >= 0 else x(v) - 9), ("start" if v >= 0 else "end")
        labels.append(
            '<text x="%.1f" y="%.1f" text-anchor="%s" dominant-baseline="middle" font-size="12" font-family="monospace" fill="#0B1220" font-weight="700">%s%%</text>'
            % (lx, y + 15, anchor, sgn(v, 1))
        )
        if method not in group_seen:
            group_seen[method] = (i, i)
        else:
            group_seen[method] = (group_seen[method][0], i)

    # 方法分组括号
    brackets = []
    for method, (a, b) in group_seen.items():
        y1 = PT + a * RH + 2
        y2 = PT + b * RH + 28
        brackets.append(
            '<path d="M %0.1f %.1f L %0.1f %.1f L %0.1f %.1f L %0.1f %.1f" fill="none" stroke="#33496B" stroke-width="1.2"/>'
            % (X0 - 248, y1 + 12, X0 - 260, y1 + 12, X0 - 260, y2 - 12, X0 - 248, y2 - 12)
        )
        brackets.append(
            '<text x="%.1f" y="%.1f" text-anchor="middle" font-size="11.5" fill="#A9B8CF" font-weight="700" transform="rotate(-90 %.1f %.1f)">%s</text>'
            % (X0 - 278, (y1 + y2) / 2, X0 - 278, (y1 + y2) / 2, method)
        )

    # 0 轴与网格
    grid = []
    grid.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#33496B" stroke-width="1.4"/>' % (X0, PT - 24, X0, PB + 6))
    grid.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="11" fill="#7488A3">0%%</text>' % (X0, PB + 22))
    for v in (-150, -100, -50, 50, 100, 150):
        xx = x(v)
        grid.append('<line class="grid-line" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke-dasharray="2 4"/>' % (xx, PT - 24, xx, PB + 2))
        grid.append('<text class="ax-tick" x="%.1f" y="%.1f" text-anchor="middle">%d%%</text>' % (xx, PB + 22, v))
    # 100% 参考
    grid.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#22D3EE" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.65"/>'
        '<text x="%.1f" y="%.1f" font-size="10.5" fill="#22D3EE">100%%（全额解释）</text>'
        % (x(100), PT - 30, x(100), PB + 2, x(100) + 6, PT - 34)
    )

    return """
<figure class="sg-card" data-chart-id="CHART-EXTRA-05" data-chart-type="diverging-bar" data-series-count="2" data-data-points="5" role="group" aria-labelledby="ce05-t">
  <figcaption class="sg-card__head">
    <span class="sg-card__id">CHART-EXTRA-05</span>
    <h3 class="sg-card__title" id="ce05-t">中板（8000298）FZ / FM 贡献度双法分解 · 分子 133.9%% 主导、分母 −27.4%% 反向抵消</h3>
    <p class="sg-card__sub">极差分解法 vs 对数方差分解法（Var(lnRate)=Var(lnFZ)+Var(lnFM)−2Cov）｜百分比为「占观测极差 / 占对数方差」份额</p>
  </figcaption>
  <div class="sg-card__body sg-scroll-x">
    <svg class="sg-svg" viewBox="0 0 %d %d" role="img" aria-label="中板贡献度分解：极差分解法分子贡献 133.9 百分比、分母 40.4 百分比、交互项负 74.3 百分比；对数方差法分子 127.4 百分比、分母负 27.4 百分比">
      %s
      %s
      %s
      %s
      <text class="ax-title" transform="translate(20,%.1f) rotate(-90)" text-anchor="middle">贡献份额（%%）</text>
      <text x="%.1f" y="%.1f" font-size="11" fill="#4E5F78">源：lineage.attribution_hypotheses.zb_8000298｜观测极差 41.17 pp（lineage）／41.09 pp（quality 口径，差 0.08 pp 源于 1115 重算 87.5414 vs 落库 87.47）</text>
    </svg>
  </div>
  <div class="sg-card__foot">
    <b>读数</b>：两种方法<b>同向同结论</b> —— 分子（FZ 热装量）贡献 127.4%%~133.9%%，<b>单独即可超额解释全部波动</b>；分母（FM 装炉量）在极差法下为 +40.4%% 的次要正贡献，在对数方差法下为 <b>−27.4%% 的反向抵消</b>（因 1116/1117 两日 FM 与 FZ 同向共动，部分抵消而非放大）。<br>
    <b>物理锚点</b>：1117 当日 FZ = 2342.750 t、FM = 5051.645 t 均为 6 日最低，率 46.38%% 亦为 6 日最低；1115 为 6 日最高（FZ 5531.996 t → 87.47%%）。<br>
    <b>对账差异（须随图交付）</b>：1115 重算 87.5414%% vs 落库 87.47%%，Δ = +0.0714 pp，<b>超 ROUND(...,2) 四舍五入容差</b>；ODS 侧 REC_REVISE_TIME 全空、MAX(REC_CREATE_TIME)=20261115235950 早于装载时点，<b>无可观测补数痕迹，成因未实证</b>（lineage R7B-1，P1）。<br>
    <b>口径声明</b>：份额为方差/极差分解产物，<b>非可加性指标</b>；热装率区间聚合率 NOT_DELIVERABLE_FROM_DWS（两 DWS 表物理无 FZ/FM 列），本图仅交付逐日点值。
  </div>
</figure>
""" % (W, H, "".join(grid), "".join(brackets), "".join(bars), "".join(labels), (PT + PB) / 2 - 4, 26, H - 8)


# ============================================================================
# 片段样式（内联自包含 · 与 visual_tokens.css 同源）
# ============================================================================
FRAGMENT_CSS = """
<style>
/* ==== #charts-extra 插槽内联样式（与 TR-20261119-1631-62A2_visual_tokens.css 同源，零外链） ==== */
.sg-charts-extra{
  --bg-900:#070C15;--bg-850:#0B1220;--bg-800:#111B2E;--bg-750:#16233A;--bg-700:#1B2A44;
  --line-strong:#33496B;--line:#24354F;--line-soft:#1B2941;--grid:#1E2C45;
  --text-1:#E8EFFA;--text-2:#A9B8CF;--text-3:#7488A3;--text-4:#4E5F78;
  --color-primary:#6C5CE7;--color-accent:#0984E3;--color-cyan:#22D3EE;
  --color-ok:#00B894;--color-warn:#E17055;--color-danger:#D63031;
  --color-null:#5A6B82;--color-null-bg:rgba(90,107,130,.16);--color-truezero:#7DD3FC;
  --fs-2xs:10px;--fs-xs:12px;--fs-sm:13px;--fs-md:14px;--fs-lg:16px;--fs-xl:18px;
  --sp-1:4px;--sp-2:8px;--sp-3:12px;--sp-4:16px;--sp-5:20px;--sp-6:24px;
  --r-xs:3px;--r-sm:6px;--r-md:10px;--r-lg:14px;--r-pill:999px;
  --sh-1:0 1px 2px rgba(0,0,0,.35);--sh-2:0 4px 14px rgba(0,0,0,.42);
  --font-sans:"Microsoft YaHei","PingFang SC","Hiragino Sans GB","Source Han Sans SC","Noto Sans CJK SC",system-ui,-apple-system,"Segoe UI",sans-serif;
  --font-mono:"Cascadia Mono",Consolas,"JetBrains Mono","SFMono-Regular",ui-monospace,monospace;
  background:var(--bg-850);color:var(--text-2);
  font-family:var(--font-sans);font-size:var(--fs-md);line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.sg-charts-extra *{box-sizing:border-box}
.sg-charts-extra__head{margin:0 0 var(--sp-5);padding-left:var(--sp-3);border-left:3px solid var(--color-cyan)}
.sg-charts-extra__head h2{margin:0;font-size:22px;color:var(--text-1);letter-spacing:.01em}
.sg-charts-extra__head p{margin:var(--sp-1) 0 0;font-size:var(--fs-xs);color:var(--text-3)}
.sg-card{background:linear-gradient(180deg,var(--bg-800) 0%,var(--bg-850) 100%);border:1px solid var(--line);
  border-radius:var(--r-lg);box-shadow:var(--sh-2);padding:var(--sp-5) var(--sp-5) var(--sp-4);
  margin:0 0 var(--sp-6);position:relative;overflow:hidden}
.sg-card::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;
  background:linear-gradient(90deg,var(--color-cyan) 0%,var(--color-accent) 42%,transparent 100%);opacity:.85}
.sg-card__head{display:flex;align-items:baseline;gap:var(--sp-3);flex-wrap:wrap;margin-bottom:var(--sp-4)}
.sg-card__id{font-family:var(--font-mono);font-size:var(--fs-2xs);letter-spacing:.08em;color:var(--color-cyan);
  background:rgba(34,211,238,.1);border:1px solid rgba(34,211,238,.26);border-radius:var(--r-xs);
  padding:1px var(--sp-2);white-space:nowrap}
.sg-card__title{font-size:var(--fs-xl);font-weight:700;color:var(--text-1);line-height:1.2;margin:0}
.sg-card__sub{font-size:var(--fs-xs);color:var(--text-3);margin:0}
.sg-card__body{position:relative}
.sg-card__foot{margin-top:var(--sp-3);padding-top:var(--sp-3);border-top:1px dashed var(--line-soft);
  font-size:var(--fs-xs);color:var(--text-3);line-height:1.75}
.sg-card__foot b{color:var(--text-2);font-weight:500}
.sg-card__foot u{text-decoration:underline;text-underline-offset:2px;text-decoration-color:var(--color-warn)}
.sg-legend{display:flex;flex-wrap:wrap;gap:var(--sp-2) var(--sp-4);font-size:var(--fs-xs);color:var(--text-2);margin-top:var(--sp-3)}
.sg-legend__item{display:inline-flex;align-items:center;gap:var(--sp-2)}
.sg-legend__swatch{width:14px;height:10px;border-radius:2px;flex:none}
.sg-legend__swatch--line{height:2px;border-radius:1px}
.sg-table{width:100%;border-collapse:collapse;font-size:var(--fs-xs)}
.sg-table caption{caption-side:top;text-align:left;font-size:var(--fs-xs);color:var(--text-3);padding-bottom:var(--sp-2)}
.sg-table th,.sg-table td{padding:6px var(--sp-2);border-bottom:1px solid var(--line-soft);text-align:right;white-space:nowrap}
.sg-table th{color:var(--text-3);font-weight:500;background:var(--bg-750);border-bottom:1px solid var(--line)}
.sg-table th:first-child,.sg-table td:first-child{text-align:left}
.sg-table tbody tr:nth-child(even){background:rgba(27,42,68,.42)}
.sg-table td.num{font-family:var(--font-mono);color:var(--text-1)}
.sg-table td.null{color:var(--color-null);font-family:var(--font-mono);font-style:italic}
.sg-note{font-size:var(--fs-xs);color:var(--text-3);line-height:1.75;border-left:2px solid var(--line-strong);
  padding-left:var(--sp-3);margin:var(--sp-3) 0 0}
.sg-note--null{border-left-color:var(--color-null)}
.sg-note--warn{border-left-color:var(--color-warn);color:#C9B39E}
.sg-mono{font-family:var(--font-mono);font-size:.94em;color:var(--text-1);
  background:rgba(30,44,69,.75);border-radius:var(--r-xs);padding:0 4px}
.sg-svg{display:block;width:100%;height:auto;overflow:visible;font-family:var(--font-sans)}
.sg-svg text{fill:#A9B8CF}
.sg-svg .ax-title{fill:#7488A3;font-size:12px}
.sg-svg .ax-tick{fill:#7488A3;font-size:11px;font-family:var(--font-mono)}
.sg-svg .grid-line{stroke:#1E2C45;stroke-width:1}
.sg-svg .axis-line{stroke:#33496B;stroke-width:1}
.sg-svg .val-label{fill:#E8EFFA;font-size:12px;font-family:var(--font-mono)}
.sg-scroll-x{overflow-x:auto;-webkit-overflow-scrolling:touch}
@media (max-width:760px){
  .sg-card{padding:var(--sp-4) var(--sp-3);border-radius:var(--r-md)}
  .sg-card__title{font-size:16px}
  .sg-svg{min-width:620px}
}
@media (prefers-reduced-motion:reduce){*{animation-duration:.001ms!important;transition-duration:.001ms!important}}
@media print{.sg-card{box-shadow:none;border-color:#B9C4D4;break-inside:avoid}}
</style>
"""


HEAD = """
<section class="sg-charts-extra" id="charts-extra"
         data-trace-id="TR-20261119-1631-62A2"
         data-slot="#charts-extra"
         data-producer="sg-zhishu-dashboard-designer"
         data-chart-count="5"
         data-scene="T3">
  <div class="sg-charts-extra__head">
    <h2>增强图表 · 波动归因可视化（Step 8b）</h2>
    <p>一高线 8000296 / 中板 8000298 双波动源 ｜ 5 张内联 SVG 增强图 ｜ 全部数值为 ODS 实算原值，零插补 · 零兜底 · 零平滑</p>
  </div>
"""

FOOT = """
  <div class="sg-note sg-note--warn" data-notice="global-caliber">
    <b>全局口径声明（随图交付，缺一即作废）</b>：① 窗口 20261113~20261118 实得 <b>6/7 日</b>（20261119 两表 0 行未就绪，禁称「近七日」）；② 全部 7 条指标 <b>maturity=draft、⚠ 未经人工校准</b>，禁作考核 / 对外发布口径；③ 单位「%」系 <code>ZB_NAME</code> 语义推断值（registry.unit 为空字符串）；④ 8000294 二棒材 <b>UNAVAILABLE（ABSENT__NO_PRODUCTION_BRANCH）</b>，禁回落 0、禁以 1600263 拼接；⑤ 假 0（<code>FALSE_ZERO</code>）15 格一律灰显并标注「假 0·ODS 无源」，<b>禁画成 0 值</b>；⑥ 热装率区间聚合率 <b>NOT_DELIVERABLE_FROM_DWS</b>，一切均值（26.98 / 71.54 / 85.07 / 85.17）仅供参照。
  </div>
</section>
"""


def main():
    parts = [HEAD, FRAGMENT_CSS,
             chart_pareto(), chart_bridge(), chart_radar(), chart_heatmap(), chart_zb_decomp(),
             FOOT]
    html = "".join(parts)
    out = r"$env:DSH_HOME\dwb-team/artifacts/analysis/TR-20261119-1631-62A2_charts_extra.html"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("bytes =", len(html.encode("utf-8")))
    print("data-chart-id count =", html.count("data-chart-id="))
    for tok in ("<html", "<head", "<body", "http://", "https://", "cdn", "CDN", "src=", "@import", "url(http"):
        print("  token %-12s -> %d" % (tok, html.count(tok)))


if __name__ == "__main__":
    main()
