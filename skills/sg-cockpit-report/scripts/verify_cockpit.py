# -*- coding: utf-8 -*-
"""产物级验收 v5：对生成的驾驶舱 HTML 做独立断言（不信任生成器自述）。

覆盖：单文件/零外链、结构、KPI 精确匹配、标准成本对比模块、D1~D5 下钻闸门、SVG 坐标、幂等。
用法：
    python verify_cockpit.py --html <report.html> --data <data.json>
退出码：0 全通过；1 存在失败项。
"""
import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HTML = os.path.join(HERE, "三钢集团生产经营驾驶舱报告.html")
DEFAULT_DATA = os.path.join(HERE, "..", "data", "cockpit_data_20261029.json")
if not os.path.exists(DEFAULT_DATA):
    DEFAULT_DATA = os.path.join(HERE, "_cockpit_data.json")

R = []


def chk(name, ok, detail=""):
    R.append({"name": name, "ok": bool(ok), "detail": str(detail)})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=DEFAULT_HTML)
    ap.add_argument("--data", default=DEFAULT_DATA)
    args = ap.parse_args(argv)

    if not os.path.exists(args.html):
        print(f"[FATAL] 找不到 {args.html}")
        return 2
    h = open(args.html, encoding="utf-8").read()
    d = json.load(open(args.data, encoding="utf-8"))
    p, c, iv, st = d["production"], d["cost"], d["inventory"], d["standard_cost"]
    bases = d["meta"]["base_order"]

    # ---------- A 单文件与零外链 ----------
    chk("A1 文件规模 ≥ 100KB", len(h.encode("utf-8")) >= 100_000, f"{len(h.encode('utf-8')):,} bytes")
    chk("A2 零外链", ("http://" not in h) and ("https://" not in h), f"http={h.count('http')}")
    chk("A3 无外部资源", (" src=" not in h) and (' rel="stylesheet"' not in h), f"src={h.count(' src=')}")
    chk("A4 结构完整", h.count("<html") == 1 and h.rstrip().endswith("</html>"), "单一根+收尾")
    chk("A5 无占位残留", all(t not in h for t in ["{prod_total", "{{", "None", "nan", "__DRILL__", "__ODS__"]), "干净")

    # ---------- B 结构 ----------
    chk("B1 SVG 数量 = 8", h.count("<svg") == 8, f"{h.count('<svg')} 个")
    chk("B2 三基地齐备", all(n in h for n in ["三明闽光", "罗源闽光", "泉州闽光"]), "本部/罗源/泉州")
    chk("B3 KPI 卡 4 张", h.count('class="kpi"') == 4, f"{h.count('class=\"kpi\"')} 张")
    chk("B4 无合成/演示正向声明", ("演示" not in h) and ("合成数据" not in h), "演示=0")
    chk("B5 勾稽闸门全通过", ">不通过<" not in h and h.count(">通过<") >= 30, f"通过 {h.count('>通过<')} 项")

    # ---------- C 数值精确匹配 ----------
    prod_total = sum(p["prod_day"].values())
    inv_total = sum(iv["by_base"].values())
    cost_now = c["series"][-1]
    bf_w = sum(p["bf_ratio"][b] * p["steel_day"][b] for b in bases) / sum(p["steel_day"].values())
    kpi = re.findall(r'<div class="val">([^<]+)<span class="unit">([^<]+)</span></div>', h)
    expect = [(f"{prod_total:,.0f}", "吨"), (f"{cost_now:,.0f}", "元/吨"),
              (f"{inv_total:,.0f}", "万元"), (f"{bf_w:.2f}", "kg/t")]
    chk("C0 KPI 数量 = 4", len(kpi) == 4, f"{len(kpi)} 张")
    for i, (ev, eu) in enumerate(expect):
        got = kpi[i] if i < len(kpi) else ("-", "-")
        chk(f"C{i+1} KPI[{i+1}] 精确匹配", got[0] == ev, f"页面={got[0]} 期望={ev}")

    # ---------- D 标准成本 vs 实际成本模块 ----------
    items = st["items"]
    impact = sum((x["act"] - x["std"]) * x["out"] for x in items) / 10000
    chk("D1 模块标题在位", "标准成本 vs 实际成本对比" in h, "首屏模块")
    chk("D2 数据来源写明实体表", st["source"]["table"] in h, st["source"]["table"])
    chk("D3 对比口径写明", "对比口径" in h and "负为节约" in h, "差异符号语义")
    chk("D4 版本切分口径写明", st["std_version"] in h and st["act_version"] in h, "标准成本/日成本")
    chk("D5 可比工序逐项在表", all(f'{x["std"]:,.2f}' in h and f'{x["act"]:,.2f}' in h for x in items),
        f"{len(items)} 个工序")
    chk("D6 净影响数值一致", f"{impact:+,.2f}" in h, f"{impact:+,.2f} 万元")
    chk("D7 不可比项已披露", all(x["alias"] in h for x in st["not_comparable"]),
        f"{len(st['not_comparable'])} 项")
    chk("D8 不可比未按 0 处理", "未按 0 处理" in h, "显式声明")
    chk("D9 成本影响列显式标注单位", "成本影响(万元)" in h, "列头")
    chk("D10 判读红线在位", "定额" in h and "重估" in h, "防止误判降本成效")

    # ---------- E 下钻闸门 D1~D5 ----------
    for k in ("drill-drawer", "drill-overlay", "dwBody", "dwCrumb"):
        chk(f"E-D1 id=\"{k}\"", f'id="{k}"' in h, "存在")
    tables = re.findall(r'<table class="realtab">(.*?)</table>', h, re.S)
    tt = sum(t.count("<td") for t in tables)
    tc = sum(t.count('onclick="openDrillL1(') for t in tables)
    chk("E-D2 明细表下钻覆盖率 ≥90%", tc / max(tt, 1) >= 0.9, f"{tc}/{tt} = {tc/max(tt,1)*100:.1f}%")
    chk("E-D3 四层分支齐备", all(f"lv==={i}" in h for i in (1, 2, 3, 4)), "lv1~lv4")
    m = re.search(r"var ODS = (\{.*?\});\n", h, re.S)
    ods = json.loads(m.group(1)) if m else {}
    chk("E-D4 L4 明细 ≥10 行（每个源表）", bool(ods) and min(len(v) for v in ods.values()) >= 10,
        "最小 %d 行" % (min(len(v) for v in ods.values()) if ods else 0))
    i2 = h.find("} else if (lv===2)")
    i3 = h.find("} else if (lv===3)")
    seg2 = h[i2:i3] if i2 > 0 and i3 > i2 else ""
    chk("E-D5 L2 含Σ构成项+落库分子+差额",
        ("Σ构成项" in seg2) and ("落库分子" in seg2) and ("差额" in seg2), "三项齐备")

    # ---------- F 引用完整性 ----------
    drill_m = re.search(r"var DRILL = (\{.*?\});\n", h, re.S)
    drill = json.loads(drill_m.group(1)) if drill_m else {}
    keys = set(re.findall(r"onclick=\"openDrillL1\('([^']+)'\)\"", h))
    chk("F1 所有点击键均有数据", not (keys - set(drill)), f"缺失 {len(keys - set(drill))} 个")
    chk("F2 DRILL 条目数 ≥ 25", len(drill) >= 25, f"{len(drill)} 条")
    chk("F3 每条含 L1/L3/L4", all(("l1" in v and "l3" in v and "l4" in v) for v in drill.values()), "三层齐备")

    # ---------- G SVG 坐标 ----------
    oob = []
    coord = re.compile(r'(?<![a-zA-Z])(?:cx|cy|x|y|x1|x2|y1|y2)="(-?\d+\.?\d*)"')
    for mm in re.finditer(r'<svg viewBox="0 0 (\d+) (\d+)".*?</svg>', h, re.S):
        W, H = int(mm.group(1)), int(mm.group(2))
        for v in coord.findall(mm.group(0)):
            fv = float(v)
            if fv < -2 or fv > max(W, H) + 2:
                oob.append(f"{fv}>{max(W,H)}")
    chk("G1 SVG 坐标不越界", not oob, "、".join(oob[:4]) or "8 张全部合规")

    # ---------- H 幂等 ----------
    try:
        for extra in (HERE, os.path.join(HERE, "scripts")):
            if extra not in sys.path:
                sys.path.insert(0, extra)
        import importlib
        spec = "gen_cockpit" if os.path.exists(os.path.join(HERE, "gen_cockpit.py")) else "_gen_cockpit"
        gen = importlib.import_module(spec)
        m1 = gen.derive(gen.load_data(args.data))
        ck = gen.reconcile(m1)
        a1 = gen.render(m1, ck)
        a2 = gen.render(m1, ck)
        chk("H1 渲染幂等", hashlib.md5(a1.encode()).hexdigest() == hashlib.md5(a2.encode()).hexdigest(),
            hashlib.md5(a1.encode()).hexdigest()[:10])
        chk("H2 磁盘文件=重渲染结果", a1 == h, "一致" if a1 == h else f"{len(a1)} vs {len(h)}")
    except Exception as e:  # noqa: BLE001
        chk("H1 渲染幂等", False, f"异常：{e}")
        chk("H2 磁盘文件=重渲染结果", False, "跳过")

    passed = sum(1 for r in R if r["ok"])
    total = len(R)
    print(f"\n=== 产物验收 v5：{passed}/{total} 通过 ===\n")
    for r in R:
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['name']:<36} {r['detail']}")
    print()
    if passed == total:
        print(f"ALL PASS ✅  {args.html}")
        return 0
    print("FAILED ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
