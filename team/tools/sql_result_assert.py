# -*- coding: utf-8 -*-
"""sql_result_assert.py —— SQL 第二阶：执行期结果断言（确定性 · 零模型调用）

来源：借鉴 dsh-superagent「Gate 层确定性、Stored work 先存后做」的思路，
      把「结果是否可信」从人工目检下沉为可复跑断言。

职责：SQL 取回结果后、交给质量专家之前，机械校验结果形态与值域。
      不通过 → 禁止进入第三阶/交付（exit 1）。

用法：
    python tools/sql_result_assert.py --result observed/data_package_<TR>.json --spec <spec.json>
    python tools/sql_result_assert.py --result <json> --spec <json> --json
    python tools/sql_result_assert.py --result <json> --spec <json> --dump-default

八类断言（spec.assertions[] 的 type）：
    rowcount     行数守恒              {"table","expect"}
    unique       主键唯一              {"table","keys":[...]}
    domain       取值域枚举            {"table","column","allow":[...]}
    value_range  数值区间（可 filter）  {"table","column","filter":{},"min","max"}
    null_rate    空值率上限            {"table","column","max"}
    all_equal    全等断言              {"table","column","expect"}
    zero_ratio   分组零值闭合          {"table","group","column","allow_groups":[...]}
    parts_sum    构成项之和=总量        {"table","parts_column","total_column","group","tolerance"}

退出码：0 通过 ｜ 1 不通过 ｜ 2 输入/环境错误
"""
import argparse
import io
import json
import os
import sys


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load(path):
    with io.open(path, encoding="utf-8-sig") as f:
        if path.lower().endswith((".yml", ".yaml")):
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "tools", "_vendor"))
            import yaml  # noqa
            return yaml.safe_load(f)
        return json.load(f)


def dig(obj, path):
    cur = obj
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except Exception:
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def rows_of(result, table):
    r = dig(result, table)
    return r if isinstance(r, list) else None


