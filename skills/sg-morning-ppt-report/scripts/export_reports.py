#!/usr/bin/env python3
"""
FineReport 早会报表批量导出 & 整合工具

从共享服务接口获取报表路径结构表，筛选有效报表，
通过 Playwright 浏览器渲染逐页导出为 PDF/HTML，最终合并，
导出合并后的文件通过企业微信发送给指定收件人。

用法:
    python export_reports.py [--date YYYY-MM-DD] [--output-dir <目录>] [-t 230012]
"""

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta

import fitz  # PyMuPDF - 用于精确检测内容边界
import requests
from playwright.sync_api import sync_playwright
from PyPDF2 import PdfReader, PdfWriter, PageObject, Transformation
from PyPDF2.generic import RectangleObject


# ── 默认配置 ────────────────────────────────────────────
API_URL = "http://eplat.fjsg.com/service/D_A_SMBBZZ00_ZHPPTINFO"
API_BODY = {
    "clientId": "sgdw-gz01",
    "clientSecret": "26DB5B8E067BB65539A17E87BC8C5AC7",
    "params": {},
    "showCount": "true",
    "offset": "0",
    "limit": 200,
}

DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "output"
)

VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080
PAGE_FORMAT = "A2"
PAGE_ORIENTATION = "landscape"
SCALE = 0.85
MARGIN_PT = 30
WAIT_MS = 5000

# ── 企微配置 ────────────────────────────────────────────
TOKEN_API_URL = os.getenv("TOKEN_API_URL", "http://eplat.fjsg.com/service/D_A_SMBBRAOC00_MRDJ_TOKEN")
TOKEN_CLIENT_ID = os.getenv("TOKEN_CLIENT_ID", "sgoc-oc01")
TOKEN_CLIENT_SECRET = os.getenv("TOKEN_CLIENT_SECRET", "FCCDFACD0DED39AEE63462C112A4F412")
WECOM_BASE_URL = "https://wecom.fjsg.com.cn"
WECOM_CHATID = os.getenv("WECOM_CHATID", "MTk3MDMyNTYwMzAxNTYxMjpHygrR7KYUifUkH0BE_m4")


# ── 步骤1：获取报表列表 ──────────────────────────────────
def fetch_report_list():
    """POST 调用接口，返回字典列表（统一格式）。"""
    resp = requests.post(API_URL, json=API_BODY, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 格式1: __blocks__.result.rows (二维数组 + columns meta)
    if "__blocks__" in data and isinstance(data["__blocks__"], dict):
        result = data["__blocks__"].get("result", {})
        if "rows" in result and isinstance(result["rows"], list):
            columns = []
            if "meta" in result and "columns" in result["meta"]:
                columns = [c["name"].upper() for c in result["meta"]["columns"]]

            if columns and len(columns) > 0:
                records = []
                for row in result["rows"]:
                    rec = {}
                    for i, val in enumerate(row):
                        if i < len(columns):
                            rec[columns[i]] = val
                    records.append(rec)
                print(f"    (解析 __blocks__.result.rows: {len(records)} 条)")
                return records

            # 无 columns meta，直接返回原始 rows
            print(f"    (__blocks__ rows 无 meta，{len(result['rows'])} 条)")
            return result["rows"]

        # __blocks__.result 可能是直接的列表
        if isinstance(result, list):
            return result

    # 格式2: 直接列表
    if isinstance(data, list):
        return data

    # 格式3: {data/result/rows/records: [...]}
    for key in ("data", "result", "rows", "records"):
        if key in data:
            return data[key]

    # 兜底
    return data


# ── 步骤2：筛选 & 排序 ────────────────────────────────────
def filter_and_sort(records):
    """EFFECTIVE=Y 且 SORT!=999，按 SORT 升序。"""
    filtered = []
    for r in records:
        # 兼容字符串和字典
        if isinstance(r, str):
            continue
        effective = str(r.get("EFFECTIVE", "")).strip().upper()
        sort_val = r.get("SORT")
        if effective != "" and sort_val is not None and int(sort_val) != 0:
            filtered.append(r)
    filtered.sort(key=lambda x: int(x.get("SORT", 0)))
    return filtered


# ── 步骤3：拼接 URL ──────────────────────────────────────
def build_url(adress, p_date):
    """为帆软报表地址拼接 p_date 参数。"""
    url = adress.replace("@1", p_date)
    if "p_date=" in url:
        url = re.sub(r"p_date=[^&]*", f"p_date={p_date}", url)
    else:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}p_date={p_date}"
    return url


