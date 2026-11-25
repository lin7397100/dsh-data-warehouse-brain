#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enable_fast_lane.py —— 给专家团组合层打「快车道优先」补丁（幂等，可反复运行）
================================================================================

做两处改动（仅文本级插入，不改任何既有 preset 的其它内容）：

  ① 主理人 preset 的 GATE-Q 段落后插入「v1.4 快车道优先」条款
     —— 依据：源包主理人 L55「快车道不豁免 GATE-Q」是 L0 裸查 82 min 的成因；
        改后单指标命中物化即绕开 GATE-Q 与 P0–P5，非快车道一律维持原全流程。

  ② 追加一个独立 preset `dwb-fast-ask`（快问·单指标秒查）
     —— 只装 persona/时间/终端/文件/技能/MCP db2，不装 subagent，物理上无法派专家。

安全性：
  - 幂等：重跑先删掉上次注入的块（靠 DWB-FAST-LANE 标记行定位）再重写
  - 可回滚：uninstall 思路 = 删标记块 + 删那一段，或直接用 install.ps1 生成的备份
  - 不猜 schema：所有插件字段照抄包内既有条目（persona / tool-pwsh / mcp-client 的写法）

用法：
  python tools/enable_fast_lane.py --file cordis.patch.yml
  python tools/enable_fast_lane.py --file cordis.patch.yml --check     # 只校验不改
  python tools/enable_fast_lane.py --file cordis.patch.yml --revert    # 逆操作

退出码：0 成功；1 校验失败；2 结构异常（找不到锚点）。
"""

import argparse
import io
import os
import re
import sys

BEGIN = "  # >>> DWB-FAST-LANE v1 (由 tools/enable_fast_lane.py 注入，勿手改) >>>"
END = "  # <<< DWB-FAST-LANE v1 <<<"
GATE_ANCHOR = "**跳过后果**：首次顶部红字告警；二次强制补做；三次触发衍薪改写为脚本硬断言。**唯一豁免**：纯对话/闲聊（不取数不出报告不派发）；快车道不豁免 GATE-Q。"

GATE_PATCH = """\
            **⏩ v1.4 快车道优先（2026-11-17 提速修正 · 覆盖上方"快车道不豁免 GATE-Q"）**

            判型是确定性的，不需要一次 LLM 子会话。**任何取数请求先跑判型脚本**，据结果分车道：

            ```
            python {{TEAM_ROOT}}/tools/route_intent.py --text "<用户原话>" --format text
            ```

            | 判型输出 | 走哪条 | 是否派辨枢 | SLA |
            |---|---|---|---|
            | `lane=fast`（fast_lane=true） | **快车道**：`tools/fast_ask.py` → 物化 SQL → 网关 → 出数 | **不派**（绕开 GATE-Q 与 P0–P5） | ≤30 s |
            | `lane=trend` | T2a 趋势快线（`sg-trend-quick`，1 条区间 SQL） | 不派 | ≤3 min |
            | `lane=root_cause` / `lane=full` | 原全流程：辨枢出 IntentContract → P0–P5 | 派 | L2/L3 |

            **快车道放行的三个硬条件（缺一即退回全流程，等价于原 GATE-Q）**：
            ① 脚本判型 `lane=fast`；② `fast_ask.py` 返回 `mode=materialized`；③ `ambiguous=false`（候选唯一）。
            → 满足三条 = **指标身份已被物化 SQL 证明**，比任何"派专家问一遍"更硬；
            → 任一条不满足（含 needs_slow_lane / 候选歧义 / 空壳 SQL）**必须**退回 GATE-Q 全流程，禁止主理人自行拍口径。

            **禁止**：
            1. 禁止 LLM 覆盖脚本判型结果；回执里必须原样贴 `route_intent.py` 输出。
            2. 禁止在快车道内做 SUM 改写/区间聚合（比率型、复合型指标一律走慢车道）。
            3. 快车道交付必须带：`zb_code` + 执行 SQL 文件名 + `maturity` 三档 + 数据限制。
"""

FAST_PRESET = """\
  # >>> DWB-FAST-LANE v1 (由 tools/enable_fast_lane.py 注入，勿手改) >>>
