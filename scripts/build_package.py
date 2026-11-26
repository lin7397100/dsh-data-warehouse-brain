# -*- coding: utf-8 -*-
"""build_package.py —— 从「本机手工版团队」生成可发行的 DSH 组合包

一次性迁移（--init）：
  1. 复制 skills/、agents/、头像、工具脚本到包内；
  2. 从本机 profile patch 抽出 24 个 preset，做三处可移植化改造；
  3. 生成 packge 自己的 cordis.patch.yml 与 panel/roster.json。

之后只需 `python scripts/build_package.py`：从**包内** agents/ 重建 prefix、重算名册。

用法：
  python scripts/build_package.py --init --team-root <团队根> --patch <profile patch>
  python scripts/build_package.py              # 常规重建（patch prefix + roster）
  python scripts/build_package.py --check      # 只校验，不写盘

退出码：0 成功；1 校验失败；2 环境错误
"""
import argparse
import io
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
PATCH_OUT = os.path.join(PKG, "cordis.patch.yml")
ROSTER_OUT = os.path.join(PKG, "panel", "roster.json")
AGENTS = os.path.join(PKG, "agents")
SKILLS = os.path.join(PKG, "skills")

PKG_NAME_DEFAULT = "@sansteel/dsh-data-warehouse-brain"
BUNDLE_DIRNAME = "dsh-data-warehouse-brain"
IND = " " * 16


def pkg_name():
    """包名以 package.json 为唯一真源（改名只需改 manifest 再重建）。"""
    try:
        man = json.load(io.open(os.path.join(PKG, "package.json"), encoding="utf-8"))
        return man.get("name") or PKG_NAME_DEFAULT
    except (OSError, ValueError):
        return PKG_NAME_DEFAULT


PKG_NAME = pkg_name()

OLD_TEAM_ROOT = ("C:/" + "Users/lin/Documents/deepseek-harness/data-warehouse-brain-team")
NEW_TEAM_ROOT = r"$env:DSH_HOME\dwb-team"

SKILL_FS_NAME = "@deepseek-ai/dsh-skill-filesystem"
BUNDLED_SKILL_EXPR = (
    "!!js process.getBuiltinModule('node:path').join("
    "process.getBuiltinModule('node:path').dirname("
    "process.getBuiltinModule('node:module').createRequire(baseUrl)"
    ".resolve('%s/package.json')), 'skills')" % PKG_NAME
)

INTERNAL_MCP_IDS = ("mcp-weknora", "mcp-db2", "mcp-wecom-group", "mcp-wecom-user")
SG_MCP_OFF = '!!js "process.env.SG_MCP === \'off\'"'
PUBLIC_GATE = SG_MCP_OFF


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass


def load_yaml():
    sys.path.insert(0, os.path.join(PKG, "team", "tools", "_vendor"))
    import yaml  # noqa
    return yaml


def check_yaml(text):
    yaml = load_yaml()

    class L(yaml.SafeLoader):
        pass

    L.add_multi_constructor("!", lambda l, s, n: None)
    L.add_multi_constructor("tag:yaml.org,2002:js", lambda l, s, n: None)
    yaml.load(text, Loader=L)


def rewrite_paths(text):
    """把本机绝对路径改写成组合包形态（三种斜杠形态都要覆盖）。"""
    home = "C:/" + "Users/lin/.dsh"
    t = text
    for base, repl in ((OLD_TEAM_ROOT, NEW_TEAM_ROOT), (home, "$env:DSH_HOME")):
        t = t.replace(base, repl)
        t = t.replace(base.replace("/", "\\"), repl)
        t = t.replace(base.replace("/", "\\\\"), repl.replace("\\", "\\\\"))
    return t


