# -*- coding: utf-8 -*-
"""三阶校验回归测试：3 正例 + 6 反例。"""
import copy
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T2 = os.path.join(HERE, "tools", "sql_result_assert.py")
T3 = os.path.join(HERE, "tools", "sql_cross_source.py")
TMP = os.path.join(HERE, "artifacts", "compiled", "_selftest")
os.makedirs(TMP, exist_ok=True)

RESULT = os.path.join(HERE, "observed", "data_package_TR-20261120-1046-9C1F.json")
SPEC = os.path.join(HERE, "knowledge", "design", "policy", "assert_spec_TR-20261120-1046-9C1F.json")
RECON = os.path.join(HERE, "knowledge", "design", "policy", "recon_TR-20261120-1046-9C1F.json")

BASE_SPEC = json.load(io.open(SPEC, encoding="utf-8"))
BASE_RECON = json.load(io.open(RECON, encoding="utf-8"))
BASE_RESULT = json.load(io.open(RESULT, encoding="utf-8"))

_fail = []


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _record(tag, name, code, expect, kw, out):
    ok = code == expect and (kw is None or kw in out)
    print("  [%s] %-34s exit=%d(期望%d)%s"
          % ("OK  " if ok else "FAIL", name, code, expect, "" if kw is None else " 「%s」" % kw))
    if not ok:
        _fail.append((tag, name, code, expect, out))


def stage2(name, expect, kw, spec_mut=None, result_mut=None):
    s = copy.deepcopy(BASE_SPEC)
    r = copy.deepcopy(BASE_RESULT)
    if spec_mut:
        spec_mut(s)
    if result_mut:
        result_mut(r)
    sp = os.path.join(TMP, "spec_%d.json" % (abs(hash(name)) % 100000))
    rp = os.path.join(TMP, "res_%d.json" % (abs(hash(name)) % 100000))
    io.open(sp, "w", encoding="utf-8").write(json.dumps(s, ensure_ascii=False))
    io.open(rp, "w", encoding="utf-8").write(json.dumps(r, ensure_ascii=False))
    code, out = _run([sys.executable, T2, "--result", rp, "--spec", sp])
    _record("S2", name, code, expect, kw, out)


def stage3(name, expect, kw, recon_mut=None):
    s = copy.deepcopy(BASE_RECON)
    if recon_mut:
        recon_mut(s)
    p = os.path.join(TMP, "recon_%d.json" % (abs(hash(name)) % 100000))
    io.open(p, "w", encoding="utf-8").write(json.dumps(s, ensure_ascii=False))
    code, out = _run([sys.executable, T3, "--spec", p])
    _record("S3", name, code, expect, kw, out)


def add_ods(delta, only_first=False):
    def _m(s):
        if only_first:
            s["metrics"] = s["metrics"][:1]
        src = s["metrics"][0]["sources"][2]
        src.pop("reason", None)
        src["values"] = {k: round(v + delta, 6) for k, v in {
            "20261113": 508.61, "20261114": 508.92, "20261115": 508.19,
            "20261116": 508.49, "20261117": 508.65, "20261118": 510.29,
            "20261119": 509.35}.items()}
    return _m


print("=== 第二阶 · 结果断言 ===")
stage2("正例 · 真实数据包", 0, "通过")

stage2("反例1 · 行数不符", 1, "行数 14（期望 15）",
       spec_mut=lambda s: s["assertions"][0].__setitem__("expect", 15))
stage2("反例2 · 厂别越界", 1, "越界取值",
       spec_mut=lambda s: s["assertions"][2].__setitem__("allow", ["泉州闽钢"]))
stage2("反例3 · 值域越界", 1, "越界",
       spec_mut=lambda s: s["assertions"][3].__setitem__("min", 1100))
stage2("反例4 · 零值闭合破坏", 1, "全 0",
       spec_mut=lambda s: s["assertions"][15].__setitem__("allow_groups", []))
stage2("反例5 · 跨表加性不闭合", 1, "构成",
       result_mut=lambda r: r["Q4_furnace_drilldown"][0].__setitem__(
           "NMRT_VALUE", str(float(r["Q4_furnace_drilldown"][0]["NMRT_VALUE"]) + 12345.0)))

print()
print("=== 第三阶 · 换源对拍 v2.2（快照对齐 + 精度感知 + 多数票）===")

DWS = {"20261113": 508.61, "20261114": 508.92, "20261115": 508.19,
       "20261116": 508.49, "20261117": 508.65, "20261118": 510.29, "20261119": 509.35}
REPORT = {"20261119": 509.3}


def fixture(spec_layers, note=""):
    """spec_layers: [(sid, layer, quantum, delta, snapshot_key)]；REPORT 层只取 20261119。"""
    srcs = []
    for sid, layer, q, delta, sk in spec_layers:
        base = REPORT if layer == "REPORT" else DWS
        srcs.append({"source_id": sid, "layer": layer, "quantum": q, "desc": note or "test",
                     "snapshot_key": sk,
                     "values": {k: round(v + delta, 6) for k, v in base.items()}})
    return {"trace_id": "TR-TEST-RECON", "quantum": 0.005,
            "metrics": [{"zb_code": "1600108", "name": "燃料比", "unit": "kg/t", "sources": srcs}]}


def recon_fixture(name, spec, expect, kw):
    p = os.path.join(TMP, "reconfix_%d.json" % (abs(hash(name)) % 100000))
    io.open(p, "w", encoding="utf-8").write(json.dumps(spec, ensure_ascii=False))
    code, out = _run([sys.executable, T3, "--spec", p])
    _record("S3", name, code, expect, kw, out)


recon_fixture("正例 · 仅单层（应 INSUFFICIENT）",
              fixture([("S1_DWS", "DWS", 0.01, 0, "D1"), ("S2_DWS", "DWS", 0.01, 0, "D1")]),
              3, "INSUFFICIENT")
recon_fixture("反例6 · 双源各执一词（应 DRIFT）",
              fixture([("S1_DWS", "DWS", 0.01, 0, "D1"), ("S2_ODS", "ODS", 0.01, 0.05, "D1")]),
              1, "DRIFT")
recon_fixture("反例7 · 三源离群（应 SOURCE_CONFLICT）",
              fixture([("S1_DWS", "DWS", 0.01, 0, "D1"), ("S2_ODS", "ODS", 0.01, 10.71, "D1"),
                       ("S3_REPORT", "REPORT", 0.1, 0, "D1")]),
              5, "SOURCE_CONFLICT")
recon_fixture("正例 · 三源一致（1位报表容差）",
              fixture([("S1_DWS", "DWS", 0.01, 0, "D1"), ("S2_ODS", "ODS", 0.01, 0, "D1"),
                       ("S3_REPORT", "REPORT", 0.1, 0, "D1")]),
              0, "VERIFIED")
recon_fixture("反例8 · 快照时点不同（应 NOT_COMPARABLE）",
              fixture([("S1_DWS", "DWS", 0.01, 0, "D1"), ("S2_ODS", "ODS", 0.01, 10.71, "LIVE9")]),
              6, "NOT_COMPARABLE")

print()
if _fail:
    print("❌ %d/11 用例失败" % len(_fail))
    for tag, name, code, expect, out in _fail:
        print("--- [%s] %s  exit=%d 期望=%d ---\n%s" % (tag, name, code, expect, out[-900:]))
    sys.exit(1)
print("✅ 全部 11 个用例通过（第二阶 1 正 5 反 + 第三阶 3 正 2 反）")
sys.exit(0)
