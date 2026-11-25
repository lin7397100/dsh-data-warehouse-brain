# -*- coding: utf-8 -*-
"""SQL 静态校验回归测试：1 正例（真实编译产物）+ 6 反例。"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "sql_static_check.py")
TMP = os.path.join(HERE, "artifacts", "compiled", "_selftest")
os.makedirs(TMP, exist_ok=True)

GOOD = os.path.join(HERE, "artifacts", "compiled",
                    "q_20261113_20261119_1600213_1600207_1600108.sql")

CASES = [
    ("正例 · 真实编译产物", None, 0, None),

    ("反例1 · 含 DELETE 写操作",
     "DELETE FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01 WHERE YMD = '20261113';",
     1, "S1 含写操作关键字"),

    ("反例2 · SELECT *",
     "SELECT * FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01 WHERE YMD = '20261113';",
     1, "S2 存在 SELECT *"),

    ("反例3 · 除法无除零保护",
     "SELECT YMD, PROD_NMRT_VALUE / PROD_DNMNT_VALUE AS R FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LT01\n"
     "WHERE WORK_DATE BETWEEN '20261113' AND '20261119';",
     1, "S5 除法未做除零保护"),

    ("反例4 · 日期字面量非 8 位",
     "SELECT YMD FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01 WHERE YMD = '2026111';",
     1, "S8 日期字面量非 8 位"),

    ("反例5 · CAST 强转无清洗",
     "SELECT YMD, CAST(ZB_VALUE AS DECIMAL(18,4)) AS V FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01\n"
     "WHERE YMD = '20261113';",
     1, "S7 CAST 强转无"),

    ("反例6 · 编造列名（别名限定）",
     "SELECT G.ZB_CODE, G.FACTORY_DIV FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01 G\n"
     "WHERE G.YMD = '20261113';",
     1, "S4 别名限定列不存在"),
]

fails = []
for i, (name, sql, expect, kw) in enumerate(CASES):
    if sql is None:
        p = GOOD
    else:
        p = os.path.join(TMP, "case%02d.sql" % i)
        io.open(p, "w", encoding="utf-8").write(sql)
    r = subprocess.run([sys.executable, TOOL, "--sql", p], capture_output=True,
                       text=True, encoding="utf-8")
    out = (r.stdout or "") + (r.stderr or "")
    ok = (r.returncode == expect) and (kw is None or kw in out)
    print("  [%s] %-28s exit=%d(期望%d)%s"
          % ("OK  " if ok else "FAIL", name, r.returncode, expect,
             "" if kw is None else " 关键词「%s」" % kw))
    if not ok:
        fails.append((name, r.returncode, expect, out[-500:]))

print()
if fails:
    print("❌ %d/%d 用例失败" % (len(fails), len(CASES)))
    for f in fails:
        print("  %s exit=%s 期望=%s\n%s" % f)
    sys.exit(1)
print("✅ 全部 %d 个用例通过（1 正例 + %d 反例）" % (len(CASES), len(CASES) - 1))
sys.exit(0)