def inject_bundled_skill_dir(block_lines):
    """给 preset 里的 skill-filesystem 行加 bundledSkillDir。返回 (lines, changed)。"""
    out, i, changed = [], 0, False
    while i < len(block_lines):
        line = block_lines[i]
        out.append(line)
        if line.strip() == "- id: skill-filesystem":
            # 下一行应是 name
            if i + 1 < len(block_lines) and SKILL_FS_NAME in block_lines[i + 1]:
                out.append(block_lines[i + 1])
                i += 2
                nxt = block_lines[i] if i < len(block_lines) else ""
                if nxt.strip() == "config:":
                    # 已有 config：往里插一行
                    out.append(nxt)
                    out.append("              bundledSkillDir: " + BUNDLED_SKILL_EXPR)
                    i += 1
                    changed = True
                else:
                    out.append("            config:")
                    out.append("              bundledSkillDir: " + BUNDLED_SKILL_EXPR)
                    changed = True
                continue
        i += 1
    return out, changed


def gate_internal_mcp(block_lines, stats):
    out = []
    cur_id = None
    for line in block_lines:
        m = re.match(r"^(\s*)- id: (mcp-[A-Za-z0-9_-]+)$", line)
        if m:
            cur_id = m.group(2)
        if cur_id in INTERNAL_MCP_IDS and line.strip() == "disabled: " + SG_MCP_OFF:
            out.append(line.replace(SG_MCP_OFF, PUBLIC_GATE))
            stats["mcp_gated"] = stats.get("mcp_gated", 0) + 1
            continue
        out.append(line)
    return out


def extract_block(patch_text):
    """抽出 profile patch 里的 DWB-TEAM 块（去掉首尾注释行），返回行列表。"""
    lines = patch_text.replace("\r\n", "\n").split("\n")
    start = next(i for i, l in enumerate(lines) if "DWB-TEAM-BEGIN" in l)
    end = next(i for i, l in enumerate(lines) if "DWB-TEAM-END" in l)
    return lines[start + 1:end]


def build_patch_from_profile(patch_path):
    raw = io.open(patch_path, encoding="utf-8").read()
    block = extract_block(raw)
    block = [rewrite_paths(l) for l in block]
    stats = dict()
    block = gate_internal_mcp(block, stats)

    # 按 preset 块分别注入 bundledSkillDir
    out, buf, changed = [], [], 0
    def flush(is_preset):
        nonlocal buf, changed
        if is_preset and buf:
            buf2, ch = inject_bundled_skill_dir(buf)
            changed += 1 if ch else 0
            out.extend(buf2)
        else:
            out.extend(buf)
        buf = []

    for line in block:
        if re.match(r"^    - id: preset-", line):
            flush(True)
        buf.append(line)
    flush(True)

    out = [l for l in out if l.strip() != ""]
    header = [
        "# 数仓智脑专家团 · DSH 组合包补丁层（%s）" % PKG_NAME,
        "#",
        "# 由 scripts/build_package.py 生成，不要手改：改 agents/*.md 后重跑即可。",
        "# 结构：一个 insert 列表 = 24 个 preset（1 主理人 + 22 专家 + 1 快问）+ 面板宿主行。",
        "# 每个 preset 自带：persona（人设） / skill-filesystem（bundledSkillDir → 包内 skills/）",
        "#   / 工具集 / compaction / delegation 白名单 / 可选 MCP 客户端。",
        "",
    ]
    # 多个顶层 `- insert:` 合并成一个（DSH 对「无 id 且非 insert」的条目会报警）
    items = [l for l in out if l.strip() != "- insert:"]
    items = [("    " + l.lstrip()) if l.strip().startswith("- id: dwb-team") else l for l in items]
    if not any(l.strip() == "- id: dwb-team" for l in items):
        items += [
            "",
            "    - id: dwb-team",
            "      name: '%s'" % PKG_NAME,
            "      config:",
            "        teamRoot: ''",
        ]
    return "\n".join(header + ["- insert:"] + items) + "\n", stats, changed


