#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
三钢数仓智脑专家团 · 语义池血缘覆盖体检
owner: sg-metadata（元数据专家）

用途
----
语义池里每条指标都带 `source_procedure`（来源存储过程）。按命名约定 `P_Xxx -> T_Xxx`
可推断目标表，但**推断结果必须与真实 DDL 校验**——推断不到的就是血缘缺口。

血缘缺口会直接拖累问数准确率：没有目标表就无法生成可执行 SQL，
`sg-eval-harness` 的 SQL 层评测会因此判负（见基线报告中 `lineage_unresolved` 计数）。

用法
----
  python scripts/check_lineage_coverage.py
  python scripts/check_lineage_coverage.py --pool knowledge/design/semantic/候选池-L0-core.csv \
      --ddl knowledge/design/indicator/source/ddl --out knowledge/observed/lineage

输出
----
  - 控制台概览
  - `血缘覆盖-<日期>.md`：分域/分表统计 + 缺口清单 + 处置建议
  - `血缘缺口-<日期>.csv`：逐条待补清单（交给 sg-metadata 解析存储过程体）
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEF_POOL = os.path.join(ROOT, "knowledge", "design", "semantic", "候选池-L0-core.csv")
# DB2 资产路径：优先环境变量 DB2_ASSETS_HOME（部署指南 §二 第3步），缺省回退本机目录。
# 兼容两种配法：变量指向资产根（含 DDL/ 子目录）或直接指向 DDL 目录。
_TEAM_ROOT = os.path.dirname(os.path.dirname(ROOT))  # .../data-warehouse-brain
_PKG_DDL = os.path.normpath(os.path.join(_TEAM_ROOT, "knowledge", "design", "indicator", "source", "ddl"))
_DB2_BASE = os.environ.get("DB2_ASSETS_HOME", _PKG_DDL)
DEF_DDL = (_DB2_BASE if os.path.basename(_DB2_BASE).upper() == "DDL"
           else os.path.join(_DB2_BASE, "DDL"))

DEF_OUT = os.path.join(ROOT, "knowledge", "observed", "lineage")


def load_ddl(ddl_root: str) -> dict:
    """返回 {表名: schema}。"""
    out = {}
    if not os.path.isdir(ddl_root):
        return out
    for schema in os.listdir(ddl_root):
        d = os.path.join(ddl_root, schema)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith("_表结构.md"):
                out[fn[:-len("_表结构.md")]] = schema
    return out