def run_assertion(a, result):
    t = a.get("type")
    tbl_name = a.get("table")
    rows = rows_of(result, tbl_name)
    detail = ""

    if rows is None:
        return False, "表路径不存在或不是数组：%s" % tbl_name

    if t == "rowcount":
        ok = len(rows) == a["expect"]
        return ok, "行数 %d（期望 %d）" % (len(rows), a["expect"])

    if t == "unique":
        keys = a["keys"]
        seen, dup = set(), 0
        for r in rows:
            k = tuple(str(r.get(c)) for c in keys)
            if k in seen:
                dup += 1
            seen.add(k)
        return dup == 0, "唯一键 %s 重复 %d 组（%d 行）" % ("+".join(keys), dup, len(rows))

    if t == "domain":
        col, allow = a["column"], set(a["allow"])
        bad = sorted({str(r.get(col)) for r in rows if str(r.get(col)) not in allow})
        return (not bad), "列 %s 越界取值：%s（允许 %s）" % (col, bad or "无", sorted(allow))

    if t == "value_range":
        col = a["column"]
        flt = a.get("filter") or {}
        vals = [num(r.get(col)) for r in rows
                if all(str(r.get(k)) == str(v) for k, v in flt.items())]
        vals = [v for v in vals if v is not None]
        if not vals:
            return False, "列 %s 在 filter=%s 下无有效数值" % (col, flt)
        lo, hi = a.get("min"), a.get("max")
        out = [v for v in vals if (lo is not None and v < lo) or (hi is not None and v > hi)]
        detail = "列 %s（%d 点）区间 [%s, %s]，越界 %d 点%s" % (
            col, len(vals), lo, hi, len(out),
            "" if not out else " → %s" % [round(x, 4) for x in out[:3]])
        return not out, detail

    if t == "null_rate":
        col = a["column"]
        n = sum(1 for r in rows if r.get(col) in (None, ""))
        rate = n / len(rows) if rows else 0.0
        return rate <= a["max"], "列 %s 空值率 %.1f%%（上限 %.1f%%）" % (col, rate * 100, a["max"] * 100)

    if t == "all_equal":
        col, exp = a["column"], a["expect"]
        bad = sorted({str(r.get(col)) for r in rows if str(r.get(col)) != str(exp)})
        return (not bad), "列 %s 全等 %r，异常取值：%s" % (col, exp, bad or "无")

    if t == "zero_ratio":
        gcol, col = a["group"], a["column"]
        allow = set(a["allow_groups"])
        groups = {}
        for r in rows:
            groups.setdefault(str(r.get(gcol)), []).append(num(r.get(col)))
        bad = []
        for g, vals in groups.items():
            nn = [v for v in vals if v is not None]
            all_zero = all(v == 0 for v in nn) if nn else True
            if g in allow and not all_zero:
                bad.append("%s 期望全 0 实为 %s" % (g, nn))
            if g not in allow and all_zero:
                bad.append("%s 期望非 0 实为全 0" % g)
        return (not bad), "分组零值闭合 %d 组：%s" % (len(groups), bad or "全部符合")

    if t == "parts_sum":
        gcol = a["group"]
        pc, tc = a["parts_column"], a["total_column"]
        tol = a.get("tolerance", 1e-6)
        groups = {}
        for r in rows:
            groups.setdefault(str(r.get(gcol)), {"parts": 0.0, "total": None, "kind": r.get("_kind")})
        # 约定：rows 中 _kind='part' 计入构成项，_kind='total' 为总量
        for r in rows:
            g = str(r.get(gcol))
            v = num(r.get(pc))
            if r.get("_kind") == "part" and v is not None:
                groups[g]["parts"] += v
            if r.get("_kind") == "total":
                groups[g]["total"] = num(r.get(tc))
        bad = []
        for g, d in groups.items():
            if d["total"] is None:
                bad.append("%s 缺总量" % g)
                continue
            if abs(d["parts"] - d["total"]) > tol:
                bad.append("%s 构成 %.6f ≠ 总量 %.6f（差 %.6f）"
                           % (g, d["parts"], d["total"], d["parts"] - d["total"]))
        return (not bad), "构成项闭合 %d 组：%s" % (len(groups), bad or "全部闭合")

    if t == "cross_sum":
        # 分组求和（本表）== 另一表对应值（跨表加性闭合）
        gcol, col = a["group"], a["column"]
        other = rows_of(result, a["vs_table"])
        if other is None:
            return False, "对拍表路径不存在：%s" % a["vs_table"]
        vkey, vcol = a["vs_key"], a["vs_column"]
        tol = a.get("tolerance", 1e-6)
        sums = {}
        for r in rows:
            v = num(r.get(col))
            if v is None:
                continue
            sums[str(r.get(gcol))] = sums.get(str(r.get(gcol)), 0.0) + v
        bad, n = [], 0
        for r in other:
            k = str(r.get(vkey))
            exp = num(r.get(vcol))
            if k not in sums or exp is None:
                continue
            n += 1
            if abs(sums[k] - exp) > tol:
                bad.append("%s 构成 %.6f ≠ %s 总量 %.6f（差 %.6f）"
                           % (k, sums[k], a["vs_table"], exp, sums[k] - exp))
        if n == 0:
            return False, "无可对齐分组（%s.%s vs %s.%s）" % (tbl_name, gcol, a["vs_table"], vkey)
        return (not bad), "跨表加性闭合 %d 组：%s" % (n, bad or "全部闭合")

    return False, "未知断言类型：%r" % (t,)


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="SQL 执行期结果断言（第二阶）")
    ap.add_argument("--result", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    for p in (args.result, args.spec):
        if not os.path.isfile(p):
            print("FAIL: 找不到 %s" % p)
            return 2

    result = load(args.result)
    spec = load(args.spec)
    assertions = spec.get("assertions") or []
    if not assertions:
        print("FAIL: spec.assertions 为空")
        return 2

    outcomes = []
    for a in assertions:
        try:
            ok, detail = run_assertion(a, result)
        except Exception as e:
            ok, detail = False, "断言执行异常：%s: %s" % (type(e).__name__, e)
        outcomes.append({"id": a.get("id", "?"), "type": a.get("type"),
                         "table": a.get("table"), "ok": ok, "detail": detail})

    failed = [o for o in outcomes if not o["ok"]]
    if args.json:
        print(json.dumps({"ok": not failed, "trace_id": spec.get("trace_id"),
                          "total": len(outcomes), "failed": len(failed),
                          "outcomes": outcomes}, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print("=" * 74)
    print("SQL 结果断言 · 第二阶（执行期 · 确定性）")
    print("=" * 74)
    print("  trace_id: %s" % spec.get("trace_id", "<none>"))
    print("  result  : %s" % os.path.basename(args.result))
    print("-" * 74)
    for o in outcomes:
        print("  [%s] %-10s %-18s %s"
              % ("PASS" if o["ok"] else "FAIL", o["id"], o["type"], o["detail"]))
    print("-" * 74)
    if failed:
        print("裁定：❌ 不通过（%d/%d）→ 数据不可信，禁止交付" % (len(failed), len(outcomes)))
    else:
        print("裁定：✅ 通过（%d/%d）→ 可进入第三阶换源对拍" % (len(outcomes), len(outcomes)))
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
