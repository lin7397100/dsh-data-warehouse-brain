"""
报告生成器 - 基于交互式模板生成专业的 HTML 报告
增强版：新增 MODULE_TYPE 总耗时分析和 SRC_OBJECT_NAME 源表名耗时统计
"""

import os
import json
from datetime import datetime


class ReportGenerator:
    """HTML 报告生成器（专业交互式增强版）"""
    
    @staticmethod
    def generate(analysis, output_path, source_file):
        """生成专业交互式 HTML 报告（增强版）"""
        print("正在生成交互式 HTML 报告（增强版）...")
        
        s = analysis['summary']
        modules = analysis['top_modules']
        modules_by_total = analysis.get('top_modules_by_total', [])
        modules_by_avg = analysis.get('top_modules_by_avg', [])
        objects = analysis.get('top_objects', [])
        all_objects_detail = analysis.get('all_objects_detail', [])
        jobs = analysis['top_jobs']
        systems = analysis['top_systems']
        anomalies = analysis['anomalies']
        
        # 计算异常模块数据
        anomaly_modules = list(set([a['module'] for a in anomalies])) if anomalies else ['无异常']
        anomaly_counts = [len([a for a in anomalies if a['module'] == m]) for m in anomaly_modules] if anomalies else [1]
        
        # 生成源表耗时明细表数据行
        all_objects_rows = ''
        for i, obj in enumerate(all_objects_detail, 1):
            avg_cls = ' class="warning"' if obj['avg_mins'] > 1 else (' class="danger"' if obj['avg_mins'] > 3 else '')
            max_cls = ' class="danger"' if obj['max_mins'] > 5 else (' class="warning"' if obj['max_mins'] > 2 else '')
            row = '<tr><td>' + str(i) + '</td><td>' + obj['name'] + '</td><td>' + obj['module'] + '</td><td>' + obj['system'] + '</td><td>' + str(obj['count']) + '</td><td class="value">' + str(obj['total_mins']) + '</td><td' + avg_cls + '>' + str(obj['avg_mins']) + '</td><td' + max_cls + '>' + str(obj['max_mins']) + '</td><td>' + str(obj['min_mins']) + '</td></tr>\n                '
            all_objects_rows += row

        # 生成抽数明细表（按 ETL_TIME 升序）
        all_details = analysis.get('all_details', [])
        all_details_rows = ''
        for i, d in enumerate(all_details, 1):
            mins_val = d['mins']
            mins_cls = ' class="danger"' if mins_val > 5 else (' class="warning"' if mins_val > 1 else '')
            status_cls = ' class="success"' if d['is_successful'].upper() == 'T' else ' class="danger"'
            status_txt = '成功' if d['is_successful'].upper() == 'T' else '失败'
            all_details_rows += (
                '<tr><td>' + str(i) + '</td>'
                '<td>' + d['src_object_name'] + '</td>'
                '<td>' + d['module_type'] + '</td>'
                '<td>' + d['src_system_id'] + '</td>'
                '<td class="value"' + mins_cls + '>' + str(mins_val) + '</td>'
                '<td>' + d['etl_time'] + '</td>'
                '<td>' + d['last_update'] + '</td>'
                '<td' + status_cls + '>' + status_txt + '</td>'
                '</tr>\n                '
            )
        
        # 模块颜色配置
        module_colors = [
            'rgba(31, 119, 180, 0.8)', 'rgba(44, 160, 44, 0.8)', 'rgba(255, 127, 14, 0.8)',
            'rgba(148, 103, 189, 0.8)', 'rgba(214, 39, 40, 0.8)', 'rgba(140, 86, 75, 0.8)',
            'rgba(227, 119, 194, 0.8)', 'rgba(127, 127, 127, 0.8)', 'rgba(23, 190, 207, 0.8)',
            'rgba(188, 189, 34, 0.8)'
        ]
        
        # 生成 HTML
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{s['date']} ETL任务执行分析报告（交互式增强版）</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Microsoft YaHei', Arial, sans-serif; }}
        body {{ background-color: #f5f7fa; padding: 20px; line-height: 1.6; color: #333; }}
        .report-container {{ max-width: 1400px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 0 20px rgba(0,0,0,0.05); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1f77b4 0%, #2ca02c 100%); color: white; padding: 30px 40px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; font-weight: 700; }}
        .header .report-meta {{ font-size: 14px; opacity: 0.9; display: flex; gap: 20px; margin-top: 15px; flex-wrap: wrap; }}
        .section {{ padding: 30px 40px; border-bottom: 1px solid #f0f0f0; }}
        .section:last-child {{ border-bottom: none; }}
        .section-title {{ font-size: 20px; color: #1f77b4; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #f0f0f0; font-weight: 600; }}
        .dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-left: 4px solid; transition: transform 0.3s ease; }}
        .card:hover {{ transform: translateY(-5px); }}
        .card.total {{ border-left-color: #1f77b4; }}
        .card.success {{ border-left-color: #2ca02c; }}
        .card.time {{ border-left-color: #ff7f0e; }}
        .card.module {{ border-left-color: #9467bd; }}
        .card.anomaly {{ border-left-color: #d62728; }}
        .card.table {{ border-left-color: #1405bd; }}
        .card.object {{ border-left-color: #8b4513; }}
        .card-title {{ font-size: 14px; color: #666; margin-bottom: 8px; }}
        .card-value {{ font-size: 24px; font-weight: 700; color: #333; }}
        .card-unit {{ font-size: 14px; color: #666; margin-left: 5px; }}
        .charts-container {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 30px; margin: 30px 0; }}
        .chart-wrapper {{ background-color: #f9f9f9; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
        .chart-title {{ font-size: 16px; color: #333; margin-bottom: 15px; font-weight: 600; text-align: center; }}
        canvas {{ width: 100% !important; height: 280px !important; }}
        .metrics-table, .detail-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }}
        .metrics-table th, .metrics-table td, .detail-table th, .detail-table td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
        .metrics-table th, .detail-table th {{ background-color: #f8f9fa; font-weight: 600; color: #333; }}
        .metrics-table .category {{ background-color: #eef2f7; font-weight: 600; color: #1f77b4; }}
        .metrics-table .value {{ font-weight: 600; }}
        .detail-table tr:hover {{ background-color: #f8f9fa; }}
        .detail-table td:first-child {{ font-weight: 600; color: #1f77b4; }}
        .success {{ color: #2ca02c; font-weight: 600; }}
        .warning {{ color: #ff7f0e; font-weight: 600; }}
        .danger {{ color: #d62728; font-weight: 600; }}
        .highlight {{ background-color: #fff3cd; }}
        .analysis-text {{ line-height: 1.8; margin-bottom: 20px; font-size: 15px; }}
        .analysis-text strong {{ color: #1f77b4; }}
        .recommendation {{ background-color: #f8f9fa; border-left: 4px solid #2ca02c; padding: 15px 20px; margin: 15px 0; border-radius: 0 4px 4px 0; }}
        .recommendation h4 {{ color: #1f77b4; margin-bottom: 10px; font-size: 16px; }}
        .recommendation ul {{ padding-left: 20px; margin: 0; }}
        .recommendation li {{ margin-bottom: 8px; }}
        .priority {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; margin-left: 10px; }}
        .priority.high {{ background-color: #ffebee; color: #d62728; }}
        .priority.medium {{ background-color: #fff3e0; color: #ff7f0e; }}
        .priority.low {{ background-color: #e8f5e9; color: #2ca02c; }}
        .conclusion {{ background-color: #e6f3ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .conclusion h4 {{ color: #1f77b4; margin-bottom: 15px; font-size: 17px; }}
        .footer {{ text-align: center; padding: 20px 0; color: #666; font-size: 14px; border-top: 1px solid #f0f0f0; }}
        .tag {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 5px; }}
        .tag.module {{ background-color: #e3f2fd; color: #1565c0; }}
        .tag.system {{ background-color: #e8f5e9; color: #2e7d32; }}
        @media (max-width: 1024px) {{ .charts-container {{ grid-template-columns: 1fr; }} }}
        @media (max-width: 768px) {{ .dashboard {{ grid-template-columns: repeat(2, 1fr); }} .section {{ padding: 20px 15px; }} .header h1 {{ font-size: 22px; }} canvas {{ height: 220px !important; }} .detail-table {{ font-size: 12px; }} .detail-table th, .detail-table td {{ padding: 6px 8px; }} }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="header">
            <h1>{s['date']} ETL任务执行分析报告（交互式增强版）</h1>
            <p>新增模块总耗时分析 | 源表名耗时统计 | 深度性能诊断</p>
            <div class="report-meta">
                <span>数据周期：{s['date']}
                <span>数据来源：{os.path.basename(source_file)}
                <span>任务类型：ETL数据同步任务
                <span>报告生成：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">一、核心指标概览</h2>
            <div class="dashboard">
                <div class="card total"><div class="card-title">总任务数</div><div class="card-value">{s['total']}<span class="card-unit">个</div></div>
                <div class="card success"><div class="card-title">任务成功率</div><div class="card-value">{s['success_rate']}<span class="card-unit">%</div></div>
                <div class="card time"><div class="card-title">总耗时</div><div class="card-value">{s.get('total_mins', round(s['avg_mins'] * s['total'], 2))}<span class="card-unit">分钟</div></div>
                <div class="card time"><div class="card-title">平均耗时</div><div class="card-value">{s['avg_mins']}<span class="card-unit">分钟</div></div>
                <div class="card module"><div class="card-title">模块类型数</div><div class="card-value">{s['module_count']}<span class="card-unit">种</div></div>
                <div class="card table"><div class="card-title">源表数量</div><div class="card-value">{s.get('object_count', len(objects))}<span class="card-unit">个</div></div>
                <div class="card anomaly"><div class="card-title">异常任务数</div><div class="card-value">{s['anomalies']}<span class="card-unit">个</div></div>
            </div>
            
            <div class="charts-container">
                <div class="chart-wrapper"><div class="chart-title">各模块总耗时分布（饼图）</div><canvas id="moduleTotalChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">各模块总耗时对比（柱状图）</div><canvas id="moduleTotalBarChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">各模块平均耗时对比（柱状图）</div><canvas id="moduleAvgChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">前15耗时最长源表名（柱状图）</div><canvas id="objectChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">前10耗时最长作业类型</div><canvas id="jobChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">ETL任务执行时间分布</div><canvas id="timeChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">前10源系统任务数分布</div><canvas id="systemChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">ETL任务耗时分布直方图</div><canvas id="durationChart"></canvas></div>
                <div class="chart-wrapper"><div class="chart-title">异常任务模块分布</div><canvas id="anomalyChart"></canvas></div>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">二、详细数据统计</h2>
            
            <h3>2.1 核心指标汇总表</h3>
            <table class="metrics-table">
                <tr><th>指标类别</th><th>指标名称</th><th>数值</th><th>说明</th></tr>
                <tr><td rowspan="3" class="category">整体执行情况</td><td>总任务数</td><td class="value">{s['total']} 个</td><td>当日ETL任务总数量</td></tr>
                <tr><td>成功任务数</td><td class="value success">{s['success']} 个</td><td>执行成功的任务数量</td></tr>
                <tr><td>成功率</td><td class="value success">{s['success_rate']}%</td><td>任务执行成功率，表现优秀</td></tr>
                <tr><td rowspan="4" class="category">耗时统计</td><td>平均耗时</td><td class="value">{s['avg_mins']} 分钟</td><td>所有任务的平均执行时间</td></tr>
                <tr><td>中位数耗时</td><td class="value">{s['median_mins']} 分钟</td><td>耗时中位数</td></tr>
                <tr><td>最长耗时</td><td class="value warning">{s['max_mins']} 分钟</td><td>单个任务的最长执行时间</td></tr>
                <tr><td>最短耗时</td><td class="value">{s['min_mins']} 分钟</td><td>单个任务的最短执行时间</td></tr>
                <tr><td rowspan="2" class="category">模块分析</td><td>模块类型数量</td><td class="value">{s['module_count']} 种</td><td>不同MODULE_TYPE的数量</td></tr>
                <tr><td>总源表数量</td><td class="value">{s.get('object_count', len(objects))} 个</td><td>不同SRC_OBJECT_NAME的数量</td></tr>
                <tr><td rowspan="3" class="category">异常检测</td><td>异常任务数</td><td class="value danger">{s['anomalies']} 个</td><td>超过3σ阈值的异常耗时任务</td></tr>
                <tr><td>异常任务比例</td><td class="value danger">{s['anomaly_rate']}%</td><td>异常任务占总任务的比例</td></tr>
                <tr><td>异常判断阈值</td><td class="value">{s['threshold_3sigma']} 分钟</td><td>基于3σ原则计算的异常判断标准</td></tr>
            </table>
            
            <h3>2.2 模块总耗时统计表</h3>
            <table class="detail-table">
                <tr><th>排名</th><th>模块类型</th><th>任务数</th><th>总耗时(分钟)</th><th>平均耗时(分钟)</th><th>最长耗时(分钟)</th><th>最短耗时(分钟)</th><th>耗时占比</th></tr>
'''
        
        # 计算总耗时
        total_mins_all = sum([m['total_mins'] for m in modules])
        
        # 添加模块统计行
        for i, m in enumerate(modules, 1):
            pct = round(m['total_mins'] / total_mins_all * 100, 1) if total_mins_all > 0 else 0
            warning_class = ' class="warning"' if m['avg'] > 1 else ''
            max_warning = ' class="danger"' if m['max'] > 3 else ''
            pct_class = ' class="danger"' if pct > 30 else (' class="warning"' if pct > 15 else '')
            html += f'''                <tr><td>{i}</td><td>{m['name']}</td><td>{m['count']}</td><td class="value">{m['total_mins']}</td><td{warning_class}>{m['avg']}</td><td{max_warning}>{m['max']}</td><td>{m['min']}</td><td{pct_class}>{pct}%</td></tr>\n'''
        
        html += f'''            </table>
            
            <h3>2.3 源表名耗时统计表（前20）</h3>
            <table class="detail-table">
                <tr><th>排名</th><th>源表名(SRC_OBJECT_NAME)</th><th>模块</th><th>源系统</th><th>执行次数</th><th>总耗时(分钟)</th><th>平均耗时(分钟)</th><th>最长耗时(分钟)</th><th>最短耗时(分钟)</th></tr>
'''
        
        # 添加源表统计行
        for i, obj in enumerate(objects, 1):
            avg_class = ' class="warning"' if obj['avg_mins'] > 1 else (' class="danger"' if obj['avg_mins'] > 3 else '')
            max_class = ' class="danger"' if obj['max_mins'] > 5 else (' class="warning"' if obj['max_mins'] > 2 else '')
            html += f'''                <tr><td>{i}</td><td>{obj['name']}</td><td>{obj['module']}</td><td>{obj['system']}</td><td>{obj['count']}</td><td class="value">{obj['total_mins']}</td><td{avg_class}>{obj['avg_mins']}</td><td{max_class}>{obj['max_mins']}</td><td>{obj['min_mins']}</td></tr>\n'''
        
        html += f'''            </table>
            
            <h3>2.4 异常任务详情表</h3>
            <table class="detail-table">
                <tr><th>序号</th><th>作业名称</th><th>模块类型</th><th>源系统ID</th><th>执行时间</th><th>耗时(分钟)</th><th>耗时(秒)</th><th>执行状态</th></tr>
'''
        
        # 添加异常任务行
        for i, a in enumerate(anomalies, 1):
            html += f'''                <tr><td>{i}</td><td>{a['job_name']}</td><td class="warning">{a['module']}</td><td>{a['system']}</td><td>{a['time']}</td><td class="danger">{a['mins']}</td><td class="danger">{a['secs']}</td><td class="success">{a['status']}</td></tr>\n'''
        
        html += f'''            </table>
            
            <h3>2.5 主要模块统计表</h3>
            <table class="detail-table">
                <tr><th>排名</th><th>模块类型</th><th>任务数</th><th>平均耗时(分钟)</th><th>最长耗时(分钟)</th><th>最短耗时(分钟)</th><th>作业类型数</th></tr>
'''
        
        # 添加模块统计行
        for i, m in enumerate(modules, 1):
            warning_class = ' class="warning"' if m['avg'] > 1 else ''
            max_warning = ' class="warning"' if m['max'] > 3 else ''
            html += f'''                <tr><td>{i}</td><td>{m['name']}</td><td>{m['count']}</td><td{warning_class}>{m['avg']}</td><td{max_warning}>{m['max']}</td><td>{m['min']}</td><td>{m['jobs']}</td></tr>\n'''
        
        # 添加分析结论和建议
        top_obj = objects[0] if objects else {'name': 'N/A', 'total_mins': 0}
        top_module = modules[0] if modules else {'name': 'N/A', 'total_mins': 0, 'avg': 0}
        
        html += f'''            </table>
            
            <h3>2.6 源表耗时明细表（全量按总耗时降序）</h3>
            <table class="detail-table">
                <tr><th>排名</th><th>源表名</th><th>模块</th><th>源系统</th><th>执行次数</th><th>总耗时(分钟)</th><th>平均耗时(分钟)</th><th>最长耗时(分钟)</th><th>最短耗时(分钟)</th></tr>
                {all_objects_rows}
            </table>

            <h3>2.7 抽数明细表（按 ETL_TIME 升序）</h3>
            <table class="detail-table">
                <tr><th>序号</th><th>源表名</th><th>模块</th><th>源系统</th><th>耗时(分钟)</th><th>开始时间(ETL_TIME)</th><th>结束时间(LAST_UPDATE)</th><th>状态</th></tr>
                {all_details_rows}
            </table>
        </div>

        <div class="section">
            <h2 class="section-title">三、专业数据分析</h2>
            <h3>3.1 核心指标深度分析</h3>
            <p class="analysis-text"><strong>执行质量分析</strong>：当日{s['total']}个ETL任务全部执行成功，成功率达到{s['success_rate']}%，这一指标表现优异，说明ETL任务的执行稳定性极佳，数据同步过程中无失败案例。</p>
            
            <p class="analysis-text"><strong>耗时特征深度分析</strong>：平均耗时{s['avg_mins']}分钟，中位数耗时{s['median_mins']}分钟，两者差距较大，表明大部分任务执行效率较高，但存在少数长耗时任务拉高了平均值，呈现典型的右偏分布特征。</p>
            
            <h3>3.2 模块总耗时分析 新增</h3>
            <p class="analysis-text"><strong>模块耗时贡献分析</strong>：{top_module['name']}模块总耗时最长（{top_module['total_mins']}分钟），占整体耗时的{round(top_module['total_mins'] / total_mins_all * 100, 1) if total_mins_all > 0 else 0}%。不同模块的任务复杂度和数据处理量存在显著不同。</p>
            
            <h3>3.3 源表名耗时分析 <span class="tag table">新增</h3>
            <p class="analysis-text"><strong>源表性能差异分析</strong>：<strong>{top_obj['name']}</strong>源表耗时最长（总耗时{top_obj['total_mins']}分钟，平均{top_obj['avg_mins']}分钟/次），建议重点关注该表的抽取性能优化。不同源表的数据量、复杂度和抽取逻辑差异导致耗时差异明显。</p>
            
            <h3>3.4 异常任务根因分析</h3>
            <p class="analysis-text"><strong>异常任务特征</strong>：基于3σ原则检测出的{s['anomalies']}个异常任务集中在特定模块和时段，可能存在系统资源竞争或数据量异常等问题。建议对异常任务进行专项分析和优化。</p>
        </div>
        
        <div class="section">
            <h2 class="section-title">四、落地化优化建议</h2>
            <div class="recommendation">
                <h4>短期优化措施 <span class="priority high">高优先级（1-2周）</h4>
                <ul>
                    <li><strong>异常任务专项优化</strong>：立即对{s['anomalies']}个异常任务进行专项优化，重点关注高耗时模块和源表。</li>
                    <li><strong>源表性能诊断</strong>：对TOP10耗时源表（如{top_obj['name']}等）进行性能诊断和优化。</li>
                    <li><strong>实时监控告警系统建设</strong>：建立ETL任务耗时实时监控系统，设置{s['threshold_3sigma']}分钟的告警阈值。</li>
                </ul>
            </div>
            
            <div class="recommendation">
                <h4>中期优化措施 <span class="priority medium">中优先级（1-2个月）</h4>
                <ul>
                    <li><strong>模块资源调配优化</strong>：针对高耗时模块（如{top_module['name']}）进行资源调配和调度策略优化。</li>
                    <li><strong>作业逻辑重构</strong>：对长耗时作业类型和源表进行逻辑重构，实现增量抽取和并行处理。</li>
                    <li><strong>源系统性能协同优化</strong>：与源系统团队协作，优化数据抽取接口性能。</li>
                </ul>
            </div>
            
            <div class="recommendation">
                <h4>长期优化措施 <span class="priority low">低优先级（2-6个月）</h4>
                <ul>
                    <li><strong>ETL系统架构升级</strong>：基于业务发展预测，引入分布式处理架构提升整体吞吐能力。</li>
                    <li><strong>性能基准体系建设</strong>：为各模块和源表建立正常的耗时基准范围，实现性能退化预警。</li>
                </ul>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">五、核心结论与建议</h2>
            <div class="conclusion">
                <h4>核心结论</h4>
                <p class="analysis-text">1. <strong>执行稳定性表现优异</strong>：成功率达到{s['success_rate']}%，无失败任务，数据同步可靠性高。</p>
                <p class="analysis-text">2. <strong>模块耗时分析明确</strong>：{top_module['name']}模块总耗时最长（{top_module['total_mins']}分钟），应作为优化重点。</p>
                <p class="analysis-text">3. <strong>源表性能差异显著</strong>：{top_obj['name']}源表耗时最长，需重点关注该表的抽取效率。</p>
                <p class="analysis-text">4. <strong>异常任务需关注</strong>：存在{s['anomalies']}个异常任务，建议进行专项分析和优化。</p>
            </div>
        </div>
        
        <div class="footer">
            <p>{s['date']} ETL任务执行分析报告（交互式增强版） | 报告类型：深度性能分析报告</p>
            <p>图表技术：基于Chart.js的交互式动态图表 | 报告生成：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            // 模块总耗时饼图
            new Chart(document.getElementById('moduleTotalChart').getContext('2d'), {{
                type: 'doughnut',
                data: {{
                    labels: {json.dumps([m['name'] for m in modules_by_total[:8]])},
                    datasets: [{{
                        data: {json.dumps([m['total_mins'] for m in modules_by_total[:8]])},
                        backgroundColor: {json.dumps(module_colors[:8])}
                    }}]
                }},
                options: {{ responsive: true, maintainAspectRatio: false, cutout: '50%', plugins: {{ legend: {{ position: 'right' }} }} }}
            }});
            
            // 各模块总耗时对比柱状图
            new Chart(document.getElementById('moduleTotalBarChart').getContext('2d'), {{
                type: 'bar',
                data: {{
                    labels: {json.dumps([m['name'] for m in analysis['all_modules_for_chart']])},
                    datasets: [{{
                        label: '总耗时（分钟）',
                        data: {json.dumps([m['total_mins'] for m in analysis['all_modules_for_chart']])},
                        backgroundColor: 'rgba(255, 127, 14, 0.7)'
                    }}]
                }},
                options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
            }});
            
            // 模块平均耗时柱状图
            new Chart(document.getElementById('moduleAvgChart').getContext('2d'), {{
                type: 'bar',
                data: {{
                    labels: {json.dumps([m['name'] for m in modules_by_avg])},
                    datasets: [{{
                        label: '平均耗时（分钟）',
                        data: {json.dumps([m['avg_mins'] for m in modules_by_avg])},
                        backgroundColor: 'rgba(31, 119, 180, 0.7)'
                    }}]
                }},
                options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y' }}
            }});
            
            // 源表耗时柱状图
            new Chart(document.getElementById('objectChart').getContext('2d'), {{
                type: 'bar',
                data: {{
                    labels: {json.dumps([obj['name'][:20] for obj in objects[:15]])},
                    datasets: [{{
                        label: '总耗时（分钟）',
                        data: {json.dumps([obj['total_mins'] for obj in objects[:15]])},
                        backgroundColor: 'rgba(139, 69, 19, 0.7)'
                    }}]
                }},
                options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y' }}
            }});
            
            // 作业耗时柱状图
            new Chart(document.getElementById('jobChart').getContext('2d'), {{
                type: 'bar',
                data: {{ labels: {json.dumps([j['name'][:20] for j in jobs])}, datasets: [{{ label: '平均耗时（分钟）', data: {json.dumps([j['avg'] for j in jobs])}, backgroundColor: 'rgba(214, 39, 40, 0.7)' }}] }},
                options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y' }}
            }});
            
            // 时间分布柱状图
            const hourLabels = Array.from({{length: 24}}, (_, i) => i + ':00');
            const hourData = Array(24).fill(0);
            {chr(10).join([f'hourData[{h}] = {c};' for h, c in analysis['hour_counts'].items()])}
            new Chart(document.getElementById('timeChart').getContext('2d'), {{
                type: 'bar',
                data: {{ labels: hourLabels, datasets: [{{ label: '任务数（个）', data: hourData, backgroundColor: 'rgba(148, 103, 189, 0.7)' }}] }},
                options: {{ responsive: true, maintainAspectRatio: false }}
            }});
            
            // 源系统柱状图
            new Chart(document.getElementById('systemChart').getContext('2d'), {{
                type: 'bar',
                data: {{ labels: {json.dumps([s['name'] for s in systems])}, datasets: [{{ label: '任务数（个）', data: {json.dumps([s['count'] for s in systems])}, backgroundColor: 'rgba(140, 86, 75, 0.7)' }}] }},
                options: {{ responsive: true, maintainAspectRatio: false }}
            }});
            
            // 耗时分布直方图
            new Chart(document.getElementById('durationChart').getContext('2d'), {{
                type: 'bar',
                data: {{ labels: {json.dumps(analysis['bin_labels'])}, datasets: [{{ label: '任务数（个）', data: {json.dumps(analysis['bin_counts'])}, backgroundColor: ['rgba(44, 160, 44, 0.7)', 'rgba(148, 103, 189, 0.7)', 'rgba(31, 119, 180, 0.7)', 'rgba(255, 127, 14, 0.7)', 'rgba(214, 39, 40, 0.5)', 'rgba(214, 39, 40, 0.7)', 'rgba(214, 39, 40, 0.9)'] }}] }},
                options: {{ responsive: true, maintainAspectRatio: false }}
            }});
            
            // 异常任务饼图
            new Chart(document.getElementById('anomalyChart').getContext('2d'), {{
                type: 'doughnut',
                data: {{ labels: {json.dumps(anomaly_modules)}, datasets: [{{ data: {json.dumps(anomaly_counts)} }}] }},
                options: {{ responsive: true, maintainAspectRatio: false, cutout: '60%' }}
            }});
        }});
    </script>
</body>
</html>'''
        
        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"HTML 报告已生成: {output_path}")
        return output_path
