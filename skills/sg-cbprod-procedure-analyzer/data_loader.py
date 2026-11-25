"""
数据加载器 - CBMS 日成本工序性能分析
从 PJJOB API 获取数据，支持时间范围筛选
"""

import os
import csv
import sys
from pathlib import Path
from datetime import datetime


class PathResolver:
    """路径解析器"""
    
    @staticmethod
    def resolve(path):
        path = str(path).strip()
        if path.startswith('桌面/') or path.startswith('桌面\\'):
            desktop = Path.home() / 'Desktop'
            path = desktop / path[3:]
        elif path.startswith('desktop/') or path.startswith('desktop\\'):
            desktop = Path.home() / 'Desktop'
            path = desktop / path[9:]
        return str(Path(path).resolve())


class DataSourceLoader:
    """数据源加载器"""
    
    @staticmethod
    def load(source, start_timestamp=None, time_start='05:00', time_end='07:00', **kwargs):
        source = str(source).strip().lower()
        
        if source in ('pjjob_api', 'pjob_api', 'pjob', 'api', 'etl_api', 'cbms_api'):
            return DataSourceLoader._load_from_pjjob_api(start_timestamp, time_start, time_end)
        
        ext = Path(source).suffix.lower()
        if ext == '.xlsx':
            return DataSourceLoader._load_from_xlsx(source)
        elif ext == '.csv':
            return DataSourceLoader._load_from_csv(source)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
    
    @staticmethod
    def _load_from_pjjob_api(start_timestamp=None, time_start='05:00', time_end='07:00'):
        """从 CBMS PJJOB API 加载数据，筛选指定时间范围"""
        import requests
        
        if start_timestamp is None:
            start_timestamp = datetime.now().strftime('%Y-%m-%d')
        
        # 如果输入的是 YYYYMMDD 格式，转换为 YYYY-MM-DD
        st = str(start_timestamp)
        if len(st) == 8 and '-' not in st:
            start_timestamp = f"{st[:4]}-{st[4:6]}-{st[6:8]}"
        
        api_url = "http://eplat.fjsg.com/service/D_A_SMBBCB00_PJJOB"
        
        payload = {
            "clientId": "sgdw-cb01",
            "clientSecret": "537410A26EC7FE29B7258A7861D1C59F",
            "params": {
                "startTimestamp": start_timestamp
            },
            "showCount": "true",
            "offset": "0",
            "limit": 2000
        }
        
        print(f"正在从 CBMS 工序 API 加载数据...")
        print(f"  API: {api_url}")
        print(f"  日期: {start_timestamp}")
        print(f"  时间范围: {time_start} - {time_end}")
        
        resp = requests.post(api_url, json=payload, timeout=120)
        resp.raise_for_status()
        
        result_data = resp.json()
        
        sys_info = result_data.get('__sys__', {})
        if sys_info.get('status', -1) != 0:
            raise Exception(f"API 返回错误: {sys_info.get('msg', 'Unknown error')}")
        
        blocks = result_data.get('__blocks__', {})
        result = blocks.get('result', {})
        meta = result.get('meta', {})
        columns = [c['name'] for c in meta.get('columns', [])]
        rows = result.get('rows', [])
        
        if not rows:
            print("API 返回空数据")
            return []
        
        print(f"  API返回: {len(rows)} 条")
        
        # 解析时间范围
        start_hour, start_min = map(int, time_start.split(':'))
        end_hour, end_min = map(int, time_end.split(':'))
        start_minutes = start_hour * 60 + start_min
        end_minutes = end_hour * 60 + end_min
        
        # 筛选数据
        data = []
        for row in rows:
            record = dict(zip(columns, row))
            
            # 时间筛选
            ts = str(record.get('START_TIMESTAMP', ''))
            if len(ts) >= 12:
                try:
                    hour = int(ts[8:10])
                    minute = int(ts[10:12])
                    rec_minutes = hour * 60 + minute
                    if start_minutes <= rec_minutes <= end_minutes:
                        # 转换 XHTIME
                        if 'XHTIME' in record and record.get('XHTIME') is not None:
                            try:
                                record['XHTIME'] = float(record['XHTIME'])
                            except (ValueError, TypeError):
                                record['XHTIME'] = 0.0
                        else:
                            record['XHTIME'] = 0.0
                        data.append(record)
                except (ValueError, IndexError):
                    pass
        
        print(f"  筛选后: {len(data)} 条 ({time_start}-{time_end})")
        print(f"  列名: {columns}")
        
        return data
    
    @staticmethod
    def _load_from_xlsx(file_path):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise ImportError("请安装 openpyxl: pip install openpyxl")
        
        file_path = PathResolver.resolve(file_path)
        print(f"正在加载 Excel 文件: {file_path}")
        wb = load_workbook(file_path)
        ws = wb.active
        headers = []
        data = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = list(row)
            else:
                data.append(dict(zip(headers, row)))
        print(f"加载完成: {len(data)} 条记录")
        return data
    
    @staticmethod
    def _load_from_csv(file_path):
        file_path = PathResolver.resolve(file_path)
        print(f"正在加载 CSV 文件: {file_path}")
        data = []
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(dict(row))
        print(f"加载完成: {len(data)} 条记录")
        return data
