#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encapsulate_indicator_skills.py — 将派生/复合指标的业务 SQL 独立封装为单个技能。

读取 knowledge/design/indicator/indicator_registry.json，对每个 level in {derived, composite}
且具备 materialized_sql_file 的指标，在 <out>/skills/ind-<ZB_CODE>/ 生成：
  - SKILL.md   指标定义 + 物化 SQL 调用方式 + 口径卡模板
  - <ZB_CODE>.sql  该指标的物化 SQL（从 materialized_sql/ 复制）

用户问数命中该指标时，优先调用 ind-<ZB_CODE> 技能直接执行，不再走编译。

用法：
  python engine/encapsulate_indicator_skills.py --out ../../skills --min-level derived
"""
import os, json, shutil, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TEAM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
REG_PATH = os.path.join(TEAM_ROOT, "knowledge", "design", "indicator", "indicator_registry.json")
MAT_DIR = os.path.join(TEAM_ROOT, "knowledge", "design", "indicator", "materialized_sql")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(TEAM_ROOT, "skills"), help="skills 根目录")
    ap.add_argument("--min-level", default="derived", choices=["derived", "composite"])
    args = ap.parse_args()

    with open(REG_PATH, encoding="utf-8") as f:
        reg = json.load(f)
    levels = ["derived", "composite"] if args.min_level == "derived" else ["composite"]

    count = 0
    for e in reg["indicators"]:
        if e["level"] not in levels or not e.get("materialized_sql_file"):
            continue
        zb = e["zb_code"]
        skdir = os.path.join(args.out, f"ind-{zb}")
        os.makedirs(skdir, exist_ok=True)
        # 复制物化 SQL（materialized_sql_file 相对 knowledge/design/indicator/，
        # 实际落在 MAT_DIR 下；以 basename 解析以免疫于前缀口径漂移）
        _rel = e["materialized_sql_file"]
        _fname = os.path.basename(_rel)
        src_sql = os.path.join(MAT_DIR, _fname)
        if os.path.isfile(src_sql):
            shutil.copyfile(src_sql, os.path.join(skdir, f"{zb}.sql"))
        # 生成 SKILL.md
        lineage = json.dumps(e.get("lineage_chain", []), ensure_ascii=False)
        skill_md = f"""---
name: ind-{zb}
description: "指标 {e['zb_name']}（ZB_CODE={zb}）独立技能：直查物化 SQL，{e.get('domain','')}域，层级 {e['level']}。"
version: 1.0.0
author: SanSteel Data Warehouse Brain (auto-encapsulated by sg-memory-engine)
tags: [sangang, indicator, auto-skill, {e.get('domain','').lower()}]
owner: sg-memory
---

# 指标技能 ind-{zb} · {e['zb_name']}

## 指标定义
- **ZB_CODE**：{zb}
- **名称**：{e['zb_name']}
- **域**：{e['domain']}
- **层级**：{e['level']}
- **厂部**：{e.get('factory_div','')}
- **单位**：{e.get('unit','')}
- **时间参数**：{', '.join(e.get('params', [])) or '(none)'}

## 调用方式（优先于编译）
1. 直接执行 `{zb}.sql`（替换时间占位符后投 DB2 MCP 只读）。
2. 或由 `sg-materialized-sql` 按 ZB_CODE 直查 `materialized_sql/{zb}.sql`。

## 口径卡模板
| 项 | 值 |
|---|---|
| 指标 | {e['zb_name']} ({zb}) |
| 层级 | {e['level']} |
| 域 | {e['domain']} |
| 单位 | {e.get('unit','')} |
| 血缘 | {lineage} |
| 置信度 | 高（物化 SQL，已校验） |

## 注意事项
- 本技能由记忆专家每日构建自动封装，命中即直调，禁止重复编译。
- 仅只读执行；结果须过质量闸门后交付。
"""
        with open(os.path.join(skdir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(skill_md)
        count += 1

    print(f"[encapsulate] generated {count} indicator skills under {args.out} (min-level={args.min_level})")

if __name__ == "__main__":
    main()
