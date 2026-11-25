import json, os, re, sys

SRC = r"C:\Users\lin\Desktop\数仓智脑专家团_v1.5.0_完整导出"
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

def split_fm(text):
    if not text.startswith("---"):
        return None, text
    idx = text.find("\n---", 3)
    if idx < 0:
        return None, text
    fm = text[3:idx].strip("\n")
    body = text[idx + 4:]
    if body.startswith("\n"):
        body = body[1:]
    return fm, body

def parse_fm_simple(fm):
    """return dict of top-level scalar keys only (enough for name/description/maxTurns)"""
    out = {}
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out

rep = {"agents": [], "skills": [], "counts": {}}

ad = os.path.join(SRC, "agents")
for fn in sorted(os.listdir(ad)):
    if not fn.endswith(".md") or ".bak" in fn:
        continue
    p = os.path.join(ad, fn)
    txt = open(p, encoding="utf-8").read()
    fm, body = split_fm(txt)
    keys = parse_fm_simple(fm) if fm else {}
    rep["agents"].append({
        "file": fn,
        "bytes": len(txt.encode("utf-8")),
        "has_fm": fm is not None,
        "fm_keys": sorted(keys.keys()),
        "name": keys.get("name", "").strip('"'),
        "moustache": body.count("{{"),
        "maxTurns": keys.get("maxTurns", ""),
        "body_chars": len(body),
    })

sd = os.path.join(SRC, "skills")
for d in sorted(os.listdir(sd)):
    p = os.path.join(sd, d, "SKILL.md")
    if not os.path.isfile(p):
        rep["skills"].append({"dir": d, "error": "no SKILL.md"})
        continue
    txt = open(p, encoding="utf-8").read()
    fm, body = split_fm(txt)
    keys = parse_fm_simple(fm) if fm else {}
    name = keys.get("name", "").strip('"')
    rep["skills"].append({
        "dir": d,
        "dir_ok": bool(KEBAB.match(d)),
        "name": name,
        "name_ok": bool(KEBAB.match(name)) if name else False,
        "name_matches_dir": name == d,
        "has_desc": "description" in keys,
        "bytes": len(txt.encode("utf-8")),
        "moustache": body.count("{{"),
        "assets": sorted(x for x in os.listdir(os.path.join(sd, d)) if x != "SKILL.md"),
    })

def dirsize(path):
    tot = 0
    n = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                tot += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return tot, n

for sub in ["knowledge", "avatars", "assets", "scripts", "observed", "agents/references", "docs"]:
    s, n = dirsize(os.path.join(SRC, sub.replace("/", os.sep)))
    rep["counts"][sub] = {"files": n, "mb": round(s / 1048576, 2)}

print(json.dumps(rep, ensure_ascii=False, indent=1))
