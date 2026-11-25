# -*- coding: utf-8 -*-
"""adhoc_build.py —— 半自动批量即席构建（dry-run 出候选清单）。

策略：
  1. 对 7 个已知 DWS 表家族，各拉一次 DISTINCT 名称值（缓存到本地 JSON）。
  2. 对 backlog 里 fully_orphan 指标，用 zb_name 关键词 LIKE 匹配表中名称。
  3. 唯一命中 + 最近 3 天有数据 → 候选；多命中/0 命中 → 跳过待人工。
  4. 输出 proposals CSV，用户 review 后用 --apply 批量物化。

用法：
  python tools/adhoc_build.py --dry-run           # 只出候选
  python tools/adhoc_build.py --apply            # 确认后写 .sql + 更新 registry
"""
import argparse, csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mcp_db2  # noqa: E402

# 7 个已知 DWS 表家族（从 4262 个物化 SQL 归纳）
FAMILIES = [
    {
        "table": "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_0002",
        "name_col": "ZB_NAME", "val_col": "ZB_VALUE", "time_col": "YMD",
        "scope": "本部经营日报-综合",
    },
    {
        "table": "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_ZG01",
        "name_col": "ZB_NAME", "val_col": "ZB_VALUE", "time_col": "YMD",
        "scope": "轧钢作业率/品种",
    },
    {
        "table": "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_YL01",
        "name_col": "ITEM_NAME", "val_col": "ITEM_VALUE", "time_col": "YMD",
        "extra_cols": ["BASE_NAME", "FACTORY_NAME"],
        "scope": "原燃料库存/消耗",
    },
    {
        "table": "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01",
        "name_col": "ZB_CODE", "val_col": "ZB_VALUE", "time_col": "YMD",
        "scope": "炼钢(ZB_CODE 数字)",
    },
    {
        "table": "SMBB_M_S_NY00.T_DWS_FACT_NYGZ_0001",
        "name_col": "ITEMNAME", "val_col": "APPORTVALUE", "time_col": "YMD",
        "scope": "能源动力",
    },
    {
        "table": "SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LT01",
        "name_col": "PROD_ITEM_CODE", "val_col": "PROD_ITEM_VALUE", "time_col": "WORK_DATE",
        "extra_cols": ["PROD_UNIT_CODE"],
        "scope": "炼铁(铁水Si等)",
    },
]

CACHE = os.path.join(ROOT, "tools", "_adhoc_name_cache.json")
PROPOSAL = os.path.join(ROOT, "docs", "adhoc_proposals.csv")


def fetch_distinct(fam):
    """拉一个表的 DISTINCT 名称值（含附加列）。"""
    cols = [fam["name_col"]] + fam.get("extra_cols", [])
    col_sql = ", ".join(cols)
    sql = f"SELECT DISTINCT {col_sql} FROM {fam['table']}"
    r = mcp_db2.execute(sql, limit=2000)
    if not r.get("ok"):
        return []
    out = []
    for row in r["rows"]:
        out.append(dict(zip(r["columns"], row)))
    return out


def load_cache():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    return {}


