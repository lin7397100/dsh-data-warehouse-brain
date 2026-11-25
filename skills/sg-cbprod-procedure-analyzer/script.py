#!/usr/bin/env python3
"""
CBMS Procedure Performance Analyzer v2.0.0
CBMS 日成本存储过程性能分析报告生成器
按数据仓库分层（ODS/DWD/DWS/ADS/DIM）分类统计
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


class ProcedureAnalyzer:
    """日成本存储过程性能分析器 - 按数据仓库分层分析"""

    COL_JOBNAME = 'JOB_NAME'
    COL_MODULE = 'MODULE_TYPE'
    COL_SUCCESS = 'IS_SUCCESSFUL'
    COL_START = 'START_TIMESTAMP'
    COL_END = 'LAST_TIMESTAMP'
    COL_MINS = 'XHTIME'
    COL_REMARK1 = 'REMARK1'
    COL_ERROR = 'ERROR_DESC'
    COL_PARAM = 'PARAM_INFO'

    # 数据仓库分层定义
    LAYER_PREFIXES = {
        'ADS': 'ADS_应用层',      # Application Data Service
        'DWS': 'DWS_汇总层',      # Data Warehouse Summary
        'DWD': 'DWD_明细层',      # Data Warehouse Detail
        'DIM': 'DIM_维度层',      # Dimension
        'ODS': 'ODS_原始层',      # Operational Data Store
    }

    # 分层颜色配置
    LAYER_COLORS = {
        'ADS_应用层': '#ff6b6b',    # 红色
        'DWS_汇总层': '#4ecdc4',    # 青色
        'DWD_明细层': '#45b7d1',    # 蓝色
        'DIM_维度层': '#96ceb4',    # 绿色
        'ODS_原始层': '#ffeaa7',    # 黄色
        '其他': '#dfe6e9',          # 灰色
    }

    def __init__(self, data):
        self.data = data
        self.analysis = {}

    def _extract_proc_name(self, jobname):
        """从 JOB_NAME 提取存储过程名称"""
        if not jobname:
            return 'Unknown'
        parts = jobname.split('.')
        return parts[-1] if len(parts) >= 2 else jobname

    def _extract_layer(self, proc_name):
        """根据存储过程名称提取数据仓库层级"""
        if not proc_name:
            return '其他'
        proc_upper = proc_name.upper()
        for prefix, layer_name in self.LAYER_PREFIXES.items():
            if proc_upper.startswith(f'P_{prefix}') or f'_{prefix}_' in proc_upper:
                return layer_name
        return '其他'

    def _calc_stats(self, records):
        """计算一组记录的基本统计"""
        if not records:
            return {'count': 0, 'success': 0, 'fail': 0, 'success_rate': 0,
                    'total_mins': 0, 'avg_mins': 0, 'max_mins': 0, 'min_mins': 0}
        mins_list = [r.get(self.COL_MINS, 0) or 0 for r in records]
        total = len(records)
        success = sum(1 for r in records if str(r.get(self.COL_SUCCESS, '')).upper() == 'T')
        total_mins = sum(mins_list)
        return {
            'count': total,
            'success': success,
            'fail': total - success,
            'success_rate': round(success / total * 100, 1) if total > 0 else 0,
            'total_mins': round(total_mins, 2),
            'avg_mins': round(total_mins / total, 2) if total > 0 else 0,
            'max_mins': round(max(mins_list), 2) if mins_list else 0,
            'min_mins': round(min(mins_list), 2) if mins_list else 0,
        }

    def analyze(self):
        if not self.data:
            raise ValueError("数据为空，无法分析")

        all_records = self.data

        # 整体统计
        overall = self._calc_stats(all_records)

        # 异常检测（3σ）
        all_mins = [r.get(self.COL_MINS, 0) or 0 for r in all_records]
        avg_mins = sum(all_mins) / len(all_mins) if all_mins else 0
        stdev = statistics.stdev(all_mins) if len(all_mins) > 1 else 0
        threshold_3sigma = avg_mins + 3 * stdev
        anomalies = [r for r in all_records if (r.get(self.COL_MINS, 0) or 0) > threshold_3sigma]

        # 按数据仓库分层分类
        layer_stats = defaultdict(lambda: {'count': 0, 'success': 0, 'mins': [], 'total_mins': 0, 'records': []})
        for r in all_records:
            proc_name = self._extract_proc_name(r.get(self.COL_JOBNAME, ''))
            layer = self._extract_layer(proc_name)
            m_val = r.get(self.COL_MINS, 0) or 0
            layer_stats[layer]['count'] += 1
            layer_stats[layer]['mins'].append(m_val)
            layer_stats[layer]['total_mins'] += m_val
            if str(r.get(self.COL_SUCCESS, '')).upper() == 'T':
                layer_stats[layer]['success'] += 1
            layer_stats[layer]['records'].append(r)

        # 按存储过程统计
        proc_stats = defaultdict(lambda: {'count': 0, 'success': 0, 'mins': [], 'total_mins': 0, 'layer': ''})
        for r in all_records:
            proc_name = self._extract_proc_name(r.get(self.COL_JOBNAME, ''))
            m_val = r.get(self.COL_MINS, 0) or 0
            proc_stats[proc_name]['count'] += 1
            proc_stats[proc_name]['mins'].append(m_val)
            proc_stats[proc_name]['total_mins'] += m_val
            proc_stats[proc_name]['layer'] = self._extract_layer(proc_name)
            if str(r.get(self.COL_SUCCESS, '')).upper() == 'T':
                proc_stats[proc_name]['success'] += 1

        # 耗时分布
        bins = [0, 5, 10, 30, 60, 120, 300, float('inf')]
        bin_labels = ['0-5秒', '5-10秒', '10-30秒', '30-60秒', '1-2分钟', '2-5分钟', '5分钟+']
        bin_counts = [0] * 7
        for m in all_mins:
            for i in range(len(bins) - 1):
                if bins[i] <= m < bins[i + 1]:
                    bin_counts[i] += 1
                    break

        # 时间分布（按分钟）
        time_dist = defaultdict(int)
        for r in all_records:
            st = str(r.get(self.COL_START, ''))
            if len(st) >= 12:
                hour = st[8:10]
                minute = st[10:12]
                time_key = f"{hour}:{minute}"
                time_dist[time_key] += 1

        # 构建层级统计列表
        layer_list = []
        for layer_name, stats in layer_stats.items():
            layer_list.append({
                'name': layer_name,
                'count': stats['count'],
                'success': stats['success'],
                'total_mins': round(stats['total_mins'], 2),
                'avg_mins': round(stats['total_mins'] / stats['count'], 2) if stats['count'] > 0 else 0,
                'max_mins': round(max(stats['mins']), 2) if stats['mins'] else 0,
                'success_rate': round(stats['success'] / stats['count'] * 100, 1) if stats['count'] > 0 else 0,
                'color': self.LAYER_COLORS.get(layer_name, '#dfe6e9'),
            })
        layer_list.sort(key=lambda x: x['total_mins'], reverse=True)

        # Top 存储过程（按总耗时）
        top_procs = []
        for proc_name, stats in sorted(proc_stats.items(), key=lambda x: x[1]['total_mins'], reverse=True):
            top_procs.append({
                'name': proc_name,
                'count': stats['count'],
                'success': stats['success'],
                'total_mins': round(stats['total_mins'], 2),
                'avg_mins': round(stats['total_mins'] / stats['count'], 2) if stats['count'] > 0 else 0,
                'max_mins': round(max(stats['mins']), 2) if stats['mins'] else 0,
                'min_mins': round(min(stats['mins']), 2) if stats['mins'] else 0,
                'success_rate': round(stats['success'] / stats['count'] * 100, 1) if stats['count'] > 0 else 0,
                'layer': stats['layer'],
            })

        # 各分层存储过程明细
        layer_proc_details = {}
        for layer_name in layer_stats.keys():
            layer_procs = [p for p in top_procs if p['layer'] == layer_name]
            layer_proc_details[layer_name] = layer_procs

        # 异常明细
        anomaly_details = [{
            'job_name': r.get(self.COL_JOBNAME, ''),
            'proc_name': self._extract_proc_name(r.get(self.COL_JOBNAME, '')),
            'start': str(r.get(self.COL_START, '')),
            'end': str(r.get(self.COL_END, '')),
            'mins': round(r.get(self.COL_MINS, 0) or 0, 2),
            'remark': str(r.get(self.COL_REMARK1, '') or ''),
            'layer': self._extract_layer(self._extract_proc_name(r.get(self.COL_JOBNAME, ''))),
        } for r in sorted(anomalies, key=lambda x: x.get(self.COL_MINS, 0) or 0, reverse=True)]

        # 全部明细（按开始时间升序）
        all_details = sorted(
            [{
                'job_name': r.get(self.COL_JOBNAME, ''),
                'proc_name': self._extract_proc_name(r.get(self.COL_JOBNAME, '')),
                'is_successful': str(r.get(self.COL_SUCCESS, '') or ''),
                'start_timestamp': str(r.get(self.COL_START, '') or ''),
                'last_timestamp': str(r.get(self.COL_END, '') or ''),
                'mins': round(r.get(self.COL_MINS, 0) or 0, 2),
                'remark': str(r.get(self.COL_REMARK1, '') or ''),
                'error_desc': str(r.get(self.COL_ERROR, '') or ''),
                'layer': self._extract_layer(self._extract_proc_name(r.get(self.COL_JOBNAME, ''))),
            } for r in all_records],
            key=lambda x: x['start_timestamp']
        )

        # 失败明细
        failed_details = [d for d in all_details if d['is_successful'].upper() != 'T']

        date_label = datetime.now().strftime('%Y-%m-%d')

        self.analysis = {
            'summary': {
                'date': date_label,
                'total': overall['count'],
                'success': overall['success'],
                'fail': overall['fail'],
                'success_rate': overall['success_rate'],
                'total_mins': overall['total_mins'],
                'avg_mins': overall['avg_mins'],
                'max_mins': overall['max_mins'],
                'min_mins': overall['min_mins'],
                'threshold_3sigma': round(threshold_3sigma, 2),
                'anomalies': len(anomalies),
                'proc_count': len(proc_stats),
                'layer_count': len(layer_stats),
            },
            'layer_stats': layer_list,
            'layer_proc_details': layer_proc_details,
            'top_procs': top_procs[:20],
            'all_procs': top_procs,
            'anomalies': anomaly_details,
            'failed_details': failed_details,
            'all_details': all_details,
            'bin_labels': bin_labels,
            'bin_counts': bin_counts,
            'time_dist': dict(sorted(time_dist.items())),
        }

        print(f"分析完成: 共 {overall['count']} 条, {len(proc_stats)} 种存储过程, {len(layer_stats)} 个分层, 总耗时 {overall['total_mins']}秒")
        return self.analysis


from data_loader import DataSourceLoader


def main():
    parser = argparse.ArgumentParser(description="CBMS 日成本存储过程性能分析")
    parser.add_argument("-s", "--source", default="cbms_api")
    parser.add_argument("-d", "--date", help="查询日期 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("-c", "--chatid", help="目标群聊 chatid（默认使用内置群ID）")
    parser.add_argument("-o", "--output", help="输出路径")
    parser.add_argument("--no-send", action="store_true")
    parser.add_argument("--time-start", default="05:00", help="开始时间 HH:MM")
    parser.add_argument("--time-end", default="07:00", help="结束时间 HH:MM")
    args = parser.parse_args()

    print("=" * 60)
    print("CBMS 日成本存储过程性能分析器 v2.0.0")
    print("=" * 60)

    try:
        data = DataSourceLoader.load(
            args.source,
            start_timestamp=args.date,
            time_start=args.time_start,
            time_end=args.time_end
        )
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        return 1

    try:
        analyzer = ProcedureAnalyzer(data)
        analysis = analyzer.analyze()
    except Exception as e:
        print(f"❌ 数据分析失败: {e}")
        import traceback; traceback.print_exc()
        return 1

    output_dir = args.output or str(Path.home() / 'Desktop')
    os.makedirs(output_dir, exist_ok=True)
    date_label = args.date or datetime.now().strftime('%Y-%m-%d')
    if len(str(date_label)) == 8 and '-' not in str(date_label):
        date_label = f"{date_label[:4]}-{date_label[4:6]}-{date_label[6:8]}"
    date_file = date_label.replace('-', '')
    output_file = os.path.join(output_dir, f"CBMS_Procedure_Analysis_{date_file}.html")

    try:
        from report_generator import ReportGenerator
        ReportGenerator.generate(analysis, output_file)
    except Exception as e:
        print(f"❌ 报告生成失败: {e}")
        import traceback; traceback.print_exc()
        return 1

    if not args.no_send:
        try:
            from wecom_sender import WeComSender
            WeComSender.send(output_file, args.chatid)
        except Exception as e:
            print(f"❌ 企微发送失败: {e}")
            print(f"报告已保存在: {output_file}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())