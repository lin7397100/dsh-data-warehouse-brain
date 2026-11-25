#!/usr/bin/env python3
"""
Report Exporter — OpenClaw Skill Script

Exports a FineReport Excel file for yesterday's date, retrieves a WeCom
access token via HTTP API, uploads the file to WeCom, and sends it.

包含自动修复逻辑，修正 FineReport 导出时已知的格式问题：
  1. 第一工作簿"三钢集团生产信息总览"：K42 底部多余内容 → 合并修正为 K28:V44
  2. 第三工作簿"三明闽光生产经营日报（2）"：K27:W34 → K27:W39，A29:A34 → A29:A35

Dependencies:
    pip install requests openpyxl

Usage:
    python script.py -u 230012
    python script.py -u 230012|127761
    python script.py -u 230012 -d 2026-03-15
"""

import os
import sys
import argparse
from datetime import date, timedelta

# Fix Windows GBK console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="帆软报表导出工具（管制/生产/ERP 报表）")
    parser.add_argument("-u", "--user", "--emp-id", dest="user",
                        help="收件人工号，多人用 | 分隔（默认 230012）")
    parser.add_argument("--chatid", default=None,
                        help="群聊 ID（appchat/send；默认 AI赋能群）")
    parser.add_argument("-d", "--date", help="报表日期，格式 YYYY-MM-DD（默认：前一天）")
    parser.add_argument("--text", action="store_true", help="发送文本通知而非文件")
    parser.add_argument("--content", default=None, help="文本通知内容（配合 --text）")
    parser.add_argument("--skip-chat", action="store_true", help="不发送群聊（默认发 AI赋能群）")
    parser.add_argument("--skip-user", action="store_true", help="不发送个人（默认发 230012）")
    parser.add_argument("--export-only", action="store_true", help="仅导出本地，不发送企微")
    return parser.parse_args()


import requests
from pathlib import Path
from openpyxl import load_workbook

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CONFIG = {
    "FINEREPORT_URL":     os.getenv("FINEREPORT_URL",     "http://172.16.100.25:8080/webroot/decision/view/report"),
    "FINEREPORT_VIEWLET": os.getenv("FINEREPORT_VIEWLET", "GZ01/ZZGZ.cpt"),
    # 2026-09-19 起统一切至「每日点检」应用（原驾驶舱 D_A_SMBBRAOC00_TOKEN 已停用）
    "TOKEN_API_URL":      os.getenv("TOKEN_API_URL",      "http://eplat.fjsg.com/service/D_A_SMBBRAOC00_MRDJ_TOKEN"),
    "TOKEN_CLIENT_ID":    os.getenv("TOKEN_CLIENT_ID",    "sgoc-oc01"),
    "TOKEN_CLIENT_SECRET":os.getenv("TOKEN_CLIENT_SECRET","FCCDFACD0DED39AEE63462C112A4F412"),
    "WECOM_BASE_URL":  os.getenv("WECOM_BASE_URL",  "https://wecom.fjsg.com.cn"),
    "WECOM_AGENT_ID":  int(os.getenv("WECOM_AGENT_ID", "1000078")),
    "WECOM_TOUSER":    os.getenv("WECOM_TOUSER",    "230012"),
    "WECOM_CHATID":    os.getenv("WECOM_CHATID",    ""),  # 从环境变量或智能表格读取
}

# 临时文件目录（技能目录下）
SCRIPT_DIR = Path(__file__).parent
TEMP_DIR = SCRIPT_DIR / "tmp"


# ---------------------------------------------------------------------------
def get_dates() -> tuple:
    """获取文件名日期（今天）和API查询日期（昨天）"""
    today = date.today()
    yesterday = today - timedelta(days=1)
    # 文件名用今天日期，API查询用昨天日期
    return yesterday.strftime("%Y-%m-%d"), today.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