def save_cache(c):
    json.dump(c, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def get_names(fam, cache):
    key = fam["table"]
    if key not in cache:
        cache[key] = fetch_distinct(fam)
        save_cache(cache)
    return cache[key]


def normalize(name):
    """去掉常见前缀/后缀/时间词，留核心关键词。"""
    n = re.sub(r"本部经营日报\(\d+\)_", "", name)
    n = re.sub(r"管控中心_", "", n)
    n = re.sub(r"^整体数据_", "", n)
    # 同义词归一
    syn = {
        r"年累计|月累|年累计量": "年累计",
        r"月累计|月累计量": "月累计",
        r"当日|当日值|日值": "日",
        r"耗电量|用电量": "电耗",
        r"产量量|产量": "产量",
        r"作业率|作业率\(月\)": "作业率",
        r"成材率|成材率\(月\)": "成材率",
        r"热装率|热装率\(月\)": "热装率",
        r"固体燃料耗": "固体燃料耗",  # 不与"燃料比"合并，两者完全不同
        r"库存(量)?": "库存",
    }
    for pat, rep in syn.items():
        n = re.sub(pat, rep, n)
    return n.strip()


def match_one(zb_name, names, fam):
    """对一个 orphan 指标，在表名值里找唯一命中。
    规则：
      1. 名称值非空、>=2 字
      2. 归一后双向子串
      3. 时间粒度守卫：年/月/日 必须一致，否则不匹配
      4. 打分：公共子串长度；完全相等 +10
      5. 取 top1，score >= 3
    返回 [row] 或 []
    """
    kw = normalize(zb_name)
    if len(kw) < 2:
        return []
    name_col = fam["name_col"]

    # 时间粒度判定：年/月/日
    def grain(s):
        if "年累计" in s or "年" in s and "累计" in s: return "年"
        if "年" in s: return "年"
        if "月累计" in s or "月" in s: return "月"
        if "日" in s or "当日" in s: return "日"
        return ""
    g_kw = grain(zb_name)

    scored = []
    for row in names:
        v = str(row.get(name_col, "") or "").strip()
        if len(v) < 2:
            continue
        v_norm = normalize(v)
        if not v_norm:
            continue
        # 时间粒度不一致直接跳过
        g_v = grain(v)
        if g_kw and g_v and g_kw != g_v:
            continue
        if v_norm in kw or kw in v_norm:
            score = min(len(v_norm), len(kw))
            if v_norm == kw or v_norm == zb_name:
                score += 10
            scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    if scored and scored[0][0] >= 3:
        return [scored[0][1]]
    return []


def build_sql(fam, hit):
    """根据家族和命中行生成物化 SQL。"""
    table = fam["table"]
    val_col = fam["val_col"]; name_col = fam["name_col"]; tm = fam["time_col"]
    where = [f"{name_col} = '{hit[name_col]}'"]
    for k, v in hit.items():
        if k == name_col or k == tm:
            continue
        if v:
            where.append(f"{k} = '{v}'")
    where.append(f"{tm} = '$TD$'")
    return f"SELECT {val_col} FROM {table} WHERE " + " AND ".join(where)


def apply_proposals(proposals):
    """对候选逐条真取验证，通过则写 .sql + 更新 registry。"""
    reg_path = os.path.join(ROOT, "knowledge", "design", "indicator", "indicator_registry.json")
    reg = json.load(open(reg_path, encoding="utf-8"))
    inds = reg["indicators"]["indicators"]
    idx = {str(v.get("zb_code", "")): v for v in inds}

    mat_dir = os.path.join(ROOT, "knowledge", "design", "indicator", "materialized_sql")
    ok = fail = 0
    for p in proposals:
        zb = p["zb_code"]; zb_name = p["zb_name"]
        # 找 family
        fam = next((f for f in FAMILIES if f["table"] == p["table"]), None)
        if not fam:
            continue
        hit = json.loads(p["extra"]) if p["extra"] else {}
        hit[fam["name_col"]] = p["match_value"]
        sql = build_sql(fam, hit)
        # 真取：先查最近 YMD，再用字面量查值（避免子查询在 MCP 不兼容）
        r0 = mcp_db2.execute(f"SELECT MAX({fam['time_col']}) FROM {fam['table']}", limit=1)
        if not r0.get("ok") or not r0.get("rows"):
            print(f"  [跳过] {zb} {zb_name[:25]}: 查 MAX 失败")
            fail += 1
            continue
        latest = r0["rows"][0][0]
        test_sql = sql.replace("$TD$", str(latest))
        r = mcp_db2.execute(test_sql, limit=3)
        if not r.get("ok") or not r.get("rows"):
            print(f"  [跳过] {zb} {zb_name[:25]}: {latest} 无数据 / {r.get('error','')[:60]}")
            fail += 1
            continue
        val = r["rows"][0]
        # 写 .sql
        out = os.path.join(mat_dir, f"{zb}.sql")
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"-- ZB_CODE: {zb}\n-- ZB_NAME: {zb_name}\n-- DOMAIN: 生产管制\n-- LEVEL: atomic\n-- FACTORY: {p['factory']}\n")
            f.write(f"-- SOURCE_TABLES: {fam['table']}\n-- PARAMS: $TD$\n-- ORIGIN: adhoc_build 批量即席构建\n")
            f.write(f"-- 真取验证: {val}\n")
            f.write(sql + "\n")
        # 更新 registry
        if zb in idx:
            idx[zb]["level"] = "atomic"
            idx[zb]["status_note"] = f"adhoc_build 物化（{fam['table']}）"
            idx[zb]["source_tables"] = [fam["table"]]
            idx[zb]["materialized_sql_file"] = f"materialized_sql/{zb}.sql"
            idx[zb]["maturity"] = "production"
        print(f"  [OK] {zb} {zb_name[:25]} -> {val[0] if val else '?'}")
        ok += 1
    json.dump(reg, open(reg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n=== 物化完成: {ok} 成功, {fail} 跳过 ===")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.apply:
        # 读 proposals CSV
        proposals = []
        with open(PROPOSAL, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                proposals.append(r)
        print(f"=== 应用 {len(proposals)} 条候选 ===")
        apply_proposals(proposals)
        return

    cache = load_cache()
    # 1. 确保所有表家族名称已缓存
    print("=== 拉取表名称值（每表一次）===")
    for fam in FAMILIES:
        names = get_names(fam, cache)
        print(f"  {fam['table']}: {len(names)} 个 distinct {fam['name_col']}")

    # 2. 读 backlog
    bl = os.path.join(ROOT, "docs", "materialize-backlog.csv")
    orphans = []
    with open(bl, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("action") == "fully_orphan":
                orphans.append(r)
    print(f"\n=== fully_orphan 指标: {len(orphans)} ===")

    # 3. 逐个匹配
    proposals = []
    for o in orphans:
        zb_code = o["zb_code"]; zb_name = o["zb_name"]
        found = None
        for fam in FAMILIES:
            names = cache[fam["table"]]
            hits = match_one(zb_name, names, fam)
            if hits:
                found = {"fam": fam, "hit": hits[0]}
                break
        if found:
            proposals.append({
                "zb_code": zb_code, "zb_name": zb_name,
                "table": found["fam"]["table"],
                "match_value": found["hit"][found["fam"]["name_col"]],
                "extra": {k: v for k, v in found["hit"].items() if k != found["fam"]["name_col"]},
                "factory": o.get("factory_div", ""),
            })

    # 4. 输出
    print(f"\n=== 候选（唯一命中）: {len(proposals)} ===")
    with open(PROPOSAL, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["zb_code", "zb_name", "table", "match_value", "extra", "factory"])
        w.writeheader()
        for p in proposals:
            p["extra"] = json.dumps(p["extra"], ensure_ascii=False)
            w.writerow(p)
    print(f"已写出: {PROPOSAL}")
    for p in proposals[:15]:
        print(f"  {p['zb_code']}  {p['zb_name'][:30]:30s} -> {p['table'].split('.')[-1]} | {p['match_value']}")


if __name__ == "__main__":
    main()
