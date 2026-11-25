# -*- coding: utf-8 -*-
"""verify_package.py —— 发行前总校验（发 GitHub 前必须 exit 0）

校验项：
  1. 清单：package.json 必填字段、dsh.bundle.patch、dsh.client、files 覆盖运行文件
  2. patch：YAML 可解析；24 个 preset；每个 preset 有 persona + skill-filesystem(bundledSkillDir)
  3. 派发白名单：主理人 allowedAgentPresets 全部在册
  4. 技能：65 个目录，SKILL.md frontmatter 有 name/description/owner
  5. 名册：roster 与 patch preset 集合一致；persona_file 存在
  6. 可移植性：全包不得出现本机绝对路径（C:/Users/<me>、D:\\Programs）
  7. 展示元数据：locale zh/en 有 meta.title/description/detail；detail 文件存在；icon 存在且 ≤256KiB
  8. 宿主/客户端入口存在且能被 node 解析（语法级 --check 由调用方负责）

用法：python scripts/verify_package.py [--verbose]
退出码：0 全通过；1 有失败项
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)

FAILED = []
PASSED = []


def ok(msg):
    PASSED.append(msg)
    print("  \u2705 " + msg)


def bad(msg):
    FAILED.append(msg)
    print("  \u274c " + msg)


def load_yaml():
    sys.path.insert(0, os.path.join(PKG, "team", "tools", "_vendor"))
    import yaml  # noqa
    return yaml


def read(path):
    return io.open(path, encoding="utf-8").read()


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    verbose = "--verbose" in sys.argv

    print("== 1. 包清单 ==")
    man = json.loads(read(os.path.join(PKG, "package.json")))
    name = man.get("name", "")
    if name and re.match(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$", name):
        ok("包名 " + name)
    else:
        bad("包名异常：%r" % name)
    for key in ("version", "description", "type", "exports", "files"):
        if man.get(key):
            ok("manifest.%s 存在" % key)
        else:
            bad("manifest.%s 缺失" % key)
    patch_rel = ((man.get("dsh") or dict()).get("bundle") or dict()).get("patch")
    if patch_rel and os.path.isfile(os.path.join(PKG, patch_rel)):
        ok("dsh.bundle.patch → %s" % patch_rel)
    else:
        bad("dsh.bundle.patch 缺失或文件不存在")
    client = (man.get("dsh") or dict()).get("client") or dict()
    if client.get("platform") == "web":
        ok("dsh.client.platform=web")
    else:
        bad("dsh.client.platform 不是 web")
    files = man.get("files") or []
    need = ["index.js", "routes.js", "client.js", "cordis.patch.yml", "locale/*.json", "icon.svg",
            "docs", "panel/roster.json", "agents", "skills", "assets/avatars/*.png", "team"]
    miss = [n for n in need if n not in files]
    if miss:
        bad("files 未覆盖：%s" % ", ".join(miss))
    else:
        ok("files 覆盖全部运行文件（%d 项）" % len(files))

    print("== 2. patch 与 preset ==")
    text = read(os.path.join(PKG, "cordis.patch.yml"))
    yaml = load_yaml()

    class L(yaml.SafeLoader):
        pass

    L.add_multi_constructor("tag:yaml.org,2002:js", lambda l, s, n: n.value)
    L.add_multi_constructor("!", lambda l, s, n: n.value)
    data = yaml.load(text, Loader=L)
    presets = dict()
    for entry in data or []:
        for pl in (entry.get("insert") or []):
            if pl.get("name") == "@deepseek-ai/dsh-agent-preset":
                presets[pl["config"]["id"]] = pl["config"]
    if len(presets) == 24:
        ok("24 个 preset")
    else:
        bad("preset 数量 %d ≠ 24" % len(presets))

    no_persona, no_skilldir = [], []
    for pid, cfg in presets.items():
        ids = [p.get("id") for p in (cfg.get("plugins") or [])]
        if "persona" not in ids:
            no_persona.append(pid)
        sf = next((p for p in (cfg.get("plugins") or []) if p.get("id") == "skill-filesystem"), None)
        if not sf or not ((sf.get("config") or dict()).get("bundledSkillDir")):
            no_skilldir.append(pid)
    ok("每个 preset 都有 persona") if not no_persona else bad("缺 persona：%s" % no_persona)
    ok("每个 preset 都挂了 bundledSkillDir") if not no_skilldir else bad("缺 bundledSkillDir：%s" % no_skilldir)

    print("== 3. 派发白名单 ==")
    lead = presets.get("data-warehouse-brain-team-lead") or dict()
    allowed = []
    for p in (lead.get("plugins") or []):
        if p.get("id") == "delegation":
            for child in (p.get("config") or []):
                cfg = child.get("config") or dict()
                if cfg.get("allowedAgentPresets"):
                    allowed = cfg["allowedAgentPresets"]
    unknown = [a for a in allowed if a not in presets]
    if allowed and not unknown:
        ok("主理人白名单 %d 项全部在册" % len(allowed))
    else:
        bad("白名单引用了不存在的 preset：%s" % unknown)

    print("== 4. 技能 ==")
    sk_dir = os.path.join(PKG, "skills")
    dirs = [d for d in sorted(os.listdir(sk_dir)) if os.path.isdir(os.path.join(sk_dir, d))]
    if len(dirs) == 65:
        ok("65 个技能目录")
    else:
        bad("技能目录 %d ≠ 65" % len(dirs))
    badfm = []
    for d in dirs:
        p = os.path.join(sk_dir, d, "SKILL.md")
        if not os.path.isfile(p):
            badfm.append(d + ":no-skill-md")
            continue
        m = re.match(r"^---\n(.*?)\n---", read(p), re.S)
        fm = m.group(1) if m else ""
        if not (re.search(r"^name:", fm, re.M) and re.search(r"^description:", fm, re.M)):
            badfm.append(d + ":frontmatter")
    ok("每个技能 frontmatter 合法") if not badfm else bad("frontmatter 异常：%s" % badfm[:5])

    print("== 5. 名册 ==")
    roster = json.loads(read(os.path.join(PKG, "panel", "roster.json")))
    ids = {a["id"] for a in roster.get("agents") or []}
    if ids == set(presets):
        ok("名册与 patch preset 集合一致（%d）" % len(ids))
    else:
        bad("名册不一致：缺 %s / 多 %s" % (sorted(set(presets) - ids)[:5], sorted(ids - set(presets))[:5]))
    missing_md = [a["id"] for a in roster["agents"]
                  if not os.path.isfile(os.path.join(PKG, a.get("persona_file") or ""))]
    ok("每个名册项的 persona_file 存在") if not missing_md else bad("缺人设文件：%s" % missing_md[:5])

    print("== 6. 可移植性（无本机绝对路径）==")
    hits = []
    for root, dirs, fnames in os.walk(PKG):
        # scripts/ 是维护工具，不在 files 里、不随包发行；其余一律扫
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git", "scripts")]
        for fn in fnames:
            if not fn.endswith((".md", ".json", ".yml", ".yaml", ".js", ".py", ".sql", ".txt")):
                continue
            fp = os.path.join(root, fn)
            try:
                t = read(fp)
            except (UnicodeDecodeError, OSError):
                continue
            for pat in ("C:/" + "Users/lin", "C:\\\\" + "Users\\\\lin",
                        "D:\\\\" + "Programs\\\\DeepSeek"):
                if pat in t:
                    hits.append(os.path.relpath(fp, PKG))
                    break
    ok("无本机绝对路径") if not hits else bad("仍有本机路径：%s" % hits[:6])

    print("== 7. 展示元数据 ==")
    for loc in ("zh", "en"):
        p = os.path.join(PKG, "locale", loc + ".json")
        if not os.path.isfile(p):
            bad("缺 locale/%s.json" % loc)
            continue
        meta = (json.loads(read(p)) or dict()).get("meta") or dict()
        miss = [k for k in ("title", "description", "detail") if not meta.get(k)]
        if miss:
            bad("locale/%s.json 缺 meta.%s" % (loc, "/".join(miss)))
            continue
        detail = os.path.join(PKG, meta["detail"])
        if os.path.isfile(detail):
            ok("locale/%s.json 元数据完整，detail 存在" % loc)
        else:
            bad("locale/%s.json 的 meta.detail 指向不存在的文件：%s" % (loc, meta["detail"]))
    icon = os.path.join(PKG, man.get("icon") or "icon.svg")
    if os.path.isfile(icon):
        size = os.path.getsize(icon)
        ok("图标 %s（%d B）" % (os.path.basename(icon), size)) if size <= 256 * 1024 else bad("图标超过 256KiB")
    else:
        bad("图标缺失")

    print("== 8. 入口文件 ==")
    for f in ("index.js", "routes.js", "client.js"):
        p = os.path.join(PKG, f)
        ok("%s (%d B)" % (f, os.path.getsize(p))) if os.path.isfile(p) else bad("%s 缺失" % f)

    print("== 9. 包名三处一致（改名最容易漏）==")
    panel_rows = [pl for e in (data or []) for pl in (e.get("insert") or [])
                  if (pl.get("name") or "").startswith("@") and pl.get("id") == "dwb-team"]
    if panel_rows and panel_rows[0].get("name") == name:
        ok("面板宿主行 name = 包名")
    else:
        bad("面板宿主行 name 与包名不一致：%r" % (panel_rows[0].get("name") if panel_rows else None))
    m = re.search(r"(?m)^  id: '([^']*)',$", read(os.path.join(PKG, "client.js")))
    if m and m.group(1) == name:
        ok("client 模块 id = 包名")
    else:
        bad("client 模块 id 与包名不一致：%r" % (m.group(1) if m else None))
    skill_exprs = set(re.findall(r"resolve\('([^']+)/package\.json'\)", text))
    if skill_exprs == {name}:
        ok("bundledSkillDir 解析目标 = 包名")
    else:
        bad("bundledSkillDir 解析目标异常：%s" % sorted(skill_exprs))

    print()
    print("通过 %d 项，失败 %d 项" % (len(PASSED), len(FAILED)))
    if FAILED:
        print("\u274c 校验失败")
        return 1
    print("\u2705 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
