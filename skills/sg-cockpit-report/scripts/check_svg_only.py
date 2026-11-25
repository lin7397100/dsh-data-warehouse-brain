# -*- coding: utf-8 -*-
"""纯 SVG / 零依赖报告体检（对应《纯SVG降级规范》第二节 T1~T6 + 第七节可机检项）。

用途：任何 HTML 报告落盘前跑一遍，确认它不依赖 ECharts/Canvas/CDN，且图表真实存在。

用法：
    python check_svg_only.py --html <report.html> [--expect-svg 8]
退出码：0 通过；1 不通过。
"""
import argparse
import os
import re
import sys

R = []


def chk(name, ok, detail=""):
    R.append({"name": name, "ok": bool(ok), "detail": str(detail)})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    ap.add_argument("--expect-svg", type=int, default=0, help="期望的 SVG 数量，0=不校验数量")
    args = ap.parse_args(argv)

    if not os.path.exists(args.html):
        print(f"[FATAL] 找不到 {args.html}")
        return 2
    h = open(args.html, encoding="utf-8").read()

    # T1 无 canvas
    chk("T1 无 <canvas>", h.count("<canvas") == 0, f"canvas={h.count('<canvas')}")
    # T2 零外部资源
    chk("T2 零外部资源", ("http://" not in h) and ("https://" not in h) and (" src=" not in h),
        f"http={h.count('http')} src={h.count(' src=')}")
    # T3 零图表库【按真实用法检测，不按字面提及】
    # 说明：正文可能出现"缺 ECharts 即降级"这类叙述，属正常；只有实际调用/引入才算违规。
    usage = {
        "echarts.init(": h.count("echarts.init("),
        "echarts.min.js": h.count("echarts.min.js"),
        "echarts.js": h.count("echarts.js"),
        "new Chart(": h.count("new Chart("),
        "Highcharts.chart(": h.count("Highcharts.chart("),
        "d3.select(": h.count("d3.select("),
        "getContext(": h.count("getContext("),
    }
    used = {k: v for k, v in usage.items() if v}
    ment = sum(h.count(k) for k in ("echarts", "ECHARTS", "echarts".upper()))
    chk("T3 零图表库真实调用", not used,
        "、".join(f"{k}×{v}" for k, v in used.items()) or f"无调用（正文提及 {ment} 次，不计违规）")
    # T4 内联 style/script
    chk("T4 样式内联", "<style" in h, f"<style>={h.count('<style')}")
    # T5 单文件（无外部链接标签）
    chk("T5 单文件自包含", ('<link' not in h) and ('<iframe' not in h), "无 link/iframe")
    # T6 每个 SVG 带 role + aria-label
    svgs = re.findall(r"<svg[^>]*>", h)
    ok6 = bool(svgs) and all(('role="img"' in s and "aria-label" in s) for s in svgs)
    chk("T6 SVG 均带 role+aria-label", ok6, f"{len(svgs)} 张")

    # 数量
    n = h.count("<svg")
    if args.expect_svg:
        chk("S1 SVG 数量符合声明", n == args.expect_svg, f"实际 {n}，期望 {args.expect_svg}")
    else:
        chk("S1 至少 1 张 SVG（不得退成纯表格）", n >= 1, f"{n} 张")

    # 坐标不越界
    oob = []
    coord = re.compile(r'(?<![a-zA-Z])(?:cx|cy|x|y|x1|x2|y1|y2|width|height)="(-?\d+\.?\d*)"')
    for mm in re.finditer(r'<svg viewBox="0 0 (\d+) (\d+)".*?</svg>', h, re.S):
        W, H = int(mm.group(1)), int(mm.group(2))
        for v in coord.findall(mm.group(0)):
            fv = float(v)
            if fv < -2 or fv > max(W, H) * 1.02 + 2:
                oob.append(f"{fv}>{max(W,H)}")
    chk("S2 SVG 坐标不越界", not oob, "、".join(oob[:4]) or "全部合规")

    # 下钻闸门（若声明为富交互报告）
    has_drawer = 'id="drill-drawer"' in h
    if has_drawer:
        for k in ("mask", "dwBody", "dwCrumb"):
            chk(f"S3 抽屉元素 id=\"{k}\"", f'id="{k}"' in h, "存在")
        tables = re.findall(r'<table class="realtab">(.*?)</table>', h, re.S)
        tt = sum(t.count("<td") for t in tables)
        tc = sum(t.count('onclick="openDrillL1(') for t in tables)
        chk("S4 下钻覆盖率 ≥90%", tc / max(tt, 1) >= 0.9, f"{tc}/{tt} = {tc/max(tt,1)*100:.1f}%")
        chk("S5 四层分支齐备", all(f"lv==={i}" in h for i in (1, 2, 3, 4)), "lv1~lv4")
        m = re.search(r"var ODS = (\{.*?\});\n", h, re.S)
        chk("S6 L4 明细 ≥10 行", bool(m) and min(len(v) for v in json_load(m.group(1)).values()) >= 10,
            "最小 %s 行" % (min(len(v) for v in json_load(m.group(1)).values()) if m else 0))
    else:
        chk("S3 未声明下钻（纯图表报告）", True, "跳过 D1~D5")

    # 正向表述检查
    chk("S7 无“演示/合成数据”正向声明", ("演示" not in h) and ("合成数据" not in h), "通过")

    passed = sum(1 for r in R if r["ok"])
    print(f"\n=== 零依赖体检：{passed}/{len(R)} 通过 ===\n")
    for r in R:
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['name']:<30} {r['detail']}")
    print()
    if passed == len(R):
        print(f"PASS ✅  {args.html}")
        return 0
    print("FAILED ❌")
    return 1


def json_load(s):
    import json
    return json.loads(s)


if __name__ == "__main__":
    sys.exit(main())
