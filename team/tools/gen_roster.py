#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_roster.py —— 从 desktop profile 的 cordis.patch.yml 抽取 24 个 preset 名册，
落盘 <TeamRoot>/panel/roster.json，供专家团面板宿主半读取。

为何需要：preset 的 id/name/description/order/persona 长度都嵌在 37 万字节的
patch YAML 内层 config 里；面板宿主半（Node）不解析 YAML，由本脚本一次性转成
纯 JSON 清单。preset 内容变更后重跑本脚本即可刷新面板名册。

用法（内置 python，PyYAML 缺失时先装到临时目录）：
  python tools/gen_roster.py
  python tools/gen_roster.py --patch <patch.yml> --out <roster.json>

退出码：0 成功；2 参数/环境错误；3 PyYAML 不可用。
"""

import argparse
import datetime as _dt
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_PATCH = os.path.join(
    os.path.expanduser("~"), ".dsh", "profiles", "desktop", "cordis.patch.yml"
)
DEFAULT_OUT = os.path.join(ROOT, "panel", "roster.json")


def _load_yaml():
    try:
        import yaml  # noqa
        return yaml
    except ImportError:
        # 兼容此前装到 %TEMP%/pyyaml_lib 的临时副本
        cand = os.path.join(os.environ.get("TEMP", ""), "pyyaml_lib")
        if os.path.isdir(cand):
            sys.path.insert(0, cand)
            try:
                import yaml  # noqa
                return yaml
            except ImportError:
                pass
    return None


def classify(preset_id, order):
    if preset_id == "data-warehouse-brain-team-lead":
        return "lead"
    if preset_id == "dwb-fast-ask":
        return "fast"
    return "expert"


# 中文职责描述（按 preset id 覆盖 patch 里透传的英文长句；内容依据各专家 persona 职责翻译，不新增能力）
CN_DESC = {
    "data-warehouse-brain-team-lead": "主理人：拆解任务、按白名单派发专家、验收汇总（不取数、不写 SQL）",
    "sg-semantic": "语义层专家：维护 6077 个 KPI 语义模型，落实「未注册指标禁用」，双引擎意图解析并生成结构化 DSL。",
    "sg-ontology": "本体专家：基于 ODS 表与 105 个存储过程（55 生产 + 50 日成本）构建实体-关系-过程-指标本体，产出全团可机读的数据血缘，并对接本体业务图谱技能。",
    "sg-metadata": "元数据专家：管理 9167 张表结构、96 个 schema，贯通 ODS/DWD/DWS/ADS 物理血缘，并对 DDL、存储过程与业务文档做 RAG 知识检索。",
    "sg-development": "数仓开发专家：确定性地把 DSL 编译为 DB2 SQL，生成与优化查询/存储过程，配置指标 SQL，并为简单自然语言查询提供快速通道。",
    "sg-quality": "质量与根因诊断专家：主导全链路根因分析，落实交付前可靠性闸口，以三因子分解推进生产成本双轮管控，监控成本批次健康度并运行 Python 数据分析。",
    "sg-insight": "洞察与可视化专家：带口径与血缘渲染查询结果，自动汇总生产与日成本报表，搭建交互式看板，撰写 Markdown/HTML/docx 报告，做趋势与多厂对标。",
    "sg-governance": "数据安全治理专家：落实四层 SQL 安全护栏，做数据敏感度分级（成本数据为敏感），强制脱敏并维护访问审计与合规。",
    "sg-skill-evolution": "技能自进化元专家：观察用户意图，从重复任务自动生成技能，督导优化其他专家技能，管理全技能库的版本、备份与回滚。",
    "sg-ontology-app-builder": "本体应用构建师：把业务需求（或上传规格）经内嵌三阶段流水线（需求探索 → 十一模型本体建模 → 自包含技能生成）产出可独立安装的领域技能。",
    "sg-metric-builder": "指标构建师：按 5S 平台数据模型规范搭建业务/原子/派生/复合四级指标体系，并为每个指标定义数据血缘；产物落地三层知识引擎并持久化。",
    "sg-memory": "记忆与技能进化编排师：负责本体、语义层、指标体系每日 0:00 增量/全量构建；会话记忆备份至 WeKnora；从重复流程与问答自动生成技能；封装派生/复合指标。",
    "sg-supervisor": "监管与元治理编排师：跟踪每个任务下的专家与技能调用链，生成逐任务流程报告，监控 SLA/耗时，标记过度派发与上下文膨胀，落实快车道纪律（单指标不派专家）。",
    "sg-zhishu-dashboard-designer": "可视化分析设计师：用现代 Web 技术制作交互图表、数据看板、画像可视化与可汇报的数据故事。",
    "sg-zhishu-report-composer": "洞察报告撰写师：把数据分析结果、知识发现与可视化综合成结构完整的分析报告，含执行摘要、关键发现与可落地建议。",
    "sg-wecom-doc": "企微文档操作专家：覆盖私有化智能表格创建/读取/编辑/删除/权限/检索全流程 API，沉淀 wecom_smartsheet_sync 等脚本的调用逻辑与字段坑点。",
    "sg-gzprod": "生产域协同架构师：作为生产域双盲核验的独立第二核验方（对照 sg-quality），统筹 GZPROD 内炼铁/炼钢/轧钢跨链协作。",
    "sg-cbprod": "成本域协同架构师：负责 CBPROD 成本利润全域：185 个例程、204 张表、12 类问答模式、38 个文档化坑点、6 条铁律、三层可比性框架、5 条自校验 SQL 与 V1–V9 版本口径体系。",
    "sg-5s-dev": "5S 数仓开发架构师：精通 16 步 xData 维度建模流水线（ODS→CDM→ADS→API）、DB2 SQL 编写、任务编排与命名合规规范，迁移自原 5S 专家包。",
    "sg-5s-qa": "5S 平台答疑排障专家：处理 5S xData 平台的页面导航、错误诊断、合规审查与标准排障流程，迁移自原 5S 专家包。",
    "sg-semantic-modeler": "语义层建模师：自动抽取 DB2 表结构与 WeKnora 知识库，用 sentence-transformers + Milvus/Qdrant 向量库构建语义嵌入，聚类同义词与规范名，把指标登记入库。",
    "sg-ontology-modeler": "本体建模师：从 DB2 存储过程（SYSCAT.ROUTINES）、用户上传业务逻辑文档与 WeKnora 知识库自动抽取实体-关系-过程-指标四元组，维护 Neo4j 图数据库（Bolt 7687）。",
    "sg-query-router": "P0 前置意图理解专家：把用户自然语言翻译为确定性意图契约 JSON（任务类型/业务域/指标/工厂/周期/物化状态/路由链/血缘要求），供编排师确定性派发。",
    "dwb-fast-ask": "单指标裸查专用：确定性判型 → 物化直查 → 过网关 → 出数（目标 ≤30 s，不派任何专家）",
}


def _default_url(expr):
    """从 !!js 表达式 `process.env.X ?? 'http://...'` 里取出兜底默认 URL。"""
    if not isinstance(expr, str):
        return ""
    quoted = re.findall(r"'([^']*)'", expr)
    return quoted[-1] if quoted else ""


def _fm_field(frontmatter, key):
    """从简单 YAML frontmatter 里取单值字段（去首尾引号）。

    2026-11-20 修复：支持块标量（`description: |` / `>` / `|-` / `>-`）——
    原实现只取到行尾的字面 `|`，导致面板上技能描述显示成 `"|"`。
    块标量会向后收集所有**缩进更深**的续行，按 YAML 规则拼接（`|` 保留换行，`>` 折成空格）。
    """
    m = re.search(r"^" + re.escape(key) + r":\s*(.*?)\s*$", frontmatter, re.M)
    if not m:
        return ""
    val = m.group(1).strip()
    if val in ("|", ">", "|-", ">-", "|+", ">+"):
        lines = frontmatter[m.end():].split("\n")
        block = []
        for ln in lines[1:]:
            if ln.strip() == "":
                block.append("")
                continue
            if not ln.startswith((" ", "\t")):
                break
            block.append(ln.strip())
        while block and block[-1] == "":
            block.pop()
        joined = "\n".join(block) if val.startswith("|") else " ".join(x for x in block if x)
        return joined.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        val = val[1:-1]
    return val


def scan_skills(skills_dir):
    """扫描 skills/<dir>/SKILL.md 的 frontmatter，按 owner 归属到专家 preset。

    返回 {owner_preset_id: [{id, dir, description, version}]}。owner 支持逗号分隔多专家
    （共享技能）；owner 是技能归属的权威结构化来源。
    """
    mapping = {}
    if not os.path.isdir(skills_dir):
        return mapping
    for d in sorted(os.listdir(skills_dir)):
        p = os.path.join(skills_dir, d, "SKILL.md")
        if not os.path.isfile(p):
            continue
        txt = io.open(p, encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---", txt, re.S)
        fm = m.group(1) if m else ""
        owner_raw = _fm_field(fm, "owner")
        owners = [o.strip() for o in owner_raw.split(",") if o.strip()]
        if not owners:
            continue
        rec = {
            "id": _fm_field(fm, "name") or d,
            "dir": d,
            "description": _fm_field(fm, "description"),
            "version": _fm_field(fm, "version"),
        }
        for o in owners:
            mapping.setdefault(o, []).append(dict(rec))
    return mapping


def _sanitize(obj):
    """把配置值转成 JSON 安全结构；!!js 表达式在我们的 Loader 里已是字符串，原样保留。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return str(obj)


