# -*- coding: utf-8 -*-
"""sql_static_check.py —— SQL 第一阶：编译期静态校验（确定性 · 零模型调用 · 零数据库连接）

来源：借鉴 dsh-superagent「Gate 层确定性、模型不碰权限」的思路，把 SQL 正确性中
      **可机械判定** 的部分从「专家经验」下沉为「脚本闸门」。

职责：在 SQL 交给 sg-development 执行 **之前** 拦截高频错误。
      不通过 → 禁止执行（exit 1）。

用法：
    python tools/sql_static_check.py --sql artifacts/compiled/q_xxx.sql
    python tools/sql_static_check.py --sql <file> --json
    python tools/sql_static_check.py --dir artifacts/compiled
    python tools/sql_static_check.py --sql <file> --strict          # WARN 也判失败
    python tools/sql_static_check.py --sql <file> --schema-json x.json

九道检查（ERR 必拦 / WARN 建议）：
    S1 只读断言：禁止 INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE/GRANT/REVOKE/CALL/COMMIT/ROLLBACK
    S2 禁止 SELECT *（无法保证列契约稳定）
    S3 表存在性（--strict-tables 时 ERR，否则 WARN）
    S4 别名限定列存在性（只对已解析到字典的表做，避免 CTE 误判）
    S5 除零保护：`/` 必须被 DECODE/NULLIF/CASE 包裹（括号栈判定，非文本邻近）
    S6 空值兜底：**顶层**聚合必须被 NVL/COALESCE 包裹（被 DECODE 包裹的嵌套聚合不算）
    S7 类型风险：VARCHAR 列强转 DECIMAL 必须经 NULLIF/TRANSLATE/TRIM 清洗
    S8 日期字面量：仅对日期列比较处的字面量校验 8 位（避免把 ZB_CODE 当日期）
    S9 语义自检：计算比率的表若未同时取分子/分母 → 无法复算对拍

退出码：0 通过 ｜ 1 不通过 ｜ 2 输入/环境错误
"""
import argparse
import glob
import io
import json
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K1 = os.path.join(PKG, "knowledge", "corpus", "docs", "K1_表结构语料.md")
MODEL = os.path.join(PKG, "knowledge", "observed", "schema", "表列模型-2026-09-02.json")

WRITE_KW = ("INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "CREATE", "ALTER",
            "TRUNCATE", "GRANT", "REVOKE", "CALL", "COMMIT", "ROLLBACK",
            "REORG", "RUNSTATS", "LOAD")
AGG = ("SUM", "AVG", "MIN", "MAX", "COUNT", "STDDEV", "VARIANCE")
GUARD_FN = {"DECODE", "NULLIF", "CASE"}
NVL_FN = {"NVL", "COALESCE", "IFNULL", "VALUE"}
DATE_COL_RE = r"(?:[A-Z_]*DATE[A-Z_]*|[A-Z_]*TIME[A-Z_]*|YMD|ACCOUNT_PERIOD|KPI_TIME|WORK_DATE)"

RESERVED = set("""
SELECT FROM WHERE GROUP BY ORDER HAVING JOIN LEFT RIGHT INNER OUTER FULL ON AS AND OR NOT
IN IS NULL LIKE BETWEEN CASE WHEN THEN ELSE END DISTINCT UNION ALL EXISTS ASC DESC
WITH VALUES FETCH FIRST ROWS ONLY OVER PARTITION RANGE ROW ROWS CURRENT DATE TIME TIMESTAMP
NULLIF COALESCE DECODE NVL NVL2 TRANSLATE TRIM UPPER LOWER SUBSTR SUBSTRING CAST LENGTH
CHAR DECIMAL DECFLOAT INTEGER INT SMALLINT BIGINT DOUBLE REAL VARCHAR
LPAD RPAD ROUND TRUNC ABS MOD CEIL FLOOR POWER SQRT ROW_NUMBER RANK DENSE_RANK
""".split())


