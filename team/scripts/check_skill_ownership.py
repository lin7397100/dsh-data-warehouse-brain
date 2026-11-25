# -*- coding: utf-8 -*-
"""技能 owner 生命周期一致性校验（配合 skill_ownership_governance.md 第四条）。

检查不变量 C1~C5；退出码 0=通过，1=不通过。
用法：python check_skill_ownership.py --root <包根>
"""
import argparse
import glob
import os
import re

# 与 members_guidance.md「退役成员清单」同步维护
RETIRED = {
    "sg-zhishu-sql-analyst",
    "sg-zhishu-data-scientist",
    "sg-zhishu-knowledge-researcher",
    "sg-report-delivery",
}
# 共享平台技能 → 期望 owner（见治理规范第三节）
SHARED = {
    "sg-analysis-engine": "sg-metadata",
    "sg-zhishu-analysis-engine": "sg-metadata",
    "sg-data-analysis-engine": "sg-metadata",
    "sg-report-composer": "sg-insight",
    "sg-kanban-builder": "sg-insight",
    "sg-multi-agent-coordination": "data-warehouse-brain-team-lead",
    "sg-task-planner": "data-warehouse-brain-team-lead",
    "sg-agentic-decision": "data-warehouse-brain-team-lead",
}
# 转实域专家 → 最低主技能数
MIN_SKILLS = {"sg-cbprod": 2, "sg-gzprod": 1}
# 允许为 0 的在册成员（共享交付角色）
ZERO_OK = {"sg-zhishu-report-composer", "sg-zhishu-dashboard-designer", "data-warehouse-brain-team-lead"}

R = []


def chk(name, ok, detail=""):
    R.append((name, ok, detail))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    root = a.root

    agents = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(root, "agents/*.md"))
              if ".bak" not in p}
    by = {}
    for p in glob.glob(os.path.join(root, "skills/*/SKILL.md")):
        sid = os.path.basename(os.path.dirname(p))
        t = open(p, "rb").read().decode("utf-8", errors="replace")
        m = re.search(r"^owner:[ \t]*(\S+)", t, re.M)
        owner = m.group(1) if m else ""
        by.setdefault(owner, []).append(sid)
        # C1 悬空 owner
        chk(f"C1 {sid} owner 指向存在成员", owner in agents or owner == "",
            owner or "（空）")

    # C1 汇总：无 owner
    noown = [s for s in (glob.glob(os.path.join(root, "skills/*/SKILL.md")))]
    noown = [os.path.basename(os.path.dirname(p)) for p in noown]
    noown = [s for s in noown if s not in by.get("", []) and not any(s in v for v in by.values())]
    chk("C1 全部技能有 owner", not noown, "、".join(noown[:5]) or "齐全")

    # C2 退役成员 0 技能
    for r in RETIRED:
        got = len(by.get(r, []))
        chk(f"C2 {r} 名下 0 技能", got == 0, f"{got} 个：{by.get(r, [])}")

    # C3 转实域专家
    for e, mn in MIN_SKILLS.items():
        got = len(by.get(e, []))
        chk(f"C3 {e} 技能 ≥{mn}", got >= mn, f"{got} 个：{by.get(e, [])}")

    # C4 共享技能白名单
    for s, want in SHARED.items():
        if s in by.get(want, []):
            chk(f"C4 {s} owner={want}", True, "一致")
        elif any(s in v for v in by.values()):
            cur = [o for o, v in by.items() if s in v][0]
            chk(f"C4 {s} owner={want}", cur == want, f"实际 {cur}")

    # C5 在册成员 0 技能（仅允许白名单）
    active_zero = [a for a in agents if a not in RETIRED and not by.get(a) and a not in ZERO_OK]
    chk("C5 在册成员 0 技能仅限白名单", not active_zero, "、".join(active_zero) or "合规")

    # C6 关键技能 owner 主责一致性（2026-11-05 新增）
    C6_MUST_MATCH = {
        "sg-semantic-layer": "sg-semantic",
        "sg-ontology-core": "sg-ontology",
        "sg-nl2sql-query": "sg-development",
        "sg-intent": "data-warehouse-brain-team-lead",
        "sg-dsl-compiler": "sg-development",
        "sg-eval-harness": "sg-quality",
        "sg-db2-executor": "sg-development",
        "sg-data-lineage": "sg-metadata",
    }
    c6_pass = True
    c6_details = []
    for skill, want in C6_MUST_MATCH.items():
        got = [o for o, v in by.items() if skill in v]
        ok = got == [want]
        if not ok:
            c6_details.append(f"{skill}: want={want} got={got or '(nobody)'}")
            c6_pass = False
    chk("C6 关键技能 owner 主责一致", c6_pass, "; ".join(c6_details[:5]) or "全部一致")

    # C7 派单模板退役 ID 扫描（2026-11-05 新增 · 防复发）
    # 背景：subagent_dispatch.md:127 曾把泉州 ODS 取数派给已退役的秦逸，
    #       而 C1~C6 只扫 SKILL.md owner 与注册位，扫不到 references 内的派单目标。
    # 规则：退役 ID 出现在「派单目标」语境（→ / owner: / subagent_type: / agent_preset: / owner=）即 FAIL；
    #       出现在明确标注 退役/不再派单/并入/禁止 的说明行属合法留痕，放行。
    # 说明性语境（合法留痕）：退役说明 / 映射表 / 墓碑自述 / 技能名引用
    LEGIT = ("退役", "不再派单", "并入", "禁止", "已退役", "去职", "不再使用",
             "不可派发", "同名技能", "技能链路", "skills/")
    c7_bad = []
    scan_files = sorted(set(
        glob.glob(os.path.join(root, "agents/*.md")) +
        glob.glob(os.path.join(root, "agents/references/*.md"))
    ))
    for p in scan_files:
        if ".bak" in p:
            continue
        stem = os.path.basename(p)[:-3]
        if stem in RETIRED:          # 墓碑 MD 自身，内容本就是退役说明
            continue
        rel = os.path.relpath(p, root).replace("\\", "/")
        for ln, line in enumerate(open(p, "rb").read().decode("utf-8", errors="replace").splitlines(), 1):
            if not any(r in line for r in RETIRED):
                continue
            if any(k in line for k in LEGIT):
                continue
            # 关键收紧：退役 ID 必须「紧跟」派单标记，才算可派发目标。
            # 避免把表格分隔符 |、流程箭头（导出→投递）、技能名引用误判为派单。
            # 2026-11-20（API 对齐 v2）：派单字段新名为 agent_preset，旧名 subagent_type
            # 仍须检出——历史文档/备份里可能残留旧名，只认新名会漏检，故两者同匹配。
            pat = r"(?:→\s*|owner\s*[:=]\s*[\"']?|(?:subagent_type|agent_preset)\s*[:=]\s*[\"']?)(" + \
                  "|".join(re.escape(r) for r in sorted(RETIRED)) + r")\b"
            if re.search(pat, line):
                c7_bad.append(f"{rel}:{ln} → {line.strip()[:90]}")
    chk("C7 派单模板无退役 ID 可派发残留", not c7_bad,
        "; ".join(c7_bad[:4]) or f"扫描 {len(scan_files)} 个文件，无残留")

    print(f"\n=== 技能 owner 一致性校验：{sum(1 for _, ok, _ in R if ok)}/{len(R)} 通过 ===\n")
    for name, ok, detail in R:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<42} {detail}")
    ok_all = all(ok for _, ok, _ in R)
    print(f"\n{'ALL PASS ✅' if ok_all else 'FAILED ❌'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
