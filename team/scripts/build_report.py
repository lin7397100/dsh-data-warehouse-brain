#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_report.py — HTML 报告骨架生成器（从源头消灭 f-string 转义泄漏）

背景
----
2026-10-28 的 v2 报告因 Python f-string 拼接时 53 处 {{ }} 未还原，
导致业务 JS 语法崩溃、4 个图表全部空白。数据闸门全绿未能拦截。

本脚本强制采用「占位符替换」而非 f-string，物理上不可能产生 {{ 泄漏。

用法
----
1. 准备数据 JSON（结构与下面 DATA_SCHEMA 一致）
2. 运行：
   python build_report.py --data data.json --js report.js --out report.html \
                          --title "近7日钢铁料耗趋势" [--echarts assets/echarts.min.js]
3. 生成后自动调用 verify_report.js 做 J1/J2/J3 校验

目录约定
--------
- 业务 JS 写在独立的 .js 文件里（纯 JS，不受 Python 语法影响）
- HTML 骨架在 SKELETON 常量里，只用 @PLACEHOLDER@ 形式占位
- 替换用 str.replace()，不用 f-string、不用 .format()、不用 % 格式化

DATA_SCHEMA
-----------
{
  "title": "近7日钢铁料耗 · 铁水耗趋势分析",
  "subtitle": "三钢集团 · 生产管制域",
  "meta": [{"label":"统计区间","value":"2026-10-21 ~ 2026-10-27"}],
  "kpis": [{"label":"本部钢铁料耗","value":"1054.58","unit":"kg/t","delta":"+2.03"}],
  "dates": ["10-21", "..."],
  "series": {
    "steel": {"benbu": [1052.88], "yilian": [1056.03]},
    "iron":  {"benbu": [853.77]}
  },
  "colors": {"benbu": "#6C5CE7"},
  "labels": {"benbu": "本部合计"},
  "caliber": {"metrics": [...], "lineage": "..."},
  "issues": [{"level":"warn","text":"罗源分母塌陷"}]
}
"""

import argparse
import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# HTML 骨架：只用 @XXX@ 占位符，绝不含 { } 与 Python 格式化语法冲突
# ---------------------------------------------------------------------------
SKELETON = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>@TITLE@</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
     background:#f5f6fa;color:#2d3436;line-height:1.65;padding:20px}
.container{max-width:1440px;margin:0 auto}
.hero{background:linear-gradient(135deg,#6C5CE7 0%,#0984E3 100%);color:#fff;
      padding:30px 36px;border-radius:16px;margin-bottom:20px;box-shadow:0 8px 24px rgba(108,92,231,.25)}
.hero h1{font-size:26px;font-weight:700;margin-bottom:6px}
.hero .sub{font-size:14px;opacity:.92}
.hero .meta{margin-top:14px;display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px}
.hero .meta span{background:rgba(255,255,255,.2);padding:5px 13px;border-radius:18px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:13px;margin-bottom:20px}
.kpi{background:#fff;padding:17px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.06);border-left:4px solid #6C5CE7}
.kpi .label{font-size:12px;color:#636e72;margin-bottom:5px}
.kpi .value{font-size:23px;font-weight:700}
.kpi .unit{font-size:12px;color:#636e72;font-weight:400;margin-left:3px}
.kpi .delta{font-size:11px;margin-top:3px;color:#636e72}
.card{background:#fff;border-radius:12px;padding:22px;margin-bottom:18px;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.card h2{font-size:16.5px;font-weight:600;margin-bottom:15px;padding-bottom:11px;
         border-bottom:2px solid #f1f2f6;display:flex;align-items:center;gap:8px}
.card h2::before{content:'';width:4px;height:16px;background:#6C5CE7;border-radius:2px}
.chart{width:100%;height:370px}
.note{background:#fff9e6;border-left:4px solid #fdcb6e;padding:14px 18px;border-radius:8px;
      margin-bottom:18px;font-size:13px;color:#636e72}
.caliber{background:#f8f9fa;border-radius:8px;padding:15px;font-size:11.5px;
         font-family:Consolas,Monaco,monospace;line-height:1.85;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{background:#f8f9fa;padding:9px 7px;text-align:right;font-weight:600;border-bottom:2px solid #e9ecef}
th:first-child,td:first-child{text-align:left}
td{padding:8px 7px;text-align:right;border-bottom:1px solid #f1f2f6}
tbody tr:hover{background:#f8f9fa}
.cell{cursor:pointer;color:#0984E3}
.cell:hover{background:#e7f5ff}
@media(max-width:768px){
  .hero{padding:20px 16px}.hero h1{font-size:19px}
  .kpi-grid{grid-template-columns:1fr 1fr}.chart{height:290px}
  table{font-size:10.5px}th,td{padding:5px 3px}
}
</style>
</head>
<body>
<div class="container">

<section id="hero">
  <div class="hero">
    <h1>@TITLE@</h1>
    <div class="sub">@SUBTITLE@</div>
    <div class="meta">@META@</div>
  </div>
</section>

@ISSUES@

<section id="kpi">
  <div class="kpi-grid">@KPIS@</div>
</section>

<section id="charts">
  @CHARTS@
</section>

<section id="charts-extra">
  <!-- 达仕增强图表插槽（T3+ 场景填充；T2 留空） -->
</section>

<section id="tables">
  @TABLES@
</section>

<section id="caliber">
  <div class="card">
    <h2>口径卡与血缘</h2>
    @CALIBER@
  </div>
</section>

<section id="conclusion">
  @CONCLUSION@
</section>

<div style="text-align:center;color:#b2bec3;font-size:11.5px;padding:18px 0">
  @FOOTER@
</div>
</div>

<!-- ECharts 内联（离线可用，禁止 CDN） -->
<script>
@ECHARTS@
</script>

<!-- 数据（由 build_report.py 注入，纯 JSON） -->
<script>
var REPORT_DATA = @DATA_JSON@;
</script>

<!-- 业务逻辑（来自独立 .js 文件，不受 Python 语法影响） -->
<script>
@BIZ_JS@
</script>
</body>
</html>
"""


def render_list(items, template):
    """把列表渲染成 HTML，用 replace 而非 f-string。"""
    out = []
    for it in items:
        s = template
        for k, v in it.items():
            s = s.replace('@' + k.upper() + '@', str(v))
        out.append(s)
    return '\n'.join(out)


META_TPL = '    <span>@LABEL@：@VALUE@</span>'
KPI_TPL = ('    <div class="kpi">\n'
           '      <div class="label">@LABEL@</div>\n'
           '      <div class="value">@VALUE@<span class="unit">@UNIT@</span></div>\n'
           '      <div class="delta">@DELTA@</div>\n'
           '    </div>')
CHART_TPL = ('  <div class="card">\n'
             '    <h2>@TITLE@</h2>\n'
             '    <div id="@ID@" class="chart"></div>\n'
             '  </div>')
ISSUE_TPL = ('<div class="note">@TEXT@</div>')


def build(data_path, js_path, out_path, echarts_path=None, title_override=None):
    data = json.load(open(data_path, encoding='utf-8'))
    biz_js = open(js_path, encoding='utf-8').read()

    # 防御：业务 JS 不得含 {{（若已含，说明作者用了错误写法，直接拒绝）
    if '{{' in biz_js or '}}' in biz_js:
        print('❌ 业务 JS 含 {{ 或 }} — 这是 f-string 转义残留，请修正后重试')
        return 1

    echarts = ''
    if echarts_path and os.path.exists(echarts_path):
        echarts = open(echarts_path, encoding='utf-8', errors='ignore').read()
    else:
        print('⚠ 未提供 echarts.min.js，报告将无图表（仅骨架）')

    html = SKELETON

    # 简单占位符替换
    html = html.replace('@TITLE@', title_override or data.get('title', '数据报告'))
    html = html.replace('@SUBTITLE@', data.get('subtitle', ''))
    html = html.replace('@META@', render_list(data.get('meta', []), META_TPL))
    html = html.replace('@KPIS@', render_list(data.get('kpis', []), KPI_TPL))

    issues = data.get('issues', [])
    if issues:
        issue_html = '<div style="margin-bottom:18px">' + '\n'.join(
            ISSUE_TPL.replace('@TEXT@', i.get('text', '')) for i in issues) + '</div>'
    else:
        issue_html = ''
    html = html.replace('@ISSUES@', issue_html)

    # 图表容器（data.charts 定义 id + title）
    charts = data.get('charts', [])
    html = html.replace('@CHARTS@', render_list(charts, CHART_TPL))

    html = html.replace('@TABLES@', data.get('tables_html', '<!-- 无明细表 -->'))

    # 口径卡（CONTRACT §5:150/151 渲染层契约，2026-11-05 整改 D7）
    #   indexed / 未注册 → 禁止进入交付，硬阻断不生成 HTML
    #   draft            → 必须标注 confidence + caliber_source + 「未经人工校准」
    #   certified        → 正常呈现
    cal = data.get('caliber', {})
    cal_lines = []
    blocked = []
    for m in cal.get('metrics', []):
        maturity = str(m.get('maturity', 'draft')).lower()
        if maturity in ('indexed', 'unregistered', 'none', ''):
            blocked.append(str(m.get('zb_code', '(未填码)')))
            continue
        cs = m.get('caliber_source')
        caliber_text = str(cs) if cs else '口径来源：缺失（禁止静默）'
        if maturity == 'draft':
            caliber_text += ' ｜ 未经人工校准'
        cal_lines.append(
            '@ZB_CODE@ · @ZB_NAME@ ｜ @UNIT@ ｜ @FACTORY@ ｜ maturity=@MATURITY@ ｜ '
            'conf=@CONFIDENCE@ ｜ @CALIBER_SOURCE@'
            .replace('@ZB_CODE@', str(m.get('zb_code', '')))
            .replace('@ZB_NAME@', str(m.get('zb_name', '')))
            .replace('@UNIT@', str(m.get('unit', '')))
            .replace('@FACTORY@', str(m.get('factory', '')))
            .replace('@MATURITY@', str(m.get('maturity', 'draft')))
            .replace('@CONFIDENCE@', str(m.get('confidence', '')))
            .replace('@CALIBER_SOURCE@', caliber_text)
        )
    if blocked:
        print('❌ CONTRACT §5:150 阻断：以下指标为 indexed/未注册，禁止进入交付：%s'
              % ', '.join(blocked))
        return 1
    if cal.get('lineage'):
        cal_lines.append('血缘：' + cal['lineage'])
    cal_html = '<div class="caliber">' + '<br>'.join(cal_lines) + '</div>'
    html = html.replace('@CALIBER@', cal_html)

    # 结论文案（若溪产出的 Markdown 直接按段落包 p；此处为轻量转换）
    conc = data.get('conclusion_html', '<!-- 若溪文案待注入 -->')
    html = html.replace('@CONCLUSION@', conc)

    html = html.replace('@FOOTER@', data.get('footer', '数仓智脑专家团 · 冶衡编排'))
    html = html.replace('@ECHARTS@', echarts)
    html = html.replace('@DATA_JSON@', json.dumps(data.get('series', {}), ensure_ascii=False))
    html = html.replace('@BIZ_JS@', biz_js)

    # 最终防御：检查所有占位符是否已替换
    leftover = re.findall(r'@[A-Z_]{3,}@', html)
    if leftover:
        print(f'❌ 未替换的占位符: {set(leftover)}')
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.', exist_ok=True)
    open(out_path, 'w', encoding='utf-8').write(html)
    print(f'✅ 已生成: {out_path}  ({os.path.getsize(out_path)/1024:.0f} KB)')

    # J1 自检（生成侧）
    m = list(re.finditer(r'<script>', html))
    biz = html[m[-1].end():html.find('</script>', m[-1].end())]
    n_open, n_close = biz.count('{{'), biz.count('}}')
    print(f'   J1 生成侧自检: {{{{={n_open}  }}}}={n_close}  {"✅" if n_open==0 and n_close==0 else "❌"}')
    if n_open or n_close:
        return 1
    print(f'   提示: 交付前请再跑 scripts/verify_report.js 做 J2/J3（真实浏览器渲染）')
    return 0


def main():
    ap = argparse.ArgumentParser(description='HTML 报告骨架生成器（零 f-string）')
    ap.add_argument('--data', required=True, help='数据 JSON 路径')
    ap.add_argument('--js', required=True, help='业务 JS 路径')
    ap.add_argument('--out', required=True, help='输出 HTML 路径')
    ap.add_argument('--echarts', default=None, help='echarts.min.js 路径')
    ap.add_argument('--title', default=None, help='覆盖标题')
    a = ap.parse_args()
    sys.exit(build(a.data, a.js, a.out, a.echarts, a.title))


if __name__ == '__main__':
    main()
