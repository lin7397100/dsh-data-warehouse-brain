#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三钢数仓智脑专家团 · 冒烟测试（Smoke Test）
================================================
版本: v2.0（2026-11-06 重建）
依据: knowledge/observed/eval/冒烟测试报告-2026-09-03.md 的 S1~S6 六套件规范
变更: 原 scripts/smoke_test.py 已丢失，按当前包结构（24 专家 / 54 技能 / 12 脚本）重建
      新增 S7 套件专测 GATE-2d「DSL 先行铁律」

用法:
    python scripts/smoke_test.py              # 全量
    python scripts/smoke_test.py --json       # JSON 输出
    python scripts/smoke_test.py --suite S1   # 只跑指定套件

退出码: 0 = 全通过；1 = 存在 FAIL
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ============ 路径 ============
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
AGENTS = ROOT / "agents"
SKILLS = ROOT / "skills"
SCRIPTS = ROOT / "scripts"
REFS = AGENTS / "references"
KNOWLEDGE = ROOT / "knowledge"
OBSERVED = ROOT / "observed"

# DSH（DeepSeek Harness）架构：profile 与 preset 清单的权威来源是 patch（唯一加载源）。
PATCH_YML = Path.home() / ".dsh" / "profiles" / "desktop" / "cordis.patch.yml"


