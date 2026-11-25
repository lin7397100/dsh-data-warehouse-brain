#!/usr/bin/env python3
"""
ETL Performance Analyzer Pro - ETL 性能分析报告生成器（专业版）
====================================================

基于交互式模板生成专业的 ETL 日志分析报告，支持多数据源，自动发送到企业微信。

支持的命令格式：
    python script.py --source "etl_api" --module "GZ4,GZ5,GZ6"
    python script.py --source "etl_api" --date "2026-03-29" --module "GZ4,GZ5,GZ6"
    python script.py --source "桌面/ETL.xlsx"
    python script.py --source "D:/data/logs.csv" --touser "230012"
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

# 修复 Windows GBK 编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


class ETLAnalyzer:
    """ETL 性能分析器"""
    
    def __init__(self, data, date=None):
        self.data = data
        self.date = date or self._detect_date()
        self.analysis = {}
        
    def _detect_date(self):
        """自动检测数据日期"""
        if self.data and 'DATE_CODE' in self.data[0]:
            return str(self.data[0]['DATE_CODE'])[:10]
        elif self.data and 'ETL_TIME' in self.data[0]:
            return str(self.data[0]['ETL_TIME'])[:10]
        return datetime.now().strftime("%Y-%m-%d")
    
    def analyze(self):
        """执行完整分析"""
        if not self.data:
            raise ValueError("数据为空，无法分析")
        
        print(f"正在分析 {len(self.data)} 条记录...")
        
        total = len(self.data)
        success = sum(1 for r in self.data if str(r.get('IS_SUCCESSFUL', '')).upper() == 'T')
        mins_list = [float(r.get('MINS', 0) or 0) for r in self.data]
        total_mins = sum(mins_list)
        avg_mins = total_mins / total if total > 0 else 0
        median_mins = statistics.median(mins_list) if mins_list else 0
        stdev_mins = statistics.stdev(mins_list) if len(mins_list) > 1 else 0
        max_mins = max(mins_list) if mins_list else 0
        min_mins = min(mins_list) if mins_list else 0
        threshold_3sigma = avg_mins + 3 * stdev_mins
        
        anomalies = [r for r in self.data if float(r.get('MINS', 0) or 0) > threshold_3sigma]
        
        # 模块统计
        module_stats = defaultdict(lambda: {'count': 0, 'mins': [], 'jobs': [], 'total_mins': 0})
        for r in self.data:
            m = r.get('MODULE_TYPE', 'Unknown')
            j = r.get('JOB_NAME', '')
            mins_val = float(r.get('MINS', 0) or 0)
            module_stats[m]['count'] += 1
            module_stats[m]['mins'].append(mins_val)
            module_stats[m]['total_mins'] += mins_val
            if j and j not in module_stats[m]['jobs']:
                module_stats[m]['jobs'].append(j)
        
        # 源表名(SRC_OBJECT_NAME)耗时统计
        object_stats = defaultdict(lambda: {'count': 0, 'total_mins': 0, 'avg_mins': 0, 'max_mins': 0, 'min_mins': float('inf'), 'module': '', 'system': ''})
        for r in self.data:
            obj = r.get('SRC_OBJECT_NAME', 'Unknown')
            mins_val = float(r.get('MINS', 0) or 0)
            object_stats[obj]['count'] += 1
            object_stats[obj]['total_mins'] += mins_val
            if mins_val > 0:
                object_stats[obj]['avg_mins'] = object_stats[obj]['total_mins'] / object_stats[obj]['count']
                object_stats[obj]['max_mins'] = max(object_stats[obj]['max_mins'], mins_val)
                object_stats[obj]['min_mins'] = min(object_stats[obj]['min_mins'], mins_val)
            if not object_stats[obj]['module']:
                object_stats[obj]['module'] = r.get('MODULE_TYPE', '')
                object_stats[obj]['system'] = r.get('SRC_SYSTEM_ID', '')
        
        # 作业类型统计
        job_stats = defaultdict(lambda: {'count': 0, 'mins': []})
        for r in self.data:
            j = r.get('JOB_NAME', 'Unknown')
            job_stats[j]['count'] += 1
            job_stats[j]['mins'].append(float(r.get('MINS', 0) or 0))
        
        # 源系统统计
        sys_stats = defaultdict(int)
        for r in self.data:
            sys_stats[r.get('SRC_SYSTEM_ID', 'Unknown')] += 1
        
        # 抽数明细（按 ETL_TIME 升序）
        all_details = sorted(
            [
                {
                    'src_object_name': r.get('SRC_OBJECT_NAME', ''),
                    'module_type':     r.get('MODULE_TYPE', ''),
                    'src_system_id':   r.get('SRC_SYSTEM_ID', ''),
                    'mins':            round(float(r.get('MINS', 0) or 0), 2),
                    'etl_time':        str(r.get('ETL_TIME', '') or ''),
                    'last_update':     str(r.get('LAST_UPDATE', '') or ''),
                    'is_successful':   str(r.get('IS_SUCCESSFUL', '') or ''),
                }
                for r in self.data
            ],
            key=lambda x: x['etl_time']
        )
        
        # 时间分布
        hour_counts = defaultdict(int)
        for r in self.data:
            t = r.get('ETL_TIME', '')
            if t:
                try:
                    h = int(str(t)[11:13])
                    hour_counts[h] += 1
                except:
                    pass
        
        # 耗时分布
        bins = [0, 0.1, 0.5, 1, 3, 5, 10, float('inf')]
        bin_labels = ['0-0.1', '0.1-0.5', '0.5-1', '1-3', '3-5', '5-10', '10+']
        bin_counts = [0] * 7
        for m in mins_list:
            for i in range(len(bins) - 1):
                if bins[i] <= m < bins[i + 1]:
                    bin_counts[i] += 1
                    break
        
        top_modules = sorted(
            [(k, {'count': v['count'], 'avg': sum(v['mins']) / len(v['mins']), 
                  'max': max(v['mins']), 'min': min(v['mins']), 'jobs': len(v['jobs']),
                  'total_mins': round(v['total_mins'], 2)})
             for k, v in module_stats.items()],
            key=lambda x: x[1]['total_mins'], reverse=True
        )
        
        # 按总耗时排序的模块（用于饼图）
        top_modules_by_total = sorted(
            [(k, round(v['total_mins'], 2)) for k, v in module_stats.items()],
            key=lambda x: x[1], reverse=True
        )[:8]
        
        # 按平均耗时排序的模块（用于柱状图）
        top_modules_by_avg = sorted(
            [(k, round(sum(v['mins']) / len(v['mins']), 2)) for k, v in module_stats.items()],
            key=lambda x: x[1], reverse=True
        )
        
        # 源表名耗时统计（前20）
        top_objects = [
            {
                'name': k,
                'count': v['count'], 
                'total_mins': round(v['total_mins'], 2),
                'avg_mins': round(v['avg_mins'], 2),
                'max_mins': round(v['max_mins'], 2),
                'min_mins': round(v['min_mins'], 2) if v['min_mins'] != float('inf') else 0,
                'module': v['module'],
                'system': v['system']
            } for k, v in object_stats.items()
        ]
        top_objects = sorted(top_objects, key=lambda x: x['total_mins'], reverse=True)[:20]
        
        top_jobs = sorted(
            [(k, {'count': v['count'], 'avg': sum(v['mins']) / len(v['mins'])})
             for k, v in job_stats.items()],
            key=lambda x: x[1]['avg'], reverse=True
        )[:10]
        
        top_systems = sorted(sys_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        
        anomaly_details = [{
            'job_name': r.get('JOB_NAME', ''),
            'module': r.get('MODULE_TYPE', ''),
            'system': r.get('SRC_SYSTEM_ID', ''),
            'time': str(r.get('ETL_TIME', '')),
            'mins': float(r.get('MINS', 0)),
            'secs': float(r.get('MINS', 0)) * 60,
            'status': '成功' if str(r.get('IS_SUCCESSFUL', '')).upper() == 'T' else '失败'
        } for r in anomalies]
        
        # 日期分布（API 数据可能有多天）
        date_counts = defaultdict(int)
        for r in self.data:
            d = str(r.get('DATE_CODE', ''))[:10]
            if d:
                date_counts[d] += 1
        
        self.analysis = {
            'summary': {
                'total': total,
                'total_mins': round(total_mins, 2),
                'success': success,
                'success_rate': round(success / total * 100, 1) if total > 0 else 0,
                'avg_mins': round(avg_mins, 2),
                'median_mins': round(median_mins, 2),
                'stdev_mins': round(stdev_mins, 2),
                'max_mins': round(max_mins, 2),
                'min_mins': round(min_mins, 2),
                'threshold_3sigma': round(threshold_3sigma, 2),
                'anomalies': len(anomalies),
                'anomaly_rate': round(len(anomalies) / total * 100, 2) if total > 0 else 0,
                'module_count': len(module_stats),
                'object_count': len(object_stats),
                'date': self.date,
                'date_counts': dict(date_counts)
            },
            'top_modules': [
                {'name': k, 'count': v['count'], 'avg': v['avg'],
                 'max': v['max'], 'min': v['min'], 'jobs': v['jobs'], 'total_mins': v['total_mins']}
                for k, v in top_modules
            ],
            'top_modules_by_total': [{'name': k, 'total_mins': v} for k, v in top_modules_by_total],
            'top_modules_by_avg': [{'name': k, 'avg_mins': v} for k, v in top_modules_by_avg],
            'all_modules_for_chart': [{'name': k, 'total_mins': round(v['total_mins'], 2)} for k, v in sorted(module_stats.items(), key=lambda x: x[1]['total_mins'], reverse=True)],
            'top_objects': top_objects,
            'all_objects_detail': [
                {
                    'name': o['name'],
                    'module': o['module'],
                    'system': o['system'],
                    'count': o['count'],
                    'total_mins': o['total_mins'],
                    'avg_mins': o['avg_mins'],
                    'max_mins': o['max_mins'],
                    'min_mins': o['min_mins']
                } for o in sorted(top_objects, key=lambda x: x['total_mins'], reverse=True)
            ],
            'all_details': all_details,
            'top_jobs': [
                {'name': k, 'count': v['count'], 'avg': round(v['avg'], 2)}
                for k, v in top_jobs
            ],
            'top_systems': [{'name': k, 'count': v} for k, v in top_systems],
            'hour_counts': dict(hour_counts),
            'bin_labels': bin_labels,
            'bin_counts': bin_counts,
            'anomalies': anomaly_details
        }
        
        print(f"分析完成: {len(module_stats)} 个模块, 总耗时 {round(total_mins, 2)} 分钟")
        return self.analysis


# 导入其他模块
from report_generator import ReportGenerator
from wecom_sender import WeComSender
from data_loader import DataSourceLoader


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="ETL 性能分析报告生成器（专业版）")
    parser.add_argument("-s", "--source", default="etl_api",
                        help="数据源: 'etl_api'(从API获取) 或 文件路径(xlsx/csv)")
    parser.add_argument("-d", "--date", help="ETL 日期（YYYY-MM-DD），API数据源有效")
    parser.add_argument("-m", "--module", default="GZ4,GZ5,GZ6",
                        help="模块类型（如 GZ4,GZ5,GZ6），API数据源有效，支持逗号分隔多个")
    parser.add_argument("--time-start", default="05:30",
                        help="ETL_TIME 开始时间（HH:MM），默认 05:30")
    parser.add_argument("--time-end", default="07:00",
                        help="ETL_TIME 结束时间（HH:MM），默认 07:00")
    parser.add_argument("-t", "--chatid", help="目标群聊 chatid（默认使用 CONFIG 中的配置）")
    parser.add_argument("-o", "--output", help="报告输出路径")
    parser.add_argument("--no-send", action="store_true", help="不发送到企微")
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    print("=" * 60)
    print("ETL Performance Analyzer Pro v2.1.0")
    print("=" * 60)
    
    # 1. 加载数据
    try:
        data = DataSourceLoader.load(
            args.source, 
            etl_date=args.date, 
            module_type=args.module,
            etl_time_start=args.time_start,
            etl_time_end=args.time_end
        )
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        return 1
    
    # 2. 分析数据
    try:
        analyzer = ETLAnalyzer(data, args.date)
        analysis = analyzer.analyze()
    except Exception as e:
        print(f"❌ 数据分析失败: {e}")
        return 1
    
    # 3. 生成报告
    output_dir = args.output or str(Path.home() / 'Desktop')
    date_str = analysis['summary']['date']
    if args.date:
        date_str = args.date.replace('-', '')
    module_label = args.module.replace(',', '-').upper()
    output_file = os.path.join(output_dir, f"ETL_Analysis_{date_str}_{module_label}.html")
    
    try:
        ReportGenerator.generate(analysis, output_file, f"ETL API ({args.module})")
    except Exception as e:
        print(f"❌ 报告生成失败: {e}")
        return 1
    
    # 4. 发送到企微
    if not args.no_send:
        try:
            WeComSender.send(output_file, args.chatid)
        except Exception as e:
            print(f"❌ 企微发送失败: {e}")
            print(f"报告已保存在: {output_file}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