def proc_to_table(proc: str) -> str:
    n = (proc or "").split(".")[-1].strip()
    return ("T_" + n[2:]) if n.startswith("P_") else n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=DEF_POOL)
    ap.add_argument("--ddl", default=DEF_DDL)
    ap.add_argument("--out", default=DEF_OUT)
    ap.add_argument("--tag", default=str(date.today()))
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.pool, encoding="utf-8-sig")))
    ddl = load_ddl(a.ddl)
    print(f"[INFO] 语义池 {len(rows)} 条 | DDL 表 {len(ddl)} 张")

    ok_rows, gaps = [], []
    for r in rows:
        proc = (r.get("source_procedure") or "").strip()
        tab = proc_to_table(proc) if proc else ""
        if not proc:
            gaps.append((r, "", "无来源存储过程"))
        elif tab not in ddl:
            gaps.append((r, tab, "推断目标表不在 DDL 中"))
        else:
            ok_rows.append((r, tab, ddl[tab]))

    n = len(rows)
    cov = len(ok_rows) / n * 100 if n else 0.0
    print(f"[INFO] 血缘可解析 {len(ok_rows)}/{n} = {cov:.1f}% | 缺口 {len(gaps)} 条")

    by_tab = Counter(f"{sch}.{t}" for _, t, sch in ok_rows)
    gap_tab = Counter(t or "(空)" for _, t, _ in gaps)
    gap_dom = defaultdict(Counter)
    for r, t, _ in gaps:
        gap_dom[r.get("domain", "?")][t or "(空)"] += 1

    os.makedirs(a.out, exist_ok=True)
    gp = os.path.join(a.out, f"血缘缺口-{a.tag}.csv")
    with open(gp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zb_code", "zb_name", "domain", "backlog",
                    "source_procedure", "推断目标表", "缺口原因"])
        for r, t, why in gaps:
            w.writerow([r.get("zb_code", ""), r.get("zb_name", ""), r.get("domain", ""),
                        r.get("backlog", ""), r.get("source_procedure", ""), t, why])

    rep = [f"# 语义池血缘覆盖体检（{a.tag}）", "",
           f"- 语义池：`{os.path.basename(a.pool)}`（{n} 条）",
           f"- DDL 表索引：{len(ddl)} 张（来自 `{a.ddl}`）",
           f"- 推断规则：`P_Xxx` → `T_Xxx`，命中 DDL 才算解析成功", "",
           "## 总览", "", "| 项 | 值 |", "|---|---|",
           f"| 血缘可解析 | {len(ok_rows)} / {n} |",
           f"| **覆盖率** | **{cov:.1f}%** |",
           f"| 血缘缺口 | {len(gaps)} 条 |", "",
           "> 覆盖率低会直接压低 `sg-eval-harness` 的 SQL 层得分；"
           "这不是评测规则的问题，是元数据缺口。", "",
           "## 已解析目标表 TOP15", "", "| 目标表 | 指标数 |", "|---|---|"]
    rep += [f"| `{k}` | {v} |" for k, v in by_tab.most_common(15)]
    rep += ["", "## 缺口分布（按推断表）", "", "| 推断目标表 | 缺口数 |", "|---|---|"]
    rep += [f"| `{k}` | {v} |" for k, v in gap_tab.most_common()]
    rep += ["", "## 缺口分布（按域）", ""]
    for dom, c in sorted(gap_dom.items(), key=lambda x: -sum(x[1].values())):
        rep.append(f"- **{dom}**（{sum(c.values())} 条）：" +
                   "、".join(f"`{t}`×{v}" for t, v in c.most_common(5)))
    rep += ["", "## 处置建议", "",
            "1. **优先查 DB2 系统目录**（本地 `GZPROD` / `CBPROD` 只有部分过程体，"
            "本次缺口的过程体本地均缺失，本地解析走不通）：", "",
            "   ```sql",
            "   -- 存储过程写表的依赖关系（MCP db2 只读执行）",
            "   SELECT R.ROUTINESCHEMA, R.ROUTINENAME,",
            "          T.TABSCHEMA, T.TABNAME, D.TABNAME AS TARGET",
            "   FROM SYSCAT.ROUTINEDEP D",
            "   JOIN SYSCAT.ROUTINES R ON R.SPECIFICNAME = D.SPECIFICNAME",
            "   LEFT JOIN SYSCAT.TABLES T ON T.TABNAME = D.TABNAME",
            "   WHERE R.ROUTINENAME IN ("
            + ",".join(f"'{t[2:]}'" for t, _ in gap_tab.most_common() if t.startswith("T_")) + ")",
            "   ORDER BY R.ROUTINENAME;",
            "   ```", "",
            "2. 若有过程体可用，则解析 `INSERT INTO` / `MERGE INTO` / `UPDATE` 的目标表补回。",
            "3. 解析结果写入 `knowledge/observed/lineage/`，**不得**直接改 `design/` 下的设计态文件。",
            "4. 仍无法确定的标记为 `lineage: unresolved`，查询时须显式告知用户口径来源未固化。",
            "5. 补完后重跑 `scripts/run_eval.py --mode baseline`，对比 SQL 层得分是否提升。", "",
            "> 本文件由 `scripts/check_lineage_coverage.py` 生成，勿手工编辑。"]

    rp = os.path.join(a.out, f"血缘覆盖-{a.tag}.md")
    open(rp, "w", encoding="utf-8").write("\n".join(rep))

    print(f"\n[OUT ] {os.path.basename(rp)}")
    print(f"[OUT ] {os.path.basename(gp)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
