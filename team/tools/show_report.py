import json

r = json.load(open(r"C:\Users\lin\AppData\Local\Doubao\User Data\Default\.doubao\agent_mode\workspace\.sessions\38454211174416642\agents\m_0cwezCcptU0\src_report.json", encoding="utf-8"))

print("AGENTS:", len(r["agents"]))
for a in r["agents"]:
    print("{:<48}{:>8}  fm={}  moustache={:<3} name={}".format(
        a["file"], a["bytes"], a["has_fm"], a["moustache"], a["name"] or "-"))

print()
print("SKILLS:", len(r["skills"]))
bad = [s for s in r["skills"] if s.get("error") or not s.get("name_ok") or not s.get("has_desc") or not s.get("dir_ok")]
print("invalid skills:", len(bad))
for s in bad:
    print("  ", s)
mou = [s for s in r["skills"] if s.get("moustache")]
print("skills containing '{{':", [(s["dir"], s["moustache"]) for s in mou][:10])
noname_match = [s["dir"] for s in r["skills"] if s.get("name") and not s.get("name_matches_dir")]
print("name != dir:", noname_match[:10], "count", len(noname_match))
print("total skill bytes:", sum(s.get("bytes", 0) for s in r["skills"]))

print()
print("DIR SIZES:")
for k, v in r["counts"].items():
    print("  {:<20} files={:>5}  {:.2f} MB".format(k, v["files"], v["mb"]))