# ── 步骤4：Playwright 导出单页 PDF ────────────────────────
def export_single_pdf(browser, url, output_path, report_name=""):
    """使用 Playwright 浏览器渲染，导出为单页 PDF。"""
    context = browser.new_context(
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        device_scale_factor=2,
    )
    page = context.new_page()

    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(WAIT_MS)

        try:
            page.wait_for_function(
                "document.readyState === 'complete'", timeout=10000
            )
        except Exception:
            pass

        # 检测内容高度，超出视口则动态扩展页高
        content_height = page.evaluate(
            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        overflow_ratio = content_height / VIEWPORT_HEIGHT

        if overflow_ratio > 1.05:
            new_vh = int(content_height * 1.03)
            page.set_viewport_size({"width": VIEWPORT_WIDTH, "height": new_vh})
            page.wait_for_timeout(500)
            page_height_mm = min(int(420 * overflow_ratio * 1.03), 2100)
            print(f"  内容溢出 ({content_height}px), 视口→{new_vh}px, 页高→{page_height_mm}mm")
            pdf_bytes = page.pdf(
                width="594mm",
                height=f"{page_height_mm}mm",
                scale=SCALE,
                print_background=True,
                margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"},
            )
        else:
            pdf_bytes = page.pdf(
                format=PAGE_FORMAT,
                landscape=(PAGE_ORIENTATION == "landscape"),
                scale=SCALE,
                print_background=True,
                margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"},
            )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

        print(f"  ✓ 已导出: {os.path.basename(output_path)}")
        return True

    except Exception as e:
        print(f"  ✗ 导出失败 [{report_name}]: {e}")
        return False
    finally:
        context.close()


# ── 步骤5-6：合并 PDF 并裁剪空白 ──────────────────────────
def merge_and_crop(pdf_paths, output_path):
    """合并多个 PDF，用 PyMuPDF 精确检测每页内容边界并裁剪空白。"""
    merged_doc = fitz.open()

    for pdf_path in pdf_paths:
        src_doc = fitz.open(pdf_path)
        merged_doc.insert_pdf(src_doc)
        src_doc.close()

    if len(merged_doc) == 0:
        print("[5/7] 没有页面可合并。")
        merged_doc.close()
        return

    # 检测并裁剪每一页
    crop_count = 0
    for page in merged_doc:
        rect = _fitz_detect_content_rect(page)
        if rect is None:
            continue

        old_w = page.rect.width
        old_h = page.rect.height
        page.set_cropbox(rect)
        crop_count += 1
        if crop_count <= 3 or crop_count == len(merged_doc):
            print(f"  页{crop_count}: {int(old_w)}x{int(old_h)} → {int(rect.width)}x{int(rect.height)}")

    # 检查并删除末页 AI 声明
    _remove_ai_declaration_page_fitz(merged_doc)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    merged_doc.save(output_path)
    merged_doc.close()

    print(f"[5/7] 合并完成: {output_path}  ({len(PdfReader(output_path).pages)} 页, 已裁剪)")


def _fitz_detect_content_rect(page):
    """使用 PyMuPDF 精确检测页面实际可见内容边界。

    优先通过低分辨率渲染后的非白像素检测肉眼可见内容，避免个别报表
    的异常矢量坐标把裁剪范围撑大；结构化对象边界作为兜底。
    最终外加 MARGIN_PT 留白。内容占比过小的视为空白页，返回 None。
    """
    visible_rect = _fitz_detect_visible_content_rect(page)
    if visible_rect is not None:
        return _expand_rect_with_margin(page, visible_rect)

    content_rects = []

    # 1) 文本块
    blocks = page.get_text("blocks")
    for b in blocks:
        content_rects.append(fitz.Rect(b[:4]))

    # 2) 矢量绘图（表格边框、线条等）
    drawings = page.get_drawings()
    for d in drawings:
        content_rects.append(d["rect"])

    # 3) 图片块
    try:
        img_infos = page.get_image_info()
        for info in img_infos:
            content_rects.append(fitz.Rect(info["bbox"]))
    except Exception:
        pass

    if not content_rects:
        return None

    # 计算所有内容的联合矩形
    union = content_rects[0]
    for r in content_rects[1:]:
        union |= r

    page_w = page.rect.width
    page_h = page.rect.height

    # 内容面积占比 < 5% 视为空白页
    content_area = union.width * union.height
    page_area = page_w * page_h
    if page_area > 0 and content_area / page_area < 0.05:
        return None

    return _expand_rect_with_margin(page, union)


def _fitz_detect_visible_content_rect(page, zoom=0.5, threshold=245):
    """通过渲染像素检测可见内容边界，忽略白色页面背景。"""
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    width = pix.width
    height = pix.height
    channels = pix.n
    samples = pix.samples

    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    for y in range(height):
        row_offset = y * width * channels
        for x in range(width):
            offset = row_offset + x * channels
            r = samples[offset]
            g = samples[offset + 1]
            b = samples[offset + 2]
            if r < threshold or g < threshold or b < threshold:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < 0:
        return None

    rect = fitz.Rect(
        min_x / zoom,
        min_y / zoom,
        (max_x + 1) / zoom,
        (max_y + 1) / zoom,
    )

    page_area = page.rect.width * page.rect.height
    content_area = rect.width * rect.height
    if page_area > 0 and content_area / page_area < 0.01:
        return None

    return rect


def _expand_rect_with_margin(page, rect):
    """给内容边界增加留白，并限制在页面范围内。"""
    page_w = page.rect.width
    page_h = page.rect.height

    left = max(0, rect.x0 - MARGIN_PT)
    top = max(0, rect.y0 - MARGIN_PT)
    right = min(page_w, rect.x1 + MARGIN_PT)
    bottom = min(page_h, rect.y1 + MARGIN_PT)

    return fitz.Rect(left, top, right, bottom)


def _remove_ai_declaration_page_fitz(doc):
    """检查最后一页是否为 AI 声明页，是则删除。"""
    if len(doc) == 0:
        return
    last_page = doc[-1]
    text = last_page.get_text()
    if "内容由AI生成" in text or "AI生成" in text:
        doc.delete_page(len(doc) - 1)
        print("  ✓ 已删除末页 AI 声明")


# ── 步骤7：企微发送 ─────────────────────────────────────
def get_access_token():
    """通过 API 获取企微 access_token。"""
    print("[6/6] 正在获取企微 access_token...")

    payload = {
        "clientId": TOKEN_CLIENT_ID,
        "clientSecret": TOKEN_CLIENT_SECRET,
    }
    resp = requests.post(TOKEN_API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 格式1: __blocks__.result.rows[0][0] (标准平台格式)
    if "__blocks__" in data:
        try:
            rows = data["__blocks__"]["result"]["rows"]
            token = str(rows[0][0])
            print(f"  ✓ token 获取成功")
            return token
        except (KeyError, IndexError, TypeError):
            pass

    # 格式2: 简单 JSON (兼容)
    for key in ("access_token", "token", "accessToken"):
        if key in data:
            print(f"  ✓ token 获取成功")
            return str(data[key])

    # 格式3: data.access_token
    if "data" in data and isinstance(data["data"], dict):
        for key in ("access_token", "token"):
            if key in data["data"]:
                print(f"  ✓ token 获取成功")
                return str(data["data"][key])

    raise Exception(f"无法从返回中提取 token: {json.dumps(data, ensure_ascii=False)[:200]}")


def upload_media(token, file_path):
    """上传文件到企微临时素材库。"""
    print(f"  正在上传文件: {os.path.basename(file_path)}")

    upload_url = f"{WECOM_BASE_URL}/cgi-bin/media/upload"
    params = {"access_token": token, "type": "file"}

    with open(file_path, "rb") as f:
        files = {"media": (os.path.basename(file_path), f)}
        resp = requests.post(upload_url, params=params, files=files, timeout=120)

    resp.raise_for_status()
    result = resp.json()

    if result.get("errcode") != 0:
        raise Exception(f"上传失败: {result.get('errmsg', 'unknown error')}")

    media_id = result.get("media_id")
    print(f"  ✓ 上传成功, media_id={media_id}")
    return media_id


def send_file_to_chat(token, media_id, chatid):
    """发送文件消息到企业微信群聊。"""
    print(f"  正在发送到群聊: {chatid}")

    send_url = f"{WECOM_BASE_URL}/cgi-bin/appchat/send"
    params = {"access_token": token}

    payload = {
        "chatid": chatid,
        "msgtype": "file",
        "file": {"media_id": media_id},
    }

    resp = requests.post(send_url, params=params, json=payload, timeout=30)
    resp.raise_for_status()
    result = resp.json()

    if result.get("errcode") != 0:
        raise Exception(f"发送失败: {result.get('errmsg', 'unknown error')}")

    print(f"  ✓ 发送成功")


def send_to_wecom(file_path, chatid):
    """直接上传并发送完整文件到企业微信群聊。"""
    sz = os.path.getsize(file_path) / 1024 / 1024
    fname = os.path.basename(file_path)
    print(f"[5/5] 发送 {fname} 到企业微信群聊 ({sz:.1f}MB)...")
    try:
        token = get_access_token()
        media_id = upload_media(token, file_path)
        send_file_to_chat(token, media_id, chatid)
        print(f"  ✓ 发送成功")
    except Exception as e:
        print(f"  ✗ 发送失败: {e}")
        raise


def cleanup_output_pdfs_after_send(output_dir):
    """企微发送成功后，删除输出目录内导出和合并生成的 PDF 文件。"""
    output_dir_abs = os.path.abspath(output_dir)

    if not os.path.isdir(output_dir_abs):
        return

    for filename in os.listdir(output_dir_abs):
        if not filename.lower().endswith(".pdf"):
            continue
        pdf_abs = os.path.join(output_dir_abs, filename)
        if not os.path.isfile(pdf_abs):
            continue
        try:
            os.remove(pdf_abs)
            print(f"  已删除输出PDF: {filename}")
        except Exception as e:
            print(f"  删除输出PDF失败 [{filename}]: {e}")


# ── 获取报表名称 ─────────────────────────────────────────
def get_report_name(record):
    """从报表记录中获取可读名称，优先 NAME/NOTE，回退到 REPORTID。"""
    for key in ("NAME", "NOTE", "REPORTID"):
        val = record.get(key, "")
        if val:
            return str(val).strip()
    return "unknown"


# ── 主流程 ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="FineReport 早会报表批量导出 & 整合工具"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="报表日期 (YYYY-MM-DD)，默认为执行前一天",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录",
    )
    parser.add_argument(
        "-c", "--chatid",
        default=None,
        help="目标群聊 chatid，默认 MTk3MDMyNTYwMzAxNTYxMjpHygrR7KYUifUkH0BE_m4",
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="仅导出不发送企微",
    )
    args = parser.parse_args()

    chatid = args.chatid or WECOM_CHATID
    do_send = not args.no_send

    # 始终导出 PDF

    if args.date:
        p_date = args.date
    else:
        p_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    print(f"=== FineReport 早会报表导出工具 ===")
    print(f"日期: {p_date}")
    print(f"格式: PDF")
    print(f"输出目录: {output_dir}")
    print(f"企微群聊: {chatid}\n")

    # 1. 获取报表列表
    print("[1/5] 获取报表列表...")
    records = fetch_report_list()
    print(f"  获取 {len(records)} 条记录")

    # 2. 筛选排序
    print("[2/5] 筛选排序...")
    reports = filter_and_sort(records)
    print(f"  有效报表: {len(reports)} 条")

    if not reports:
        print("没有符合条件的报表，退出。")
        return

    # 3. 拼接 URL
    urls = []
    report_names = []
    for r in reports:
        adress = r.get("ADRESS", "")
        name = get_report_name(r)
        if not adress:
            print(f"  ⚠ 跳过无地址报表: {name}")
            continue
        url = build_url(adress, p_date)
        urls.append((url, name))
        report_names.append(name)

    # 4. Playwright 导出 PDF
    pdf_paths = []
    print(f"\n[3/5] Playwright 浏览器渲染导出 ({len(urls)} 份)...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for idx, (url, name) in enumerate(urls, 1):
            safe_name = re.sub(r'[\\/*?:"<>|]', "_", name)

            filename = f"{idx:02d}_{safe_name}.pdf"
            output_path = os.path.join(output_dir, filename)
            success = export_single_pdf(browser, url, output_path, name)
            if success:
                pdf_paths.append(output_path)

            time.sleep(0.5)
        browser.close()

    total_exported = len(pdf_paths)
    print(f"  成功导出: {total_exported}/{len(urls)} 份")

    merged_files = []

    # 合并且裁剪 PDF
    if pdf_paths:
        print(f"\n[4/5] 合并 PDF 并裁剪空白...")
        merged_pdf = os.path.join(output_dir, f"早会PPT报表全部({p_date}).pdf")
        merge_and_crop(pdf_paths, merged_pdf)
        merged_files.append(merged_pdf)

    if not merged_files:
        print("\n没有成功导出的报表。")
        return

    print(f"\n=== 导出完成 ===")
    for f in merged_files:
        size_mb = os.path.getsize(f) / 1024 / 1024
        print(f"合集文件: {f} ({size_mb:.1f}MB)")

    # 6. 企微发送
    if do_send:
        print()
        for f in merged_files:
            try:
                send_to_wecom(f, chatid)
                cleanup_output_pdfs_after_send(output_dir)
            except Exception as e:
                print(f"\n  ✗ 企微发送失败 [{os.path.basename(f)}]: {e}")
        print()
        print(f"\n=== 全部完成 ===")
    else:
        print(f"\n=== 导出完成（跳过企微发送） ===")


if __name__ == "__main__":
    main()
