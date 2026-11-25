#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enable_jev.py —— 给专家团组合层打「jev 判定闸」补丁（幂等，可反复运行）
================================================================================

两处纯文本插入（不改任何既有 preset 的其它内容）：

  ① 主理人（冶衡）persona：在 v1.4 快车道条款之后，追加「v1.5 jev 判定闸」——
     说明何时问 4B 小模型、三个脚本怎么调、以及**七条不可逾越的红线**。
  ② 快问（dwb-fast-ask）persona：追加「第 1.5 步 jev 判定闸」——
     口语长句可先经 jev_router 降级；候选歧义时用 jev_pick 定案或弃权。

依据（均为 2026-11-18 本机实测，不是推测）：
  · 规则闸对 26 字口语「麻烦你帮我确认一下…实际产出到底多少」判 full；
    jev 判「单指标取数」 conf 0.966 → 降级 fast（省一条 82 min 的慢链）。
  · 「6#高炉矿耗突然掉下来了」规则漏判（无"为什么/异常"词），jev 判「归因诊断」 conf 0.987 → 改路由 T2b。
  · 问「高炉矿耗」未指定炉号时，jev 会以 conf 0.928 自信地选「1#高炉矿耗」——
    **阈值挡不住**，因此写死"未指定编号→必须请用户点名"。
  · 指标级别 atomic/derived 预分类实测 40%（30 条真值）→ 明令禁用。
  · 业务域预分类实测 80%（20 条真值）→ 只作建议，必须披露。

安全性：幂等（先剥旧块再写）、可回滚（--revert）、不猜 schema（只做文本插入 + PyYAML 校验）。

用法：
  python tools/enable_jev.py --file cordis.patch.yml [--pylibs <pylibs目录>]
  python tools/enable_jev.py --file cordis.patch.yml --check
  python tools/enable_jev.py --file cordis.patch.yml --revert