def load_columns(k1_path, model_path, extra_path=None):
    cols, roles = {}, {}
    if os.path.isfile(k1_path):
        table = None
        with io.open(k1_path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^##\s+([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\s*$", line.strip())
                if m:
                    table = m.group(1).split(".")[-1].upper()
                    cols.setdefault(table, {})
                    continue
                if table is None or not line.strip().startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 4 or cells[0] in ("字段",) or set(cells[0]) <= {"-"}:
                    continue
                name = cells[0].upper()
                if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
                    continue
                cols[table][name] = (cells[1].upper(), cells[2])

    if os.path.isfile(model_path):
        try:
            with io.open(model_path, encoding="utf-8") as f:
                model = json.load(f)
        except Exception:
            model = {}
        for t, meta in (model or {}).items():
            t = t.upper()
            cols.setdefault(t, {})
            r = {}
            for role in ("date", "unit", "item", "val", "nmrt", "dnmt"):
                v = (meta or {}).get(role)
                if isinstance(v, str) and v.strip():
                    r[role] = v.strip().upper()
                    cols[t].setdefault(r[role], ("UNKNOWN", ""))
            if r:
                roles[t] = r

    if extra_path and os.path.isfile(extra_path):
        with io.open(extra_path, encoding="utf-8") as f:
            extra = json.load(f)
        for t, cs in (extra or {}).items():
            t = t.upper()
            cols.setdefault(t, {})
            if isinstance(cs, list):
                for c in cs:
                    cols[t].setdefault(str(c).upper(), ("UNKNOWN", ""))
            elif isinstance(cs, dict):
                for c, ty in cs.items():
                    cols[t][str(c).upper()] = (str(ty).upper(), "")
    return cols, roles


def strip_noise(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    lits = []

    def _sub(m):
        lits.append((m.start(), m.group(0)))
        return "__LIT__" + " " * max(0, len(m.group(0)) - 7)

    return re.sub(r"'(?:[^']|'')*'", _sub, sql), lits


def split_statements(sql):
    parts, buf, in_str = [], [], False
    for ch in sql:
        if ch == "'":
            in_str = not in_str
        if ch == ";" and not in_str:
            if "".join(buf).strip():
                parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return parts


def fn_stack(stmt):
    """返回每个字符位置上的「包围函数名元组」（括号栈）。"""
    stack, out = [], []
    i = 0
    n = len(stmt)
    while i < n:
        ch = stmt[i]
        if ch == "(":
            j = i - 1
            while j >= 0 and stmt[j].isspace():
                j -= 1
            k = j
            while k >= 0 and (stmt[k].isalnum() or stmt[k] == "_"):
                k -= 1
            name = stmt[k + 1:j + 1].upper()
            stack.append(name if name and not name[0].isdigit() else "")
            out.append(tuple(stack))
        elif ch == ")":
            if stack:
                stack.pop()
            out.append(tuple(stack))
        else:
            out.append(tuple(stack))
        i += 1
    return out


def check_statement(stmt, literals, cols, roles, opts):
    errs, warns, oks = [], [], []
    up = stmt.upper()

    bad = [k for k in WRITE_KW if re.search(r"\b%s\b" % re.escape(k), up)]
    if bad:
        errs.append("S1 含写操作关键字：%s（只读护栏）" % ", ".join(sorted(set(bad))))
    else:
        oks.append("S1 只读")

    if re.search(r"\bSELECT\s+(?:DISTINCT\s+)?\*", up):
        errs.append("S2 存在 SELECT *（必须显式投影）")
    else:
        oks.append("S2 无 SELECT *")

    # S3 表解析
    tables, alias = [], {}
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?)(?:\s+(?:AS\s+)?([A-Za-z][A-Za-z0-9_]*))?", stmt, re.I):
        raw = m.group(1)
        tbl = raw.split(".")[-1].upper()
        if tbl in RESERVED:
            continue
        tables.append(tbl)
        a = (m.group(2) or "").upper()
        if a and a not in RESERVED:
            alias[a] = tbl
    known = sorted({t for t in tables if t in cols})
    unknown = sorted({t for t in tables if t not in cols})
    if unknown:
        (errs if opts["strict_tables"] else warns).append("S3 表未在列字典：%s" % ", ".join(unknown))
    if tables:
        oks.append("S3 表解析 %d/%d 已知" % (len(known), len(set(tables))))

    # S4 别名限定列（仅当别名解析到已知表）
    universe = set()
    for t in known:
        universe |= set(cols[t].keys())
    badcols = set()
    for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]*)\s*\.\s*([A-Za-z][A-Za-z0-9_]*)\b", stmt):
        q, c = m.group(1).upper(), m.group(2).upper()
        tgt = alias.get(q)
        if tgt in cols and c not in cols[tgt] and c not in RESERVED:
            badcols.add("%s.%s" % (q, c))
    if badcols:
        errs.append("S4 别名限定列不存在：%s" % ", ".join(sorted(badcols)))
    elif known:
        oks.append("S4 别名限定列全部存在")

    # S5 除零保护（括号栈）
    fs = fn_stack(stmt)
    div_bad = []
    for m in re.finditer(r"/", stmt):
        i = m.start()
        stack = fs[i] if i < len(fs) else ()
        if not any(f in GUARD_FN for f in stack):
            div_bad.append(stmt[max(0, i - 35):i + 35].replace("\n", " "))
    if div_bad:
        errs.append("S5 除法未做除零保护：%d 处，例：%s" % (len(div_bad), div_bad[0][:68]))
    elif "/" in stmt:
        oks.append("S5 除法全有除零保护")

    # S6 顶层聚合空值兜底
    if not opts["ignore_nvl"]:
        miss = []
        for a in AGG:
            for m in re.finditer(r"\b%s\s*\(" % a, up):
                i = m.start()
                stack = fs[i] if i < len(fs) else ()
                if not stack:
                    miss.append(a)
                elif not any(f in NVL_FN or f in GUARD_FN for f in stack):
                    miss.append(a)
        if miss:
            warns.append("S6 顶层聚合未包 NVL：%s（%d 处）" % (",".join(sorted(set(miss))), len(miss)))
        else:
            oks.append("S6 聚合有空值兜底")

    # S7 强转清洗
    if re.search(r"\bCAST\s*\([^)]*\bAS\s+(?:DECIMAL|DECFLOAT|INTEGER|BIGINT)\b", up):
        if not re.search(r"(NULLIF|TRANSLATE|TRIM)\s*\(", up):
            errs.append("S7 CAST 强转无 NULLIF/TRANSLATE/TRIM 清洗（-420/-171 风险）")
        else:
            oks.append("S7 强转已清洗")

    # S8 日期字面量（仅日期列比较处）
    bad_dates = []
    for pos, lit in literals:
        v = lit.strip("'")
        if not re.fullmatch(r"\d+", v):
            continue
        before = stmt[max(0, pos - 48):pos].upper()
        if not re.search(r"%s\s*(?:=|>=|<=|<|>|BETWEEN)\s*$" % DATE_COL_RE, before) and \
           not re.search(r"BETWEEN\s*$", before):
            continue
        if len(v) not in (8,):
            bad_dates.append(lit)
    if bad_dates:
        errs.append("S8 日期字面量非 8 位：%s" % ", ".join(bad_dates[:5]))
    elif any(1 for _ in literals):
        oks.append("S8 日期字面量格式正确")

    # S9 比率复算自检（仅当语句确实算了比率）
    if "/" in stmt:
        for t in known:
            r = roles.get(t, {})
            if not (r.get("nmrt") and r.get("dnmt")):
                continue
            if r["nmrt"] not in up or r["dnmt"] not in up:
                warns.append("S9 %s 算了比率但未同时取 %s/%s，无法复算对拍"
                             % (t, r["nmrt"], r["dnmt"]))
                break
    return errs, warns, oks


