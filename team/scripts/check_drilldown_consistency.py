#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据下钻规则一致性校验（Drilldown Consistency Checker）
=========================================================
版本: v1.0 ｜ 2026-11-06
职责: 校验「数据下钻规则_权威手册.md」是否被全团正确引用，
      以及是否存在旧版本/冲突定义残留。

用法:
    python scripts/check_drilldown_consistency.py
    python scripts/check_drilldown_consistency.py --json

退出码: 0 = 全通过；1 = 存在 FAIL
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORITY = "knowledge/kb/数据下钻规则_权威手册.md"

# 必须引用权威源的文件（成员 + 核心 reference + 技能）
REQUIRED_REFS = [
    # 成员 MD
    "agents/sg-insight.md",
    "agents/sg-zhishu-report-composer.md",
    "agents/sg-zhishu-dashboard-designer.md",
    "agents/sg-quality.md",
    "agents/sg-supervisor.md",
    "agents/sg-development.md",
    # 主理人
    "agents/data-warehouse-brain-team-lead.md",
    # 核心 reference
    "agents/references/report_rules.md",
    "agents/references/traceability_sql.md",
    # 技能
    "skills/sg-cockpit-report/SKILL.md",
    "skills/sg-data-lineage/SKILL.md",
]

# 代码层实现文件（2026-11-06 补：原校验只覆盖 MD 文档，漏掉真正生成 HTML 的 Python 代码）
CODE_FILES = [
    "skills/sg-cockpit-report/scripts/gen_cockpit.py",
    "skills/sg-cockpit-report/scripts/verify_cockpit.py",
    "skills/sg-cockpit-report/scripts/check_svg_only.py",
    "skills/sg-cockpit-report/references/纯SVG降级规范.md",
]

# 代码层旧命名特征（出现即 FAIL，非 WARN —— 会导致生成产物按手册校验全失败）
CODE_LEGACY = [
    (r'id="drawer"', 'id="drawer" → 应为 id="drill-drawer"'),
    (r'id="mask"', 'id="mask" → 应为 id="drill-overlay"'),
    (r'openDrawer\(', 'openDrawer( → 应为 openDrillL1('),
    (r'closeDrawer\(', 'closeDrawer( → 应为 closeDrill('),
    (r'getElementById\([\'"]drawer[\'"]\)', "getElementById('drawer') → 应为 'drill-drawer'"),
    (r'getElementById\([\'"]mask[\'"]\)', "getElementById('mask') → 应为 'drill-overlay'"),
]

# 白名单：属于其他功能（非数据下钻），不参与检查
WHITELIST = [
    "skills/ontology-app-builder/tools/generate_ui_workbench.py",  # 本体工作台搜索弹窗
]

# 旧版本下钻逻辑的冲突特征（出现即需人工确认）
LEGACY_PATTERNS = [
    (r'id="drawer"(?!-)', '旧 DOM id="drawer"（应为 id="drill-drawer"）'),
    (r'三层抽屉', '旧「三层抽屉」表述（应为四层）'),
    (r'openDrawer\(', '旧函数名 openDrawer（应为 openDrillL1）'),
]

results = []


def add(cid, name, ok, evidence="", warn=False):
    results.append({
        "id": cid,
        "name": name,
        "status": "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL"),
        "evidence": evidence,
    })


