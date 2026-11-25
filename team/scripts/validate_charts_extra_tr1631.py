# -*- coding: utf-8 -*-
"""几何/结构校验：#charts-extra 片段（SVG 边界、字体溢出估算、标签重叠）"""
import re
from lxml import etree, html as lhtml

P = r"$env:DSH_HOME\dwb-team/artifacts/analysis/TR-20261119-1631-62A2_charts_extra.html"
src = open(P, encoding="utf-8").read()

print("== 1. 纯 HTML 子集检查 ==")
for tok in ("<!DOCTYPE", "<html", "<head", "<body", "</html>", "</head>", "</body>"):
    assert tok not in src, tok
print("   OK：无 <html>/<head>/<body>/DOCTYPE 包裹")

print("== 2. 片元可解析 ==")
frag = lhtml.fragment_fromstring(src)
print("   fragment root =", frag.tag, "| 子元素数 =", len(frag))

print("== 3. SVG XML 良构 + 边界 ==")
svgs = re.findall(r"<svg\b.*?</svg>", src, re.S)
print("   SVG 数 =", len(svgs))
for i, s in enumerate(svgs, 1):
    root = etree.fromstring(s.encode("utf-8"))
    vb = root.get("viewBox").split()
    W, H = float(vb[2]), float(vb[3])
    bad = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        try:
            if tag == "rect":
                x, y = float(el.get("x", 0)), float(el.get("y", 0))
                w, h = float(el.get("width", 0)), float(el.get("height", 0))
                if x < -2 or y < -2 or x + w > W + 2 or y + h > H + 2:
                    bad.append(("rect", x, y, x + w, y + h))
            elif tag == "text":
                x, y = float(el.get("x", 0)), float(el.get("y", 0))
                if x < -2 or y < -2 or x > W + 2 or y > H + 2:
                    bad.append(("text", x, y, (el.text or "")[:14]))
            elif tag in ("circle",):
                cx, cy, r = float(el.get("cx")), float(el.get("cy")), float(el.get("r"))
                if cx - r < -2 or cy - r < -2 or cx + r > W + 2 or cy + r > H + 2:
                    bad.append(("circle", cx, cy, r))
            elif tag == "polygon":
                pts = [float(v) for v in el.get("points").replace(",", " ").split()]
                xs, ys = pts[0::2], pts[1::2]
                if min(xs) < -2 or max(xs) > W + 2 or min(ys) < -2 or max(ys) > H + 2:
                    bad.append(("polygon", min(xs), max(xs), min(ys), max(ys)))
            elif tag == "polyline":
                pts = [float(v) for v in el.get("points").replace(",", " ").split()]
                xs, ys = pts[0::2], pts[1::2]
                if min(xs) < -2 or max(xs) > W + 2 or min(ys) < -2 or max(ys) > H + 2:
                    bad.append(("polyline", min(xs), max(xs), min(ys), max(ys)))
            elif tag == "line":
                x1, y1 = float(el.get("x1")), float(el.get("y1"))
                x2, y2 = float(el.get("x2")), float(el.get("y2"))
                for xx, yy in ((x1, y1), (x2, y2)):
                    if xx < -2 or yy < -2 or xx > W + 2 or yy > H + 2:
                        bad.append(("line", xx, yy))
        except (TypeError, ValueError):
            pass
    # 右边界粗估（CJK 全宽 1em，ASCII 约 0.55em）
    over = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "text" or not (el.text or "").strip():
            continue
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        fs = float(el.get("font-size", 12))
        anchor = el.get("text-anchor", "start")
        w = sum(fs * (1.0 if ord(c) > 127 else 0.56) for c in el.text)
        x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
        if x0 < -6 or x0 + w > W + 6:
            over.append((round(x0), round(x0 + w), W, el.text[:18]))
    print("   #%d viewBox=%sx%s 越界元素=%d 文本横向溢出=%d" % (i, W, H, len(bad), len(over)))
    for b in bad[:5]:
        print("      [越界]", b)
    for o in over[:5]:
        print("      [溢出]", o)

print("== 4. 关键属性/契约 ==")
ids = re.findall(r'data-chart-id="([^"]+)"', src)
types = re.findall(r'data-chart-type="([^"]+)"', src)
pts = re.findall(r'data-data-points="([^"]+)"', src)
print("   chart_id =", ids)
print("   type     =", types)
print("   points   =", pts)
print("   data-chart-id 计数 =", src.count("data-chart-id="))
print("   producer =", re.findall(r'data-producer="([^"]+)"', src))
print("   slot     =", re.findall(r'data-slot="([^"]+)"', src))

print("== 5. 假 0 / 真 0 / 单位 标注 ==")
for kw in ("假 0", "假0", "真 0", "--color-null", "#5A6B82", "未取证", "n/a", "炉次", "pp", "t（"):
    print("   %-14s %d" % (kw, src.count(kw)))
print("   0.00 出现在图元坐标次数（应仅作轴/值标注）:", len(re.findall(r">0\.00<", src)))

print("== 6. 花括号/模板泄漏 ==")
print("   '{' =", src.count("{"), " '}' =", src.count("}"), " '%s' =", src.count("%s"), " '%%' 残留 =", src.count("%%"))

print("== 7. 编码 ==")
print("   utf-8 bytes =", len(src.encode("utf-8")), " chars =", len(src))
