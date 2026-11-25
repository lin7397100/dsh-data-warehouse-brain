#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技能清单维护引擎（每日构建闭环 第 7 步）· 确定性可重跑

职责：
  1. 扫描 skills/*/SKILL.md，解析 frontmatter（name/description/tags/owner）重建清单。
  2. type 判定：`ind-*` → indicator-skill；其余 → expert-skill。
  3. **沿用旧** last_used / call_count / status / experimental（按 id 关联旧清单），
     避免每日重建丢失调用统计。
  4. 治理策略：experimental 且 call_count==0 → status="deprecated"（**不物理删除**）。
  5. 写前备份 .bak.<DATE>，保证失败可回滚。

用法：
    python skills/sg-memory-engine/engine/build_skill_inventory.py [--date YYYY-MM-DD]

注意：本清单记录**全部**技能（含 ind-* 自动指标技能），仅用于运行时派发登记；
      ind-* **不注册进 plugin.json**（plugin.json 只登记专家级技能，见 data-warehouse-brain 发布版）。
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

MARKER = ".codebuddy-plugin"


def find_team_root(start: str) -> str:
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, MARKER)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError("未找到团队根目录（缺少 .codebuddy-plugin 标记）")
        cur = parent


def parse_frontmatter(path: str) -> dict:
    """极简 frontmatter 解析：仅取 name/description/tags/owner 标量与内联列表。"""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    fm, block = {}, m.group(1)
    for line in block.split("\n"):
        mm = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not mm:
            continue
        key, val = mm.group(1), mm.group(2).strip()
        if key == "tags":
            inner = val.strip()
            if inner.startswith("[") and inner.endswith("]"):
                fm["tags"] = [t.strip().strip("'\"") for t in inner[1:-1].split(",") if t.strip()]
            else:
                fm["tags"] = []
        elif key in ("name", "description", "owner"):
            fm[key] = val.strip().strip('"').strip("'")
    return fm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()
    date = args.date

    root = find_team_root(os.path.dirname(os.path.abspath(__file__)))
    skills_dir = os.path.join(root, "skills")
    inv_path = os.path.join(root, "knowledge", "design", "skill_inventory.json")

    # ---- 载入旧清单以沿用调用统计 ----
    old_by_id = {}
    if os.path.exists(inv_path):
        try:
            with open(inv_path, encoding="utf-8") as f:
                old = json.load(f)
            for s in old.get("skills", []):
                old_by_id[s.get("id")] = s
        except Exception as ex:
            print(f"[inventory] 警告：旧清单解析失败（{ex}），调用统计将重置")

    skills = []
    for name in sorted(os.listdir(skills_dir)):
        d = os.path.join(skills_dir, name)
        sk_md = os.path.join(d, "SKILL.md")
        if not os.path.isdir(d) or not os.path.exists(sk_md):
            continue
        fm = parse_frontmatter(sk_md)
        prev = old_by_id.get(name, {})
        stype = "indicator-skill" if name.startswith("ind-") else "expert-skill"
        entry = {
            "id": name,
            "name": fm.get("name") or name,
            "trigger": fm.get("description") or "",
            "source": f"skills/{name}/SKILL.md",
            "type": stype,
            "owner": fm.get("owner") or prev.get("owner") or "sg-memory",
            "tags": fm.get("tags", prev.get("tags", []) or []),
            # 沿用旧统计
            "status": prev.get("status", "active"),
            "experimental": bool(prev.get("experimental", False)),
            "last_used": prev.get("last_used"),
            "call_count": int(prev.get("call_count", 0) or 0),
        }
        # 治理策略：实验性且零调用 → deprecated（不删）
        if entry["experimental"] and entry["call_count"] == 0:
            entry["status"] = "deprecated"
        skills.append(entry)

    n_exp = sum(1 for s in skills if s["type"] == "expert-skill")
    n_ind = sum(1 for s in skills if s["type"] == "indicator-skill")
    n_dep = sum(1 for s in skills if s["status"] == "deprecated")

    payload = {
        "meta": {
            "generated_at": f"{date}T00:00:00",
            "maintainer": "sg-memory (铭枢)",
            "total_skills": len(skills),
            "expert_skills": n_exp,
            "indicator_skills": n_ind,
            "deprecated": n_dep,
            "schema": ["id", "name", "trigger", "source", "type", "status",
                       "experimental", "last_used", "call_count"],
            "policy": "命中即直调，禁止重复编译；experimental 且 call_count==0 超周期标记 "
                      "deprecated（不物理删除）；本地 knowledge/ 为权威基线。",
        },
        "skills": skills,
    }

    # ---- 写前备份 ----
    if os.path.exists(inv_path):
        bak = f"{inv_path}.bak.{date}"
        with open(inv_path, encoding="utf-8") as fsrc, open(bak, "w", encoding="utf-8") as fdst:
            fdst.write(fsrc.read())
        print(f"[inventory] 已备份 -> {os.path.basename(bak)}")

    os.makedirs(os.path.dirname(inv_path), exist_ok=True)
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[inventory] total={len(skills)} expert={n_exp} indicator={n_ind} deprecated={n_dep}")
    if n_dep:
        print("[inventory] deprecated ids: "
              + ", ".join(s["id"] for s in skills if s["status"] == "deprecated"))

    # ---- 与旧清单 id 集合比对 ----
    if old_by_id:
        a, b = set(old_by_id), {s["id"] for s in skills}
        print(f"[inventory] vs 上一版: added={len(b - a)} removed={len(a - b)} "
              f"same={'YES' if a == b else 'NO'}")
        for i in sorted(b - a):
            print(f"           + {i}")
        for i in sorted(a - b):
            print(f"           - {i}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