def read(p):
    try:
        return (ROOT / p).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def main():
    # 2026-11-20 修复：必须在 argparse 之前切 UTF-8。
    # Windows 控制台默认 GBK，报告项名含 U+2194 时 print 会抛 UnicodeEncodeError → exit 1。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="数据下钻规则一致性校验")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print("=" * 66)
    print("数据下钻规则一致性校验 v1.0")
    print("=" * 66)
    print(f"根目录: {ROOT}")
    print(f"权威源: {AUTHORITY}")
    print()

    # ========== A. 权威源存在性 ==========
    auth = read(AUTHORITY)
    add("A1", "权威手册存在", auth is not None,
        f"{len(auth)} 字符" if auth else "文件不存在")

    if auth:
        # 五要素齐备
        five = {
            "触发条件": "## 1. 触发条件" in auth,
            "层级路径": "## 2. 层级路径" in auth,
            "维度与指标口径": "## 4. 维度与指标口径" in auth,
            "数据范围": "## 5. 数据范围" in auth,
            "输出结果格式": "## 6. 输出结果格式" in auth,
        }
        missing = [k for k, v in five.items() if not v]
        add("A2", "五要素齐备", not missing,
            "全部齐备" if not missing else f"缺失: {missing}")

        # D1~D5 定义
        d_ok = all(f"**D{i}**" in auth for i in range(1, 6))
        add("A3", "D1~D5 定义完整", d_ok,
            "D1~D5 全部定义" if d_ok else "存在缺失")

        # 四层
        lv_ok = all(f"lv==={i}" in auth for i in range(1, 5))
        add("A4", "四层分支（lv===1~4）", lv_ok,
            "4 层齐全" if lv_ok else "层数不足")

        # window.__D 契约
        add("A5", "window.__D 四层契约", "window.__D" in auth and "lineage" in auth,
            "含完整契约" if "window.__D" in auth else "缺失")

    # ========== B. 引用一致性 ==========
    ref_missing = []
    ref_ok = []
    for f in REQUIRED_REFS:
        s = read(f)
        if s is None:
            ref_missing.append(f"{f}(不存在)")
            continue
        if AUTHORITY.split("/")[-1] in s or "数据下钻规则_权威手册" in s:
            ref_ok.append(f)
        else:
            ref_missing.append(f)

    add("B1", "全团引用权威源", not ref_missing,
        f"{len(ref_ok)}/{len(REQUIRED_REFS)} 已引用"
        + (f"｜缺失: {ref_missing}" if ref_missing else ""))

    # ========== C. D1~D5 双轨统一 ==========
    insight = read("agents/sg-insight.md") or ""
    cockpit = read("skills/sg-cockpit-report/SKILL.md") or ""

    i_ok = "数据下钻规则_权威手册" in insight
    c_ok = "数据下钻规则_权威手册" in cockpit
    add("C1", "sg-insight 指向权威源", i_ok, "已指向" if i_ok else "未指向")
    add("C2", "sg-cockpit-report 指向权威源", c_ok, "已指向" if c_ok else "未指向")

    # ========== D. report_rules 断链修复 ==========
    rr = read("agents/references/report_rules.md") or ""
    has_d_table = ("D1" in rr and "D5" in rr) and "数据下钻规则_权威手册" in rr
    add("D1", "report_rules D1~D5 断链已补", has_d_table,
        "含定义+引用" if has_d_table else "仍为断链")

    # ========== E. 旧版本残留检测 ==========
    scan_files = [f for f in REQUIRED_REFS if not f.endswith(".bak")]
    legacy_hits = []
    for f in scan_files:
        s = read(f)
        if not s:
            continue
        for pat, desc in LEGACY_PATTERNS:
            if re.search(pat, s):
                legacy_hits.append(f"{f}: {desc}")

    add("E1", "无旧版本下钻逻辑残留", not legacy_hits,
        "无残留" if not legacy_hits else f"{len(legacy_hits)} 处: {legacy_hits[:3]}",
        warn=True)

    # ========== F. 知识库索引登记 ==========
    idx = read("knowledge/kb/知识库索引.md") or ""
    add("F1", "知识库索引已登记", "数据下钻规则_权威手册" in idx,
        "已登记" if "数据下钻规则_权威手册" in idx else "未登记")

    # ========== G. 路由触发表 ==========
    lead = read("agents/data-warehouse-brain-team-lead.md") or ""
    add("G1", "主理人路由触发表已挂载",
        "数据下钻规则_权威手册" in lead,
        "已挂载" if "数据下钻规则_权威手册" in lead else "未挂载")

    # ========== H. 模板资产 ==========
    tpl = ROOT / "assets/drilldown_template.html"
    add("H1", "下钻模板资产存在", tpl.exists(),
        f"{tpl.stat().st_size} B" if tpl.exists() else "缺失")

    # ========== I. 代码层实现（2026-11-06 补 · 原盲区）==========
    # 问题：原校验只扫 MD 文档，漏掉真正生成 HTML 的 Python 代码。
    #       gen_cockpit.py 曾长期使用 openDrawer/id="drawer"，与模板不一致，
    #       导致「按手册校验驾驶舱产物 D1/D2 必然全 FAIL」。
    code_missing = []
    for f in CODE_FILES:
        if not (ROOT / f).exists():
            code_missing.append(f"{f}(不存在)")
    add("I1", "代码层文件齐备", not code_missing,
        f"{len(CODE_FILES)} 个文件" if not code_missing else f"缺失: {code_missing}")

    code_legacy = []
    for f in CODE_FILES:
        p = ROOT / f
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        for pat, desc in CODE_LEGACY:
            if re.search(pat, t):
                code_legacy.append(f"{p.name}: {desc}")

    add("I2", "代码层无旧命名（会致产物校验失败）", not code_legacy,
        "无残留" if not code_legacy else f"{len(code_legacy)} 处: {code_legacy[:3]}")

    # 代码层语法可解析
    syntax_bad = []
    for f in CODE_FILES:
        if not f.endswith(".py"):
            continue
        p = ROOT / f
        if not p.exists():
            continue
        try:
            import ast
            ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as e:
            syntax_bad.append(f"{p.name}: {e.msg}")
    add("I3", "代码层语法可解析", not syntax_bad,
        "全部 OK" if not syntax_bad else f"{syntax_bad}")

    # 生成器与模板的 DOM 命名一致性
    gen = read("skills/sg-cockpit-report/scripts/gen_cockpit.py") or ""
    tpl_txt = read("assets/drilldown_template.html") or ""
    dom_pairs = [
        ("drill-drawer", 'id="drill-drawer"' in gen, 'id="drill-drawer"' in tpl_txt),
        ("drill-overlay", 'id="drill-overlay"' in gen, 'id="drill-overlay"' in tpl_txt),
        ("openDrillL1", "function openDrillL1(" in gen, "function openDrillL1(" in tpl_txt),
        ("closeDrill", "function closeDrill(" in gen, "function closeDrill(" in tpl_txt),
    ]
    mism = [n for n, g, t in dom_pairs if not (g and t)]
    add("I4", "生成器↔模板 命名一致", not mism,
        "4 项全一致" if not mism else f"不一致: {mism}")

    # ========== 汇总 ==========
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    print("校验结果：")
    for r in results:
        icon = {"PASS": "OK  ", "WARN": "WARN", "FAIL": "FAIL"}[r["status"]]
        print(f"  [{icon}] {r['id']:4s} {r['name']}")
        if r["evidence"]:
            print(f"         └─ {r['evidence']}")

    print()
    print("=" * 66)
    rate = passed / total * 100 if total else 0
    print(f"  总计: {passed}/{total} 通过 ({rate:.1f}%)  警告={warned}  失败={failed}")
    print("=" * 66)

    if failed:
        print("\n失败项：")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  [FAIL] {r['id']} {r['name']} — {r['evidence']}")

    if args.json:
        print()
        print(json.dumps({
            "total": total, "passed": passed,
            "warned": warned, "failed": failed,
            "rate": round(rate, 2), "results": results,
        }, ensure_ascii=False, indent=2))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
