# -*- coding: utf-8 -*-
"""freshness_gate.py —— 第六道闸门：埋点时点闸门（确定性 · 零模型调用）

存在理由（证据 · 2026-11-20 用户纠正）：
  `knowledge/kb/ETL抽数日志与存储过程日志_权威区分.md`（🔴 铁律级）早就规定
  「全链路追溯六步：定指标→验血缘→解过程→**查抽数**→**查过程日志**→查落表」，
  `iron_rules.md` 第 14 条也写「三层埋点缺一不可」。
  但专家团在做 ODS 重算对拍时**三步全跳过**，只比了值、没比时点，
  于是把「ETL 07:30 后重抽导致的数据变化」误判成「数据错」。

  本闸门把那条铁律变成**可执行检查**：任何跨层对拍/根因分析，必须先过此闸。

用法：
    python tools/freshness_gate.py --probe knowledge/design/policy/probe_<TR>.json
    python tools/freshness_gate.py --probe <json> --json
    python tools/freshness_gate.py --template            # 打印探针模板

五道检查（任一失败 exit 1，禁止进入对拍/根因结论）：
    F1 ETL 抽数齐备  每个 ODS 表至少 1 条 ETL 记录（V_PUB_JOB_LOGS_LD_1D_X）
    F2 过程执行齐备  procedure 至少 1 条且 IS_SUCCESSFUL='T'（<CREATER_SCHEMA>.T_PUB_JOB_LOGS）
    F3 落表时间齐备  DWS 表有 LOAD_TIME / REC_CREATE_TIME
    F4 时点严格有序  ETL_TIME ≤ 过程 START ≤ 过程 LAST ≤ 落表 LOAD_TIME
    F5 跨源可比性    对拍源的 snapshot_key 必须一致，否则判 NOT_COMPARABLE

退出码：0 通过 ｜ 1 缺埋点/时序倒挂（禁止下结论） ｜ 6 跨源不可比 ｜ 2 输入错误
"""
import argparse
import datetime as _dt
import io
import json
import os
import sys

EXIT = {"PASS": 0, "FAIL": 1, "NOT_COMPARABLE": 6}


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def parse_ts(v):
    """容错解析：20261119073503 / 2026-11-19 07:35:03 / 2026-11-19T07:35:03"""
    if not v:
        return None
    s = str(v).strip().replace("-", "").replace(":", "").replace(" ", "").replace("T", "")
    s = s.split(".")[0]
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return _dt.datetime.strptime(s[:len(fmt.replace("%Y", "YYYY").replace("%m", "MM")
                                              .replace("%d", "DD").replace("%H", "HH")
                                              .replace("%M", "MM").replace("%S", "SS"))], fmt)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------- API 直采（--fetch）
# 来源：skills/sg-gzprod-etl-analyzer（ETL 抽数日志）
#       skills/sg-cbprod-procedure-analyzer（存储过程执行日志）
ETL_API = "http://eplat.fjsg.com/service/D_A_SMBBCS01_JOBLOGS_LD1D_X"
ETL_AUTH = ("sgdw-cs01", os.getenv("EPLAT_CLIENT_SECRET_CS01", ""))
PROC_API = "http://eplat.fjsg.com/service/D_A_SMBBCB00_PJJOB"
PROC_AUTH = ("sgdw-cb01", os.getenv("EPLAT_CLIENT_SECRET_CS01", ""))