def run_file(path, cols, roles, opts):
    with io.open(path, encoding="utf-8-sig") as f:
        sql = f.read()
    clean, literals = strip_noise(sql)
    stmts = split_statements(clean)
    e_all, w_all, o_all = [], [], []
    for idx, s in enumerate(stmts, 1):
        e, w, o = check_statement(s, literals, cols, roles, opts)
        e_all += ["[Q%d] %s" % (idx, x) for x in e]
        w_all += ["[Q%d] %s" % (idx, x) for x in w]
        o_all.append((idx, o))
    return len(stmts), e_all, w_all, o_all


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="SQL 编译期静态校验（第一阶）")
    ap.add_argument("--sql")
    ap.add_argument("--dir")
    ap.add_argument("--schema-json")
    ap.add_argument("--strict-tables", action="store_true")
    ap.add_argument("--ignore-nvl", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="只打印裁定")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.sql and not args.dir:
        print("FAIL: 需 --sql 或 --dir")
        return 2
    files = [args.sql] if args.sql else sorted(glob.glob(os.path.join(args.dir, "*.sql")))
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        print("FAIL: 未找到 SQL 文件")
        return 2

    cols, roles = load_columns(K1, MODEL, args.schema_json)
    opts = {"strict_tables": args.strict_tables, "ignore_nvl": args.ignore_nvl}

    report, failed, te, tw = [], False, 0, 0
    for p in files:
        n, e, w, o = run_file(p, cols, roles, opts)
        bad = bool(e) or (args.strict and bool(w))
        failed = failed or bad
        te += len(e)
        tw += len(w)
        report.append({"file": os.path.basename(p), "statements": n,
                       "errors": e, "warnings": w,
                       "checks": [{"q": q, "items": it} for q, it in o]})

    if args.json:
        print(json.dumps({"ok": not failed, "files": report, "errors": te, "warnings": tw},
                         ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print("=" * 72)
    print("SQL 静态校验 · 第一阶（编译期 · 确定性）")
    print("=" * 72)
    print("  列字典：%d 表 ｜ 语义角色：%d 表" % (len(cols), len(roles)))
    for r in report:
        print("-" * 72)
        print("  %s（%d 条语句）" % (r["file"], r["statements"]))
        if not args.quiet:
            for c in r["checks"]:
                for item in c["items"]:
                    print("    [PASS] Q%d %s" % (c["q"], item))
            for w in r["warnings"]:
                print("    [WARN] %s" % w)
        for e in r["errors"]:
            print("    [FAIL] %s" % e)
    print("=" * 72)
    print(("裁定：❌ 不通过（ERR %d ｜ WARN %d）→ 禁止执行，退回 sg-development 重编" % (te, tw))
          if failed else ("裁定：✅ 通过（ERR 0 ｜ WARN %d）→ 可进入第二阶执行" % tw))
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