- insert:
  - id: preset-dwb-fast-ask
    name: '@deepseek-ai/dsh-agent-preset'
    config:
      id: dwb-fast-ask
      name: 快问 Quick · 单指标秒查
      description: 单指标裸查专用：确定性判型 → 物化直查 → 过网关 → 出数（目标 ≤30 s，不派任何专家）
      order: 99
      plugins:
      - id: persona
        name: '@deepseek-ai/dsh-persona'
        config:
          prefix: |2

            # 快问 Quick · 单指标秒查（dwb-fast-ask）

            ## 唯一职责

            用户问「某个指标是多少 / 口径是什么 / 怎么算」时，用确定性脚本取数。**不派专家、不走 GATE-Q、不跑 P0–P5。**

            ## 固定四步（禁止跳步，禁止自行判型）

            ```
            1) python {{TEAM_ROOT}}/tools/route_intent.py --text "<用户原话>" --format text
               → 只有 lane=fast 才继续；lane≠fast 立即停，回复"这题需要完整链路，请在主理人会话里问"

            2) python {{TEAM_ROOT}}/tools/fast_ask.py --text "<用户原话>" --date <YYYYMMDD> --gate
               → 读 JSON：mode=materialized 且 ambiguous=false 才取数
               → mode=needs_slow_lane / ambiguous=true → 停，说明原因（不得自己猜指标）

            3) 取 sql_executed 原文，会话内调 mcp__db2__execute_sql（只读单语句）

            4) 按 sg-qa-render 格式输出：结果表 + 口径卡（zb_code/名称/粒度/来源表/SQL 文件名）
               + maturity 三档 + 数据限制
            ```

            ## 硬规则

            - 禁止内联改写 SQL 表达式；比率型/复合型指标不做 SUM。
            - 禁止加载 `indicator_registry.json` 全量；只读单个 `materialized_sql/<code>.sql`。
            - `maturity` 缺失按 `draft` 处理并披露「未经语义层校准」。
            - 任一脚本 exit≠0 → 原样报错，**禁止编数**。
            - 目标 ≤30 s；超 5 min 必复述已得结果 + 未完成项（L0 硬超时熔断）。
      - id: time-context
        name: '@deepseek-ai/dsh-time-context'
      - id: tool-bash
        name: '@deepseek-ai/dsh-tool-bash'
        disabled: !!js "process.platform === 'win32'"
      - id: tool-pwsh
        name: '@deepseek-ai/dsh-tool-pwsh'
        disabled: !!js "process.platform !== 'win32'"
      - id: tool-fs
        name: '@deepseek-ai/dsh-tool-fs'
      - id: tool-fs-search
        name: '@deepseek-ai/dsh-tool-fs-search'
      - id: tool-skill
        name: '@deepseek-ai/dsh-tool-skill'
      - id: skill-filesystem
        name: '@deepseek-ai/dsh-skill-filesystem'
      - id: mcp-db2
        name: '@deepseek-ai/dsh-mcp-client'
        config:
          serverName: db2
          transport: streamable-http
          url: !!js "process.env.SG_DB2_MCP_URL ?? 'http://10.18.136.38:8765/mcp'"
          toolCallTimeoutMs: 60000
        disabled: !!js "process.env.SG_MCP === 'off'"
  # <<< DWB-FAST-LANE v1 <<<
"""


def load_yaml(path, pylibs):
    try:
        if pylibs:
            sys.path.insert(0, pylibs)
        import yaml  # noqa
    except Exception as e:
        return None, "PyYAML 不可用（请用 --pylibs 指向内置 pylibs 目录）：%s" % e
    with io.open(path, encoding="utf-8") as f:
        text = f.read()
    class L(yaml.SafeLoader):
        pass
    L.add_multi_constructor("tag:yaml.org,2002:js", lambda loader, suffix, node: node.value)
    L.add_multi_constructor("!", lambda loader, suffix, node: node.value)
    return yaml.load(text, Loader=L), None


def check(path, pylibs):
    data, err = load_yaml(path, pylibs)
    if err:
        return 1, err
    if not isinstance(data, list):
        return 1, "根节点不是数组"
    presets = []
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("insert"), list):
            for pl in entry["insert"]:
                cfg = (pl or {}).get("config") or {}
                if (pl or {}).get("name") == "@deepseek-ai/dsh-agent-preset":
                    presets.append(cfg.get("id"))
    dup = [p for p in set(presets) if presets.count(p) > 1]
    msg = "preset 数=%d ｜ fast-ask 在场=%s ｜ 重复=%s" % (
        len(presets), "dwb-fast-ask" in presets, dup or "无")
    return (0 if (len(presets) == 24 and "dwb-fast-ask" in presets and not dup) else 1), msg


def main():
    ap = argparse.ArgumentParser(description="给专家团组合层打「快车道优先」补丁（幂等）")
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

    # 幂等：先剥掉上次注入的块
    stripped = re.sub(r"(?ms)^  # >>> DWB-FAST-LANE.*?^  # <<< DWB-FAST-LANE[^\r\n]*\r?\n", "", raw)
    gate_patched = "**⏩ v1.4 快车道优先" in stripped
    if gate_patched:
        # 已有 GATE 补丁时，先把旧补丁段删掉再重写（保持单份）
        stripped = re.sub(
            r"(?ms)\r?\n\s{12}\*\*⏩ v1\.4 快车道优先.*?maturity\` 三档 \+ 数据限制。\r?\n", "\r\n", stripped)

    if args.revert:
        io.open(path, "w", encoding="utf-8", newline="").write(stripped)
        print("已回滚快车道补丁（GATE 段恢复原样，fast-ask preset 已移除）")
        return 0

    # ① GATE-Q 段落补丁
    if GATE_ANCHOR not in stripped:
        print("找不到 GATE-Q 锚点，文件可能已改造过或来源不同：%s" % GATE_ANCHOR[:40])
        return 2
    lines = stripped.split(eol)
    anchor_idx = [i for i, l in enumerate(lines) if GATE_ANCHOR in l]
    if len(anchor_idx) != 1:
        print("GATE-Q 锚点出现 %d 次（应为 1）" % len(anchor_idx))
        return 2
    i = anchor_idx[0]
    ins = [""] + GATE_PATCH.rstrip("\n").split("\n")
    lines[i + 1:i + 1] = ins
    patched = eol.join(lines)

    # ② 追加 fast-ask preset（文件末必须是换行结尾）
    if not patched.endswith(eol):
        patched += eol
    patched += FAST_PRESET.rstrip("\n").replace("\n", eol) + eol

    io.open(path, "w", encoding="utf-8", newline="").write(patched)

    code, msg = check(path, args.pylibs)
    print("写入完成 ｜ %s" % msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