def _plugin_node(x):
    """把一条 preset 插件声明序列化为面板可渲染的树节点（分组递归子节点）。"""
    if not isinstance(x, dict):
        return None
    node = {
        "id": x.get("id"),
        "package": x.get("name") or "",
        "group": bool(x.get("group")),
    }
    disabled = x.get("disabled")
    if disabled is not None:
        node["disabled_expr"] = str(disabled)
    cfg = x.get("config")
    if x.get("group"):
        node["isolate"] = _sanitize(x.get("isolate") or {})
        node["children"] = [_plugin_node(ch) for ch in (cfg or []) if isinstance(ch, dict)]
    else:
        node["config"] = _sanitize(cfg or {})
    return node


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", default=DEFAULT_PATCH)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    if not os.path.isfile(args.patch):
        print("找不到 patch：" + args.patch, file=sys.stderr)
        return 2

    yaml = _load_yaml()
    if yaml is None:
        print("PyYAML 不可用：请先 `pip install pyyaml` 或确认 %TEMP%/pyyaml_lib", file=sys.stderr)
        return 3

    text = io.open(args.patch, encoding="utf-8").read()

    class L(yaml.SafeLoader):
        pass

    def _unknown(loader, suffix, node):
        return node.value

    L.add_multi_constructor("tag:yaml.org,2002:js", _unknown)
    L.add_multi_constructor("!", _unknown)
    data = yaml.load(text, Loader=L)

    skills_map = scan_skills(os.path.join(ROOT, "skills"))
    rows = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        inserts = entry.get("insert")
        if not isinstance(inserts, list):
            continue
        for pl in inserts:
            if not isinstance(pl, dict):
                continue
            if pl.get("name") != "@deepseek-ai/dsh-agent-preset":
                continue
            c = pl.get("config") or {}
            plugins = c.get("plugins") or []
            plugin_ids, skill_dirs, prefix, mcp = [], [], "", []
            tree = []
            for x in plugins:
                if not isinstance(x, dict):
                    continue
                pid = x.get("id")
                if pid:
                    plugin_ids.append(pid)
                cfg = x.get("config") or {}
                if pid == "persona":
                    prefix = cfg.get("prefix") or ""
                if pid in ("skill-filesystem", "skill"):
                    sd = cfg.get("skills") or cfg.get("skillDirs") or []
                    if isinstance(sd, list):
                        skill_dirs.extend([str(s) for s in sd])
                if pid and (pid.startswith("mcp-") or x.get("name") == "@deepseek-ai/dsh-mcp-client"):
                    mcp.append({
                        "id": pid,
                        "server_name": cfg.get("serverName") or "",
                        "transport": cfg.get("transport") or "",
                        "url": _default_url(cfg.get("url")),
                    })
                node = _plugin_node(x)
                if node:
                    tree.append(node)
            pid = c.get("id")
            rows.append({
                "id": pid,
                "name": c.get("name") or pid,
                "description": CN_DESC.get(pid, c.get("description") or ""),
                "order": c.get("order") or 99,
                "group": classify(pid, c.get("order") or 99),
                "plugins": plugin_ids,
                "mcp": mcp,
                "skill_dirs": skill_dirs,
                "skills": skills_map.get(pid, []),
                "prefix_len": len(prefix or ""),
                "persona_file": os.path.join("agents", (pid or "") + ".md"),
                "config_tree": tree,
            })

    rows.sort(key=lambda r: (r["order"], r["id"] or ""))

    # 被多个专家共有的技能，在面板上打「共享」标记
    skill_owners = {}
    for r in rows:
        for s in r["skills"]:
            skill_owners.setdefault(s["id"], 0)
            skill_owners[s["id"]] += 1
    for r in rows:
        for s in r["skills"]:
            if skill_owners[s["id"]] > 1:
                s["shared"] = True

    roster_ids = {r["id"] for r in rows}
    orphans = sorted(o for o in skills_map if o not in roster_ids)
    if orphans:
        print("警告：以下技能 owner 未匹配到名册专家：" + ", ".join(orphans), file=sys.stderr)

    roster = {
        "meta": {
            "generated_at": _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "patch_path": args.patch,
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

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with io.open(args.out, "w", encoding="utf-8") as f:
        json.dump(roster, f, ensure_ascii=False, indent=2)

    print("名册写入：%s（%d 个：lead=%d expert=%d fast=%d）" % (
        args.out, len(rows),
        roster["meta"]["groups"]["lead"],
        roster["meta"]["groups"]["expert"],
        roster["meta"]["groups"]["fast"],
    ))
    dup = [r["id"] for r in rows if [x["id"] for x in rows].count(r["id"]) > 1]
    if dup:
        print("警告：存在重复 id：" + ", ".join(sorted(set(dup))), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
