#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""校验生成的 DSH 组合包：YAML 可解析、preset 引用闭合、persona 合法、技能可发现。"""
import json, os, re, sys

import yaml


class L(yaml.SafeLoader):
    pass


def _js(loader, node):
    return "@@js:" + str(loader.construct_scalar(node))


L.add_constructor("tag:yaml.org,2002:js", _js)

OUT = sys.argv[1]
errs, warns, info = [], [], []

with open(os.path.join(OUT, "cordis.patch.yml"), encoding="utf-8") as f:
    doc = yaml.load(f, Loader=L)

if not isinstance(doc, list) or not doc or "insert" not in doc[0]:
    errs.append("根结构不是 [{insert: [...]}]")
    print(errs)
    sys.exit(1)

rows = doc[0]["insert"]
presets = [r for r in rows if r.get("name") == "@deepseek-ai/dsh-agent-preset"]
info.append("preset 行数 = %d" % len(presets))

ids, maccess = [], {}
for p in presets:
    cfg = p.get("config") or {}
    pid = cfg.get("id")
    if not pid:
        errs.append("preset 缺 config.id: %s" % p.get("id"))
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", str(pid)):
        errs.append("preset id 非 kebab-case: %r" % pid)
    if pid in ids:
        errs.append("preset id 重复: %s" % pid)
    ids.append(pid)
    plugins = cfg.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        errs.append("%s 缺 plugins 列表" % pid)
        continue
    by_id = {}
    for row in plugins:
        rid = row.get("id")
        if not rid:
            errs.append("%s 内子行缺 id: %r" % (pid, row.get("name")))
        if rid in by_id:
            errs.append("%s 内子行 id 重复: %s" % (pid, rid))
        by_id[rid] = row
    persona = by_id.get("persona")
    if not persona:
        errs.append("%s 缺 persona 行" % pid)
    else:
        pre = (persona.get("config") or {}).get("prefix") or ""
        if len(pre.strip()) < 200:
            warns.append("%s persona 过短(%d 字节)" % (pid, len(pre)))
        if "{{" in pre:
            errs.append("%s persona 仍含 '{{'（模板变量冲突）" % pid)
    for need in ("tool-fs", "tool-skill", "skill-filesystem"):
        if need not in by_id:
            warns.append("%s 缺 %s" % (pid, need))
    # persona 块文本往返：YAML 里的 prefix 必须与 personas/<id>.md 逐字节一致
    if persona:
        pre = (persona.get("config") or {}).get("prefix") or ""
        f = os.path.join(OUT, "personas", str(pid) + ".md")
        if not os.path.isfile(f):
            errs.append("%s 缺 personas/%s.md" % (pid, pid))
        elif pre != open(f, encoding="utf-8").read():
            errs.append("%s persona 与 personas/*.md 不一致（YAML 转义问题）" % pid)
    dele = by_id.get("delegation")
    if dele:
        sub = next((r for r in (dele.get("config") or []) if r.get("id") == "tool-subagent"), None)
        if sub:
            maccess[pid] = (sub.get("config") or {}).get("allowedAgentPresets") or []

lead = [p for p in presets if (p.get("config") or {}).get("id") and "team-lead" in (p["config"]["id"])]
info.append("主理人 preset = %s" % (lead[0]["config"]["id"] if lead else "缺失"))
if len(lead) != 1:
    errs.append("应恰有 1 个主理人 preset，实际 %d" % len(lead))
else:
    allowed = maccess.get(lead[0]["config"]["id"], [])
    info.append("主理人可派发专家 = %d" % len(allowed))
    missing = [a for a in allowed if a not in ids]
    if missing:
        errs.append("allowedAgentPresets 指向不存在的 preset: %s" % missing)
    dup = len(allowed) != len(set(allowed))
    if dup:
        errs.append("allowedAgentPresets 有重复")
    experts = [i for i in ids if i not in (lead[0]["config"]["id"],)]
    notallowed = [e for e in experts if e not in allowed]
    if notallowed:
        errs.append("专家 preset 未在主理人白名单内: %s" % notallowed)

# 技能目录
sk = os.path.join(OUT, "skills")
if not os.path.isdir(sk):
    errs.append("缺 skills/ 目录")
else:
    dirs = sorted(d for d in os.listdir(sk) if os.path.isdir(os.path.join(sk, d)))
    info.append("技能目录 = %d" % len(dirs))
    bad = []
    for d in dirs:
        f = os.path.join(sk, d, "SKILL.md")
        if not os.path.isfile(f):
            bad.append(d + "(无SKILL.md)")
            continue
        head = open(f, encoding="utf-8").read(2000)
        if not head.startswith("---"):
            bad.append(d + "(无frontmatter)")
        elif not re.search(r"^description:", head, re.M):
            bad.append(d + "(缺description)")
        elif not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", d):
            bad.append(d + "(目录名非kebab)")
    if bad:
        errs.append("技能不合规: %s" % bad)

for sub in ("personas", "references"):
    n = len(os.listdir(os.path.join(OUT, sub))) if os.path.isdir(os.path.join(OUT, sub)) else 0
    info.append("%s/ 文件 = %d" % (sub, n))

print("\n".join(info))
print()
print("ERRORS:", len(errs))
for e in errs:
    print("  ✗", e)
print("WARNINGS:", len(warns))
for w in warns[:20]:
    print("  ! ", w)
json.dump({"info": info, "errors": errs, "warnings": warns},
          open(os.path.join(OUT, "validation.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
sys.exit(1 if errs else 0)
