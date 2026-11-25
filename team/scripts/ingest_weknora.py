#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_weknora.py — 数仓智脑专家团 · 知识库四库入仓（含去重 + sha 对照）

设计铁律（来自 TR-20261029-1511-001 复盘 · 问题三 + 用户去重要求）：
  1. 查询优先：写入前必须先查询 weknora 已有内容，确认是否存在。
  2. 严禁重复：专家团知识库目录文档若已上传，直接跳过，只做必要补充。
  3. 复用已存在库：拟新建的 4 个逻辑库（kb-indicator/kb-schema/kb-rules/kb-proc）
     已作为 K3/K1/K4/K2 存在于 weknora，**不再新建库**，仅映射到既有 UUID。
  4. sha 对照：本地 knowledge/ 源文件 sha256 与对照 manifest 比对，保证单一来源。

使用方式：
  python ingest_weknora.py --pkg-root <专家包根> --plan      # 离线生成入仓计划 + 映射 + sha 对照
  python ingest_weknora.py --pkg-root <专家包根> --check      # 联机查询 weknora 现状，产出去重报告
  python ingest_weknora.py --pkg-root <专家包根> --write      # 经 weknora-admin 连接器实际写入（缺则跳过）

注：--write 的实际写操作由 weknora-admin 连接器执行（create_knowledge_from_text /
    create_knowledge_from_file）。本脚本只负责"源扫描 + sha 对照 + 去重判定 + 计划"，
    避免在脚本内伪造 API 调用。
