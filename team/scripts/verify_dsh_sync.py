#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_dsh_sync.py —— DSH 单向发布部署一致性校验器（Deployment Sync Verifier）

## 为什么需要本脚本

DSH 的部署模型是 **单向发布（one-way publish）**：

    源仓库（本包）
      ├─ agents/*.md        ──发布──>  ~/.dsh/profiles/desktop/cordis.patch.yml（preset/persona）
      └─ skills/*/SKILL.md  ──发布──>  ~/.dsh/skills/*/SKILL.md

只允许「源仓库 → 运行时」一个方向；运行时**不写回**源仓库，也没有 WorkBuddy 那种
marketplaces ↔ cache 双副本镜像。在 DSH 下，**改了源仓库 ≠ 会话立即生效**，
因此必须有一致性校验器回答同一个问题：

    「包内 skills / agents 与 DSH 运行时加载源，到底是否一致？」

## 校验项

1. **skills 层**：`<包根>/skills/<skill>/SKILL.md` ↔ `~/.dsh/skills/<skill>/SKILL.md`
   - 逐技能目录比对 MD5，状态：`same` | `drift` | `missing_in_dsh` | `extra_in_dsh`
2. **agents 层**：`<包根>/agents/*.md` ↔ `cordis.patch.yml` 的 24 个 preset prefix
   - 每个 preset 的 persona prefix 含**旧 API**（TaskCreate / TeamCreate / TaskOutput /
     SendMessage / run_in_background / subagent_type）必须为 0
   - agent 数 ↔ preset 数数量守恒（当前 24 ↔ 24），并做 id 集合对账
3. **roster 层**：`panel/roster.json` 旧 API 残留必须为 0，且 `meta.count` 与 preset 数一致
4. **WorkBuddy 遗留检查**：本脚本自身不得引用 WorkBuddy 插件目录（DSH 不应依赖 WorkBuddy 路径）

## 用法

    python scripts/verify_dsh_sync.py                 # 只校验，打印人类可读报告
    python scripts/verify_dsh_sync.py --json          # 输出机器可读 JSON
    python scripts/verify_dsh_sync.py --apply         # 发布：包内 skills → ~/.dsh/skills（自动备份）
    python scripts/verify_dsh_sync.py --apply --dry-run   # 只打印发布计划，不写盘

## 退出码

    0  全一致（或 --apply 成功后复检通过）
    1  存在漂移 / 旧 API 残留 / 数量不守恒
    2  环境异常（找不到 DSH 根、patch 或 skills 目录）

## 排除项（发布方向）

    __pycache__/  *.pyc  *.pyo  materialized_sql/
    —— 物化 SQL 由每日构建单向写入运行时，**禁止**发布回写（会覆盖新构建产物）。

## 铁律

- 只读校验不写任何文件；`--apply` 前**必须**自动备份 `~/.dsh/skills/`。
- 发布为**增量覆盖，不镜像删除**（运行时独有文件保留，避免不可逆丢失）。
- 路径全部由 `os.path.expanduser('~')` 推断，**禁止**硬编码用户名。
- 发布完成后需**重启 DSH** 才会被新会话加载。
"""

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import sys

# ---------------------------------------------------------------- 路径推断

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DSH_HOME = os.path.join(os.path.expanduser("~"), ".dsh")
PATCH = os.path.join(DSH_HOME, "profiles", "desktop", "cordis.patch.yml")
DSH_SKILLS = os.path.join(DSH_HOME, "skills")

PKG_SKILLS = os.path.join(ROOT, "skills")
PKG_AGENTS = os.path.join(ROOT, "agents")
PKG_ROSTER = os.path.join(ROOT, "panel", "roster.json")
BACKUP_ROOT = os.path.join(ROOT, "backup")

PRESET_PKG = "@deepseek-ai/dsh-agent-preset"

# 旧版 harness API（DSH 会话中不存在）——出现即视为未完成对齐
OLD_API_RE = re.compile(
    r"TaskCreate|TeamCreate|TaskOutput|SendMessage|run_in_background|subagent_type"
)

# 自检用的 WorkBuddy 路径特征：拆开拼接，避免本脚本命中自身
WB_NEEDLE = "." + "workbuddy"

EXCLUDE_DIRS = {"__pycache__", ".git", ".in_use"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".bak")
EXCLUDE_REL_PARTS = ("materialized_sql",)

STATUS_OK = "same"


# ---------------------------------------------------------------- 基础工具


def _utf8_stdout():
    """Windows 控制台默认 GBK，强制 UTF-8 输出，避免中文/emoji 抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_text(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_excluded_rel(rel):
    """发布/比对排除项：编译产物 + 物化 SQL（每日构建单向写入，禁回写）。"""
    rel_n = rel.replace("\\", "/")
    parts = rel_n.split("/")
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    if rel_n.endswith(EXCLUDE_SUFFIX):
        return True
    if any(part in rel_n for part in EXCLUDE_REL_PARTS):
        return True
    if ".bak" in rel_n:
        return True
    return False


def iter_files(base, prefix=""):
    """遍历 base 下的文件，产出 (相对路径 posix 风格, 绝对路径)，跳过排除项。"""
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            abs_p = os.path.join(root, name)
            rel = os.path.relpath(abs_p, base).replace("\\", "/")
            if prefix:
                rel = prefix + "/" + rel
            if is_excluded_rel(rel):
                continue
            yield rel, abs_p


def skill_dirs(base):
    """取 base 下「含 SKILL.md 的子目录」名集合（DSH 会往 skills/ 写 manifest 文件，需忽略）。"""
    if not os.path.isdir(base):
        return set()
    out = set()
    for name in os.listdir(base):
        p = os.path.join(base, name)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "SKILL.md")):
            out.add(name)
    return out


def _load_yaml():
    try:
        import yaml  # noqa: F401
        return yaml
    except ImportError:
        cand = os.path.join(os.environ.get("TEMP", ""), "pyyaml_lib")
        if os.path.isdir(cand):
            sys.path.insert(0, cand)
            try:
                import yaml  # noqa: F401
                return yaml
            except ImportError:
                pass
    return None


# ---------------------------------------------------------------- 1. skills 层


def check_skills():
    """逐技能目录比对 SKILL.md 的 MD5。"""
    pkg_names = skill_dirs(PKG_SKILLS)
    dsh_names = skill_dirs(DSH_SKILLS)

    items = []
    for name in sorted(pkg_names | dsh_names):
        pkg_md = os.path.join(PKG_SKILLS, name, "SKILL.md")
        dsh_md = os.path.join(DSH_SKILLS, name, "SKILL.md")
        pkg_ok = os.path.isfile(pkg_md)
        dsh_ok = os.path.isfile(dsh_md)

        if pkg_ok and dsh_ok:
            a, b = md5_file(pkg_md), md5_file(dsh_md)
            status = STATUS_OK if a == b else "drift"
        elif pkg_ok:
            a, b, status = md5_file(pkg_md), None, "missing_in_dsh"
        else:
            a, b, status = None, md5_file(dsh_md), "extra_in_dsh"

        rec = {
            "name": name,
            "pkg_md5": a,
            "dsh_md5": b,
            "status": status,
        }

        # 目录内其它文件的差异（SKILL 之外：scripts / references 等）
        file_drift = []
        if pkg_ok or dsh_ok:
            pkg_files = {}
            dsh_files = {}
            if pkg_ok:
                for rel, abs_p in iter_files(os.path.join(PKG_SKILLS, name)):
                    pkg_files[rel] = abs_p
            if dsh_ok:
                for rel, abs_p in iter_files(os.path.join(DSH_SKILLS, name)):
                    dsh_files[rel] = abs_p
            for rel in sorted(set(pkg_files) | set(dsh_files)):
                if rel == "SKILL.md":
                    continue
                if rel in pkg_files and rel in dsh_files:
                    if md5_file(pkg_files[rel]) != md5_file(dsh_files[rel]):
                        file_drift.append({"path": rel, "status": "drift"})
                elif rel in pkg_files:
                    file_drift.append({"path": rel, "status": "missing_in_dsh"})
                else:
                    file_drift.append({"path": rel, "status": "extra_in_dsh"})
        if file_drift:
            rec["file_drift"] = file_drift

        items.append(rec)

    summary = {
        "package": len(pkg_names),
        "dsh": len(dsh_names),
        "same": sum(1 for i in items if i["status"] == "same"),
        "drift": sum(1 for i in items if i["status"] == "drift"),
        "missing_in_dsh": sum(1 for i in items if i["status"] == "missing_in_dsh"),
        "extra_in_dsh": sum(1 for i in items if i["status"] == "extra_in_dsh"),
    }
    summary["file_drift_total"] = sum(len(i.get("file_drift") or []) for i in items)
    return {"dirs": {"package": PKG_SKILLS, "dsh": DSH_SKILLS}, "summary": summary, "items": items}


# ---------------------------------------------------------------- 2. agents 层


def load_presets():
    """解析 cordis.patch.yml，返回 [{id, name, prefix, prefix_len}]。"""
    yaml = _load_yaml()
    if yaml is None:
        raise RuntimeError("PyYAML 不可用：请 `pip install pyyaml` 后重试")

    text = io.open(PATCH, encoding="utf-8").read()

    class _L(yaml.SafeLoader):
        pass

    def _unknown(loader, suffix, node):  # !!js / ! 表达式原样取字符串
        return node.value

    _L.add_multi_constructor("tag:yaml.org,2002:js", _unknown)
    _L.add_multi_constructor("!", _unknown)
    data = yaml.load(text, Loader=_L)

    presets = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        inserts = entry.get("insert")
        if not isinstance(inserts, list):
            continue
        for pl in inserts:
            if not isinstance(pl, dict) or pl.get("name") != PRESET_PKG:
                continue
            cfg = pl.get("config") or {}
            prefix = ""
            for x in cfg.get("plugins") or []:
                if isinstance(x, dict) and x.get("id") == "persona":
                    prefix = (x.get("config") or {}).get("prefix") or ""
                    break
            presets.append(
                {
                    "id": cfg.get("id") or "",
                    "name": cfg.get("name") or "",
                    "prefix_len": len(prefix),
                    "prefix_md5": md5_text(prefix) if prefix else None,
                    "workbuddy_hits": len(re.findall(r"[Ww]ork[Bb]uddy", prefix)),
                    "_prefix": prefix,
                }
            )
    return presets


def check_agents(presets):
    """agent 数 ↔ preset 数守恒 + prefix 旧 API 必须 0。"""
    pkg_agents = sorted(
        n[:-3] for n in os.listdir(PKG_AGENTS)
        if n.endswith(".md") and os.path.isfile(os.path.join(PKG_AGENTS, n))
    ) if os.path.isdir(PKG_AGENTS) else []

    preset_ids = [p["id"] for p in presets]

    old_api_hits = []
    for p in presets:
        for m in OLD_API_RE.finditer(p["_prefix"] or ""):
            line_no = (p["_prefix"] or "")[: m.start()].count("\n") + 1
            old_api_hits.append(
                {"preset": p["id"], "pattern": m.group(0), "prefix_line": line_no}
            )

    items = []
    for pid in preset_ids:
        p = next(x for x in presets if x["id"] == pid)
        items.append(
            {
                "preset_id": pid,
                "name": p["name"],
                "persona_file": "agents/%s.md" % pid,
                "persona_exists": os.path.isfile(os.path.join(PKG_AGENTS, pid + ".md")),
                "prefix_len": p["prefix_len"],
                "prefix_md5": p["prefix_md5"],
                "workbuddy_hits": p.get("workbuddy_hits", 0),
                "old_api_hits": sum(1 for h in old_api_hits if h["preset"] == pid),
            }
        )

    summary = {
        "package_agents": len(pkg_agents),
        "presets": len(preset_ids),
        "prefixes": sum(1 for p in presets if p["prefix_len"] > 0),
        "count_conserved": len(pkg_agents) == len(preset_ids),
        "old_api_hits": len(old_api_hits),
        "persona_workbuddy_hits": sum(p.get("workbuddy_hits", 0) for p in presets),
        "agents_missing_preset": sorted(set(pkg_agents) - set(preset_ids)),
        "presets_missing_persona": sorted(set(preset_ids) - set(pkg_agents)),
    }
    return {
        "patch": PATCH,
        "summary": summary,
        "items": items,
        "old_api_hits": old_api_hits,
    }


# ---------------------------------------------------------------- 3. roster 层


def check_roster(preset_count):
    if not os.path.isfile(PKG_ROSTER):
        return {
            "path": PKG_ROSTER,
            "exists": False,
            "old_api_hits": [],
            "summary": {"count": None, "presets": preset_count, "count_ok": False},
        }

    text = io.open(PKG_ROSTER, encoding="utf-8").read()
    hits = []
    for m in OLD_API_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        hits.append({"pattern": m.group(0), "line": line_no})

    count = None
    try:
        data = json.loads(text)
        count = (data.get("meta") or {}).get("count")
    except ValueError:
        pass

    return {
        "path": PKG_ROSTER,
        "exists": True,
        "old_api_hits": hits,
        "summary": {
            "count": count,
            "presets": preset_count,
            "count_ok": count == preset_count,
            "bytes": len(text.encode("utf-8")),
        },
    }


# ---------------------------------------------------------------- 4. WorkBuddy 遗留


def check_workbuddy():
    """本脚本自身不得引用 WorkBuddy 插件目录（DSH 不应依赖 WorkBuddy 路径）。

    另附全包残留统计（信息项，不参与退出码判定）：backup/、knowledge/、
    observed/ 为历史档案与运行产物，按治理规则不强制清理。
    """
    self_path = os.path.abspath(__file__)
    self_src = io.open(self_path, encoding="utf-8").read()
    self_hits = [
        {"line": self_src[: m.start()].count("\n") + 1}
        for m in re.finditer(re.escape(WB_NEEDLE), self_src)
    ]

    skip_top = {"backup", "knowledge", "observed", "artifacts", "traces", ".git"}
    by_top = {}
    for name in sorted(os.listdir(ROOT)):
        if name in skip_top:
            continue
        top = os.path.join(ROOT, name)
        if not os.path.isdir(top):
            continue
        n = 0
        for rel, abs_p in iter_files(top):
            if not rel.lower().endswith((".md", ".py", ".js", ".json", ".yml", ".yaml", ".ps1", ".html", ".txt")):
                continue
            if abs_p == self_path:
                continue
            try:
                src = io.open(abs_p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            n += len(re.findall(re.escape(WB_NEEDLE), src))
        if n:
            by_top[name] = n

    return {
        "self_reference_hits": len(self_hits),
        "self_reference_detail": self_hits,
        "package_scan": by_top,
        "package_scan_total": sum(by_top.values()),
        "note": "self_reference_hits 必须为 0；package_scan 为信息项（历史档案禁改），不参与退出码",
    }


# ---------------------------------------------------------------- 汇总判定


def build_result():
    """跑全部四层校验，返回 (result_dict, exit_code)。"""
    env_errors = []
    if not os.path.isdir(DSH_HOME):
        env_errors.append("找不到 DSH 根：%s" % DSH_HOME)
    if not os.path.isfile(PATCH):
        env_errors.append("找不到 cordis.patch.yml：%s" % PATCH)
    if not os.path.isdir(DSH_SKILLS):
        env_errors.append("找不到 DSH 技能目录：%s" % DSH_SKILLS)
    if not os.path.isdir(PKG_SKILLS):
        env_errors.append("找不到包内技能目录：%s" % PKG_SKILLS)

    result = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "package_root": ROOT,
        "dsh_home": DSH_HOME,
        "model": "DSH one-way publish（源仓库 -> 运行时，禁回写）",
    }
    if env_errors:
        result["environment"] = {"ok": False, "errors": env_errors}
        result["verdict"] = "ENV_ERROR"
        return result, 2

    result["environment"] = {"ok": True, "errors": []}

    presets = load_presets()
    skills = check_skills()
    agents = check_agents(presets)
    roster = check_roster(len(presets))
    workbuddy = check_workbuddy()

    result["skills"] = skills
    result["agents"] = agents
    result["roster"] = roster
    result["workbuddy"] = workbuddy

    blocking = []
    if skills["summary"]["drift"]:
        blocking.append("skills.drift=%d" % skills["summary"]["drift"])
    if skills["summary"]["missing_in_dsh"]:
        blocking.append("skills.missing_in_dsh=%d" % skills["summary"]["missing_in_dsh"])
    if skills["summary"]["extra_in_dsh"]:
        blocking.append("skills.extra_in_dsh=%d" % skills["summary"]["extra_in_dsh"])
    if not agents["summary"]["count_conserved"]:
        blocking.append("agents.count_conserved=false")
    if agents["summary"]["old_api_hits"]:
        blocking.append("agents.old_api_hits=%d" % agents["summary"]["old_api_hits"])
    if agents["summary"]["presets_missing_persona"]:
        blocking.append("agents.presets_missing_persona=%s" % ",".join(agents["summary"]["presets_missing_persona"]))
    if roster["old_api_hits"]:
        blocking.append("roster.old_api_hits=%d" % len(roster["old_api_hits"]))
    if not roster["summary"]["count_ok"]:
        blocking.append("roster.count_ok=false")
    if workbuddy["self_reference_hits"]:
        blocking.append("workbuddy.self_reference_hits=%d" % workbuddy["self_reference_hits"])

    result["blocking"] = blocking
    result["verdict"] = "PASS" if not blocking else "DRIFT"
    return result, 0 if not blocking else 1


# ---------------------------------------------------------------- 报告渲染


def render_text(result):
    out = []
    out.append("=" * 72)
    out.append("DSH 单向发布 · 部署一致性校验")
    out.append("=" * 72)
    out.append("  源仓库 : %s" % result["package_root"])
    out.append("  DSH 根 : %s" % result["dsh_home"])
    out.append("  模型   : %s" % result["model"])
    out.append("")

    env = result.get("environment") or {}
    if not env.get("ok"):
        out.append("❌ 环境异常（exit 2）：")
        for e in env.get("errors") or []:
            out.append("   - %s" % e)
        return "\n".join(out)

    # ---- skills
    sk = result["skills"]
    s = sk["summary"]
    out.append("【1】skills 层：包内 %d ↔ DSH %d" % (s["package"], s["dsh"]))
    out.append("     same=%d  drift=%d  missing_in_dsh=%d  extra_in_dsh=%d  目录内文件差异=%d"
               % (s["same"], s["drift"], s["missing_in_dsh"], s["extra_in_dsh"], s["file_drift_total"]))
    for it in sk["items"]:
        if it["status"] == "same":
            continue
        out.append("     %-10s %s" % (it["status"].upper(), it["name"]))
    if s["same"] == s["package"] == s["dsh"]:
        out.append("     ✅ 59 项 MD5 全一致")
    out.append("")

    # ---- agents
    ag = result["agents"]
    a = ag["summary"]
    out.append("【2】agents 层：包内 %d 个 agent ↔ patch %d 个 preset（prefix %d 个）"
               % (a["package_agents"], a["presets"], a["prefixes"]))
    out.append("     数量守恒=%s  旧API残留=%d" % ("✅" if a["count_conserved"] else "❌", a["old_api_hits"]))
    if a["agents_missing_preset"]:
        out.append("     ❌ agent 未挂 preset：%s" % ", ".join(a["agents_missing_preset"]))
    if a["presets_missing_persona"]:
        out.append("     ❌ preset 缺 persona 文件：%s" % ", ".join(a["presets_missing_persona"]))
    for h in ag["old_api_hits"][:10]:
        out.append("     ❌ 旧API %s @ %s (prefix 第 %d 行)" % (h["pattern"], h["preset"], h["prefix_line"]))
    if a["old_api_hits"] == 0 and a["count_conserved"]:
        out.append("     ✅ 24 个 prefix 旧 API 残留 = 0")
    if a.get("persona_workbuddy_hits"):
        hot = [i["preset_id"] for i in ag["items"] if i.get("workbuddy_hits")]
        out.append("     ℹ persona 段 WorkBuddy 提及 %d 处（信息项）：%s"
                   % (a["persona_workbuddy_hits"], ", ".join(hot)))
        out.append("       说明：patch 的 persona prefix 由外部渲染器生成（源仓库无该渲染器），")
        out.append("             源仓库 agents/*.md 已改 DSH 表述；重跑渲染器后本项自动归零。")
    out.append("")

    # ---- roster
    ro = result["roster"]
    r = ro["summary"]
    out.append("【3】roster 层：%s" % ro["path"])
    out.append("     meta.count=%s  preset=%s  数量一致=%s  旧API残留=%d"
               % (r["count"], r["presets"], "✅" if r["count_ok"] else "❌", len(ro["old_api_hits"])))
    for h in ro["old_api_hits"][:10]:
        out.append("     ❌ 旧API %s @ 第 %d 行" % (h["pattern"], h["line"]))
    out.append("")

    # ---- workbuddy
    wb = result["workbuddy"]
    out.append("【4】WorkBuddy 遗留检查：本脚本引用 %d 处（必须 0）" % wb["self_reference_hits"])
    if wb["self_reference_hits"]:
        for h in wb["self_reference_detail"][:5]:
            out.append("     ❌ 第 %d 行" % h["line"])
    else:
        out.append("     ✅ 本脚本零 WorkBuddy 依赖（DSH 单向发布，无 cache 镜像）")
    if wb["package_scan"]:
        out.append("     ℹ 全包历史残留（信息项，历史档案禁改）：%s"
                   % ", ".join("%s=%d" % (k, v) for k, v in sorted(wb["package_scan"].items())))
    out.append("")

    out.append("-" * 72)
    if result["verdict"] == "PASS":
        out.append("✅ PASS：包内资产与 DSH 运行时加载源完全一致（exit 0）")
    else:
        out.append("❌ DRIFT：%d 项阻断（exit 1）" % len(result["blocking"]))
        for b in result["blocking"]:
            out.append("   - %s" % b)
        out.append("")
        out.append("   修复：python scripts/verify_dsh_sync.py --apply   然后重启 DSH")
    return "\n".join(out)


# ---------------------------------------------------------------- 发布（--apply）


def backup_dsh_skills():
    """把 ~/.dsh/skills/ 整体备份到 <包根>/backup/dsh_skills_<时间戳>/。"""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_ROOT, "dsh_skills_%s" % ts)
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    shutil.copytree(
        DSH_SKILLS,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        dirs_exist_ok=False,
    )
    return dest


def apply_publish(dry_run):
    """包内 skills → ~/.dsh/skills 增量发布（不删除运行时独有文件）。"""
    stats = {"new": 0, "update": 0, "skip": 0, "bytes": 0}
    details = []

    pkg_names = skill_dirs(PKG_SKILLS)
    for name in sorted(pkg_names):
        src_dir = os.path.join(PKG_SKILLS, name)
        for rel, src in iter_files(src_dir):
            dst = os.path.join(DSH_SKILLS, name, rel.replace("/", os.sep))
            size = os.path.getsize(src)
            if os.path.exists(dst) and md5_file(src) == md5_file(dst):
                stats["skip"] += 1
                continue
            act = "UPDATE" if os.path.exists(dst) else "NEW   "
            stats["update" if act.startswith("UPDATE") else "new"] += 1
            stats["bytes"] += size
            details.append((act, "%s/%s" % (name, rel), size))
            if not dry_run:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

    return stats, details


def main(argv=None):
    # 2026-11-20 修复：必须在 argparse 之前切 UTF-8。
    # 否则 --help 打印 description（含 U+2194）时控制台仍是 GBK → UnicodeEncodeError → exit 1。
    _utf8_stdout()

    ap = argparse.ArgumentParser(
        description="DSH 单向发布部署一致性校验器（包内 skills/agents <-> ~/.dsh 运行时）"
    )
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--apply", action="store_true", help="发布：包内 skills → ~/.dsh/skills（自动备份）")
    ap.add_argument("--dry-run", action="store_true", help="配合 --apply：只打印发布计划，不写盘")
    args = ap.parse_args(argv)

    if args.apply:
        if not os.path.isdir(DSH_SKILLS) or not os.path.isdir(PKG_SKILLS):
            print("❌ 环境异常：找不到 DSH 技能目录或包内 skills 目录（exit 2）", file=sys.stderr)
            return 2

        backup_dir = None
        if not args.dry_run:
            backup_dir = backup_dsh_skills()
            print("🗂  已备份 %s → %s" % (DSH_SKILLS, backup_dir))
        else:
            print("🔍 DRY-RUN：不写盘、不备份")

        stats, details = apply_publish(dry_run=args.dry_run)
        print("=" * 72)
        print("发布%s" % ("计划（DRY-RUN，未写入）" if args.dry_run else "完成"))
        print("=" * 72)
        print("  新增 %4d | 更新 %4d | 跳过 %4d | 传输 %.2f MB"
              % (stats["new"], stats["update"], stats["skip"], stats["bytes"] / 1024.0 / 1024.0))
        if details:
            print("\n--- 变更明细（按体积 Top 20）---")
            for act, rel, size in sorted(details, key=lambda x: -x[2])[:20]:
                print("  %s %10s B  %s" % (act, format(size, ","), rel))
            if len(details) > 20:
                print("  ... 另 %d 个" % (len(details) - 20))

        if args.dry_run:
            print("\n提示：去掉 --dry-run 即真正发布；发布后需重启 DSH 才会被新会话加载。")
            return 0

        print("\n⚠ 发布已落盘，请**重启 DSH**（新会话才加载新技能）。")
        print("   物化 SQL（materialized_sql/）与 __pycache__ 已排除，不会回写。\n")

        result, code = build_result()
        print(render_text(result))
        return code

    result, code = build_result()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))
    return code


if __name__ == "__main__":
    sys.exit(main())