def export_report(api_date: str, file_date: str) -> Path:
    url = f"{CONFIG['FINEREPORT_URL']}?viewlet={CONFIG['FINEREPORT_VIEWLET']}&op=export&format=excel&p_date={api_date}"
    print(f"[1/5] 正在导出报表 {api_date}...")

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"三钢生产经营日报-{file_date}.xlsx"
    file_path = TEMP_DIR / file_name
    file_path.write_bytes(resp.content)
    print(f"      已保存: {file_path}")
    return file_path


# ---------------------------------------------------------------------------
def _unmerge_intersecting(ws, r1: int, r2: int, c1: int, c2: int) -> int:
    """取消所有与 [r1..r2] × [c1..c2] 相交的合并区，返回取消个数。

    2026-11-20 修复：原代码只 unmerge 了白名单里的几个范围，但 `K32:V48`
    横跨 32~48 行，覆盖了 42~44 行 —— 于是下面写 `s1.cell(42..44, 11..22).value = None`
    时拿到的是 `MergedCell`（只读），抛 `'MergedCell' object attribute 'value' is read-only`。
    正确做法：写之前先把**所有相交**的合并区拆掉。
    """
    n = 0
    for mr in list(ws.merged_cells.ranges):
        if mr.max_row < r1 or mr.min_row > r2 or mr.max_col < c1 or mr.min_col > c2:
            continue
        ws.unmerge_cells(str(mr))
        n += 1
    return n


def fix_report(file_path: Path) -> None:
    """
    自动修复 FineReport 导出时的已知格式问题。

    问题1：三钢集团生产信息总览
      K42:V44 出现与 K28:V41 相同的重复内容 → 清空 K42:V44，合并为 K28:V44
      K32:V48 十一、昨日质量区域合并问题 → 清除多余内容，合并为 K32:V48

    问题2：三明闽光生产经营日报（2）备注区
      K27:W34 → K27:W39，A29:A34 → A29:A35
    """
    print("[2/5] 自动修复报表格式问题...")

    wb = load_workbook(file_path)
    fixed_count = 0

    # ---------- 问题1 & 问题1-2: 三钢集团生产信息总览 ----------
    sheet1_name = '三钢集团生产信息总览'
    if sheet1_name in wb.sheetnames:
        s1 = wb[sheet1_name]
        merged_strs = {str(m) for m in s1.merged_cells.ranges}

        k42_val = s1.cell(42, 11).value
        has_k42_merge = any(
            str(m) in ('K42:V44', 'K42:V43', 'K42:V42') for m in s1.merged_cells.ranges
        )
        if k42_val is not None or has_k42_merge:
            # 先拆掉所有与 42~44 行 × 11~22 列相交的合并区（含 K32:V48 这类跨行合并）
            _unmerge_intersecting(s1, 42, 44, 11, 22)
            for r in range(42, 45):
                for c in range(11, 23):
                    try:
                        s1.cell(r, c).value = None
                    except AttributeError:
                        # 极端情况：仍有残余 MergedCell，跳过（不能因此中断整条导出）
                        pass
            s1.merge_cells('K28:V44')
            fixed_count += 1
            print("      [Fix1] K42 多余内容已清除，合并修正为 K28:V44")
            # 2026-11-20 修复：Fix1（K28:V44）与 Fix2（K32:V48）**竞争同一区域**
            #   （K32:V48 覆盖 32~48 行 × 11~22 列，与 K28:V44 的 32~44 行重叠），
            #   两者互斥。以 Fix1 为准，跳过 Fix2，否则 merge_cells 抛 (39, 11)。
            print("      [Fix2] 跳过（K28:V44 与 K32:V48 区域重叠，以 Fix1 为准）")
        else:
            print("      [Fix1] 第一工作簿无需修复")
            k32_related_merges = [m for m in merged_strs
                                  if any(f'{col}{row}' in m for col in ['K','L','M','N','O','P','Q','R','S','T','U','V'] for row in range(32, 49))]
            if k32_related_merges:
                for mr in list(s1.merged_cells.ranges):
                    mr_str = str(mr)
                    if any(f'{col}{row}' in mr_str for col in ['K','L','M','N','O','P','Q','R','S','T','U','V'] for row in range(32, 49)):
                        s1.unmerge_cells(mr_str)
                _unmerge_intersecting(s1, 32, 48, 11, 22)
                s1.merge_cells('K32:V48')
                fixed_count += 1
                print("      [Fix2] 十一、昨日质量区域 K32:V48 已修复")
            elif 'K32:V48' not in merged_strs:
                _unmerge_intersecting(s1, 32, 48, 11, 22)
                s1.merge_cells('K32:V48')
                fixed_count += 1
                print("      [Fix2] 十一、昨日质量区域 K32:V48 新增合并")

        s1.row_dimensions[32].height = 300

        for r in range(32, 49):
            s1.row_dimensions[r].height = 30

    # ---------- 问题2: 三明闽光生产经营日报（2） ----------
    sheet3_name = '三明闽光生产经营日报（2）'
    if sheet3_name in wb.sheetnames:
        s3 = wb[sheet3_name]
        merged_strs = {str(m) for m in s3.merged_cells.ranges}

        if 'K27:W34' in merged_strs:
            s3.unmerge_cells('K27:W34')
            s3.merge_cells('K27:W39')
            fixed_count += 1
            print(f"      [Fix3] 备注区合并修正 K27:W34 → K27:W39")
        else:
            print(f"      [Fix3] 备注区 K27 无需修复")

        # 检查 A29:A34 相关合并范围是否需要修复（扩展范围以处理可能的差异）
        a29_merged = any(
            f'A29:A{row}' in merged_strs 
            for row in range(34, 36)
        )
        if a29_merged:
            # 查找并取消任何 A29 相关的合并
            for mr in list(s3.merged_cells.ranges):
                mr_str = str(mr)
                if 'A29:A' in mr_str:
                    s3.unmerge_cells(mr_str)
            s3.merge_cells('A29:A35')
            fixed_count += 1
            print(f"      [Fix4] 左侧合并修正 A29:A34 → A29:A35")
        else:
            print(f"      [Fix4] A29 合并区无需修复")

    if fixed_count > 0:
        wb.save(file_path)
        print(f"      共修复 {fixed_count} 处，已保存。")
    else:
        print("      未发现需要修复的问题。")
    wb.close()