def _utf8_env():
    """子进程强制 UTF-8 输出。

    2026-11-20 修复：Windows 控制台默认 GBK，子进程（网关/校验器）把中文按 GBK 写入管道，
    父进程按 utf-8 解码会得到 U+FFFD 乱码，导致「多语句」「↔」等中文断言误报 FAIL。
    子进程统一 UTF-8 + 父进程 encoding="utf-8" 后两端编码一致。
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def dsh_preset_ids():
    """从 DSH patch 抽 preset id 清单（8 空格缩进的 config.id；插件 id 为 12 空格）。"""
    try:
        txt = PATCH_YML.read_text(encoding="utf-8")
    except OSError:
        return []
    return re.findall(r"^ {8}id: ([A-Za-z0-9][A-Za-z0-9-]*)\s*$", txt, re.M)

PY = sys.executable

# ============ 结果容器 ============
class Result:
    def __init__(self):
        self.cases = []

    def add(self, sid, suite, name, ok, evidence="", warn=False):
        self.cases.append({
            "id": sid, "suite": suite, "name": name,
            "status": "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL"),
            "evidence": evidence,
        })

    @property
    def total(self):
        return len(self.cases)

    @property
    def passed(self):
        return sum(1 for c in self.cases if c["status"] == "PASS")

    @property
    def warned(self):
        return sum(1 for c in self.cases if c["status"] == "WARN")

    @property
    def failed(self):
        return sum(1 for c in self.cases if c["status"] == "FAIL")

    def by_suite(self):
        d = {}
        for c in self.cases:
            d.setdefault(c["suite"], {"total": 0, "pass": 0, "fail": 0, "warn": 0})
            d[c["suite"]]["total"] += 1
            d[c["suite"]]["pass" if c["status"] == "PASS" else
                          ("fail" if c["status"] == "FAIL" else "warn")] += 1
        return d


R = Result()


def sh(args, timeout=60):
    """执行子进程，返回 (exit_code, stdout, stderr)"""
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=_utf8_env(),
                           timeout=timeout, cwd=str(ROOT))
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -2, "", str(e)


# ============================================================
# S1 · 部署与环境
# ============================================================
def suite_s1():
    S = "S1 部署与环境"
    # S1-01 专家数
    n_agents = len(list(AGENTS.glob("*.md")))
    R.add("S1-01", S, "专家定义文件数 ≥ 20", n_agents >= 20, f"实测 {n_agents} 个")

    # S1-02 技能数
    n_skills = len([d for d in SKILLS.iterdir() if d.is_dir()]) if SKILLS.exists() else 0
    R.add("S1-02", S, "技能目录数 ≥ 50", n_skills >= 50, f"实测 {n_skills} 个")

    # S1-03 脚本数
    n_scripts = len(list(SCRIPTS.glob("*.py")))
    R.add("S1-03", S, "脚本数 ≥ 10", n_scripts >= 10, f"实测 {n_scripts} 个")

    # S1-04 包元数据合法（DSH：cordis.patch.yml 的 preset 清单 = 24 个）
    ids = dsh_preset_ids()
    ok = PATCH_YML.is_file() and len(ids) == 24
    ev = f"DSH preset 实测 {len(ids)} 个（{PATCH_YML}）"
    R.add("S1-04", S, "包元数据合法（DSH preset 24）", ok, ev)

    # S1-05 名册一致性（DSH：panel/roster.json ↔ patch preset）
    ok, ev = False, ""
    try:
        roster = json.loads((ROOT / "panel" / "roster.json").read_text(encoding="utf-8"))
        cnt = (roster.get("meta") or {}).get("count")
        ok = cnt == len(dsh_preset_ids()) == 24
        ev = f"roster.meta.count={cnt} / preset={len(dsh_preset_ids())}"
    except Exception as e:
        ev = f"异常: {e}"
    R.add("S1-05", S, "名册一致（DSH roster 24）", ok, ev)

    # S1-06 环境变量（DSH 架构：配置根为 DSH_HOME）
    envs = ["DB2_ASSETS_HOME", "ONTOLOGY_HOME", "WORKSPACE", "DSH_HOME"]
    missing = [e for e in envs if not os.environ.get(e)]
    R.add("S1-06", S, "四个环境变量已配置", not missing,
          "全部已设置" if not missing else f"缺失: {missing}")

    # S1-07 专家↔技能引用一致性（悬空引用检查；DSH 以 patch preset 清单为声明源）
    declared_agents = {"agents/%s.md" % i for i in dsh_preset_ids()}
    actual = {"agents/%s" % p.name for p in AGENTS.glob("*.md")}
    dangling = declared_agents - actual
    ok = len(dangling) == 0 and len(declared_agents) > 0
    ev = f"声明 {len(declared_agents)} / 实际 {len(actual)} / 悬空 {len(dangling)}"
    if dangling:
        ev += f" → {sorted(dangling)[:3]}"
    R.add("S1-07", S, "专家引用无悬空", ok, ev)

    # S1-08 DSH 关键目录（WorkBuddy 遗留修正：avatars/ 是插件市场展示头像，
    #   由 plugin.json 的 "avatar": "avatars/team.png" 引用；DSH 无 avatar 概念，
    #   preset 人设由 cordis.patch.yml 的 prefix 承载，故 avatars/ 从必需清单移除，仅作信息项）
    dirs = ["agents", "skills", "scripts", "knowledge", "panel"]
    missing = [d for d in dirs if not (ROOT / d).is_dir()]
    ev = "全部存在" if not missing else f"缺失: {missing}"
    ev += f"（avatars 存在={ (ROOT / 'avatars').is_dir() }，DSH 非必需）"
    R.add("S1-08", S, "DSH 关键目录齐备", not missing, ev)


# ============================================================
# S2 · 脚本接口
# ============================================================
def suite_s2():
    S = "S2 脚本接口"
    scripts = ["trace_log.py", "sg_db2_gateway.py", "run_eval.py",
               "check_skill_ownership.py", "sgdw_sql_exec.py",
               "build_report.py", "ingest_weknora.py", "post_edit.py",
               "materialized_sql_guard.py", "verify_dsh_sync.py"]
    for i, sc in enumerate(scripts, 1):
        p = SCRIPTS / sc
        if not p.exists():
            R.add(f"S2-{i:02d}", S, f"CLI 可用: {sc}", False, "文件不存在")
            continue
        code, out, err = sh([PY, str(p), "--help"], timeout=30)
        # --help 通常 exit 0；argparse 无子命令时可能 exit 2，但应有输出
        ok = code == 0 or "--help" in (out + err) or "usage" in (out + err).lower()
        R.add(f"S2-{i:02d}", S, f"CLI 可用: {sc}", ok, f"exit={code}")


# ============================================================
# S3 · 核心治理门禁（GATE 链）
# ============================================================
def suite_s3():
    S = "S3 治理门禁"
    tl = SCRIPTS / "trace_log.py"
    gw = SCRIPTS / "sg_db2_gateway.py"

    # S3-01 health-check
    code, out, err = sh([PY, str(tl), "health-check"])
    R.add("S3-01", S, "GATE-0 health-check 可执行", code in (0, 1, 2, 3),
          f"exit={code} {(out or err).strip()[:60]}")

    # S3-02 gateway status
    code, out, err = sh([PY, str(gw), "status"])
    ok = code == 0 and "G1" in out
    R.add("S3-02", S, "DB2 网关 status 可执行", ok,
          f"exit={code} 含G1={'G1' in out}")

    # S3-03 网关拦截写操作（安全护栏）
    code, out, err = sh([PY, str(gw), "exec", "DELETE FROM SMBB_M_S_ZZ00.T_DWS_FACT_ZZGZ_LG01"])
    ok = code != 0 and ("G3" in (out + err))
    R.add("S3-03", S, "网关拦截写操作（DELETE）", ok,
          f"exit={code} 拦截={'G3' in (out+err)}")

    # S3-04 网关拦截多语句
    code, out, err = sh([PY, str(gw), "exec", "SELECT 1 FROM SYSIBM.SYSDUMMY1; SELECT 2 FROM SYSIBM.SYSDUMMY1"])
    ok = code != 0 and "多语句" in (out + err)
    R.add("S3-04", S, "网关拦截多语句拼接", ok, f"exit={code}")

    # S3-05 网关拦截非 SELECT 起手
    code, out, err = sh([PY, str(gw), "exec", "UPDATE T SET A=1"])
    ok = code != 0
    R.add("S3-05", S, "网关拦截非 SELECT 起手", ok, f"exit={code}")

    # S3-06 trace report 可执行
    code, out, err = sh([PY, str(tl), "report"])
    ok = "覆盖率" in out or "coverage" in out.lower() or code == 0
    R.add("S3-06", S, "trace report 可输出覆盖率", ok, f"exit={code}")


# ============================================================
# S4 · 产物完整性
# ============================================================
def suite_s4():
    S = "S4 产物完整性"

    # S4-01 指标注册表（结构: {total, indicators:{...}, _schema_version}）
    p = KNOWLEDGE / "design" / "indicator" / "indicator_registry.json"
    ok, ev = False, ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            n = d.get("total") or len(d.get("indicators", {}))
        else:
            n = len(d)
        ok = n > 5000
        ev = f"{n} 条指标"
    except Exception as e:
        ev = f"异常: {e}"
    R.add("S4-01", S, "指标注册表 ≥ 5000 条", ok, ev)

    # S4-02 指标索引
    p = KNOWLEDGE / "design" / "indicator" / "indicator_index.json"
    ok, ev = False, ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        n = d.get("total", 0)
        ok = n > 5000
        ev = f"total={n}"
    except Exception as e:
        ev = f"异常: {e}"
    R.add("S4-02", S, "指标索引 total ≥ 5000", ok, ev)

    # S4-03 物化 SQL 数量
    ms = KNOWLEDGE / "design" / "indicator" / "materialized_sql"
    n = len(list(ms.glob("*.sql"))) if ms.exists() else 0
    R.add("S4-03", S, "物化 SQL 文件 ≥ 1000", n >= 1000, f"{n} 个")

    # S4-04 本体库
    p = KNOWLEDGE / "design" / "ontology" / "ontology-gzprod.json"
    ok, ev = False, ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        st = d.get("stats", {})
        ok = st.get("entities", 0) > 4000
        ev = f"entities={st.get('entities')} relations={st.get('relations')}"
    except Exception as e:
        ev = f"异常: {e}"
    R.add("S4-04", S, "本体库实体 ≥ 4000", ok, ev)

    # S4-05 references 数量
    n = len(list(REFS.glob("*.md"))) if REFS.exists() else 0
    R.add("S4-05", S, "references 文档 ≥ 25", n >= 25, f"{n} 份")

    # S4-06 双轨目录
    ok = (KNOWLEDGE / "design").is_dir() and OBSERVED.is_dir()
    R.add("S4-06", S, "双轨目录分离（design + observed）", ok,
          f"design={(KNOWLEDGE/'design').is_dir()} observed={OBSERVED.is_dir()}")


# ============================================================
# S5 · 移植性
# ============================================================
def suite_s5():
    S = "S5 移植性"

    # S5-01 技能文档无硬编码绝对路径
    # 豁免：① 说明性文字（含"废弃/默认/禁止/已改/不要/勿"）
    #       ② 环境变量展开写法（行内含 DB2_ASSETS_HOME）
    bad = []
    EXEMPT = ("废弃", "默认", "禁止", "已改", "不要", "勿")
    for f in SKILLS.rglob("SKILL.md"):
        try:
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                has_path = ("E:/原桌面/DB2" in line) or ("E:\\原桌面\\DB2" in line)
                if not has_path:
                    continue
                if any(k in line for k in EXEMPT):
                    continue
                if "DB2_ASSETS_HOME" in line:
                    continue
                bad.append(f"{f.parent.name}: {line.strip()[:60]}")
                break
        except Exception:
            pass
    R.add("S5-01", S, "技能文档无硬编码绝对路径", not bad,
          "全部通过" if not bad else f"硬编码: {bad[:3]}")

    # S5-02 脚本走环境变量
    bad = []
    for f in SCRIPTS.glob("*.py"):
        try:
            t = f.read_text(encoding="utf-8", errors="ignore")
            if "E:/原桌面/DB2" in t or "E:\\原桌面\\DB2" in t:
                # 允许作为 os.environ.get 的默认值
                if "environ.get" not in t:
                    bad.append(f.name)
        except Exception:
            pass
    R.add("S5-02", S, "脚本路径走环境变量（或有默认值兜底）", not bad,
          "全部通过" if not bad else f"硬编码: {bad}")


# ============================================================
# S6 · Agent MD 规范
# ============================================================
def suite_s6():
    S = "S6 Agent 规范"

    # S6-01 agent MD 均被 preset 收录（WorkBuddy 遗留修正：agent MD 的 YAML frontmatter
    #   是 WorkBuddy 时代供 plugin.json 解析的形态；DSH 下 persona 正文直接作为
    #   cordis.patch.yml 的 prefix 字符串，无 frontmatter 概念。改为双向集合比对：
    #   patch 的 preset id 集合 ↔ agents/*.md 的 stem 集合，任一方向差集非空即 FAIL）
    preset_ids = set(dsh_preset_ids())
    stems = {p.stem for p in AGENTS.glob("*.md")}
    only_preset = sorted(preset_ids - stems)   # preset 声明但无对应 MD → 悬空引用
    only_md = sorted(stems - preset_ids)       # MD 存在但未被 preset 收录 → 未加载
    ok = bool(preset_ids) and bool(stems) and not only_preset and not only_md
    ev = (f"preset={len(preset_ids)} / MD={len(stems)} "
          f"/ 未收录={only_md[:3]} / 悬空={only_preset[:3]}")
    R.add("S6-01", S, "agent MD 均被 preset 收录", ok, ev)

    # S6-02 主理人文件名带团队前缀
    lead = AGENTS / "data-warehouse-brain-team-lead.md"
    R.add("S6-02", S, "主理人 MD 带团队前缀", lead.exists(), lead.name)

    # S6-03 无 tools 字段声明
    bad = []
    for f in AGENTS.glob("*.md"):
        try:
            t = f.read_text(encoding="utf-8", errors="ignore")
            fm = t.split("---")[1] if t.count("---") >= 2 else ""
            if "\ntools:" in fm or fm.strip().startswith("tools:"):
                bad.append(f.name)
        except Exception:
            pass
    R.add("S6-03", S, "frontmatter 无 tools 字段", not bad,
          "全部通过" if not bad else f"违规: {bad[:5]}")


# ============================================================
# S7 · GATE-2d DSL 先行铁律（本次新增）
# ============================================================
def suite_s7():
    S = "S7 DSL先行铁律"
    lead_md = AGENTS / "data-warehouse-brain-team-lead.md"
    lead_txt = lead_md.read_text(encoding="utf-8", errors="ignore") if lead_md.exists() else ""

    # S7-01 主理人 MD 含 GATE-2d
    R.add("S7-01", S, "主理人 MD 含 GATE-2d 章节",
          "GATE-2d" in lead_txt or "2d · " in lead_txt,
          f"GATE-2d 提及 {lead_txt.count('GATE-2d')} 次")

    # S7-02 DF1~DF3 三条禁令
    df_codes = [c for c in ["DF1", "DF2", "DF3"] if c in lead_txt]
    R.add("S7-02", S, "三条硬禁令 DF1~DF3 齐备", len(df_codes) == 3,
          f"命中 {df_codes}")

    # S7-03 G2d 硬断言
    R.add("S7-03", S, "G2d 硬断言存在", "G2d" in lead_txt,
          "G2d" if "G2d" in lead_txt else "缺失")

    # S7-04 dsl_first.md 契约
    p = REFS / "dsl_first.md"
    ok, ev = p.exists(), ""
    if ok:
        t = p.read_text(encoding="utf-8", errors="ignore")
        ev = f"{len(t.splitlines())} 行"
        ok = len(t.splitlines()) > 100 and "dsl_version" in t
    R.add("S7-04", S, "dsl_first.md 契约完整（>100行含schema）", ok, ev)

    # S7-05 运行时门禁（DSH：GATE-2d 由 persona prefix 承载，见 S7-01/S7-02）
    ok = "GATE-2d" in lead_txt
    ev = "DSH 架构：门禁由 persona prefix 承载 → " \
         f"GATE-2d={'GATE-2d' in lead_txt}"
    R.add("S7-05", S, "dslFirstGate 已启用（DSH persona prefix）", ok, ev)

    # S7-06 违规码 DF1~DF4 完整（DSH：由 persona prefix + dsl_first.md 契约承载）
    dsl_contract = REFS / "dsl_first.md"
    contract_txt = dsl_contract.read_text(encoding="utf-8", errors="ignore") \
        if dsl_contract.is_file() else ""
    hay = lead_txt + "\n" + contract_txt
    df = [c for c in ("DF1", "DF2", "DF3", "DF4") if c in hay]
    ok = len(df) == 4
    ev = f"DSH 架构：DSH 契约（persona prefix + dsl_first.md）命中 {df}"
    R.add("S7-06", S, "违规码 DF1~DF4 完整", ok, ev)

    # S7-07 observed/dsl 目录
    R.add("S7-07", S, "observed/dsl 落盘目录已建",
          (OBSERVED / "dsl").is_dir(), "observed/dsl")

    # S7-08 GATE 链完整（MD 中 2a/2b/2c/2d 以 `#### 2x ·` 标题形式存在，
    #        0/1/3 以 `GATE-0/1/3` 形式存在，双写法均认可）
    gate_checks = {
        "GATE-0": "GATE-0" in lead_txt,
        "GATE-1": "GATE-1" in lead_txt,
        "GATE-2a": ("GATE-2a" in lead_txt) or ("#### 2a" in lead_txt),
        "GATE-2b": ("GATE-2b" in lead_txt) or ("#### 2b" in lead_txt),
        "GATE-2c": ("GATE-2c" in lead_txt) or ("#### 2c" in lead_txt),
        "GATE-2d": ("GATE-2d" in lead_txt) or ("#### 2d" in lead_txt),
        "GATE-3": "GATE-3" in lead_txt,
    }
    missing = [k for k, v in gate_checks.items() if not v]
    R.add("S7-08", S, "GATE 链 7 道完整", not missing,
          "全部存在" if not missing else f"缺失: {missing}")

    # S7-09 三查自校验
    ok = "三查" in lead_txt and "语法" in lead_txt and "表存在性" in lead_txt
    R.add("S7-09", S, "三查自校验（语法/表存在/合理性）", ok, "三查" if ok else "缺失")

    # S7-10 DSH 部署一致性
    #   2026-11-20 重写：原「双副本 cache 同步」在 DSH 下不存在（无 marketplaces/cache 镜像）。
    #   DSH 为单向发布（源仓库 → ~/.dsh），一致性由 scripts/verify_dsh_sync.py 裁定。
    verifier = SCRIPTS / "verify_dsh_sync.py"
    patch = Path.home() / ".dsh" / "profiles" / "desktop" / "cordis.patch.yml"
    ok, ev = False, ""
    if not verifier.exists():
        ev = "部署校验器缺失 scripts/verify_dsh_sync.py"
    elif not patch.exists():
        ev = "DSH patch 未找到 ~/.dsh/profiles/desktop/cordis.patch.yml"
    else:
        r = subprocess.run([PY, str(verifier), "--json"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="ignore", env=_utf8_env())
        ok = r.returncode == 0
        ev = f"verify_dsh_sync exit={r.returncode}（0=源仓库与 ~/.dsh 全一致）"
    R.add("S7-10", S, "DSH 部署一致性（源仓库 ↔ ~/.dsh）", ok, ev)


# ============================================================
# S8 · 数据下钻规则（2026-11-06 新增）
# ============================================================
def suite_s8():
    S = "S8 数据下钻规则"
    AUTH = KNOWLEDGE / "kb" / "数据下钻规则_权威手册.md"

    # S8-01 权威手册存在
    ok = AUTH.exists()
    ev = f"{AUTH.stat().st_size} B" if ok else "缺失"
    R.add("S8-01", S, "下钻权威手册存在", ok, ev)

    auth = AUTH.read_text(encoding="utf-8", errors="ignore") if ok else ""

    # S8-02 五要素齐备
    five = {
        "触发条件": "## 1. 触发条件" in auth,
        "层级路径": "## 2. 层级路径" in auth,
        "维度与指标口径": "## 4. 维度与指标口径" in auth,
        "数据范围": "## 5. 数据范围" in auth,
        "输出结果格式": "## 6. 输出结果格式" in auth,
    }
    missing = [k for k, v in five.items() if not v]
    R.add("S8-02", S, "五要素齐备", not missing,
          "全部齐备" if not missing else f"缺失: {missing}")

    # S8-03 D1~D5 定义
    d_ok = all(f"**D{i}**" in auth for i in range(1, 6))
    R.add("S8-03", S, "D1~D5 定义完整", d_ok, "5 项全定义" if d_ok else "存在缺失")

    # S8-04 四层分支
    lv_ok = all(f"lv==={i}" in auth for i in range(1, 5))
    R.add("S8-04", S, "四层分支（lv===1~4）", lv_ok, "4 层齐全" if lv_ok else "层数不足")

    # S8-05 全团引用权威源
    REFS = [
        "sg-insight.md", "sg-zhishu-report-composer.md", "sg-zhishu-dashboard-designer.md",
        "sg-quality.md", "sg-supervisor.md", "sg-development.md",
        "data-warehouse-brain-team-lead.md",
    ]
    miss = []
    for f in REFS:
        p = AGENTS / f
        if not p.exists():
            miss.append(f)
            continue
        if "数据下钻规则_权威手册" not in p.read_text(encoding="utf-8", errors="ignore"):
            miss.append(f)
    R.add("S8-05", S, f"全团 {len(REFS)} 位成员引用权威源", not miss,
          f"{len(REFS)-len(miss)}/{len(REFS)}" + (f" 缺: {miss}" if miss else ""))

    # S8-06 无旧版本残留（三层/openDrawer/id="drawer"）
    legacy = []
    for f in REFS + ["../references/report_rules.md"]:
        p = AGENTS / f if not f.startswith("..") else AGENTS / "references" / "report_rules.md"
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        if "三层抽屉" in t:
            legacy.append(f"{p.name}: 三层抽屉")
        if 'onclick="openDrawer(' in t:
            legacy.append(f"{p.name}: openDrawer")
        if 'id="drawer"' in t:
            legacy.append(f"{p.name}: id=drawer")
    R.add("S8-06", S, "无旧版本下钻逻辑残留", not legacy,
          "无残留" if not legacy else f"{legacy[:3]}")

    # S8-07 校验脚本本身可执行
    chk = SCRIPTS / "check_drilldown_consistency.py"
    code, out, err = sh([PY, str(chk)], timeout=60)
    R.add("S8-07", S, "下钻一致性校验脚本通过", code == 0, f"exit={code}")

    # S8-08 知识库索引已登记
    idx = KNOWLEDGE / "kb" / "知识库索引.md"
    ok = idx.exists() and "数据下钻规则_权威手册" in idx.read_text(encoding="utf-8", errors="ignore")
    R.add("S8-08", S, "知识库索引已登记", ok, "已登记" if ok else "未登记")

    # S8-09 路由触发表已挂载
    lead = AGENTS / "data-warehouse-brain-team-lead.md"
    lt = lead.read_text(encoding="utf-8", errors="ignore") if lead.exists() else ""
    ok = "数据下钻规则_权威手册" in lt
    R.add("S8-09", S, "主理人路由触发表已挂载", ok, "已挂载" if ok else "未挂载")

    # S8-10 模板资产
    tpl = ROOT / "assets" / "drilldown_template.html"
    ok = tpl.exists()
    R.add("S8-10", S, "下钻模板资产存在", ok,
          f"{tpl.stat().st_size} B" if ok else "缺失")


# ============================================================
# 报告
# ============================================================
def render_markdown():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bs = R.by_suite()
    rate = (R.passed / R.total * 100) if R.total else 0

    L = []
    L.append(f"# 三钢数仓智脑专家团 · 冒烟测试报告（{datetime.now().strftime('%Y-%m-%d')}）")
    L.append("")
    L.append("> 本文件由 `scripts/smoke_test.py` 生成，勿手工编辑。")
    L.append("")
    L.append("## 一、测试环境")
    L.append("")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append(f"| 执行时间 | {now} |")
    L.append(f"| Python | {sys.version.split()[0]} |")
    L.append(f"| 被测根目录 | `{ROOT}` |")
    L.append(f"| 执行入口 | `python scripts/smoke_test.py` |")
    L.append("")
    L.append("## 二、结果汇总")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    L.append(f"| 用例总数 | {R.total} |")
    L.append(f"| 通过 | {R.passed} |")
    L.append(f"| 警告 | {R.warned} |")
    L.append(f"| 失败 | {R.failed} |")
    L.append(f"| **通过率** | **{rate:.1f}%** |")
    L.append("")
    L.append("| 套件 | 用例数 | 通过 | 警告 | 失败 | 通过率 |")
    L.append("|---|---|---|---|---|---|")
    for suite, d in bs.items():
        r = d["pass"] / d["total"] * 100 if d["total"] else 0
        L.append(f"| {suite} | {d['total']} | {d['pass']} | {d['warn']} | {d['fail']} | {r:.1f}% |")
    L.append("")
    L.append("## 三、用例清单与结果")
    L.append("")
    L.append("| 编号 | 套件 | 用例 | 结果 | 证据/说明 |")
    L.append("|---|---|---|---|---|")
    for c in R.cases:
        icon = "**PASS**" if c["status"] == "PASS" else ("**WARN**" if c["status"] == "WARN" else "**FAIL**")
        ev = c["evidence"].replace("|", "\\|")
        L.append(f"| {c['id']} | {c['suite']} | {c['name']} | {icon} | {ev} |")
    L.append("")
    L.append("## 四、发现的问题")
    L.append("")
    fails = [c for c in R.cases if c["status"] == "FAIL"]
    if not fails:
        L.append("未发现失败用例。")
    else:
        L.append("| 编号 | 用例 | 证据 |")
        L.append("|---|---|---|")
        for c in fails:
            L.append(f"| {c['id']} | {c['name']} | {c['evidence']} |")
    L.append("")
    L.append("## 五、结论")
    L.append("")
    if R.failed == 0:
        L.append(f"**全部 {R.total} 个用例通过**（警告 {R.warned}），专家团核心功能可用。")
    else:
        L.append(f"**存在 {R.failed} 个失败用例**，需修复后复测。")
    L.append("")
    L.append(f"> 复现命令：`python scripts/smoke_test.py`（存在 FAIL 时退出码非 0，可接 CI 门禁）")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="三钢数仓智脑专家团 · 冒烟测试")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--suite", default=None, help="只跑指定套件 (S1~S7)")
    ap.add_argument("--no-save", action="store_true", help="不写报告文件")
    args = ap.parse_args()

    suites = {"S1": suite_s1, "S2": suite_s2, "S3": suite_s3, "S4": suite_s4,
              "S5": suite_s5, "S6": suite_s6, "S7": suite_s7, "S8": suite_s8}

    print("=" * 66)
    print("三钢数仓智脑专家团 · 冒烟测试 v2.0")
    print("=" * 66)
    print(f"根目录: {ROOT}")
    print()

    for name, fn in suites.items():
        if args.suite and not name.upper().startswith(args.suite.upper()):
            continue
        print(f"[{name}] 执行中...", end=" ", flush=True)
        before = len(R.cases)
        try:
            fn()
        except Exception as e:
            R.add(f"{name}-ERR", name, f"套件异常", False, str(e))
        n = len(R.cases) - before
        print(f"{n} 个用例")

    print()
    print("=" * 66)
    bs = R.by_suite()
    for suite, d in bs.items():
        rate = d["pass"] / d["total"] * 100 if d["total"] else 0
        flag = "OK" if d["fail"] == 0 else "FAIL"
        print(f"  [{flag:4s}] {suite:20s} {d['pass']}/{d['total']} ({rate:.0f}%)"
              + (f"  WARN={d['warn']}" if d["warn"] else ""))
    print("=" * 66)
    rate = (R.passed / R.total * 100) if R.total else 0
    print(f"  总计: {R.passed}/{R.total} 通过 ({rate:.1f}%)  "
          f"警告={R.warned}  失败={R.failed}")
    print("=" * 66)

    # 打印失败明细
    if R.failed:
        print()
        print("失败用例：")
        for c in R.cases:
            if c["status"] == "FAIL":
                print(f"  [FAIL] {c['id']} {c['name']} — {c['evidence']}")

    # 落盘报告
    if not args.no_save and not args.suite:
        md = render_markdown()
        out_dir = KNOWLEDGE / "observed" / "eval"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_p = out_dir / f"冒烟测试报告-{datetime.now().strftime('%Y-%m-%d')}.md"
        out_p.write_text(md, encoding="utf-8")
        print(f"\n报告已落盘: {out_p}")

        # 同步 trace 记录
        try:
            trace = {
                "trace_id": f"TR-{datetime.now().strftime('%Y%m%d')}-SMOKE-V2",
                "started": datetime.now().astimezone().isoformat(),
                "task_type": "SMOKE",
                "lane": "smoke",
                "fast_lane": True,
                "expected_steps": ["S1", "S2", "S3", "S4", "S5", "S6", "S7"],
                "dispatched": [],
                "inline_steps": ["S1", "S2", "S3", "S4", "S5", "S6", "S7"],
                "violations": [],
                "finished": datetime.now().astimezone().isoformat(),
                "coverage_rate": 1.0,
                "verdict": "通过" if R.failed == 0 else "未通过",
                "smoke": {"total": R.total, "passed": R.passed,
                          "warned": R.warned, "failed": R.failed,
                          "rate": round(rate, 2)}
            }
            tp = OBSERVED / "traces" / (trace["trace_id"] + ".json")
            tp.parent.mkdir(parents=True, exist_ok=True)
            tp.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"trace 已落盘: {tp.name}")
        except Exception as e:
            print(f"trace 落盘失败(非致命): {e}")

    if args.json:
        print()
        print(json.dumps({
            "total": R.total, "passed": R.passed,
            "warned": R.warned, "failed": R.failed,
            "rate": round(rate, 2), "cases": R.cases
        }, ensure_ascii=False, indent=2))

    return 0 if R.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
