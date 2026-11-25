"""
数据加载器 - 支持多种数据源（XLSX/CSV/API/ETL_LOGS_API）
支持逗号分隔的多模块（如 GZ4,GZ5,GZ6）
"""

import os
import csv
from pathlib import Path
from datetime import datetime


class PathResolver:
    """路径解析器"""
    
    @staticmethod
    def resolve(path):
        """解析路径"""
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
    def load(source, etl_date=None, module_type=None, etl_time_start=None, etl_time_end=None):
        source = str(source).strip().lower()
        
        if source in ('etl_api', 'etl', 'etllogs', 'api'):
            return DataSourceLoader._load_from_etl_api(etl_date, module_type, etl_time_start, etl_time_end)
        
        if source.startswith('api:'):
            return DataSourceLoader._load_from_api(source[4:])
        
        ext = Path(source).suffix.lower()
        
        if ext == '.xlsx':
            return DataSourceLoader._load_from_xlsx(source)
        elif ext == '.csv':
            return DataSourceLoader._load_from_csv(source)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
    
    @staticmethod
    def _load_from_etl_api(etl_date=None, module_type=None, etl_time_start=None, etl_time_end=None):
        """从 ETL 日志 API 加载数据（支持逗号分隔的多模块）"""
        import requests
        
        if module_type is None:
            module_type = 'GZ4,GZ5,GZ6'
        if etl_date is None or etl_date == '':
            etl_date = datetime.now().strftime('%Y-%m-%d')
        
        api_url = "http://eplat.fjsg.com/service/D_A_SMBBCS01_JOBLOGS_LD1D_X"
        modules = [m.strip() for m in module_type.split(',') if m.strip()]
        
        print(f"正在从 ETL 日志 API 加载数据...")
        print(f"  API: {api_url}")
        print(f"  日期: {etl_date}")
        print(f"  模块: {module_type}")
        
        col_mapping = {
            'DATECODE': 'DATE_CODE',
            'SRCSYSTEMID': 'SRC_SYSTEM_ID',
            'SRCOBJECTNAME': 'SRC_OBJECT_NAME',
            'DESSYSTEMID': 'DES_SYSTEM_ID',
            'DESOBJECTNAME': 'DES_OBJECT_NAME',
            'ISSUCCESSFUL': 'IS_SUCCESSFUL',
            'ETLTIME': 'ETL_TIME',
            'LASTUPDATE': 'LAST_UPDATE',
            'MODULETYPE': 'MODULE_TYPE',
            'JOBSEQ': 'JOB_SEQ',
            'CONDITIONORACLE': 'CONDITION_ORACLE',
            'JOBNAME': 'JOB_NAME',
            'SRCOBJECTDESC': 'SRC_OBJECT_DESC',
            'CONDITION': 'CONDITION'
        }
        
        all_data = []
        for mod in modules:
            payload = {
                "clientId": "sgdw-cs01",
                "clientSecret": "40E25CA4DA58B18D506A48048C60ADA6",
                "params": {
                    "etlTime": etl_date,
                    "moduleType": mod
                },
                "showCount": "true",
                "offset": "0",
                "limit": 2000
            }
            
            print(f"  正在加载 {mod} ...", end=' ')
            resp = requests.post(api_url, json=payload, timeout=60)
            resp.raise_for_status()
            
            result_data = resp.json()
            sys_info = result_data.get('__sys__', {})
            if sys_info.get('status', -1) != 0:
                print(f"跳过 (API错误: {sys_info.get('msg', 'Unknown')})")
                continue
            
            blocks = result_data.get('__blocks__', {})
            result = blocks.get('result', {})
            meta = result.get('meta', {})
            columns = [c['name'] for c in meta.get('columns', [])]
            rows = result.get('rows', [])
            
            mod_data = []
            for row in rows:
                record = dict(zip(columns, row))
                mapped = {}
                for col, val in record.items():
                    new_col = col_mapping.get(col, col)
                    mapped[new_col] = val
                
                etl_time = str(mapped.get('ETL_TIME', ''))
                if etl_time:
                    date_part = etl_time[:10]
                    time_part = etl_time[11:16] if len(etl_time) > 11 else ''
                    if date_part != etl_date:
                        continue
                    if time_part:
                        t_start = etl_time_start or '05:30'
                        t_end = etl_time_end or '07:00'
                        if time_part < t_start or time_part > t_end:
                            continue
                
                if mapped.get('MINS') is None:
                    continue
                try:
                    mapped['MINS'] = float(mapped['MINS'])
                except (ValueError, TypeError):
                    continue
                mod_data.append(mapped)
            
            print(f"{len(mod_data)} 条")
            all_data.extend(mod_data)
        
        print(f"加载完成: 共 {len(all_data)} 条有效记录 ({len(modules)} 个模块)")
        return all_data
    
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
    
    @staticmethod
    def _load_from_api(url):
        import requests
        
        print(f"正在从 API 加载数据: {url}")
        
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        
        data = resp.json()
        
        if isinstance(data, dict):
            for key in ['data', 'results', 'items', 'records']:
                if key in data:
                    data = data[key]
                    break
        
        if not isinstance(data, list):
            data = [data]
        
        print(f"加载完成: {len(data)} 条记录")
        return data
