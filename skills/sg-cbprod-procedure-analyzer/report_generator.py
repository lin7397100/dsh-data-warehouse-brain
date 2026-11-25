"""
报告生成器 - CBMS 日成本存储过程性能分析报告 v2.0.0
按数据仓库分层（ODS/DWD/DWS/ADS/DIM）分析
"""

import json
from datetime import datetime


class ReportGenerator:

    @staticmethod
    def generate(analysis, output_path):
        print("正在生成 HTML 报告...")

        s = analysis['summary']
        layer_stats = analysis['layer_stats']
        layer_proc_details = analysis.get('layer_proc_details', {})
        top_procs = analysis['top_procs']
        anomalies = analysis['anomalies']
        all_details = analysis.get('all_details', [])
        bin_labels = analysis['bin_labels']
        bin_counts = analysis['bin_counts']
        time_dist = analysis['time_dist']

        # 构建分层统计面板
        layer_panels_html = ''
        for layer in layer_stats:
            pct = round(layer['total_mins'] / s['total_mins'] * 100, 1) if s['total_mins'] > 0 else 0
            count_pct = round(layer['count'] / s['total'] * 100, 1) if s['total'] > 0 else 0
            color = layer.get('color', '#dfe6e9')
            layer_panels_html += f'''
<div class="layer-card" style="border-left:4px solid {color}">
<div class="layer-header">
<span class="layer-name" style="color:{color}">{layer['name']}</span>
<span class="layer-count">{layer['count']} 条</span>
</div>
<div class="layer-stats">
<div class="stat"><span class="label">成功率</span><span class="value {'success' if layer['success_rate'] >= 99 else 'warning' if layer['success_rate'] >= 95 else 'danger'}">{layer['success_rate']}%</span></div>
<div class="stat"><span class="label">总耗时</span><span class="value">{layer['total_mins']}秒</span></div>
<div class="stat"><span class="label">平均耗时</span><span class="value {'warning' if layer['avg_mins'] > 60 else 'danger' if layer['avg_mins'] > 200 else ''}">{layer['avg_mins']}秒</span></div>
<div class="stat"><span class="label">最长耗时</span><span class="value">{layer['max_mins']}秒</span></div>
</div>
<div class="layer-bar">
<div class="bar-label"><span>耗时占比</span><span>{pct}%</span></div>
<div class="bar-bg"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>
</div>
<div class="layer-bar">
<div class="bar-label"><span>执行占比</span><span>{count_pct}%</span></div>
<div class="bar-bg"><div class="bar-fill" style="width:{count_pct}%;background:{color};opacity:0.6"></div></div>
</div>
</div>
'''

        # 构建各分层存储过程明细表
        layer_tables_html = ''
        for layer in layer_stats:
            layer_name = layer['name']
            layer_procs = layer_proc_details.get(layer_name, [])
            if not layer_procs:
                continue
            color = layer.get('color', '#dfe6e9')
            rows_html = ''
            for i, p in enumerate(layer_procs, 1):
                avg_cls = 'warning' if p['avg_mins'] > 60 else 'danger' if p['avg_mins'] > 200 else ''
                rate_cls = 'success' if p['success_rate'] >= 99 else 'warning' if p['success_rate'] >= 95 else 'danger'
                rows_html += f'''
<tr>
<td>{i}</td>
<td style="max-width:300px;word-break:break-all;font-size:12px">{p['name']}</td>
<td>{p['count']}</td>
<td class="{rate_cls}">{p['success_rate']}%</td>
<td class="value">{p['total_mins']}</td>
<td class="{avg_cls}">{p['avg_mins']}</td>
<td>{p['max_mins']}</td>
</tr>'''
            layer_tables_html += f'''
<div class="section">
<h2 class="section-title" style="color:{color}">{layer_name} 存储过程明细（{len(layer_procs)} 种）</h2>
<table>
<tr><th>#</th><th>存储过程名称</th><th>执行次数</th><th>成功率</th><th>总耗时(秒)</th><th>平均(秒)</th><th>最长(秒)</th></tr>
{rows_html if rows_html else '<tr><td colspan="7" style="text-align:center;color:#888;padding:20px">暂无数据</td></tr>'}
</table>
</div>'''

        # Top20 高耗时存储过程表
        top_table_rows = ''
        for i, p in enumerate(top_procs, 1):
            avg_cls = 'warning' if p['avg_mins'] > 60 else 'danger' if p['avg_mins'] > 200 else ''
            rate_cls = 'success' if p['success_rate'] >= 99 else 'warning' if p['success_rate'] >= 95 else 'danger'
            layer_color = p.get('layer', '其他')
            layer_tag = f'<span class="layer-tag" style="background:{analysis["layer_stats"][0].get("color","#dfe6e9") if analysis["layer_stats"] else "#dfe6e9"}20;color:inherit">{p["layer"]}</span>' if p['layer'] != '其他' else ''
            top_table_rows += f'''
<tr>
<td>{i}</td>
<td style="max-width:300px;word-break:break-all;font-size:12px">{p['name']} {layer_tag}</td>
<td>{p['count']}</td>
<td class="{rate_cls}">{p['success_rate']}%</td>
<td class="value">{p['total_mins']}</td>
<td class="{avg_cls}">{p['avg_mins']}</td>
<td>{p['max_mins']}</td>
</tr>'''

        # 异常明细表
        anomaly_rows = ''
        for i, a in enumerate(anomalies, 1):
            anomaly_rows += f'''
<tr>
<td>{i}</td>
<td style="max-width:260px;word-break:break-all;font-size:12px">{a['proc_name']}</td>
<td class="danger">{a['mins']}秒</td>
<td>{a['start']}</td>
<td>{a['end']}</td>
<td>{a['layer']}</td>
<td>{a['remark']}</td>
</tr>'''

        # 执行明细表
        details_rows = ''
        for i, d in enumerate(all_details, 1):
            mins_cls = 'danger' if d['mins'] > 300 else 'warning' if d['mins'] > 60 else ''
            status = '成功' if d['is_successful'].upper() == 'T' else '失败'
            status_cls = 'success' if status == '成功' else 'danger'
            err = f'<br><span style="color:#d62728;font-size:11px">{d["error_desc"][:80]}</span>' if d['error_desc'] else ''
            details_rows += f'''
<tr>
<td>{i}</td>
<td style="max-width:280px;word-break:break-all;font-size:12px">{d['proc_name']}</td>
<td>{d['layer']}</td>
<td class="{mins_cls}">{d['mins']}秒</td>
<td>{d['start_timestamp']}</td>
<td>{d['last_timestamp']}</td>
<td class="{status_cls}">{status}{err}</td>
</tr>'''

        # JS 数据
        js_layer_names = json.dumps([l['name'] for l in layer_stats])
        js_layer_mins = json.dumps([l['total_mins'] for l in layer_stats])
        js_layer_counts = json.dumps([l['count'] for l in layer_stats])
        js_layer_avg = json.dumps([l['avg_mins'] for l in layer_stats])
        js_layer_colors = json.dumps([l.get('color', '#dfe6e9') for l in layer_stats])
        js_top_names = json.dumps([p['name'][:40] for p in top_procs[:15]])
        js_top_mins = json.dumps([p['total_mins'] for p in top_procs[:15]])
        js_bin_labels = json.dumps(bin_labels)
        js_bin_counts = json.dumps(bin_counts)
        js_time_labels = json.dumps(list(time_dist.keys()))
        js_time_data = json.dumps(list(time_dist.values()))

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{s['date']} CBMS 存储过程性能分析报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Microsoft YaHei',Arial,sans-serif}}
body{{background:#f5f7fa;padding:20px;line-height:1.6;color:#333}}
.report-container{{max-width:1400px;margin:0 auto;background:white;border-radius:10px;box-shadow:0 0 20px rgba(0,0,0,0.06);overflow:hidden}}
.header{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:28px 40px}}
.header h1{{font-size:26px;font-weight:700;margin-bottom:6px}}
.header p{{font-size:13px;opacity:0.9}}
.header .meta{{font-size:13px;opacity:0.9;display:flex;gap:18px;margin-top:12px;flex-wrap:wrap}}
.section{{padding:28px 40px;border-bottom:1px solid #f0f0f0}}
.section:last-child{{border-bottom:none}}
.section-title{{font-size:18px;color:#667eea;margin-bottom:18px;padding-bottom:8px;border-bottom:2px solid #f0f0f0;font-weight:600}}
.dashboard{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px}}
.card{{background:white;border-radius:8px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,0.05);border-left:4px solid;transition:transform .2s}}
.card:hover{{transform:translateY(-2px)}}
.card.blue{{border-left-color:#667eea}}
.card.green{{border-left-color:#2ca02c}}
.card.red{{border-left-color:#d62728}}
.card.orange{{border-left-color:#ff7f0e}}
.card.purple{{border-left-color:#764ba2}}
.card-title{{font-size:12px;color:#888;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px}}
.card-value{{font-size:22px;font-weight:700;color:#222}}
.card-unit{{font-size:12px;color:#888;margin-left:3px}}
.layer-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin:20px 0}}
.layer-card{{background:white;border-radius:10px;padding:16px 20px;box-shadow:0 2px 8px rgba(0,0,0,0.05)}}
.layer-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:8px;border-bottom:1px dashed #eee}}
.layer-name{{font-size:15px;font-weight:700}}
.layer-count{{font-size:13px;color:#888}}
.layer-stats{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px}}
.layer-stats .stat{{display:flex;flex-direction:column;gap:2px}}
.layer-stats .label{{font-size:11px;color:#888;text-transform:uppercase}}
.layer-stats .value{{font-size:16px;font-weight:700}}
.layer-bar{{margin-top:8px}}
.bar-label{{display:flex;justify-content:space-between;font-size:11px;color:#666;margin-bottom:4px}}
.bar-bg{{height:8px;background:#f0f0f0;border-radius:4px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px;transition:width .5s}}
.charts-container{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:24px;margin:20px 0}}
.chart-wrapper{{background:#fafafa;border-radius:8px;padding:18px;box-shadow:0 1px 6px rgba(0,0,0,0.04)}}
.chart-title{{font-size:14px;color:#444;margin-bottom:10px;font-weight:600;text-align:center}}
canvas{{width:100%!important;height:260px!important}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}}
th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#f8f9fa;font-weight:600;color:#555;font-size:12px}}
tr:hover{{background:#fafafa}}
td:first-child{{color:#667eea;font-weight:600;width:40px}}
.success{{color:#2ca02c;font-weight:600}}
.warning{{color:#ff7f0e;font-weight:600}}
.danger{{color:#d62728;font-weight:600}}
.value{{color:#667eea;font-weight:600}}
.layer-tag{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;margin-left:6px}}
.search-bar{{margin-bottom:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.search-bar input{{padding:8px 14px;border:2px solid #ddd;border-radius:8px;font-size:13px;min-width:240px;flex:1;max-width:360px}}
.search-bar span{{color:#777;font-size:13px;white-space:nowrap}}
.search-bar button{{padding:8px 14px;background:#eee;border:1px solid #ddd;border-radius:8px;cursor:pointer;font-size:13px}}
.footer{{text-align:center;padding:18px;color:#aaa;font-size:12px;border-top:1px solid #f0f0f0}}
@media(max-width:1024px){{.charts-container{{grid-template-columns:1fr}}.layer-grid{{grid-template-columns:1fr}}}}
@media(max-width:768px){{.section{{padding:18px 14px}}.header h1{{font-size:20px}}}}
</style>
</head>
<body>
<div class="report-container">

<div class="header">
<h1>{s['date']} CBMS 存储过程性能分析报告</h1>
<p>CBMS Procedure Performance Analyzer v2.0 | 按数据仓库分层分析</p>
<div class="meta">
<span>查询日期：{s['date']}</span>
<span>存储过程：{s['proc_count']} 种</span>
<span>数据分层：{s['layer_count']} 个</span>
<span>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
</div>
</div>

<div class="section">
<h2 class="section-title">一、整体执行概况</h2>
<div class="dashboard">
<div class="card blue"><div class="card-title">执行总数</div><div class="card-value">{s['total']}<span class="card-unit">条</span></div></div>
<div class="card green"><div class="card-title">成功数</div><div class="card-value">{s['success']}<span class="card-unit">条</span></div></div>
<div class="card red"><div class="card-title">失败数</div><div class="card-value">{s['fail']}<span class="card-unit">条</span></div></div>
<div class="card green"><div class="card-title">成功率</div><div class="card-value">{s['success_rate']}<span class="card-unit">%</span></div></div>
<div class="card orange"><div class="card-title">总耗时</div><div class="card-value">{s['total_mins']}<span class="card-unit">秒</span></div></div>
<div class="card orange"><div class="card-title">平均耗时</div><div class="card-value">{s['avg_mins']}<span class="card-unit">秒</span></div></div>
<div class="card red"><div class="card-title">最长耗时</div><div class="card-value">{s['max_mins']}<span class="card-unit">秒</span></div></div>
<div class="card purple"><div class="card-title">异常作业</div><div class="card-value">{s['anomalies']}<span class="card-unit">个</span></div></div>
</div>

<h3 style="font-size:15px;color:#667eea;margin:20px 0 12px">各分层统计</h3>
<div class="layer-grid">
{layer_panels_html}
</div>

<div class="charts-container">
<div class="chart-wrapper"><div class="chart-title">各分层耗时占比</div><canvas id="layerPieChart"></canvas></div>
<div class="chart-wrapper"><div class="chart-title">各分层执行次数占比</div><canvas id="layerCountPieChart"></canvas></div>
<div class="chart-wrapper"><div class="chart-title">Top15 高耗时存储过程（秒）</div><canvas id="topChart"></canvas></div>
<div class="chart-wrapper"><div class="chart-title">耗时分布统计</div><canvas id="durationChart"></canvas></div>
<div class="chart-wrapper"><div class="chart-title">执行时间分布（按分钟）</div><canvas id="timeChart"></canvas></div>
<div class="chart-wrapper"><div class="chart-title">各分层平均耗时对比（秒）</div><canvas id="layerAvgChart"></canvas></div>
</div>
</div>

<div class="section">
<h2 class="section-title">二、Top20 高耗时存储过程</h2>
<table>
<tr><th>#</th><th>存储过程名称</th><th>执行次数</th><th>成功率</th><th>总耗时(秒)</th><th>平均(秒)</th><th>最长(秒)</th></tr>
{top_table_rows if top_table_rows else '<tr><td colspan="7" style="text-align:center;color:#888;padding:20px">暂无数据</td></tr>'}
</table>
</div>

{layer_tables_html}

<div class="section">
<h2 class="section-title" style="color:#d62728">异常作业详情（超 3σ 阈值：{s['threshold_3sigma']} 秒，共 {s['anomalies']} 个）</h2>
<table>
<tr><th>#</th><th>存储过程名称</th><th>耗时(秒)</th><th>开始时间</th><th>结束时间</th><th>分层</th><th>备注</th></tr>
{anomaly_rows if anomaly_rows else '<tr><td colspan="7" style="text-align:center;color:#2ca02c;padding:20px">✅ 无异常作业</td></tr>'}
</table>
</div>

<div class="section">
<h2 class="section-title">执行明细（{len(all_details)} 条，按开始时间升序）</h2>
<div class="search-bar">
<input type="text" id="searchInput" placeholder="输入存储过程名称关键词搜索..." onkeyup="filterTable()">
<span id="searchCount">共 {len(all_details)} 条记录</span>
<button onclick="clearSearch()">清除</button>
</div>
<table id="detailsTable">
<tr><th>#</th><th>存储过程名称</th><th>分层</th><th>耗时(秒)</th><th>开始时间</th><th>结束时间</th><th>状态</th></tr>
{details_rows}
</table>
</div>

<div class="footer">
<p>{s['date']} CBMS 存储过程性能分析报告 | Procedure Performance Analyzer v2.0</p>
<p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>

</div>

<script>
document.addEventListener('DOMContentLoaded', function(){{
    // 分层耗时占比
    new Chart(document.getElementById('layerPieChart').getContext('2d'), {{
        type: 'doughnut',
        data: {{
            labels: {js_layer_names},
            datasets: [{{ data: {js_layer_mins}, backgroundColor: {js_layer_colors} }}]
        }},
        options: {{ responsive: true, maintainAspectRatio: false, cutout: '55%', plugins: {{ legend: {{ position: 'right' }} }} }}
    }});

    // 分层执行次数占比
    new Chart(document.getElementById('layerCountPieChart').getContext('2d'), {{
        type: 'doughnut',
        data: {{
            labels: {js_layer_names},
            datasets: [{{ data: {js_layer_counts}, backgroundColor: {js_layer_colors} }}]
        }},
        options: {{ responsive: true, maintainAspectRatio: false, cutout: '55%', plugins: {{ legend: {{ position: 'right' }} }} }}
    }});

    // Top15 高耗时
    new Chart(document.getElementById('topChart').getContext('2d'), {{
        type: 'bar',
        data: {{ labels: {js_top_names}, datasets: [{{ label: '总耗时(秒)', data: {js_top_mins}, backgroundColor: 'rgba(102,126,234,0.7)' }}] }},
        options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y' }}
    }});

    // 耗时分布
    new Chart(document.getElementById('durationChart').getContext('2d'), {{
        type: 'bar',
        data: {{ labels: {js_bin_labels}, datasets: [{{ label: '作业数', data: {js_bin_counts}, backgroundColor: ['#2ca02c','#1f77b4','#ff7f0e','#ff7f0e','#d62728','#d62728','#8b0000'] }}] }},
        options: {{ responsive: true, maintainAspectRatio: false }}
    }});

    // 执行时间分布
    new Chart(document.getElementById('timeChart').getContext('2d'), {{
        type: 'line',
        data: {{ labels: {js_time_labels}, datasets: [{{ label: '作业数', data: {js_time_data}, borderColor: '#764ba2', backgroundColor: 'rgba(118,75,162,0.1)', fill: true, tension: 0.3 }}] }},
        options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ maxTicksLimit: 20 }} }} }} }}
    }});

    // 各分层平均耗时
    new Chart(document.getElementById('layerAvgChart').getContext('2d'), {{
        type: 'bar',
        data: {{ labels: {js_layer_names}, datasets: [{{ label: '平均耗时(秒)', data: {js_layer_avg}, backgroundColor: {js_layer_colors} }}] }},
        options: {{ responsive: true, maintainAspectRatio: false }}
    }});

    // 搜索过滤
    function filterTable() {{
        var input = document.getElementById('searchInput');
        var filter = input.value.toLowerCase();
        var table = document.getElementById('detailsTable');
        var rows = table.querySelectorAll('tbody tr');
        var count = 0;
        rows.forEach(function(row) {{
            var name = (row.cells[1] || {{}}).textContent || '';
            if (name.toLowerCase().indexOf(filter) > -1) {{
                row.style.display = '';
                count++;
                var numCell = row.cells[0];
                if (numCell) numCell.textContent = count;
            }} else {{
                row.style.display = 'none';
            }}
        }});
        var countSpan = document.getElementById('searchCount');
        if (countSpan) countSpan.textContent = '共 ' + count + ' 条记录';
    }}

    function clearSearch() {{
        var inp = document.getElementById('searchInput');
        if (inp) inp.value = '';
        filterTable();
    }}
}});
</script>
</body>
</html>'''

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"HTML 报告已生成: {output_path}")
        return output_path