def _post_json(url, payload, timeout=60):
    import json as _json
    import urllib.request
    req = urllib.request.Request(
        url, data=_json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json;charset=UTF-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _json.loads(r.read().decode("utf-8"))


def _rows(body):
    sysinfo = body.get("__sys__") or {}
    if sysinfo.get("status", -1) != 0:
        raise RuntimeError("API 返回错误：%s" % sysinfo.get("msg", "unknown"))
    res = ((body.get("__blocks__") or {}).get("result") or {})
    cols = [c["name"] for c in ((res.get("meta") or {}).get("columns") or [])]
    return [dict(zip(cols, row)) for row in (res.get("rows") or [])]


def fetch_etl(date_code, modules, ods_tables):
    """拉取 ETL 抽数日志，按 DES_OBJECT_NAME 过滤。date_code 形如 2026-11-19。"""
    want = {t.strip().upper() for t in (ods_tables or []) if t.strip()}
    out = []
    for mod in [m.strip() for m in (modules or "GZ4,GZ5,GZ6").split(",") if m.strip()]:
        try:
            body = _post_json(ETL_API, {
                "clientId": ETL_AUTH[0], "clientSecret": ETL_AUTH[1],
                "params": {"etlTime": date_code, "moduleType": mod},
                "showCount": "true", "offset": "0", "limit": 2000})
            rows = _rows(body)
        except Exception as e:  # noqa: BLE001
            print("  [WARN] ETL 模块 %s 拉取失败：%s" % (mod, e))
            continue
        for r in rows:
            des = str(r.get("DESOBJECTNAME") or "").upper()
            if want and des not in want:
                continue
            out.append({
                "des_object_name": r.get("DESOBJECTNAME"),
                "date_code": r.get("DATECODE"),
                "etl_time": r.get("ETLTIME"),
                "last_update": r.get("LASTUPDATE"),
                "is_successful": r.get("ISSUCCESSFUL"),
                "mins": r.get("MINS"),
                "job_name": r.get("JOBNAME"),
                "src_system_id": r.get("SRCSYSTEMID"),
            })
    return out


def fetch_proc(date_code, procedure, time_start="00:00", time_end="23:59"):
    """拉取存储过程执行日志，按 JOB_NAME 包含过程名过滤。date_code 形如 2026-11-19。"""
    try:
        body = _post_json(PROC_API, {
            "clientId": PROC_AUTH[0], "clientSecret": PROC_AUTH[1],
            "params": {"startTimestamp": date_code},
            "showCount": "true", "offset": "0", "limit": 2000})
        rows = _rows(body)
    except Exception as e:  # noqa: BLE001
        print("  [WARN] 过程日志拉取失败：%s" % e)
        return []
    key = (procedure or "").upper()
    sh, sm = map(int, time_start.split(":"))
    eh, em = map(int, time_end.split(":"))
    lo, hi = sh * 60 + sm, eh * 60 + em
    out = []
    for r in rows:
        jn = str(r.get("JOB_NAME") or "").upper()
        if key and key not in jn:
            continue
        ts = str(r.get("START_TIMESTAMP") or "")
        if len(ts) >= 12:
            mins = int(ts[8:10]) * 60 + int(ts[10:12])
            if not (lo <= mins <= hi):
                continue
        out.append({
            "job_name": r.get("JOB_NAME"),
            "start_timestamp": r.get("START_TIMESTAMP"),
            "last_timestamp": r.get("LAST_TIMESTAMP"),
            "elapsed": r.get("XHTIME"),
            "is_successful": r.get("IS_SUCCESSFUL"),
            "param_info": r.get("PARAM_INFO"),
            "error_desc": r.get("ERROR_DESC"),
        })
    return out


def build_probe_from_api(a):
    """用 --fetch 参数组装探针（自动拉三层埋点）。"""
    d = a.date
    iso = "%s-%s-%s" % (d[:4], d[4:6], d[6:8]) if "-" not in d else d
    ods = [t.strip() for t in (a.ods_tables or "").split(",") if t.strip()]
    print("  正在拉取 ETL 抽数日志（%s / %s）..." % (iso, a.module))
    etl = fetch_etl(iso, a.module, ods)
    print("    → %d 条" % len(etl))
    print("  正在拉取存储过程执行日志（%s / %s）..." % (iso, a.procedure or "全部"))
    proc = fetch_proc(iso, a.procedure)
    print("    → %d 条" % len(proc))
    # 生产域（ZZ00）过程日志 API 不覆盖 → 允许用 --proc-log 回填 DB2 查询结果
    if not proc and a.proc_log:
        if os.path.isfile(a.proc_log):
            with io.open(a.proc_log, encoding="utf-8-sig") as f:
                loaded = json.load(f)
            proc = loaded if isinstance(loaded, list) else (loaded.get("rows") or [])
            print("    ↳ 已从 --proc-log 回填 %d 条（DB2 T_PUB_JOB_LOGS）" % len(proc))
        else:
            print("  [WARN] --proc-log 文件不存在：%s" % a.proc_log)
    return {
        "trace_id": a.trace_id or "TR-FRESH-AUTO",
        "target": {
            "zb_code": a.zb_code or "", "date": d,
            "ods_tables": ods, "procedure": a.procedure or "",
            "creater_schema": a.creater_schema or "", "dws_table": a.dws_table or "",
            "procedure_source": "api" if proc else "db2",
        },
        "probes": {
            "etl": etl, "procedure": proc,
            "load": ([{"table": a.dws_table, "load_time": a.load_time}] if a.load_time else []),
        },
        "comparison": {"sources": []},
    }


TEMPLATE = {
    "_说明": "把本模板填好后存为 knowledge/design/policy/probe_<TR>.json，再跑 freshness_gate.py",
    "trace_id": "TR-YYYYMMDD-HHMM-XXXX",
    "target": {
        "zb_code": "1600213",
        "date": "20261119",
        "ods_tables": ["T_ODS_TMMSM21", "T_ODS_TMMSM01"],
        "procedure": "P_DWS_FACT_ZZGZ_0003",
        "creater_schema": "SMBB_M_S_ZZ00",
        "dws_table": "T_DWS_FACT_ZZGZ_LG01"
    },
    "probes": {
        "etl": [
            {"des_object_name": "T_ODS_TMMSM21", "date_code": "2026-11-19",
             "etl_time": "2026-11-19 05:32:44", "last_update": "2026-11-19 05:33:40",
             "is_successful": "T", "mins": 0.96, "job_name": "LD_COM_312",
             "src_system_id": "SGP1Z1"}
        ],
        "procedure": [
            {"job_name": "P_DWS_FACT_ZZGZ_0003", "start_timestamp": "20261119045537",
             "last_timestamp": "20261119045734", "elapsed": 116, "is_successful": "T",
             "param_info": "P_YMD=20261118"}
        ],
        "load": [
            {"table": "T_DWS_FACT_ZZGZ_LG01", "load_time": "20261119073503"}
        ]
    },
    "comparison": {
        "sources": [
            {"source_id": "S1_DWS", "layer": "DWS", "snapshot_key": "D-20261119"},
            {"source_id": "S2_ODS", "layer": "ODS", "snapshot_key": "LIVE-20261120T1720"}
        ]
    }
}


def check(probe):
    tgt = probe.get("target") or {}
    pr = probe.get("probes") or {}
    etl = pr.get("etl") or []
    proc = pr.get("procedure") or []
    load = pr.get("load") or []
    errs, oks, warns = [], [], []

    # F1 ETL 抽数齐备
    want = [t.upper() for t in (tgt.get("ods_tables") or [])]
    got = {(x.get("des_object_name") or "").upper() for x in etl}
    missing = [t for t in want if t not in got]
    if not etl:
        errs.append("F1 ETL 抽数日志为空（须查 SMBB_M_A_CS01.V_PUB_JOB_LOGS_LD_1D_X）")
    elif missing:
        errs.append("F1 以下 ODS 表缺 ETL 抽数记录：%s" % ", ".join(missing))
    else:
        oks.append("F1 ETL 抽数齐备（%d 张 ODS 表 / %d 条记录）" % (len(want), len(etl)))
    bad_etl = [x.get("job_name") for x in etl if str(x.get("is_successful", "T")).upper() != "T"]
    if bad_etl:
        errs.append("F1 ETL 抽数失败：%s" % ", ".join(str(b) for b in bad_etl))

    # F2 过程执行齐备
    proc_name = (tgt.get("procedure") or "").upper()
    hit = [x for x in proc if proc_name and proc_name in (x.get("job_name") or "").upper()]
    # 2026-11-20 实测：PJJOB API 只覆盖 CB00 成本域（D_A_SMBBCB00_PJJOB）；
    # 生产域 ZZ00 的过程日志**没有对应 API**，必须查 DB2 SMBB_M_S_ZZ00.T_PUB_JOB_LOGS。
    is_prod_domain = any(k in proc_name for k in ("ZZGZ", "ZZ00", "GZPROD"))
    if not proc:
        if is_prod_domain:
            errs.append(
                "F2 生产域过程 %s 的过程日志**不在 PJJOB API 覆盖范围**"
                "（该 API 仅 CB00 成本域）→ 必须查 DB2 `SMBB_M_S_ZZ00.T_PUB_JOB_LOGS`"
                "（`WHERE JOB_NAME LIKE '%%%s%%' AND SUBSTR(START_TIMESTAMP,1,8)='<YYYYMMDD>'`）"
                "，再用 `--proc-log` 回填" % (proc_name or "?", proc_name or "?"))
        else:
            errs.append("F2 存储过程执行日志为空（须查 <CREATER_SCHEMA>.T_PUB_JOB_LOGS）")
    elif proc_name and not hit:
        errs.append("F2 未找到过程 %s 的执行记录" % proc_name)
    else:
        oks.append("F2 过程执行日志齐备（%s，%d 条）" % (proc_name or "—", len(proc or hit)))
    bad_proc = [x.get("job_name") for x in (hit or proc) if str(x.get("is_successful", "T")).upper() != "T"]
    if bad_proc:
        errs.append("F2 过程执行失败：%s" % ", ".join(str(b) for b in bad_proc))

    # F3 落表时间齐备
    dws = (tgt.get("dws_table") or "").upper()
    lh = [x for x in load if not dws or dws in (x.get("table") or "").upper()]
    lts = [parse_ts(x.get("load_time") or x.get("rec_create_time")) for x in lh]
    lts = [t for t in lts if t]
    if not lts:
        errs.append("F3 目标表缺 LOAD_TIME / REC_CREATE_TIME（%s）" % (dws or "未指定"))
    else:
        oks.append("F3 落表时间齐备（%s LOAD_TIME=%s）"
                   % (dws or "—", max(lts).strftime("%Y%m%d%H%M%S")))

    # F4 时点严格有序
    ets = sorted(t for t in (parse_ts(x.get("etl_time")) for x in etl) if t)
    sts = sorted(t for t in (parse_ts(x.get("start_timestamp")) for x in (hit or proc)) if t)
    fts = sorted(t for t in (parse_ts(x.get("last_timestamp")) for x in (hit or proc)) if t)
    if ets and sts and lts:
        first_etl, last_etl = ets[0], ets[-1]
        first_proc, last_proc = sts[0], (fts[-1] if fts else sts[-1])
        last_load = max(lts)
        # 基本序：过程必须在落表之前结束（否则落表时间不可信）
        if last_proc > last_load:
            errs.append("F4 时序倒挂：过程结束 %s 晚于落表 %s"
                        % (last_proc.strftime("%H:%M:%S"), last_load.strftime("%H:%M:%S")))
            # 基本序：过程开始前 ODS 至少抽过一次
        elif first_etl > first_proc:
            warns.append("F4 过程首次执行 %s 早于首次 ETL 抽数 %s（首跑可能用了前一日数据）"
                         % (first_proc.strftime("%H:%M:%S"), first_etl.strftime("%H:%M:%S")))
        else:
            oks.append("F4 时点有序：ETL 首抽 %s ≤ 过程 %s→%s ≤ 落表 %s"
                       % (first_etl.strftime("%H:%M:%S"), first_proc.strftime("%H:%M:%S"),
                          last_proc.strftime("%H:%M:%S"), last_load.strftime("%H:%M:%S")))
        # ⭐ 关键：落表之后 ODS 是否又抽过数（= DWS 快照落后的直接证据）
        newer = [t for t in ets if t > last_load]
        if newer:
            warns.append(
                "F4 ⚠ **落表 %s 之后 ODS 又抽数 %d 次（最晚 %s）** → "
                "DWS 快照已落后于 ODS，**两者不可直接比，差异不等于数据错**"
                % (last_load.strftime("%Y-%m-%d %H:%M:%S"), len(newer),
                   max(newer).strftime("%Y-%m-%d %H:%M:%S")))
    else:
        warns.append("F4 埋点不全，无法验证时序（缺 ETL/过程/落表 中至少一类）")

    # F5 跨源可比性
    srcs = ((probe.get("comparison") or {}).get("sources")) or []
    keys = {(s.get("snapshot_key") or s.get("snapshot_time")) for s in srcs if s.get("snapshot_key") or s.get("snapshot_time")}
    if len(srcs) >= 2 and len(keys) > 1:
        errs.append("F5 跨源不可比：snapshot_key 不一致 %s → 时间不同，**禁止判数据对错**"
                    % sorted(str(k) for k in keys))

    if errs:
        verdict = "FAIL"
    elif any("F5" in e for e in errs):
        verdict = "NOT_COMPARABLE"
    else:
        verdict = "PASS"
    return verdict, errs, warns, oks


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="埋点时点闸门（第六道）")
    ap.add_argument("--probe", help="探针 JSON 路径")
    ap.add_argument("--template", action="store_true", help="打印探针模板")
    ap.add_argument("--json", action="store_true")
    # ---- --fetch：直接调 API 拉三层埋点（免手工填探针）----
    ap.add_argument("--fetch", action="store_true", help="从 ETL/过程日志 API 直采埋点")
    ap.add_argument("--date", default="", help="YYYYMMDD 或 YYYY-MM-DD")
    ap.add_argument("--module", default="GZ4,GZ5,GZ6", help="ETL 模块，逗号分隔")
    ap.add_argument("--ods-tables", default="", help="ODS 表名，逗号分隔（过滤 DESOBJECTNAME）")
    ap.add_argument("--procedure", default="", help="存储过程名（过滤 JOB_NAME）")
    ap.add_argument("--creater-schema", default="")
    ap.add_argument("--dws-table", default="")
    ap.add_argument("--load-time", default="", help="DWS 落表时间 YYYYMMDDHH24MISS")
    ap.add_argument("--zb-code", default="")
    ap.add_argument("--trace-id", default="")
    ap.add_argument("--proc-log", default="",
                    help="DB2 查得的 T_PUB_JOB_LOGS 结果 JSON（生产域过程日志 API 不覆盖时回填）")
    ap.add_argument("--dump-probe", action="store_true", help="配合 --fetch：把探针落盘后再判")
    args = ap.parse_args(argv)

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0

    if args.fetch:
        if not args.date:
            print("FAIL: --fetch 需 --date")
            return 2
        probe = build_probe_from_api(args)
        if args.dump_probe:
            out = os.path.join(PKG, "knowledge", "design", "policy",
                               "probe_%s.json" % (args.trace_id or args.date))
            with io.open(out, "w", encoding="utf-8") as f:
                json.dump(probe, f, ensure_ascii=False, indent=2)
            print("  探针已落盘：%s" % out)
    elif args.probe:
        if not os.path.isfile(args.probe):
            print("FAIL: 找不到 %s" % args.probe)
            return 2
        with io.open(args.probe, encoding="utf-8-sig") as f:
            probe = json.load(f)
    else:
        print("FAIL: 需 --probe 或 --fetch 或 --template")
        return 2

    verdict, errs, warns, oks = check(probe)
    if "F5" in "".join(errs):
        verdict = "NOT_COMPARABLE"

    if args.json:
        print(json.dumps({"verdict": verdict, "trace_id": probe.get("trace_id"),
                          "errors": errs, "warnings": warns, "checks": oks},
                         ensure_ascii=False, indent=2))
        return EXIT.get(verdict, 1)

    tgt = probe.get("target") or {}
    print("=" * 80)
    print("埋点时点闸门 · 第六道（全链路追溯三层埋点）")
    print("=" * 80)
    print("  指标 : %s ｜ 日期 : %s" % (tgt.get("zb_code", "—"), tgt.get("date", "—")))
    print("  过程 : %s @ %s" % (tgt.get("procedure", "—"), tgt.get("creater_schema", "—")))
    print("-" * 80)
    print("  三层埋点时间线：")
    for x in (probe.get("probes") or {}).get("etl") or []:
        print("    [ETL 抽数]    %-16s %s  →  %s  (%s min, %s)"
              % (x.get("des_object_name", "?"), x.get("etl_time", "?"),
                 x.get("last_update", "?"), x.get("mins", "?"), x.get("job_name", "?")))
    for x in (probe.get("probes") or {}).get("procedure") or []:
        print("    [过程执行]    %-32s %s → %s  (%ss, %s)"
              % (x.get("job_name", "?"), x.get("start_timestamp", "?"),
                 x.get("last_timestamp", "?"), x.get("elapsed", "?"), x.get("is_successful", "?")))
    for x in (probe.get("probes") or {}).get("load") or []:
        print("    [落表]        %-32s LOAD_TIME=%s"
              % (x.get("table", "?"), x.get("load_time", "?")))
    print("-" * 80)
    for o in oks:
        print("  [PASS] %s" % o)
    for w in warns:
        print("  [WARN] %s" % w)
    for e in errs:
        print("  [FAIL] %s" % e)
    print("-" * 80)
    if verdict == "PASS":
        print("裁定：✅ 通过 → 三层埋点齐备、时点有序，可进入对拍/根因结论")
    elif verdict == "NOT_COMPARABLE":
        print("裁定：⏳ 跨源不可比 → **禁止判数据对错**；须对齐快照（重跑 DWS）后再比")
    else:
        print("裁定：❌ 不通过（%d 项）→ **禁止下根因/对拍结论**" % len(errs))
    print("=" * 80)
    return EXIT.get(verdict, 1)


if __name__ == "__main__":
    sys.exit(main())
