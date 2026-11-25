#!/usr/bin/env python3
"""
CBMS Report Exporter — OpenClaw Skill Script

Exports CBMS (Cost Management System) FineReport Excel files, retrieves a WeCom
access token via HTTP API, uploads the files to WeCom, and sends them.

Supports 15 different report types with configurable parameters.

Dependencies:
    pip install requests openpyxl

Usage:
    python script.py                    # Export all reports to default recipient
    python script.py -r 1,3,5           # Export specific reports
    python script.py -u 230012          # Specify recipient
    python script.py -u 230012 -d 2026-03-15  # Specify date
"""

import os
import sys
import argparse
import shutil
from datetime import date, timedelta
from urllib.parse import quote

# Fix Windows GBK console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="CBMS帆软报表导出工具")
    parser.add_argument("-r", "--reports", help="报表编号，多个用逗号分隔，如 1,3,5（默认：全部）")
    parser.add_argument("-u", "--user", help="收件人工号，多人用 | 分隔（--export-only时可选）")
    parser.add_argument("-d", "--date", help="报表日期，格式 YYYY-MM-DD（默认：前一天）")
    parser.add_argument("--export-only", action="store_true",
                        help="仅导出报表到本地，不发送企微")
    parser.add_argument("--save-path", default=None,
                        help="报表保存路径（--export-only时默认桌面）")
    parser.add_argument("--chatid", default=None,
                        help="企微群聊chatid，指定后发送文件到群聊")
    parser.add_argument("--send-xlsx-each", action="store_true",
                        help="导出后将每个xlsx单独发送到企微（个人+群聊），HTML合并失败时不删除xlsx")
    return parser.parse_args()


from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
from openpyxl.utils import get_column_letter
from copy import copy
import openpyxl
import re
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CONFIG = {
    "FINEREPORT_BASE_URL": os.getenv("FINEREPORT_BASE_URL", "http://172.16.100.25:8080/webroot/decision/view/report"),
    # 每日点检应用的 Token 接口（原驾驶舱 D_A_SMBBRAOC00_TOKEN 已废弃）
    "TOKEN_API_URL": os.getenv("TOKEN_API_URL", "http://eplat.fjsg.com/service/D_A_SMBBRAOC00_MRDJ_TOKEN"),
    "TOKEN_CLIENT_ID": os.getenv("TOKEN_CLIENT_ID", "sgoc-oc01"),
    "TOKEN_CLIENT_SECRET": os.getenv("TOKEN_CLIENT_SECRET", "FCCDFACD0DED39AEE63462C112A4F412"),
    "WECOM_BASE_URL": os.getenv("WECOM_BASE_URL", "https://wecom.fjsg.com.cn"),
    # 每日点检应用 AgentId（原驾驶舱 1000046）
    "WECOM_AGENT_ID": int(os.getenv("WECOM_AGENT_ID", "1000078")),
    "WECOM_TOUSER": os.getenv("WECOM_TOUSER", "230012"),
    # 默认群聊（每日点检群）
    "WECOM_CHATID": os.getenv("WECOM_CHATID", ""),  # 从环境变量或智能表格读取
}

# Temporary file directory
SCRIPT_DIR = Path(__file__).parent
TEMP_DIR = SCRIPT_DIR / "tmp"

# ---------------------------------------------------------------------------
# REPORT REGISTRY
# ---------------------------------------------------------------------------
# Each report has: viewlet, params (list of URL param strings), filename pattern
# {yesterday} = yesterday in YYYYMMDD format
# {yesterday_v1} = yesterday + 'V1' (e.g., 20260329V1)
# {mm} = month with leading zero
# {dd} = day with leading zero

REPORTS = {
    1: {
        "name": "工序指标表",
        "viewlet": "CBZXRCB04.cpt",
        "params": [
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "ACCOUNT_PERIOD={yesterday_v1}",
        ],
        "filename": "{mm}月{dd}日工序指标表.xlsx",
    },
    2: {
        "name": "边际贡献表",
        "viewlet": "CBZXRCB01.cpt",
        "params": [
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
        ],
        "filename": "{mm}月{dd}日边际贡献表.xlsx",
    },
    3: {
        "name": "焦化工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=1",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
        ],
        "filename": "{mm}月{dd}日焦化工序成本表.xlsx",
    },
    4: {
        "name": "烧结工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=2",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
        ],
        "filename": "{mm}月{dd}日烧结工序成本表.xlsx",
    },
    5: {
        "name": "球团工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=3",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
        ],
        "filename": "{mm}月{dd}日球团工序成本表.xlsx",
    },
    6: {
        "name": "炼铁工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=4",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
        ],
        "filename": "{mm}月{dd}日炼铁工序成本表.xlsx",
    },
    7: {
        "name": "长材炼钢工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=5",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=100430401,100430402",
        ],
        "filename": "{mm}月{dd}日长材炼钢工序成本表.xlsx",
    },
    8: {
        "name": "板材炼钢工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=5",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=1004505",
        ],
        "filename": "{mm}月{dd}日板材炼钢工序成本表.xlsx",
    },
    9: {
        "name": "一棒工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=6",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=100430801",
        ],
        "filename": "{mm}月{dd}日一棒工序成本表.xlsx",
    },
    10: {
        "name": "圆棒工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=6",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=100430802",
        ],
        "filename": "{mm}月{dd}日圆棒工序成本表.xlsx",
    },
    11: {
        "name": "中大棒工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=6",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=10043080301",
        ],
        "filename": "{mm}月{dd}日中大棒工序成本表.xlsx",
    },
    12: {
        "name": "一高工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=7",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=100430701",
        ],
        "filename": "{mm}月{dd}日一高工序成本表.xlsx",
    },
    13: {
        "name": "二高工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=7",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=100430702",
        ],
        "filename": "{mm}月{dd}日二高工序成本表.xlsx",
    },
    14: {
        "name": "三高工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=7",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
            "COST_CENTER=100430703",
        ],
        "filename": "{mm}月{dd}日三高工序成本表.xlsx",
    },
    15: {
        "name": "中板工序成本表",
        "viewlet": "CBZXRCB30.cpt",
        "params": [
            "TYPE=8",
            "COMPANY_CODE=100",
            "MONTH={yesterday}",
            "MONTH_C={yesterday_v1}",
        ],
        "filename": "{mm}月{dd}日中板工序成本表.xlsx",
    },
}


# ---------------------------------------------------------------------------
def get_date_formats(target_date: date) -> dict:
    """Get various date format strings for URL parameters and filenames"""
    return {
        "yesterday": target_date.strftime("%Y%m%d"),
        "yesterday_v1": target_date.strftime("%Y%m%d") + "V1",
        "mm": target_date.strftime("%m"),
        "dd": target_date.strftime("%d"),
        "yyyy_mm_dd": target_date.strftime("%Y-%m-%d"),
    }


# ---------------------------------------------------------------------------
def build_report_url(report: dict, date_fmt: dict) -> str:
    """Build the FineReport export URL for a given report"""
    base_url = CONFIG["FINEREPORT_BASE_URL"]
    viewlet = report["viewlet"]

    # Build URL with viewlet and export format
    # extype=simple: 原样导出, preserves original layout without pagination artifacts
    url = f"{base_url}?viewlet={viewlet}&op=export&format=excel&extype=simple"

    # Add parameters with date substitution
    for param in report["params"]:
        # Substitute date placeholders
        param_value = param
        for key, value in date_fmt.items():
            param_value = param_value.replace("{" + key + "}", value)
        url += f"&{param_value}"

    return url