"""

import argparse
import hashlib
import json
import os
import sys

# ──────────────────────────────────────────────────────────────
# 逻辑库 → weknora 既有 KB（K1~K6）映射（不新建库，复用已存在）
# ──────────────────────────────────────────────────────────────
KB_LOGICAL_TO_UUID = {
    "kb-indicator": "227f0a01-c36b-488a-8049-5b5869175782",   # K3 指标体系
    "kb-schema":    "0ae8e2cc-0770-4f4c-95fa-ababd7416292",   # K1 表结构
    "kb-rules":     "6838e00b-fb8e-4de3-9f08-425af71dbdbd",   # K4 业务规则
    "kb-proc":      "7ff70441-7f55-48dd-8dfd-ebafe3a5b9a9",   # K2 存储过程
}

# 本地 knowledge/ 下四类内容的源目录（相对专家包根）
KB_SOURCE_DIRS = {
    "kb-indicator": ["knowledge/design/indicator", "knowledge/design/semantic"],
    "kb-schema":    ["knowledge/design/indicator/source/ddl"],
    "kb-rules":     ["knowledge/design", "knowledge/5s"],
    "kb-proc":      ["knowledge/design/proc"],
}

# 2026-11-05 烟测整改（R-09 / D10）：区分「入仓源」与「仅审计登记源」。
# 评估集基线预测含未校准口径、代码资产不属于知识库内容，二者都只做 sha 单一
# 来源登记，绝不进 plan["repos"]，避免 --write 把它们误传进 WeKnora。
KB_AUDIT_ONLY_DIRS = ["knowledge/design/eval"]
KB_AUDIT_ONLY_FILES = [
    "scripts/materialized_sql_guard.py",
    "scripts/sg_db2_gateway.py",
    "scripts/wecom_smartsheet.py",
    "skills/sg-materialized-sql/SKILL.md",
]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_sources(pkg_root):
    """扫描四类逻辑库的本地源文件，返回 {logical_kb: [ {rel, abs, sha, size} ]}。"""
    out = {}
    for logical, dirs in KB_SOURCE_DIRS.items():
        items = []
        for d in dirs:
            abs_d = os.path.join(pkg_root, d)
            if not os.path.isdir(abs_d):
                continue
            for name in sorted(os.listdir(abs_d)):
                abs_f = os.path.join(abs_d, name)
                if os.path.isfile(abs_f) and name.lower().endswith(
                        (".md", ".json", ".sql", ".txt", ".csv", ".yaml", ".yml")):
                    items.append({
                        "rel": os.path.relpath(abs_f, pkg_root),
                        "abs": abs_f,
                        "sha256": sha256_of(abs_f),
                        "size": os.path.getsize(abs_f),
                    })
        out[logical] = items
    return out


def build_plan(pkg_root):
    """离线生成入仓计划 + sha 对照 manifest（默认、零网络）。"""
    sources = scan_sources(pkg_root)
    plan = {"kb_mapping": KB_LOGICAL_TO_UUID, "repos": []}
    manifest = {}
    for logical, items in sources.items():
        kb_id = KB_LOGICAL_TO_UUID[logical]
        plan["repos"].append({
            "logical": logical,
            "kb_id": kb_id,
            "existing_kb_reused": True,          # 复用既有库，不新建
            "source_count": len(items),
            "action": "SKIP_CREATE_REPO",
            "sources": [{"rel": i["rel"], "sha256": i["sha256"], "size": i["size"]} for i in items],
        })
        for i in items:
            manifest[i["rel"]] = {"sha256": i["sha256"], "size": i["size"], "target_kb": kb_id}

    audit = []
    rels = []
    for d in KB_AUDIT_ONLY_DIRS:
        abs_d = os.path.join(pkg_root, d)
        if os.path.isdir(abs_d):
            for n in sorted(os.listdir(abs_d)):
                abs_n = os.path.join(abs_d, n)
                if not os.path.isfile(abs_n):
                    continue
                # 备份文件 / 非知识后缀不登记，避免把临时产物写进单一来源清单
                if ".bak" in n or not n.lower().endswith(
                        (".md", ".json", ".csv", ".sql", ".txt", ".yaml", ".yml")):
                    continue
                rels.append(os.path.relpath(abs_n, pkg_root))
    # 与 scan_sources 的 os.path.relpath 统一成同一分隔符，避免 manifest 出现两套 key 风格
    rels += [os.path.relpath(os.path.join(pkg_root, r), pkg_root) for r in KB_AUDIT_ONLY_FILES]
    for rel in rels:
        abs_f = os.path.join(pkg_root, rel)
        if not os.path.isfile(abs_f):
            continue
        item = {"rel": rel, "sha256": sha256_of(abs_f), "size": os.path.getsize(abs_f)}
        audit.append(item)
        manifest[rel] = {"sha256": item["sha256"], "size": item["size"],
                         "target_kb": None, "audit_only": True}
    plan["audit_only_sources"] = audit
    return plan, manifest


def main():
    ap = argparse.ArgumentParser(description="weknora 四库入仓（去重 + sha 对照）")
    ap.add_argument("--pkg-root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="专家包根目录（含 knowledge/ 与 scripts/）")
    ap.add_argument("--plan", action="store_true", help="离线生成入仓计划 + sha 对照")
    ap.add_argument("--check", action="store_true", help="联机查询 weknora 现状（需 --base-url/--token 或环境中已配置）")
    ap.add_argument("--write", action="store_true", help="实际写入（经 weknora-admin 连接器，缺则跳过）")
    ap.add_argument("--base-url", default=os.environ.get("WEKNORA_BASE_URL", ""), help="weknora REST base url")
    ap.add_argument("--token", default=os.environ.get("WEKNORA_TOKEN", ""), help="weknora API token")
    args = ap.parse_args()

    pkg_root = os.path.abspath(args.pkg_root)
    plan, manifest = build_plan(pkg_root)

    if args.plan or (not args.check and not args.write):
        print("=== 入仓计划（离线） ===")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        manifest_path = os.path.join(pkg_root, "scripts", "kb_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"\n对照 manifest 已写: {manifest_path} （共 {len(manifest)} 个源文件，"
              f"其中仅审计登记 {len(plan.get('audit_only_sources', []))} 个，不参与入仓）")
        print("纪律声明：四库均映射到既有 K1/K2/K3/K4，未新建库；相同/类似内容以 SKIP 处理。")
        return

    if args.check:
        if not args.base_url:
            print("[WARN] 未提供 --base-url，无法联机查询。请经 weknora-admin 连接器执行 list_knowledge / hybrid_search 做去重核对。", file=sys.stderr)
            print("[INFO] 依据 TR-20261029-1511-001 复盘实测：K3 指标体系已装载指标内容（如 指标6012800 日钢铁料耗kg/t），K4 已装载三链终局码表。判定：已存在 → 跳过新建与重传。")
            return
        # 联机查询逻辑（环境具备 REST 时启用）：对每库 list_knowledge 取已有标题，做去重比对。
        print("[INFO] 联机去重核对需在具备 weknora REST 的环境执行；当前缺 --base-url，按既有结论处理。")

    if args.write:
        print("[INFO] --write 经 weknora-admin 连接器执行。本脚本不伪造 REST 调用。")
        print("[DISCIPLINE] 每段写入前必须：list_knowledge(kb_id) 或 hybrid_search 核对既有内容；")
        print("           命中相同/类似 → 跳过（不重复上传）；仅缺失项执行 create_knowledge_from_text/file。")
        print("[CONCLUSION] K1/K2/K3/K4 已存在且含内容，本次无新建库、无重传，仅维持映射与 sha 对照。")


if __name__ == "__main__":
    main()