# ---------------------------------------------------------------------------
def get_access_token() -> str:
    api_url = CONFIG["TOKEN_API_URL"]
    print("[2/5] 正在获取企微Token...")

    payload = {
        "clientId":     CONFIG["TOKEN_CLIENT_ID"],
        "clientSecret": CONFIG["TOKEN_CLIENT_SECRET"],
        "params":       {},
        "offset":       0,
        "limit":        10,
        "userId":       ""
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
    print("      Token 获取成功")
    return token


# ---------------------------------------------------------------------------
def upload_to_wecom(file_path: Path, access_token: str) -> str:
    url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/media/upload"
    params = {"access_token": access_token, "type": "file"}
    print(f"[3/5] 正在上传文件...")

    with file_path.open("rb") as f:
        resp = requests.post(url, params=params, files={"media": (file_path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"上传失败: {data.get('errmsg')}")

    media_id = data["media_id"]
    print(f"      media_id: {media_id}")
    return media_id


# ---------------------------------------------------------------------------
def send_wecom_message(media_id: str, access_token: str) -> None:
    url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/message/send"
    params = {"access_token": access_token}
    payload = {
        "touser":  CONFIG["WECOM_TOUSER"],
        "msgtype": "file",
        "agentid": CONFIG["WECOM_AGENT_ID"],
        "file":    {"media_id": media_id},
    }
    print(f"[4/5] 正在发送给 {CONFIG['WECOM_TOUSER']}...")

    resp = requests.post(url, params=params, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"发送失败: {data.get('errmsg')}")
    print("      发送成功")


# ---------------------------------------------------------------------------
def send_file_to_chat(media_id: str, access_token: str, chatid: str) -> None:
    """发送文件消息到群聊（appchat/send，按 chatid，不依赖 agentid）。"""
    url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/appchat/send"
    payload = {"chatid": chatid, "msgtype": "file", "file": {"media_id": media_id}}
    print(f"[4/5] 正在发送到群聊 {chatid} ...")
    resp = requests.post(url, params={"access_token": access_token}, json=payload, timeout=30)
    resp.raise_for_status()
    d = resp.json()
    if d.get("errcode", 0) != 0:
        raise RuntimeError(f"群聊发送失败: {d.get('errmsg')}")
    print("      群聊发送成功")


# ---------------------------------------------------------------------------
def send_text(access_token: str, content: str, touser=None, chatid=None) -> None:
    """发送文本通知到个人和/或群聊（touser 严禁 @all）。"""
    if touser and touser.strip() == "@all":
        raise RuntimeError("touser 禁止使用 @all，请指定具体工号")
    if touser:
        payload = {"touser": touser, "msgtype": "text",
                   "agentid": CONFIG["WECOM_AGENT_ID"], "text": {"content": content}}
        resp = requests.post(f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/message/send",
                             params={"access_token": access_token}, json=payload, timeout=30)
        resp.raise_for_status()
        d = resp.json()
        if d.get("errcode", 0) != 0:
            raise RuntimeError(f"个人文本发送失败: {d.get('errmsg')}")
        print(f"      文本已发送至个人 {touser}")
    if chatid:
        payload = {"chatid": chatid, "msgtype": "text", "text": {"content": content}}
        resp = requests.post(f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/appchat/send",
                             params={"access_token": access_token}, json=payload, timeout=30)
        resp.raise_for_status()
        d = resp.json()
        if d.get("errcode", 0) != 0:
            raise RuntimeError(f"群聊文本发送失败: {d.get('errmsg')}")
        print(f"      文本已发送至群聊 {chatid}")


# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    today = date.today()  # 当前日期（用于文件名）

    if args.user:
        CONFIG["WECOM_TOUSER"] = args.user

    # 默认投递目标：个人 230012 + 群聊 AI赋能群；显式参数可覆盖，--skip-* 可关闭
    touser = None if args.skip_user else CONFIG["WECOM_TOUSER"]
    chatid = None if args.skip_chat else (args.chatid or CONFIG["WECOM_CHATID"])

    if args.date:
        api_date = args.date
        file_date = today.strftime("%Y%m%d")
    else:
        api_date, file_date = get_dates()

    if not touser and not chatid and not args.export_only:
        print("[FAIL] 请指定收件人工号或群聊: python script.py -u 230012")
        return 1

    file_path = None
    try:
        print(f"[DATE] 日期: {api_date}")
        print(f"[SEND] 个人: {touser or '(不发送)'} | 群聊: {chatid or '(不发送)'}")

        file_path = export_report(api_date, file_date)
        fix_report(file_path)

        if args.export_only:
            print(f"[SKIP] --export-only：已导出本地，跳过企微发送 -> {file_path}")
            print("\n[OK] 成功！报表已导出（未发送）。")
            return 0

        access_token = get_access_token()

        if args.text:
            content = args.content or f"【管制报表通知】{api_date} 报表已生成。"
            send_text(access_token, content, touser=touser, chatid=chatid)
        else:
            media_id = upload_to_wecom(file_path, access_token)
            if touser:
                send_wecom_message(media_id, access_token)
            if chatid:
                send_file_to_chat(media_id, access_token, chatid)

        print("[5/5] 清理临时文件...")
        file_path.unlink(missing_ok=True)

        print("\n[OK] 成功！报表已发送到企微。")
        return 0

    except Exception as exc:
        print(f"\n[FAIL] 失败: {exc}", file=sys.stderr)
        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
