# -*- coding: utf-8 -*-
"""埋点时点闸门（第六道）回归测试：1 正例 + 7 反例。"""
import copy
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(HERE, "tools", "freshness_gate.py")
TMP = os.path.join(HERE, "artifacts", "compiled", "_selftest")
os.makedirs(TMP, exist_ok=True)

BASE = {
    "trace_id": "TR-TEST-FRESH",
    "target": {"zb_code": "1600213", "date": "20261119",
               "ods_tables": ["T_ODS_TMMSM21"],
               "procedure": "P_DWS_FACT_ZZGZ_0003", "creater_schema": "SMBB_M_S_ZZ00",
               "dws_table": "T_DWS_FACT_ZZGZ_LG01"},
    "probes": {
        "etl": [{"des_object_name": "T_ODS_TMMSM21", "etl_time": "2026-11-19 05:32:44",
                 "last_update": "2026-11-19 05:33:40", "is_successful": "T",
                 "mins": 0.96, "job_name": "LD_COM_312"}],
        "procedure": [{"job_name": "P_DWS_FACT_ZZGZ_0003", "start_timestamp": "20261119045537",
                       "last_timestamp": "20261119045734", "elapsed": 116, "is_successful": "T"}],
        "load": [{"table": "T_DWS_FACT_ZZGZ_LG01", "load_time": "20261119073503"}],
    },
    "comparison": {"sources": [
        {"source_id": "S1", "layer": "DWS", "snapshot_key": "D-20261119"},
        {"source_id": "S2", "layer": "REPORT", "snapshot_key": "D-20261119"},
    ]},
}

CASES = []


def case(name, mutate, expect, kw):
    c = copy.deepcopy(BASE)
    mutate(c)
    CASES.append((name, c, expect, kw))


case("正例 · 三层埋点齐备且同快照", lambda c: None, 0, "通过")

case("反例1 · 缺 ETL 抽数日志", lambda c: c["probes"].__setitem__("etl", []), 1, "ETL 抽数日志为空")
case("反例2 · 缺过程执行日志", lambda c: c["probes"].__setitem__("procedure", []),
     1, "不在 PJJOB API 覆盖范围")
case("反例3 · 缺落表时间", lambda c: c["probes"].__setitem__("load", []), 1, "缺 LOAD_TIME")
case("反例4 · ETL 抽数失败",
     lambda c: c["probes"]["etl"][0].__setitem__("is_successful", "F"), 1, "ETL 抽数失败")
case("反例5 · 过程执行失败",
     lambda c: c["probes"]["procedure"][0].__setitem__("is_successful", "F"), 1, "过程执行失败")
case("反例6 · 时序倒挂（过程晚于落表）",
     lambda c: c["probes"]["procedure"][0].__setitem__("last_timestamp", "20261119235959"),
     1, "时序倒挂")
case("反例7 · 跨源快照不可比",
     lambda c: c["comparison"]["sources"][1].__setitem__("snapshot_key", "LIVE-20261120T1720"),
     6, "跨源不可比")

fails = []
for i, (name, c, expect, kw) in enumerate(CASES):
    p = os.path.join(TMP, "fresh%02d.json" % i)
    io.open(p, "w", encoding="utf-8").write(json.dumps(c, ensure_ascii=False))
    r = subprocess.run([sys.executable, GATE, "--probe", p], capture_output=True,
                       text=True, encoding="utf-8")
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == expect and kw in out
    print("  [%s] %-28s exit=%d(期望%d) 「%s」"
          % ("OK  " if ok else "FAIL", name, r.returncode, expect, kw))
    if not ok:
        fails.append((name, r.returncode, expect, out[-700:]))

# 额外：落表后 ODS 重抽 → 必须 WARN 但 exit 0
c = copy.deepcopy(BASE)
c["probes"]["etl"].append({"des_object_name": "T_ODS_TMMSM21", "etl_time": "2026-11-19 12:09:12",
                           "last_update": "2026-11-19 12:09:14", "is_successful": "T",
                           "mins": 0.03, "job_name": "LD_COM_312"})
p = os.path.join(TMP, "fresh_rerun.json")
io.open(p, "w", encoding="utf-8").write(json.dumps(c, ensure_ascii=False))
r = subprocess.run([sys.executable, GATE, "--probe", p], capture_output=True, text=True, encoding="utf-8")
out = (r.stdout or "") + (r.stderr or "")
ok = r.returncode == 0 and "又抽数" in out and "不可直接比" in out
print("  [%s] %-28s exit=%d(期望0) 「落表后重抽→WARN 但放行」"
      % ("OK  " if ok else "FAIL", "正例 · 落表后 ODS 重抽告警", r.returncode))
if not ok:
    fails.append(("落表后重抽", r.returncode, 0, out[-700:]))

print()
if fails:
    print("❌ %d/8 用例失败" % len(fails))
    for f in fails:
        print("--- %s exit=%s 期望=%s ---\n%s" % f)
    sys.exit(1)
print("✅ 全部 8 个用例通过（2 正例 + 6 反例）")
sys.exit(0)