def build_patch_from_agents():
    """常规重建：用 agents/*.md 重渲染每个 preset 的 prefix，其余结构取现有 patch。"""
    raw = io.open(PATCH_OUT, encoding="utf-8").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    out, i = [], 0
    rebuilt = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.match(r"^    - id: preset-(.+)$", line)
        if not m:
            i += 1
            continue
        pid = m.group(1)
        md_path = os.path.join(AGENTS, pid + ".md")
        if not os.path.isfile(md_path):
            i += 1
            continue
        # 找本块内的 'prefix: |'
        j = i + 1
        while j < len(lines) and not lines[j].startswith("    - id: "):
            j += 1
        pre = next((k for k in range(i, j) if lines[k].strip() == "prefix: |"), None)
        if pre is None:
            i += 1
            continue
        e = pre + 1
        while e < j and (lines[e].strip() == "" or lines[e].startswith(IND)):
            e += 1
        while e > pre + 1 and lines[e - 1].strip() == "":
            e -= 1
        new_block = render_prefix(md_path)
        old_chars = sum(len(x) for x in lines[pre + 1:e])
        new_chars = sum(len(x) for x in new_block)
        # 防膨胀护栏（与 tools/sync_persona.py 同规则）：
        # agents/*.md 是「详细知识库」，patch prefix 是「浓缩手册」，两者本就不同。
        # 主理人 MD 约 75K 字符而 prefix 仅 13K，直接渲染会撑爆上下文。
        if old_chars > 0 and new_chars > old_chars * 1.5:
            out.extend(lines[i + 1:e])
            i = e
            continue
        out.extend(lines[i + 1:pre + 1])
        out.extend(new_block)
        i = e
        rebuilt += 1
        continue
    text = nl.join(out)
    check_yaml(text)
    return text, rebuilt