# ---------------------------------------------------------------------------
def format_excel(file_path: Path) -> Path:
    """
    Minimally normalize FineReport exports for HTML conversion.

    FineReport exports already have professional styling (fonts, fills, borders,
    merged cells, freeze panes). This function preserves ALL original formatting
    and only:
    - Ensures consistent number formatting for data cells
    - Preserves original freeze panes (FineReport typically freezes at row 6)

    We do NOT overwrite fonts, fills, borders, alignment, or column widths.
    """
    wb = openpyxl.load_workbook(file_path)

    for ws in wb.worksheets:
        max_row = ws.max_row
        max_col = ws.max_column

        if max_row == 0 or max_col == 0:
            continue

        # Preserve original freeze panes set by FineReport
        # FineReport typically uses: 日成本表=A6, 边际贡献表=C1, 工序指标表=A3
        original_freeze = ws.freeze_panes

        # Light number format normalization for numeric data cells
        # Only apply to cells that don't already have a number format
        for row_idx in range(1, max_row + 1):
            for col_idx in range(1, max_col + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                if cell.value is not None and isinstance(cell.value, (int, float)):
                    if not cell.number_format or cell.number_format == 'General':
                        cell.number_format = '#,##0.00'

        # Ensure freeze panes are preserved (don't overwrite)
        if original_freeze:
            ws.freeze_panes = original_freeze

    wb.save(file_path)
    print(f"    已格式化: {file_path.name}")
    return file_path


# ---------------------------------------------------------------------------
# HTML export functions
# ---------------------------------------------------------------------------

# Header keywords to detect header rows in FineReport exports
_HEADER_KEYWORDS = [
    "项目", "单位", "单价", "指标", "名称", "产量", "售价", "成本",
    "边际", "固定", "变动", "差异", "标准", "实际", "累计", "当日",
    "用量", "总成本", "人工", "折旧", "检验", "修理", "小计", "税费",
    "利润", "波动", "收入", "费用", "数量", "金额", "本期", "上期",
    "同比", "环比", "完成", "预算", "计划",
]

# Title keywords to detect title row (row 1)
_TITLE_KEYWORDS = ["日", "月", "表", "报表", "测算", "成本"]


def _detect_row_type(ws, row_idx: int, max_col: int) -> str:
    """Detect whether a row is title, header, sub-header, or data row.

    Uses FineReport freeze panes as primary signal, with keyword heuristics
    as fallback. FineReport exports consistently freeze at the row right
    after the header area (e.g. A6 means rows 1-5 are non-data, C1 means
    rows 1-2 are non-data in the header area).

    When freeze_panes is set, rows at or beyond the freeze boundary are
    ALWAYS treated as data — never promoted to header by heuristics.
    """
    vals = []
    for c in range(1, max_col + 1):
        v = ws.cell(row=row_idx, column=c).value
        if v is not None:
            vals.append(str(v))

    text = " ".join(vals)

    # Use freeze pane to determine the header boundary
    # FineReport: A6 = freeze at col A row 6 => rows 1-5 are headers
    # FineReport: A3 = freeze at col A row 3 => rows 1-2 are headers
    freeze_row = None
    if ws.freeze_panes:
        try:
            from openpyxl.utils import coordinate_to_tuple
            fr, fc = coordinate_to_tuple(ws.freeze_panes)
            freeze_row = fr
        except Exception:
            pass

    # Title row: always row 1 in FineReport exports
    if row_idx == 1:
        return "title"

    # When freeze_panes is set, only rows BEFORE the freeze boundary
    # can be headers. Rows at or beyond freeze are always data.
    # SPECIAL CASE: fr=1 means "freeze columns only, no row freeze"
    #   (e.g. C1 = freeze cols A-B, no frozen rows). In this case,
    #   fall through to keyword heuristics for row detection.
    if freeze_row is not None:
        if freeze_row > 1 and row_idx >= freeze_row:
            return "data"
        if freeze_row > 1:
            # Row is within freeze zone (header area)
            for kw in _HEADER_KEYWORDS:
                if kw in text:
                    return "header"
            # Within freeze zone but no keywords: sub_header
            if row_idx > 1:
                return "sub_header"

    # No freeze_panes — use keyword heuristics
    header_kw_count = sum(1 for kw in _HEADER_KEYWORDS if kw in text)
    if header_kw_count >= 2:
        return "header"
    if header_kw_count == 1 and row_idx <= 5:
        return "header"
    if row_idx <= 3 and text.strip() and header_kw_count == 0:
        return "sub_header"

    return "data"


# Excel indexed color palette (standard 56-color palette)
_INDEXED_COLORS = [
    '#000000','#FFFFFF','#FF0000','#00FF00','#0000FF','#FFFF00','#FF00FF','#00FFFF',
    '#800000','#008000','#000080','#808000','#800080','#008080','#C0C0C0','#808080',
    '#9999FF','#993366','#FFFFCC','#CCFFFF','#660066','#FF8080','#0066CC','#CCCCFF',
    '#000080','#FF00FF','#FFFF00','#00FFFF','#800080','#800000','#008080','#0000FF',
    '#00CCFF','#CCFFFF','#CCFFCC','#FFFF99','#99CCFF','#FF99CC','#CC99FF','#FFCC99',
    '#3366FF','#33CCCC','#99CC00','#FFCC00','#FF9900','#FF6600','#666699','#969696',
    '#003366','#339966','#003300','#333300','#993300','#993366','#333399','#333333',
]

# Theme color mapping (openpyxl theme index -> default color)
_THEME_COLORS = {
    0: '#FFFFFF', 1: '#000000', 2: '#4472C4', 3: '#ED7D31',
    4: '#FFC000', 5: '#5B9BD5', 6: '#70AD47', 7: '#264478',
    8: '#9B9B9B', 9: '#D9D9D9',
}


def _extract_color(color_obj):
    """Extract CSS color string from openpyxl Color object.

    FineReport uses indexed colors extensively (e.g. indexed=64 for 'automatic'/black,
    indexed=8 for dark blue fills, etc.). This function handles all color types:
    rgb, theme, indexed, and themed (theme + tint for fills).

    IMPORTANT: openpyxl Color.theme and Color.indexed properties may raise
    ValueError when the underlying XML has unexpected types. We safely catch these.
    """
    if not color_obj:
        return None
    try:
        color_type = getattr(color_obj, 'type', None)

        # RGB type: direct hex color (most common in FineReport)
        if color_type == 'rgb':
            rgb = None
            try:
                raw = color_obj.rgb
                if raw:
                    rgb = str(raw)
            except Exception:
                pass
            if not rgb:
                return None
            if len(rgb) == 8:
                rgb = rgb[2:]  # Strip ARGB alpha prefix
            if rgb and rgb.upper() != '000000':
                return f'#{rgb.upper()}'
            return None  # black -> None = use default

        # Theme + tint (FineReport fills sometimes use this)
        if color_type == 'theme':
            theme = None
            try:
                theme = color_obj.theme
            except (ValueError, TypeError):
                pass
            if theme is not None:
                base = _THEME_COLORS.get(theme, '#000000')
                tint = getattr(color_obj, 'tint', 0) or 0
                if tint != 0:
                    return _apply_tint(base, tint)
                return base
            # Theme but theme is None -> try rgb fallback
            return None

        # Indexed color (FineReport borders and fills commonly use indexed)
        if color_type == 'indexed':
            idx = None
            try:
                idx = color_obj.indexed
            except (ValueError, TypeError):
                pass
            if idx is not None and 0 <= idx < len(_INDEXED_COLORS):
                return _INDEXED_COLORS[idx]
            return None

        # Fallback: rgb field exists but type not explicitly 'rgb'
        try:
            raw = color_obj.rgb
            if raw:
                rgb = str(raw)
                if len(rgb) == 8:
                    rgb = rgb[2:]
                if rgb and rgb.upper() != '000000':
                    return f'#{rgb.upper()}'
        except Exception:
            pass

    except Exception:
        pass
    return None


def _apply_tint(hex_color: str, tint: float) -> str:
    """Apply Excel-style tint to a hex color.

    tint < 0: darken (mix with black), tint > 0: lighten (mix with white).
    Formula matches Excel's OpenXML spec for CT_Color.
    """
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    if tint < 0:
        factor = 1.0 + tint
        r, g, b = int(r * factor), int(g * factor), int(b * factor)
    elif tint > 0:
        factor = 1.0 - tint
        r = int(r * factor + 255 * tint)
        g = int(g * factor + 255 * tint)
        b = int(b * factor + 255 * tint)
    return f'#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}'


def build_cell_css(cell, row_type: str, row_idx: int, col_idx: int) -> str:
    """Build CSS style string, faithfully preserving original FineReport styles.

    Key improvements:
    - Handle indexed colors (FineReport uses them for borders/fills)
    - Handle theme+tint colors (FineReport header fills)
    - Always emit explicit border colors (not relying on CSS defaults)
    """
    styles = []

    # Font - use original if available, fall back to sensible defaults
    font = cell.font
    font_name = font.name if (font and font.name) else '微软雅黑'
    # Strip quotes from font name. When the font name is embedded inside an
    # HTML style="..." attribute, wrapping it in double-quotes (e.g.
    # font-family: "宋体") prematurely terminates the attribute value.
    # Single-quoting or no-quoting avoids the conflict.
    font_name = font_name.replace('"', '').replace("'", '')
    # Only quote names that contain spaces (CSS requires it); prefer single quotes
    # inside double-quoted HTML attributes to avoid parser conflicts.
    if any(c in font_name for c in (' ', ',', ';', '!')):
        styles.append(f"font-family: '{font_name}', sans-serif")
    else:
        styles.append(f'font-family: {font_name}, sans-serif')

    if font:
        if font.size:
            styles.append(f'font-size: {font.size}pt')
        if font.bold:
            styles.append('font-weight: bold')
        if font.italic:
            styles.append('font-style: italic')
        if font.underline:
            styles.append('text-decoration: underline')
    # Color - try to extract from font, fallback based on row_type
    font_color = _extract_color(font.color) if font else None
    if font_color:
        styles.append(f'color: {font_color}')

    # Fill (background) - preserve original FineReport colors
    # FineReport often uses bgColor for cell background (e.g. #D9E1F2 for title, #DBEFFF for header)
    # We check both fgColor and bgColor and prefer the non-black one
    fill = cell.fill
    has_fill = False
    if fill:
        if fill.patternType == 'solid' or fill.patternType:
            fg_color = _extract_color(fill.fgColor)
            bg_color = _extract_color(fill.bgColor)
            use_color = None
            if fg_color:
                use_color = fg_color
            elif bg_color:
                use_color = bg_color
            if use_color:
                # Drop #E7F8FD (FineReport default data-row fill) so CSS
                # nth-child zebra striping takes over for visual clarity.
                # Keep all non-default fills (#FFFF00, #DBEFFF, etc.).
                if use_color.upper() != '#E7F8FD':
                    styles.append(f'background-color: {use_color}')
                    has_fill = True
        elif fill.patternType and fill.patternType != 'none':
            fg_color = _extract_color(fill.fgColor)
            if fg_color and fg_color.upper() != '#E7F8FD':
                styles.append(f'background-color: {fg_color}')
                has_fill = True

    # Row-type fallback for cells without original styling
    has_font_color = font_color is not None
    if not has_font_color and not has_fill:
        if row_type == 'title':
            styles.append('color: #666666')
            styles.append('font-weight: bold')
            styles.append('font-size: 17pt')
        elif row_type == 'header':
            styles.append('color: #1a56b0')
            styles.append('background-color: #B8D4F0')
            styles.append('font-weight: bold')
        elif row_type == 'sub_header':
            styles.append('color: #666666')
            styles.append('background-color: #D6E6F5')
            styles.append('font-weight: bold')
            styles.append('font-size: 10pt')

    # Border - faithfully preserve original FineReport border styles
    border = cell.border
    has_border = False
    if border:
        border_css_map = {
            'thin': '1px solid', 'medium': '2px solid', 'thick': '3px solid',
            'dotted': '1px dotted', 'dashed': '1px dashed', 'double': '3px double',
            'hair': '0.5px solid', 'mediumDashed': '2px dashed',
            'dashDot': '1px dashed', 'slantDashDot': '1px dashed',
        }
        for side_name in ['left', 'right', 'top', 'bottom']:
            side = getattr(border, side_name)
            if side and side.style:
                border_css = border_css_map.get(side.style, '1px solid')
                side_color = _extract_color(side.color)
                # FineReport indexed color 64 = automatic (black)
                if not side_color:
                    side_color = '#000000'
                styles.append(f'border-{side_name}: {border_css} {side_color}')
                has_border = True
    if not has_border:
        # All rows get visible borders for consistent table rendering
        styles.append('border: 1px solid #888888')

    # Alignment - preserve original
    alignment = cell.alignment
    if alignment:
        if alignment.horizontal:
            styles.append(f'text-align: {alignment.horizontal}')
        if alignment.vertical:
            vmap = {'center': 'middle', 'top': 'top', 'bottom': 'bottom'}
            styles.append(f'vertical-align: {vmap.get(alignment.vertical, "middle")}')
        else:
            styles.append('vertical-align: middle')
        if alignment.wrap_text:
            styles.append('white-space: normal')
            styles.append('word-break: break-all')
    else:
        styles.append('vertical-align: middle')

    # Padding for readability
    styles.append('padding: 3px 6px')

    return '; '.join(styles)


def format_cell_value(value, number_format: str) -> str:
    """Format cell value for HTML display"""
    if value is None:
        return ''

    from datetime import datetime as dt_datetime, date as dt_date

    if isinstance(value, dt_datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, dt_date):
        return value.strftime('%Y-%m-%d')

    if isinstance(value, (int, float)):
        fmt = number_format or ''
        if '%' in fmt:
            return f'{value * 100:.2f}%'
        if '#,##0.00' in fmt or '0.00' in fmt:
            return f'{value:,.2f}'
        if '#,##0' in fmt:
            return f'{value:,.0f}'
        if isinstance(value, float):
            if value == int(value):
                return str(int(value))
            return f'{value:.2f}'
        return str(value)

    # Escape HTML special characters
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def sheet_to_html(ws) -> str:
    """Convert a worksheet to a responsive HTML table, preserving merged cells.

    Reads freeze_panes from Excel to implement:
    - Row freeze: thead fills from rows 1 to freeze_row-1; table-wrapper
      overflow:auto + thead position:sticky freezes header rows on scroll.
    - Column freeze: first freeze_col-1 columns get .colhead class with
      position:sticky left:0 + opaque background, freezing them as user
      scrolls horizontally.
    """
    max_row = ws.max_row
    max_col = ws.max_column

    if max_row == 0 or max_col == 0:
        return ''

    # Parse freeze panes
    freeze_cols = 0
    try:
        from openpyxl.utils import coordinate_to_tuple
        fr, fc = coordinate_to_tuple(ws.freeze_panes) if ws.freeze_panes else (None, None)
        if fc is not None and fc > 1:
            freeze_cols = fc - 1  # Columns A through fc-1 are frozen per Excel
        else:
            # When Excel has row-only freeze (e.g. A6, A5), text column A or B
            # (the "项目"/"名称"/"指标" column) should still be frozen for
            # horizontal scrolling. In FineReport exports, column A is often
            # empty due to merged cells; the real label col is B.
            col_a_keywords = ['项', '名称', '指标', '工序', '品种', '规格', '产线']
            for col_chk in (1, 2):  # Check A then B
                a_text = ''
                for r in range(1, min(6, max_row+1)):
                    v = ws.cell(row=r, column=col_chk).value
                    if v:
                        a_text += str(v) + ' '
                if any(kw in a_text for kw in col_a_keywords):
                    freeze_cols = col_chk  # Freeze through this column
                    break
    except Exception:
        pass

    # Drop column A if entirely empty (common in FineReport exports where
    # merged cells push labels into column B). Adjust freeze_cols down by 1
    # if A was being frozen (it no longer exists).
    skip_cols = set()
    try:
        col_a_empty = True
        for r in range(1, min(max_row + 1, 20)):
            v = ws.cell(row=r, column=1).value
            if v is not None and str(v).strip() != '':
                col_a_empty = False
                break
        if col_a_empty:
            skip_cols.add(1)
            if freeze_cols >= 1:
                freeze_cols -= 1  # A is gone, B→A
                if freeze_cols < 1:
                    freeze_cols = 0
    except Exception:
        pass

    # Build merged cell map
    hidden_cells = set()
    merge_map = {}

    for mr in ws.merged_cells.ranges:
        min_row, min_col = mr.min_row, mr.min_col
        max_r, max_c = mr.max_row, mr.max_col
        rowspan = max_r - min_row + 1
        colspan = max_c - min_col + 1
        merge_map[(min_row, min_col)] = (rowspan, colspan)
        for r in range(min_row, max_r + 1):
            for c in range(min_col, max_c + 1):
                if (r, c) != (min_row, min_col):
                    hidden_cells.add((r, c))

    # Pre-detect row types for all rows
    row_types = {}
    for row_idx in range(1, max_row + 1):
        row_types[row_idx] = _detect_row_type(ws, row_idx, max_col)

    # Calculate total table width in Excel units for responsive scaling
    total_excel_width = 0
    for col_idx in range(1, max_col + 1):
        if col_idx in skip_cols:
            continue
        col_letter = get_column_letter(col_idx)
        w = 10
        if col_letter in ws.column_dimensions and ws.column_dimensions[col_letter].width:
            w = ws.column_dimensions[col_letter].width
        total_excel_width += w

    html = ['<div class="table-wrapper">', '<table class="report-table">']

    # Column widths via colgroup — use percentage for responsive sizing
    # Also compute cumulative px widths for column freeze (sticky positioning)
    html.append('<colgroup>')
    frozen_left_px = [0.0]  # left offset for each frozen column
    col_out_idx = {}          # map original Excel col index -> output col index (0-based)
    out_col = 0

    for col_idx in range(1, max_col + 1):
        if col_idx in skip_cols:
            col_out_idx[col_idx] = -1  # skipped
            continue
        out_col += 1
        col_out_idx[col_idx] = out_col  # 1-based output column index
        col_letter = get_column_letter(col_idx)
        exc_w = 10
        if col_letter in ws.column_dimensions and ws.column_dimensions[col_letter].width:
            exc_w = ws.column_dimensions[col_letter].width
        px_w = int(exc_w * 6.5)
        pct = max(exc_w / max(total_excel_width, 1) * 100, 3)
        html.append(f'<col style="width: {pct:.1f}%; min-width: {px_w}px">')
        if out_col <= freeze_cols:
            frozen_left_px.append(frozen_left_px[-1] + px_w)
    html.append('</colgroup>')

    # Headers
    html.append('<thead>')
    for row_idx in range(1, max_row + 1):
        row_type = row_types[row_idx]
        if row_type not in ('title', 'header', 'sub_header'):
            break

        html.append('<tr>')
        for col_idx in range(1, max_col + 1):
            if col_idx in skip_cols:
                continue
            if (row_idx, col_idx) in hidden_cells:
                continue

            cell = ws.cell(row=row_idx, column=col_idx)
            rowspan, colspan = merge_map.get((row_idx, col_idx), (1, 1))
            css = build_cell_css(cell, row_type, row_idx, col_idx)
            value = format_cell_value(cell.value, cell.number_format)

            tag = 'th'
            # Column freeze: inject sticky left for frozen columns
            freeze_css = ''
            oc = col_out_idx.get(col_idx, 0)
            if oc >= 1 and oc <= freeze_cols and oc - 1 <= len(frozen_left_px) - 1:
                # Extract existing background-color or use thead default
                bg_match = re.search(r'background-color:\s*([^;]+)', css)
                bg = bg_match.group(1) if bg_match else '#B4C8E0'
                freeze_css = f' position: sticky; left: {frozen_left_px[oc-1]}px; z-index: 11; background-color: {bg};'
            attrs = f' style="{css};{freeze_css}"'
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            if colspan > 1:
                attrs += f' colspan="{colspan}"'

            html.append(f'<{tag}{attrs}>{value}</{tag}>')
        html.append('</tr>')
    html.append('</thead>')

    # Body - data rows
    data_start = None
    for row_idx in range(1, max_row + 1):
        if row_types[row_idx] not in ('title', 'header', 'sub_header'):
            data_start = row_idx
            break

    if data_start:
        html.append('<tbody>')
        data_row_count = 0
        for row_idx in range(data_start, max_row + 1):
            row_type = row_types[row_idx]
            # Detect category/summary rows that should NOT get zebra striping.
            # Only rows with #FFFF00 (category total) or #DBEFFF (header bleed)
            # are skipped; rows with just #E7F8FD (FineReport default) are normal
            # data rows that DO get zebra striping.
            row_is_special = False
            row_has_num = False
            for col_idx in range(1, max_col + 1):
                if (row_idx, col_idx) in hidden_cells:
                    continue
                cell = ws.cell(row=row_idx, column=col_idx)
                if cell.fill and cell.fill.patternType:
                    fg = _extract_color(cell.fill.fgColor)
                    bg = _extract_color(cell.fill.bgColor)
                    fc = (fg or bg or '').upper().lstrip('#')
                    # #FFFF00 = category total row, #DBEFFF = header area bleed
                    if fc in ('FFFF00', 'DBEFFF'):
                        row_is_special = True
                if isinstance(cell.value, (int, float)) and cell.value is not None:
                    row_has_num = True

            # Zebra striping: Python-side counter (avoids CSS nth-child
            # pitfalls when category rows are interleaved with data rows)
            row_style = ''
            if not row_is_special and row_has_num:
                data_row_count += 1
                if data_row_count % 2 == 0:
                    row_style = ' style="background-color: #E7F8FD"'
            html.append(f'<tr{row_style}>')
            for col_idx in range(1, max_col + 1):
                if col_idx in skip_cols:
                    continue
                if (row_idx, col_idx) in hidden_cells:
                    continue

                cell = ws.cell(row=row_idx, column=col_idx)
                rowspan, colspan = merge_map.get((row_idx, col_idx), (1, 1))
                css = build_cell_css(cell, row_type, row_idx, col_idx)
                value = format_cell_value(cell.value, cell.number_format)

                # Apply special classes for data cells
                extra_class = ''
                if isinstance(cell.value, (int, float)) and cell.value is not None:
                    extra_class = ' class="num-cell"'

                # Column freeze: inject sticky left for frozen columns in tbody
                freeze_css = ''
                oc = col_out_idx.get(col_idx, 0)
                if oc >= 1 and oc <= freeze_cols and oc - 1 <= len(frozen_left_px) - 1:
                    # Extract existing background-color, or use row style bg, or white default.
                    # Must NOT use 'inherit' — transparent bg makes frozen cells invisible
                    # on top of scrolled content.
                    bg_match = re.search(r'background-color:\s*([^;]+)', css)
                    if bg_match:
                        bg = bg_match.group(1).strip()
                    else:
                        row_bg = re.search(r'background-color:\s*([^;"]+)', row_style)
                        bg = row_bg.group(1).strip() if row_bg else '#FFFFFF'
                    freeze_css = f' position: sticky; left: {frozen_left_px[oc-1]}px; z-index: 5; background-color: {bg};'

                attrs = f'{extra_class} style="{css};{freeze_css}"'
                if rowspan > 1:
                    attrs += f' rowspan="{rowspan}"'
                if colspan > 1:
                    attrs += f' colspan="{colspan}"'

                html.append(f'<td{attrs}>{value}</td>')
            html.append('</tr>')
        html.append('</tbody>')

    html.append('</table>')
    html.append('</div>')
    return '\n'.join(html)


def generate_html_report(exported_files: list, date_label: str) -> Path:
    """
    Generate a single HTML file with:
    - TOC as responsive card grid (mobile-friendly)
    - All sheet content as styled HTML tables
    - JS-based smooth scroll navigation for reliable mobile back-links
    """
    toc_cards = []  # Card-style TOC entries
    content_sections = []

    for idx, (report_label, file_path) in enumerate(exported_files):
        # report_label can be either an int (REPORTS key) or a str (display name)
        if isinstance(report_label, int):
            report_name = REPORTS[report_label]['name']
            report_id = report_label
        else:
            report_name = report_label
            report_id = idx + 1  # 1-based display numbering
        wb = openpyxl.load_workbook(file_path)

        # Build TOC card — single-sheet: card links directly to content;
        # multi-sheet: card body shows sub-sheet tag pills
        if len(wb.sheetnames) == 1:
            # Single sheet — card header IS the link, no sub-sheet tags needed
            sheet_id = f'report_{report_id}_sheet_0'
            toc_cards.append(f'''\
<a class="toc-card" href="#{sheet_id}" data-target="{sheet_id}"
   onclick="return scrollToTarget('{sheet_id}')">
  <div class="toc-card-header">
    <span class="num">{report_id}</span>
    <span>{report_name}</span>
  </div>
</a>''')
        else:
            # Multi-sheet — show sub-sheet pills
            sheet_tags = []
            for sheet_idx, sheet_name in enumerate(wb.sheetnames):
                sid = f'report_{report_id}_sheet_{sheet_idx}'
                safe_name = sheet_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                sheet_tags.append(
                    f'<a class="sheet-tag" href="#{sid}" '
                    f'onclick="return scrollToTarget(\'{sid}\')">{safe_name}</a>'
                )
            toc_cards.append(f'''\
<a class="toc-card" href="#report_{report_id}" data-target="report_{report_id}"
   onclick="return scrollToTarget('report_{report_id}')">
  <div class="toc-card-header">
    <span class="num">{report_id}</span>
    <span>{report_name}</span>
  </div>
  <div class="toc-card-body">
    {''.join(sheet_tags)}
  </div>
</a>''')

        # Content section
        content_sections.append(f'<div class="report-section" id="report_{report_id}">')
        content_sections.append(f'<h2>{report_name}</h2>')

        for sheet_idx, sheet_name in enumerate(wb.sheetnames):
            sheet_id = f'report_{report_id}_sheet_{sheet_idx}'
            ws = wb[sheet_name]
            safe_name = sheet_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            content_sections.append(f'<div class="sheet-section" id="{sheet_id}">')
            content_sections.append(f'<h3>{safe_name}</h3>')
            content_sections.append(sheet_to_html(ws))
            content_sections.append(
                '<p class="back-link">'
                '<a href="#toc" onclick="return scrollToTarget(\'toc\')">'
                '&#8593; 返回目录</a></p>'
            )
            content_sections.append('</div>')

        content_sections.append('</div>')
        wb.close()

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=2.0, user-scalable=yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<title>CBMS成本管理报表 - {date_label}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: "微软雅黑", "Microsoft YaHei", -apple-system, sans-serif;
    padding: 12px;
    background: #f0f2f5;
    color: #333;
    line-height: 1.5;
    -webkit-text-size-adjust: 100%;
}}
h1 {{ text-align: center; color: #1a1a2e; margin-bottom: 6px; font-size: clamp(18px, 5vw, 24px); }}
h2 {{
    color: #fff;
    background: #4472C4;
    padding: 10px 16px;
    margin: 0 0 16px;
    border-radius: 6px;
    font-size: clamp(15px, 4vw, 18px);
}}
h3 {{
    color: #333;
    margin: 0 0 8px;
    padding: 8px 12px;
    background: #D9E1F2;
    border-left: 4px solid #4472C4;
    font-size: clamp(13px, 3.5vw, 15px);
    border-radius: 3px;
}}

/* ============ TOC CARDS ============ */
#toc {{
    background: #fff;
    padding: 20px 16px;
    border-radius: 10px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    margin-bottom: 24px;
}}
#toc > p {{
    text-align: center;
    color: #888;
    margin-bottom: 18px;
    font-size: 14px;
}}
.toc-cards {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
}}
/* Wider screens: maximum 3 columns for a clean desktop layout */
@media (min-width: 1100px) {{
    .toc-cards {{
        grid-template-columns: repeat(3, 1fr);
    }}
}}
@media (min-width: 700px) and (max-width: 1099px) {{
    .toc-cards {{
        grid-template-columns: repeat(2, 1fr);
    }}
}}
@media (max-width: 699px) {{
    .toc-cards {{
        grid-template-columns: 1fr;
    }}
}}
.toc-card {{
    display: block;
    background: #f8f9fc;
    border: 1px solid #e0e4ed;
    border-radius: 8px;
    text-decoration: none;
    transition: all 0.2s ease;
    overflow: hidden;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
}}
.toc-card:hover, .toc-card:active {{
    border-color: #4472C4;
    box-shadow: 0 2px 8px rgba(68,114,196,0.2);
    transform: translateY(-1px);
}}
.toc-card-header {{
    display: flex;
    align-items: center;
    padding: 10px 14px;
    background: #4472C4;
    color: #fff;
    font-size: 14px;
    font-weight: bold;
    gap: 8px;
}}
.toc-card-header .num {{
    background: rgba(255,255,255,0.25);
    min-width: 26px;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    flex-shrink: 0;
}}
.toc-card-header span:last-child {{
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.toc-card-body {{
    padding: 8px 14px 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 4px 6px;
    max-height: 120px;
    overflow-y: auto;
}}
.sheet-tag {{
    display: inline-block;
    font-size: 11px;
    color: #555;
    background: #e8ecf4;
    padding: 3px 8px;
    border-radius: 12px;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-decoration: none;
    transition: background 0.15s;
}}
.sheet-tag:hover, .sheet-tag:active {{
    background: #4472C4;
    color: #fff;
}}

/* ============ REPORT SECTIONS ============ */
.report-section {{
    background: #fff;
    padding: 20px 16px;
    border-radius: 10px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    margin-bottom: 24px;
}}
.sheet-section {{
    margin-bottom: 28px;
}}
.back-link {{
    text-align: right;
    margin-top: 8px;
    margin-bottom: 16px;
    padding: 6px 0;
    border-top: 1px solid #eee;
}}
.back-link a {{
    display: inline-block;
    color: #4472C4;
    text-decoration: none;
    font-size: 13px;
    padding: 6px 14px;
    border: 1px solid #4472C4;
    border-radius: 20px;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
}}
.back-link a:hover, .back-link a:active {{
    background: #4472C4;
    color: #fff;
}}

/* ============ RESPONSIVE TABLE ============ */
/* Table wrapper with freeze-pane support:
   overflow:auto creates a scroll container so thead position:sticky
   can freeze header rows as user scrolls vertically.
   max-height caps the visible area; horizontal scroll still works. */
.table-wrapper {{
    overflow: auto;
    max-height: 80vh;
    -webkit-overflow-scrolling: touch;
    border: 2px solid #999999;
    border-radius: 6px;
    background: #fff;
}}
.report-table {{
    /* border-collapse:separate is required for position:sticky on <td>/<th>
       to work across all browsers. border-spacing:0 keeps the collapsed look. */
    border-collapse: separate;
    border-spacing: 0;
    width: auto;
    min-width: 100%;
    font-size: clamp(10px, 2.5vw, 12px);
    table-layout: auto;
    border: 1px solid #888888;
}}
.report-table thead {{
    position: sticky;
    top: 0;
    z-index: 10;
}}
/* Ensure header cells are opaque so scrolled content doesn't bleed through */
.report-table thead th, .report-table thead td {{
    background-color: #B4C8E0;
}}
.report-table thead tr:first-child th {{
    border-top: 2px solid #666666;
}}
/* Frozen columns: must sit above scrolled cells */
.report-table th[style*="sticky"], .report-table td[style*="sticky"] {{
    background-color: #fff;
    box-shadow: 2px 0 6px rgba(0,0,0,0.08);
}}
.report-table tbody tr[style*="E7F8FD"] td[style*="sticky"] {{
    background-color: #E7F8FD;
}}
.report-table tbody tr:last-child td {{
    border-bottom: 2px solid #666666;
}}
/* Zebra striping applied inline via <tr style="..."> — category rows
   (#FFFF00) and empty rows keep no background; data rows get alternating
   #E7F8FD computed server-side to avoid CSS nth-child interleave bugs. */
.report-table th, .report-table td {{
    white-space: nowrap;
    min-width: 50px;
    border: 1px solid #cccccc;
}}
.report-table .num-cell {{
    text-align: right;
    font-variant-numeric: tabular-nums;
}}


/* ============ FLOATING NAV ============ */
.back-top {{
    position: fixed;
    bottom: 24px;
    right: 20px;
    background: #4472C4;
    color: #fff;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    box-shadow: 0 3px 12px rgba(68,114,196,0.35);
    z-index: 999;
    font-size: 20px;
    font-weight: bold;
    transition: all 0.2s;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
}}
.back-top:hover, .back-top:active {{
    background: #365084;
    transform: scale(1.1);
}}

/* ============ MOBILE ============ */
@media (max-width: 600px) {{
    body {{ padding: 6px; }}
    .toc-cards {{ grid-template-columns: 1fr; gap: 6px; }}
    .toc-card-header {{ font-size: 12px; padding: 6px 10px; }}
    .toc-card-header .num {{ width: 22px; height: 22px; font-size: 10px; }}
    .toc-card-body {{ max-height: 90px; padding: 6px 10px; }}
    .sheet-tag {{ font-size: 9px; padding: 2px 5px; border-radius: 10px; }}
    .report-section {{ padding: 10px 6px; border-radius: 6px; }}
    .report-table {{ min-width: 420px; font-size: 9px; }}
    .report-table th, .report-table td {{ padding: 2px 3px !important; min-width: 40px; }}
    .back-top {{ bottom: 12px; right: 8px; width: 36px; height: 36px; font-size: 16px; }}
    h2 {{ padding: 6px 10px; font-size: 14px; }}
    h3 {{ padding: 4px 8px; font-size: 12px; }}
    #toc {{ padding: 12px 6px; }}
    #toc > p {{ font-size: 12px; }}
}}
</style>
<script>
// Smooth scroll to target with offset (accounts for any sticky headers)
function scrollToTarget(id) {{
    var el = document.getElementById(id);
    if (el) {{
        var top = el.getBoundingClientRect().top + window.pageYOffset - 60;
        window.scrollTo({{ top: top, behavior: 'smooth' }});
        // Fallback for browsers without smooth scroll support
        setTimeout(function() {{
            if (Math.abs(window.pageYOffset - top) > 100) {{
                window.scrollTo(0, top);
            }}
        }}, 600);
    }}
    return false;
}}

document.addEventListener('DOMContentLoaded', function() {{
    // Intercept all TOC card clicks for reliable navigation
    document.querySelectorAll('.toc-card').forEach(function(card) {{
        card.addEventListener('click', function(e) {{
            var targetId = this.getAttribute('data-target');
            if (targetId) {{
                e.preventDefault();
                scrollToTarget(targetId);
            }}
        }});
    }});

    // Intercept all back-to-TOC links for reliable navigation
    document.querySelectorAll('.back-link a[href="#toc"]').forEach(function(link) {{
        link.addEventListener('click', function(e) {{
            e.preventDefault();
            scrollToTarget('toc');
        }});
    }});

    // Floating back-to-top button
    var backTop = document.querySelector('.back-top');
    if (backTop) {{
        backTop.addEventListener('click', function(e) {{
            e.preventDefault();
            scrollToTarget('toc');
        }});
    }}
}});
</script>
</head>
<body>

<div id="toc">
<h1>&#x1F4CA; CBMS成本管理报表</h1>
<p>报表日期：{date_label}</p>
<div class="toc-cards">
{''.join(toc_cards)}
</div>
</div>

{''.join(content_sections)}

<a href="#toc" class="back-top" aria-label="返回目录">&#8593;</a>

</body>
</html>'''

    html_path = TEMP_DIR / f'{date_label.replace("-", "")}_CBMS报表.html'
    html_path.write_text(html, encoding='utf-8')
    print(f"  已生成HTML: {html_path.name} ({html_path.stat().st_size:,} bytes)")
    return html_path


# ---------------------------------------------------------------------------
def merge_sheets_if_needed(file_path: Path, report_name: str, date_label: str) -> Path:
    """
    [DISABLED] Previously merged multi-sheet workbooks.
    Now we keep original sheet structure after column cleaning.
    """
    return file_path  # No merge, keep original structure

    # Create a new workbook for merged output
    merged_wb = openpyxl.Workbook()
    merged_ws = merged_wb.active
    merged_ws.title = "汇总"

    # Style definitions
    title_font = Font(name="微软雅黑", size=14, bold=True)
    header_font = Font(name="微软雅黑", size=11, bold=True)
    section_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    section_fill = PatternFill("solid", fgColor="4472C4")  # Blue
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    current_row = 1

    # Title row
    merged_ws.row_dimensions[current_row].height = 30
    merged_ws.merge_cells(start_row=current_row, start_column=1,
                          end_row=current_row, end_column=20)
    title_cell = merged_ws.cell(row=current_row, column=1,
                                  value=f"{date_label} {report_name}（合并汇总）")
    title_cell.font = title_font
    title_cell.alignment = center_align
    current_row += 1

    # Add a blank row
    current_row += 1

    for sheet_name in wb.sheetnames:
        src_ws = wb[sheet_name]
        max_col = src_ws.max_column

        # Section header row
        merged_ws.row_dimensions[current_row].height = 22
        merged_ws.merge_cells(start_row=current_row, start_column=1,
                                end_row=current_row, end_column=max_col)
        section_cell = merged_ws.cell(row=current_row, column=1,
                                        value=f"▶ {sheet_name}")
        section_cell.font = section_font
        section_cell.fill = section_fill
        section_cell.alignment = left_align
        current_row += 1

        # Copy column headers from row 1-3 of source sheet
        for row_idx in range(1, min(4, src_ws.max_row + 1)):
            src_row = list(src_ws.iter_rows(min_row=row_idx, max_row=row_idx,
                                             values_only=True))[0]
            merged_ws.row_dimensions[current_row].height = 18
            for col_idx, val in enumerate(src_row[:max_col], start=1):
                cell = merged_ws.cell(row=current_row, column=col_idx, value=val)
                cell.border = thin_border
                cell.alignment = center_align
                cell.font = header_font if row_idx <= 3 else Font(name="微软雅黑", size=10)
            current_row += 1

        # Copy data rows (starting from row 5 to skip redundant headers)
        for row_idx in range(5, src_ws.max_row + 1):
            src_row_vals = list(src_ws.iter_rows(min_row=row_idx, max_row=row_idx,
                                                   values_only=True))[0]
            merged_ws.row_dimensions[current_row].height = 16
            for col_idx, val in enumerate(src_row_vals[:max_col], start=1):
                cell = merged_ws.cell(row=current_row, column=col_idx, value=val)
                cell.border = thin_border
                cell.alignment = center_align
                cell.font = Font(name="微软雅黑", size=10)
            current_row += 1

        # Blank row between sections
        current_row += 1

    # Auto-adjust column widths
    for col_idx in range(1, max_col + 1):
        col_letter = get_column_letter(col_idx)
        max_width = 12
        for row in merged_ws.iter_rows(min_row=3, max_row=current_row - 1,
                                        min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value:
                    val_len = len(str(cell.value))
                    if val_len > max_width:
                        max_width = min(val_len, 30)
        merged_ws.column_dimensions[col_letter].width = max_width + 2

    # Save merged file
    merged_file_path = file_path.with_name(file_path.stem + "_merged" + file_path.suffix)
    merged_wb.save(merged_file_path)
    # Replace original with merged
    file_path.unlink()
    print(f"    已合并为单Sheet: {merged_file_path.name}")
    return merged_file_path


# ---------------------------------------------------------------------------
def export_report(report_id: int, date_fmt: dict) -> Path:
    """Export a single report to a temporary file"""
    report = REPORTS[report_id]
    url = build_report_url(report, date_fmt)

    print(f"  正在导出: {report['name']}...")

    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()

        # Check if response is actually an Excel file
        content_type = resp.headers.get("Content-Type", "")
        if "excel" not in content_type.lower() and "spreadsheet" not in content_type.lower():
            # Could be an error page, check content
            if len(resp.content) < 10000:
                preview = resp.content[:500].decode("utf-8", errors="ignore")
                if "error" in preview.lower() or "错误" in preview:
                    print(f"    ⚠️ 报表返回可能有问题: {preview[:100]}")

        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # Build filename with date substitution
        filename = report["filename"]
        for key, value in date_fmt.items():
            filename = filename.replace("{" + key + "}", value)

        file_path = TEMP_DIR / filename
        file_path.write_bytes(resp.content)

        print(f"    已保存: {file_path.name} ({file_path.stat().st_size} bytes)")
        return file_path

    except Exception as e:
        print(f"    ❌ 导出失败: {e}")
        return None


# ---------------------------------------------------------------------------
def get_access_token() -> str:
    """Get WeCom access token via API"""
    api_url = CONFIG["TOKEN_API_URL"]
    print("[获取企微Token]")

    payload = {
        "clientId": CONFIG["TOKEN_CLIENT_ID"],
        "clientSecret": CONFIG["TOKEN_CLIENT_SECRET"],
        "params": {},
        "offset": 0,
        "limit": 10,
        "userId": ""
    }

    resp = requests.post(api_url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    blocks = data.get("__blocks__", {})
    sys_info = data.get("__sys__", {})
    if not blocks or "result" not in blocks:
        msg = sys_info.get("msg", "未知错误")
        raise RuntimeError(f"Token API 错误: {msg}")

    token = data["__blocks__"]["result"]["rows"][0][0]
    print("  Token 获取成功")
    return token


# ---------------------------------------------------------------------------
def upload_to_wecom(file_path: Path, access_token: str) -> str:
    """Upload file to WeCom temporary media"""
    url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/media/upload"
    params = {"access_token": access_token, "type": "file"}
    print(f"  上传: {file_path.name}")

    # Detect content type from file extension
    ext = file_path.suffix.lower()
    content_types = {
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.html': 'text/html',
        '.htm': 'text/html',
        '.pdf': 'application/pdf',
        '.csv': 'text/csv',
    }
    content_type = content_types.get(ext, 'application/octet-stream')

    with file_path.open("rb") as f:
        resp = requests.post(
            url,
            params=params,
            files={"media": (file_path.name, f, content_type)},
            timeout=60
        )
    resp.raise_for_status()
    data = resp.json()

    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"上传失败: {data.get('errmsg')}")

    return data["media_id"]


# ---------------------------------------------------------------------------
def send_wecom_message(media_id: str, access_token: str, filename: str) -> None:
    """发送文件消息到企微个人（每日点检应用 message/send）"""
    url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/message/send"
    params = {"access_token": access_token}
    payload = {
        "touser": CONFIG["WECOM_TOUSER"],
        "msgtype": "file",
        "agentid": CONFIG["WECOM_AGENT_ID"],
        "file": {"media_id": media_id},
    }
    print(f"  正在发送个人消息: {filename} -> {CONFIG['WECOM_TOUSER']} (agentid={CONFIG['WECOM_AGENT_ID']})")

    resp = requests.post(url, params=params, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"个人发送失败: {data.get('errmsg')} (errcode={data.get('errcode')})")
    print("      个人发送成功")


# ---------------------------------------------------------------------------
def send_wecom_chat(file_path: Path, access_token: str, chatid: str = None) -> None:
    """发送文件到企微群聊（appchat/send）—— 参考 chat-exporter-backup 实现

    流程：media/upload 获取 media_id -> appchat/send 发送
    """
    # chatid 缺省时用配置中的默认群聊
    chatid = chatid or CONFIG.get("WECOM_CHATID")
    if not chatid:
        raise RuntimeError("未指定群聊 chatid")

    # Step 1: 上传文件获取 media_id
    media_id = upload_to_wecom(file_path, access_token)

    # Step 2: 发送到群聊
    url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/appchat/send"
    params = {"access_token": access_token}
    payload = {
        "chatid": chatid,
        "msgtype": "file",
        "file": {"media_id": media_id},
    }
    print(f"  正在发送到群聊 {chatid} ... 文件: {file_path.name}")

    resp = requests.post(url, params=params, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"群聊发送失败: {data.get('errmsg')} (errcode={data.get('errcode')})")
    print("      群聊发送成功")


# ---------------------------------------------------------------------------
def main():
    args = parse_args()

    # Determine target date (default: yesterday)
    if args.date:
        target_date = date.fromisoformat(args.date)
    else:
        target_date = date.today() - timedelta(days=1)

    date_fmt = get_date_formats(target_date)

    # Determine which reports to export
    if args.reports:
        try:
            report_ids = [int(x.strip()) for x in args.reports.split(",")]
        except ValueError:
            print("❌ 报表编号格式错误，请使用逗号分隔的数字，如: 1,3,5")
            return 1
    else:
        report_ids = list(REPORTS.keys())

    # Validate report IDs
    invalid_ids = [rid for rid in report_ids if rid not in REPORTS]
    if invalid_ids:
        print(f"❌ 无效的报表编号: {invalid_ids}")
        print(f"   有效编号: {list(REPORTS.keys())}")
        return 1

    # ============================================================
    # --export-only 分支：只导出保存到本地，不发企微
    # ============================================================
    if args.export_only:
        # 保存目录：用户指定 > 桌面
        if args.save_path:
            save_dir = Path(args.save_path)
        else:
            save_dir = Path.home() / "Desktop"

        save_dir.mkdir(parents=True, exist_ok=True)

        # Also normalize date_fmt for the report name (e.g. "09月16日")
        report_date_label = f"{date_fmt['mm']}月{date_fmt['dd']}日"
        print(f"\n{'='*50}")
        print(f"CBMS 报表导出工具（仅本地导出）")
        print(f"{'='*50}")
        print(f"📅 日期: {report_date_label}")
        print(f"📂 保存至: {save_dir}")
        print(f"📊 报表: {len(report_ids)} 个")
        print(f"{'='*50}\n")

        success_count = 0
        for report_id in report_ids:
            file_path = export_report(report_id, date_fmt)
            if file_path:
                # Apply light formatting to preserve FineReport styling
                try:
                    format_excel(file_path)
                except Exception as e:
                    print(f"    格式化跳过: {e}")
                # Copy to target directory (handle same-name overwrite)
                target = save_dir / file_path.name
                if target.exists():
                    target.unlink()
                shutil.copy2(file_path, target)
                file_path.unlink(missing_ok=True)
                print(f"    → 已保存: {target.name} ({target.stat().st_size} bytes)")
                success_count += 1
            else:
                print(f"    ❌ 导出失败，跳过")

        print(f"\n{'='*50}")
        if success_count > 0:
            print(f"✅ 完成！{success_count} 个报表已保存至")
            print(f"   {save_dir}")
        else:
            print(f"❌ 没有成功导出任何报表")
        print(f"{'='*50}\n")
        return 0 if success_count > 0 else 1

    # ============================================================
    # 标准分支：导出 + 发送企微
    # ============================================================
    # Override recipient if specified
    if args.user:
        CONFIG["WECOM_TOUSER"] = args.user

    if not CONFIG["WECOM_TOUSER"]:
        print("❌ 请指定收件人工号: python script.py -u 230012")
        return 1

    print(f"\n{'='*50}")
    print(f"CBMS 报表导出工具")
    print(f"{'='*50}")
    print(f"📅 日期: {date_fmt['yyyy_mm_dd']}")
    print(f"👤 收件人: {CONFIG['WECOM_TOUSER']}")
    print(f"📊 报表: {len(report_ids)} 个")
    print(f"{'='*50}\n")

    # Export all requested reports
    exported_files = []
    for report_id in report_ids:
        file_path = export_report(report_id, date_fmt)
        if file_path:
            exported_files.append((report_id, file_path))

    if not exported_files:
        print("\n❌ 没有成功导出任何报表")
        return 1

    print(f"\n✅ 成功导出 {len(exported_files)} 个报表")

    # Determine if WeCom sending is needed
    send_to_wecom = bool(CONFIG["WECOM_TOUSER"] or args.chatid)

    # --send-xlsx-each: 每个xlsx单独发送到企微
    if args.send_xlsx_each and send_to_wecom:
        print(f"\n[逐个发送xlsx到企微]")
        try:
            access_token = get_access_token()
        except Exception as e:
            print(f"\n❌ 获取企微Token失败: {e}")
            return 1

        xlsx_personal_ok = False
        xlsx_group_ok = False

        for report_id, xlsx_path in exported_files:
            report_name = REPORTS[report_id]["name"]
            print(f"\n  --- {report_name} ---")
            if CONFIG["WECOM_TOUSER"]:
                try:
                    mid = upload_to_wecom(xlsx_path, access_token)
                    send_wecom_message(mid, access_token, xlsx_path.name)
                    print(f"    ✅ 个人已发: {xlsx_path.name}")
                    xlsx_personal_ok = True
                except Exception as e:
                    print(f"    ❌ 个人发送失败: {e}")
            if args.chatid:
                try:
                    send_wecom_chat(xlsx_path, access_token, args.chatid)
                    print(f"    ✅ 群聊已发: {xlsx_path.name}")
                    xlsx_group_ok = True
                except Exception as e:
                    print(f"    ❌ 群聊发送失败: {e}")

        xlsx_send_ok = xlsx_personal_ok or xlsx_group_ok

        # HTML合并：失败则不清除xlsx（xlsx已在企微，无需本地副本）
        html_ok = False
        html_path = None
        try:
            html_path = generate_html_report(exported_files, date_fmt['yyyy_mm_dd'])
            html_ok = True
        except Exception as e:
            print(f"\n❌ HTML合并失败: {e}（xlsx已发送企微，文件暂留tmp目录）")

        if html_ok:
            # HTML合并成功：清理xlsx、发送HTML
            print(f"\n[清理临时Excel文件]")
            for _, fp in exported_files:
                fp.unlink(missing_ok=True)
                print(f"  删除: {fp.name}")

            html_personal_ok = False
            html_group_ok = False
            if CONFIG["WECOM_TOUSER"]:
                try:
                    mid = upload_to_wecom(html_path, access_token)
                    send_wecom_message(mid, access_token, html_path.name)
                    print(f"  ✅ HTML个人已发: {html_path.name}")
                    html_personal_ok = True
                except Exception as e:
                    print(f"  ❌ HTML个人发送失败: {e}")
            if args.chatid:
                try:
                    send_wecom_chat(html_path, access_token, args.chatid)
                    print(f"  ✅ HTML群聊已发: {html_path.name}")
                    html_group_ok = True
                except Exception as e:
                    print(f"  ❌ HTML群聊发送失败: {e}")

            html_path.unlink(missing_ok=True)
            print(f"  删除: {html_path.name}")

            success = xlsx_send_ok or html_personal_ok or html_group_ok
            print(f"\n{'='*50}")
            print(f"✅ 完成！xlsx逐个发送完毕")
            print(f"   xlsx: {'✅' if xlsx_send_ok else '❌'} | HTML: {'✅' if (html_personal_ok or html_group_ok) else '❌'}")
            print(f"   个人: {CONFIG['WECOM_TOUSER']} | 群聊: {args.chatid}")
            print(f"{'='*50}\n")
            return 0 if success else 1
        else:
            # HTML失败：xlsx已发企微，保留本地tmp
            success = xlsx_send_ok
            print(f"\n{'='*50}")
            print(f"{'✅' if success else '❌'} 完成！xlsx已发送企微，HTML合并失败（xlsx暂存tmp）")
            print(f"{'='*50}\n")
            return 0 if success else 1

    # ============================================================
    # 标准分支：导出 + 合并HTML + 发送
    # ============================================================

    # Generate combined HTML report with TOC
    print(f"\n[生成HTML报表]")
    try:
        html_path = generate_html_report(exported_files, date_fmt['yyyy_mm_dd'])
    except Exception as e:
        print(f"\n❌ 生成HTML失败: {e}")
        for _, fp in exported_files:
            fp.unlink(missing_ok=True)
        return 1

    # Clean up temporary Excel files (no longer needed after HTML generation)
    print(f"\n[清理临时Excel文件]")
    for _, fp in exported_files:
        fp.unlink(missing_ok=True)
        print(f"  删除: {fp.name}")

    # Get WeCom token
    try:
        access_token = get_access_token()
    except Exception as e:
        print(f"\n❌ 获取企微Token失败: {e}")
        html_path.unlink(missing_ok=True)
        return 1

    # Upload and send the HTML file
    print(f"\n[发送到企微]")
    personal_ok = False
    group_ok = False

    # 发送个人（用户ID）
    if CONFIG["WECOM_TOUSER"]:
        try:
            media_id = upload_to_wecom(html_path, access_token)
            send_wecom_message(media_id, access_token, html_path.name)
            print(f"  ✅ 个人消息已发送: {html_path.name} -> {CONFIG['WECOM_TOUSER']}")
            personal_ok = True
        except Exception as e:
            print(f"  ❌ 个人消息发送失败: {e}")

    # 发送群聊（chatid）
    if args.chatid:
        try:
            send_wecom_chat(html_path, access_token, args.chatid)
            print(f"  ✅ 群聊消息已发送: {html_path.name} -> {args.chatid}")
            group_ok = True
        except Exception as e:
            print(f"  ❌ 群聊发送失败: {e}")

    # Clean up HTML file
    html_path.unlink(missing_ok=True)
    print(f"  删除: {html_path.name}")

    success = personal_ok or group_ok
    print(f"\n{'='*50}")
    if personal_ok and group_ok:
        print(f"✅ 完成！HTML报表已发送至 个人({CONFIG['WECOM_TOUSER']}) 和群聊({args.chatid})")
    elif personal_ok:
        print(f"✅ 完成！HTML报表已发送至 {CONFIG['WECOM_TOUSER']}")
    elif group_ok:
        print(f"✅ 完成！HTML报表已发送至群聊 {args.chatid}")
    else:
        print(f"❌ 发送失败")
    print(f"{'='*50}\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