退出码：0 成功；1 校验失败；2 结构异常（锚点/重复）。
"""

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

LEAD_ANCHOR = "            3. 快车道交付必须带：`zb_code` + 执行 SQL 文件名 + `maturity` 三档 + 数据限制。"
FAST_ANCHOR = "            - 目标 ≤30 s；超 5 min 必复述已得结果 + 未完成项（L0 硬超时熔断）。"

END_MARK = "            <!-- <<< DWB-JEV v1 <<< -->"
LEAD_BEGIN = "            **⏩ v1.6 jev 判定闸（2026-11-18 · 小模型语义判定，只做「建议位」）**"
FAST_BEGIN = "            ## jev 判定闸（第 1.5 步 · v1.6，建议位）"

LEAD_BLOCK = LEAD_BEGIN + """

            本机 jev：`http://10.233.2.32:11434/v1/systemone`，模型 `tev1:4b-32k`（4.3B / decision 能力；单问 0.7–1.4 s；返回 choice·score·noul + 概率 + confidence）。可用环境变量 `JEV_URL` / `JEV_MODEL` 覆盖。

            | 什么时候用 | 命令 | 采纳门槛 |
            |---|---|---|
            | 规则判 full、但疑似只是「啰嗦的单指标」 | `python {{TEAM_ROOT}}/tools/jev_router.py --text "<原话>" --format text` | conf ≥ 0.85 |
            | `fast_ask.py` 返回 `ambiguous` / `needs_slow_lane` 且候选 ≥2 | `python {{TEAM_ROOT}}/tools/jev_pick.py --text "<原话>" --from-fastask <fastask 输出文件>` | conf ≥ 0.90 **且** top1−top2 ≥ 0.50 |
            | 治数工单/故障进流程前定优先级 | `python {{TEAM_ROOT}}/tools/jev_query.py --preset urgency --state "<原文>" --text` | P(急) ≥ 0.80 |
            | 质量归类（五维：完整性/唯一性/有效性/一致性/及时性） | `python {{TEAM_ROOT}}/tools/jev_query.py --preset quality --state "<原文>" --text` | conf ≥ 0.60 · **仅建议位** |
            | 根因归类（五类：口径歧义/数据延迟/计算缺陷/源数据错误/参数错误） | `python {{TEAM_ROOT}}/tools/jev_query.py --preset rootcause --state "<原文>" --text` | conf ≥ 0.70 · **仅建议位** |

            **七条不可逾越（违反任一条都等同于编造）**：
            1. **含 HEAVY 词的请求，jev 无权降级**（对标 / 本周 / 各工序 / 各基地 / 报告 / 汇总 / 分析…）。脚本已内建，禁止绕过。
            2. 网络不可达（脚本 exit=4）→ **退回规则结论**，禁止凭印象判型。
            3. 问题没指定编号而候选全带编号（1#/2#/5#…）→ **必须请用户点名**，不得替用户挑一个炉子。
            4. 编号不存在（如 9#）→ 直接弃权，**不得改答别的编号**。
            5. 指标级别 atomic/derived 预分类**禁用**：实测 30 条真值仅 40% 准确。
            6. 业务域预分类只作建议：实测 20 条真值 80%，**必须披露「jev 建议，需人工复核」，不得直接写入注册表**。
            7. jev 只判定、不出数：取数仍然只走 `fast_ask.py` → 物化 SQL → `mcp__db2__execute_sql`。
            8. **quality / rootcause 只进报告不上闸**：定义集实测 95%（conf≥0.60 覆盖 95% 且该段 100% 正确），但**双解工单的过信率 60%（quality）/ 100%（rootcause）**——所以必须把 top2 与概率一并列出并标「jev 建议，需人工确认」，**不得据此关闭工单、不得写回注册表、不得单独充当根因结论**。

            自测与复评（改动判定口径后必须重跑）：
            `python {{TEAM_ROOT}}/tools/jev_eval.py --task quality` / `--task rootcause`（评测集在 `{{TEAM_ROOT}}/docs/jev-eval/`）。

            派发专家时若需要语义判定，在 subtask 里写明上面的命令与门槛（专家侧同一套阈值）。
""" + END_MARK + "\n"

FAST_BLOCK = FAST_BEGIN + """

            仅当 `route_intent.py` 判 `lane=full`、而你判断「啰嗦但本质是一个单指标」时才走这一步：

            ```
            python {{TEAM_ROOT}}/tools/jev_router.py --text "<原话>" --format text
            ```
            → 只有输出 `lane=fast` 且 `source=jev`、`conf≥0.85` 才允许继续 `fast_ask.py`；否则按原规则停。

            `fast_ask.py` 返回 `ambiguous=true` 或 `mode=needs_slow_lane`、且候选 ≥2 时：

            ```
            python {{TEAM_ROOT}}/tools/jev_pick.py --text "<原话>" --from-fastask <fastask 输出 json 路径>
            ```
            → exit=0 且 `adopted=true` 才按返回的 `zb_code` 继续；`has_sql=false` 时停（转物化/临时口径流程）。
            → exit=3（弃权）**必须把候选抛给用户点名**，禁止自己选一个。
            → jev 不可达（exit=4）→ 按原规则停，禁止编造。