def render_prefix(md_path):
    md = io.open(md_path, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    while md and md[0].strip() == "":
        md.pop(0)
    if not md or not md[0].startswith("# "):
        raise SystemExit("FAIL: %s 首行不是 '# 标题'" % md_path)
    out = ["", md[0], ""]
    body = md[1:]
    while body and body[0].strip() == "":
        body.pop(0)
    out += [l for l in body]
    while out and out[-1].strip() == "":
        out.pop()
    return [IND + l if l.strip() else "" for l in out]


def build_roster(patch_text):
    yaml = load_yaml()

    class L(yaml.SafeLoader):
        pass

    L.add_multi_constructor("tag:yaml.org,2002:js", lambda l, s, n: n.value)
    L.add_multi_constructor("!", lambda l, s, n: n.value)
    data = yaml.load(patch_text, Loader=L)

    skills_map = scan_skills(SKILLS)
    rows = []
    for entry in data or []:
        for pl in (entry.get("insert") or []):
            if pl.get("name") != "@deepseek-ai/dsh-agent-preset":
                continue
            c = pl.get("config") or dict()
            plugins = c.get("plugins") or []
            plugin_ids, skill_dirs, prefix, mcp = [], [], "", []
            for x in plugins:
                pid = x.get("id")
                if pid:
                    plugin_ids.append(pid)
                cfg = x.get("config") or dict()
                if pid == "persona":
                    prefix = cfg.get("prefix") or ""
                if pid and pid.startswith("skill"):
                    sd = cfg.get("skills") or cfg.get("skillDirs") or cfg.get("bundledSkillDir")
                    if isinstance(sd, str):
                        skill_dirs.append(sd)
                    elif isinstance(sd, list):
                        skill_dirs.extend([str(s) for s in sd])
                if pid and (pid.startswith("mcp-") or x.get("name") == "@deepseek-ai/dsh-mcp-client"):
                    mcp.append({"id": pid, "server_name": cfg.get("serverName") or "",
                                "transport": cfg.get("transport") or ""})
            rows.append({
                "id": c.get("id"),
                "name": c.get("name") or c.get("id"),
                "description": CN_DESC.get(c.get("id"), c.get("description") or ""),
                "order": c.get("order") or 99,
                "group": ("lead" if c.get("id") == "data-warehouse-brain-team-lead"
                          else "fast" if c.get("id") == "dwb-fast-ask" else "expert"),
                "plugins": plugin_ids,
                "mcp": mcp,
                "skill_dirs": skill_dirs,
                "skills": skills_map.get(c.get("id"), []),
                "prefix_len": len(prefix or ""),
                "persona_file": os.path.join("agents", (c.get("id") or "") + ".md"),
            })
    rows.sort(key=lambda r: (r["order"], r["id"] or ""))
    return {
        "meta": {
            "generated_at": "",
            "package": PKG_NAME,
            "count": len(rows),
            "skill_count": sum(len(r["skills"]) for r in rows),
            "groups": {
                "lead": sum(1 for r in rows if r["group"] == "lead"),
                "expert": sum(1 for r in rows if r["group"] == "expert"),
                "fast": sum(1 for r in rows if r["group"] == "fast"),
            },
        },
        "agents": rows,
    }


def _fm(fm, key):
    m = re.search(r"^" + re.escape(key) + r":\s*(.*?)\s*$", fm, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    if v in ("|", ">", "|-", ">-", "|+", ">+"):
        return ""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    return v


def scan_skills(skills_dir):
    mapping = dict()
    if not os.path.isdir(skills_dir):
        return mapping
    for d in sorted(os.listdir(skills_dir)):
        p = os.path.join(skills_dir, d, "SKILL.md")
        if not os.path.isfile(p):
            continue
        txt = io.open(p, encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---", txt, re.S)
        fm = m.group(1) if m else ""
        owners = [o.strip() for o in _fm(fm, "owner").split(",") if o.strip()]
        if not owners:
            continue
        rec = {"id": _fm(fm, "name") or d, "dir": d,
               "description": _fm(fm, "description"), "version": _fm(fm, "version")}
        for o in owners:
            mapping.setdefault(o, []).append(dict(rec))
    return mapping


CN_DESC = {
    "data-warehouse-brain-team-lead": "主理人：拆解任务、按白名单派发专家、验收汇总（不取数、不写 SQL）",
    "sg-semantic": "语义层专家：维护 KPI 语义模型，落实「未注册指标禁用」，双引擎意图解析并生成结构化 DSL。",
    "sg-ontology": "本体专家：构建实体-关系-过程-指标本体，产出全团可机读的数据血缘，并对接本体业务图谱技能。",
    "sg-metadata": "元数据专家：管理表结构与 Schema，贯通物理血缘，承担 RAG 知识检索与 EPLAT 设计态解析。",
    "sg-development": "数仓开发专家：确定性地把 DSL 编译为 DB2 SQL，生成与优化查询/存储过程，配置指标 SQL。",
    "sg-quality": "质量与根因诊断专家：主导全链路根因分析，落实交付前可靠性闸口，做成本批次健康度监控。",
    "sg-insight": "洞察与可视化专家：带口径与血缘渲染结果，汇总报表，搭建交互式看板，撰写报告，做趋势与多厂对标。",
    "sg-governance": "数据安全治理专家：四层 SQL 安全护栏，数据分级分类，脱敏与访问审计合规。",
    "sg-skill-evolution": "技能自进化元专家：从重复任务自动生成技能，督导优化其他技能，管理版本与回滚。",
    "sg-ontology-app-builder": "本体应用构建师：把业务需求经三阶段流水线产出可独立安装的领域技能。",
    "sg-metric-builder": "指标构建师：按 5S 规范搭建四级指标体系与指标血缘，产物落地三层知识引擎。",
    "sg-memory": "记忆与技能进化编排师：每日构建本体/语义/指标资产，备份会话记忆，封装指标技能。",
    "sg-supervisor": "监管与元治理编排师：跟踪专家与技能调用链，生成逐任务流程报告，监控 SLA 与上下文膨胀。",
    "sg-zhishu-dashboard-designer": "可视化分析设计师：制作交互图表、数据看板与可汇报的数据故事。",
    "sg-zhishu-report-composer": "洞察报告撰写师：把分析结果综合成含执行摘要与建议的完整报告。",
    "sg-wecom-doc": "企微文档操作专家：覆盖智能表格创建/读取/编辑/权限/检索全流程。",
    "sg-gzprod": "生产域协同架构师：生产域双盲核验的独立第二核验方，统筹炼铁/炼钢/轧钢跨链协作。",
    "sg-cbprod": "成本域协同架构师：成本利润全域口径、可比性框架与自校验 SQL。",
    "sg-5s-dev": "5S 数仓开发架构师：XData 维度建模流水线、DB2 SQL、任务编排与命名合规。",
    "sg-5s-qa": "5S 平台答疑排障专家：页面导航、错误诊断、合规审查与标准排障流程。",
    "sg-semantic-modeler": "语义层建模师：向量化与聚类生成同义词，注册指标并同步知识库。",
    "sg-ontology-modeler": "本体建模师：从存储过程与文档抽取四元组，维护 Neo4j 图谱。",
    "sg-query-router": "P0 前置意图理解专家：把自然语言翻译为确定性意图契约 JSON。",
    "dwb-fast-ask": "单指标裸查专用：确定性判型 → 物化直查 → 过网关 → 出数（不派专家）",
}


def init_copy(team_root):
    counts = dict()
    # skills
    dst = os.path.join(PKG, "skills")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    n = 0
    for name in sorted(os.listdir(os.path.join(team_root, "skills"))):
        src = os.path.join(team_root, "skills", name)
        if not os.path.isdir(src) or name in ("__pycache__", "materialized_sql"):
            continue
        tgt = os.path.join(dst, name)
        shutil.copytree(src, tgt, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "materialized_sql"))
        # SKILL.md 里的绝对路径一并改写（cd <团队根>/skills/... → $env:DSH_HOME\...）
        for root, _dirs, files in os.walk(tgt):
            for fn in files:
                if not fn.endswith((".md", ".sql", ".py", ".json", ".txt", ".env")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    txt = io.open(fp, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                fixed = rewrite_paths(txt)
                if fixed != txt:
                    io.open(fp, "w", encoding="utf-8").write(fixed)
        n += 1
    counts["skills"] = n

    # agents
    dst = os.path.join(PKG, "agents")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for name in sorted(os.listdir(os.path.join(team_root, "agents"))):
        if not name.endswith(".md") or name.startswith("_"):
            continue
        txt = io.open(os.path.join(team_root, "agents", name), encoding="utf-8").read()
        io.open(os.path.join(dst, name), "w", encoding="utf-8").write(rewrite_paths(txt))
        n += 1
    counts["agents"] = n
    # 人设引用的 agents/references/*.md（外置详细规范）必须一起发
    ref_src = os.path.join(team_root, "agents", "references")
    if os.path.isdir(ref_src):
        ref_dst = os.path.join(dst, "references")
        if os.path.isdir(ref_dst):
            shutil.rmtree(ref_dst)
        shutil.copytree(ref_src, ref_dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_*"))
        for root, _dirs, files in os.walk(ref_dst):
            for fn in files:
                if not fn.endswith((".md", ".py", ".sql")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    txt = io.open(fp, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                fixed = rewrite_paths(txt)
                if fixed != txt:
                    io.open(fp, "w", encoding="utf-8").write(fixed)
        counts["agent_references"] = len(os.listdir(ref_dst))

    # avatars
    dst = os.path.join(PKG, "assets", "avatars")
    os.makedirs(dst, exist_ok=True)
    src = os.path.join(team_root, "panel", "dwb-team-panel", "assets", "avatars")
    n = 0
    for name in os.listdir(src):
        if name.endswith(".png"):
            shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
            n += 1
    counts["avatars"] = n

    # team runtime scripts
    for sub in ("tools", "scripts"):
        dst = os.path.join(PKG, "team", sub)
        os.makedirs(dst, exist_ok=True)
        src = os.path.join(team_root, sub)
        n = 0
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "_deprecated")]
            for f in files:
                if f.endswith((".pyc",)) or f.startswith("_tmp_"):
                    continue
                if sub == "tools" and f.startswith("_") and f != "_vendor":
                    continue
                rel = os.path.relpath(os.path.join(root, f), src)
                tgt = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                shutil.copy2(os.path.join(root, f), tgt)
                n += 1
        counts["team_" + sub] = n

    # panel 源码：首次迁移才复制；之后以**包内为准**（避免覆盖包自己的改造）
    for f in ("index.js", "routes.js", "client.js", "icon.svg"):
        src = os.path.join(team_root, "panel", "dwb-team-panel", f)
        dst = os.path.join(PKG, f)
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copy2(src, dst)
    for loc in ("zh.json", "en.json"):
        src = os.path.join(team_root, "panel", "dwb-team-panel", "locale", loc)
        dst = os.path.join(PKG, "locale", loc)
        if os.path.isfile(src) and not os.path.isfile(dst):
            os.makedirs(os.path.join(PKG, "locale"), exist_ok=True)
            shutil.copy2(src, dst)

    # 运行脚本里的本机路径同样要改写（脚本被专家直接调用）
    for sub in ("tools", "scripts"):
        for root, _dirs, files in os.walk(os.path.join(PKG, "team", sub)):
            for fn in files:
                if not fn.endswith((".py", ".md", ".sql", ".txt", ".json", ".env")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    txt = io.open(fp, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                fixed = rewrite_paths(txt)
                if fixed != txt:
                    io.open(fp, "w", encoding="utf-8").write(fixed)
    return counts


PANEL_ROW = """
- insert:
    - id: dwb-team
      name: '%s'
      config:
        teamRoot: ''
""" % PKG_NAME


def ensure_panel_row(text):
    if "- id: dwb-team" in text:
        return text
    return text.rstrip("\n") + "\n" + PANEL_ROW


def strip_preset_mcp(text):
    """删除 preset 里的 mcp-client 行：改由面板 MCP 开关托管（mcp.js）。

    为什么：preset 内的 mcp-client 只在预设首次激活时求值一次，用户点不动；
    挪到 Host 级 mcpManager.register() 才能"点开关即时生效"。
    """
    lines = text.split("\n")
    out = []
    i = 0
    removed = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s+)- id: (mcp-[A-Za-z0-9_-]+)$", line)
        if m:
            indent = len(m.group(1))
            i += 1
            # 跳到下一个同级或更浅的行
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() == "":
                    i += 1
                    continue
                lead = len(nxt) - len(nxt.lstrip())
                if lead < indent or (lead == indent and nxt.lstrip().startswith("- ")):
                    break
                i += 1
            removed += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out), removed


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="一次性迁移：从团队根复制资产并重建 patch")
    ap.add_argument("--team-root", default=os.environ.get("DWB_TEAM_ROOT", ""))
    ap.add_argument("--patch", default=os.path.join(
        os.path.expanduser("~"), ".dsh", "profiles", "desktop", "cordis.patch.yml"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)

    if a.check:
        text = io.open(PATCH_OUT, encoding="utf-8").read()
        check_yaml(text)
        roster = json.load(io.open(ROSTER_OUT, encoding="utf-8"))
        print("patch YAML OK；roster=%d 个 preset，%d 条技能归属"
              % (roster["meta"]["count"], roster["meta"]["skill_count"]))
        return 0

    if a.init:
        team_root = a.team_root
        if not team_root or not os.path.isdir(team_root):
            print("FAIL: --team-root 无效：%r" % team_root)
            return 2
        counts = init_copy(team_root)
        print("已复制：" + "，".join("%s=%d" % (k, v) for k, v in counts.items()))
        text, stats, changed = build_patch_from_profile(a.patch)
        # B 方案：preset 保留 MCP 行（0.2.1 无 mcp-manager，删了就断通道）
        n_mcp = 0
        print("已从 preset 移除 %d 个 mcp-* 行（改由面板 MCP 开关托管）" % n_mcp)
        io.open(PATCH_OUT, "w", encoding="utf-8").write(text)
        print("patch 生成：%d 个 preset 注入 bundledSkillDir，%d 个内网 MCP 行改为默认关"
              % (changed, stats.get("mcp_gated", 0)))
    else:
        text, rebuilt = build_patch_from_agents()
        text, n_mcp = strip_preset_mcp(text)
        n_mcp = 0  # 保留 preset 内 MCP 行
        io.open(PATCH_OUT, "w", encoding="utf-8").write(text)
        print("patch 重建：%d 个 preset 的 persona 来自 agents/*.md" % rebuilt)

    text = io.open(PATCH_OUT, encoding="utf-8").read()
    check_yaml(text)
    roster = build_roster(text)
    import datetime
    roster["meta"]["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    os.makedirs(os.path.dirname(ROSTER_OUT), exist_ok=True)
    io.open(ROSTER_OUT, "w", encoding="utf-8").write(
        json.dumps(roster, ensure_ascii=False, indent=2))
    print("roster：%d 个 preset（lead=%d expert=%d fast=%d），技能归属 %d 条"
          % (roster["meta"]["count"], roster["meta"]["groups"]["lead"],
             roster["meta"]["groups"]["expert"], roster["meta"]["groups"]["fast"],
             roster["meta"]["skill_count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