""" + END_MARK + "\n"


def load_yaml(path, pylibs):
    try:
        if pylibs:
            sys.path.insert(0, pylibs)
        import yaml  # noqa
    except Exception as e:
        return None, "PyYAML 不可用（请用 --pylibs 指向内置 pylibs）：%s" % e
    text = io.open(path, encoding="utf-8").read()

    class L(yaml.SafeLoader):
        pass

    L.add_multi_constructor("tag:yaml.org,2002:js", lambda loader, suffix, node: node.value)
    L.add_multi_constructor("!", lambda loader, suffix, node: node.value)
    return yaml.load(text, Loader=L), None


def count_presets(data):
    ids = []
    for entry in data or []:
        if isinstance(entry, dict) and isinstance(entry.get("insert"), list):
            for pl in entry["insert"]:
                if (pl or {}).get("name") == "@deepseek-ai/dsh-agent-preset":
                    ids.append(((pl or {}).get("config") or {}).get("id"))
    return ids


def strip_blocks(text):
    for begin in (LEAD_BEGIN, FAST_BEGIN):
        pat = re.compile(r"(?ms)^" + re.escape(begin) + r".*?^" + re.escape(END_MARK) + r"\r?\n")
        text = pat.sub("", text)
    return text


def check(path, pylibs):
    data, err = load_yaml(path, pylibs)
    if err:
        return 1, err
    text = io.open(path, encoding="utf-8").read()
    ids = count_presets(data)
    dup = [p for p in set(ids) if ids.count(p) > 1]
    lead_n = text.count(LEAD_BEGIN)
    fast_n = text.count(FAST_BEGIN)
    end_n = text.count(END_MARK)
    issues = []
    if len(ids) != 24:
        issues.append("preset 数=%d（应为 24）" % len(ids))
    if dup:
        issues.append("重复 preset：%s" % dup)
    if lead_n != 1:
        issues.append("主理人 jev 块出现 %d 次（应为 1）" % lead_n)
    if fast_n != 1:
        issues.append("快问 jev 块出现 %d 次（应为 1）" % fast_n)
    if end_n != 2:
        issues.append("END 标记出现 %d 次（应为 2）" % end_n)
    for f in ("jev_query.py", "jev_router.py", "jev_pick.py", "jev_eval.py"):
        if not os.path.exists(os.path.join(HERE, f)):
            issues.append("缺 %s" % f)
    msg = ("preset=%d ｜ 主理人块=%d ｜ 快问块=%d ｜ END=%d ｜ 重复=%s ｜ 问题=%s"
           % (len(ids), lead_n, fast_n, end_n, dup or "无", "；".join(issues) if issues else "无"))
    return (0 if not issues else 1), msg


def insert_after(text, anchor, block, eol):
    lines = text.split(eol)
    idx = [i for i, l in enumerate(lines) if l.strip() == anchor.strip()]
    if len(idx) != 1:
        return None, "锚点出现 %d 次（应为 1）：%s" % (len(idx), anchor.strip()[:30])
    i = idx[0]
    ins = [""] + [l.replace("\n", "") for l in block.rstrip("\n").split("\n")]
    lines[i + 1:i + 1] = ins
    return eol.join(lines), None


def main():
    ap = argparse.ArgumentParser(description="给专家团组合层打「jev 判定闸」补丁（幂等）")
    ap.add_argument("--file", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--pylibs", default="")
    args = ap.parse_args()
    path = os.path.abspath(args.file)
    if not os.path.exists(path):
        print("文件不存在：%s" % path)
        return 2

    if args.check:
        code, msg = check(path, args.pylibs)
        print(msg)
        return code

    raw = io.open(path, encoding="utf-8").read()
    eol = "\r\n" if "\r\n" in raw else "\n"
    stripped = strip_blocks(raw)

    if args.revert:
        io.open(path, "w", encoding="utf-8", newline="").write(stripped)
        print("已回滚 jev 补丁（主理人与快问的 jev 块已移除，其它内容未动）")
        return 0

    # ① 主理人
    text, err = insert_after(stripped, LEAD_ANCHOR, LEAD_BLOCK.replace("\n", eol), eol)
    if err:
        print("主理人锚点异常：%s" % err)
        return 2
    # ② 快问（锚点在 ① 之后，位置会变，重新定位）
    text2, err2 = insert_after(text, FAST_ANCHOR, FAST_BLOCK.replace("\n", eol), eol)
    if err2:
        print("快问锚点异常：%s" % err2)
        return 2

    if not text2.endswith(eol):
        text2 += eol
    io.open(path, "w", encoding="utf-8", newline="").write(text2)

    code, msg = check(path, args.pylibs)
    print("写入完成 ｜ %s" % msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
