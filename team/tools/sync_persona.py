# -*- coding: utf-8 -*-
"""sync_persona.py —— 把 agents/<id>.md 单向发布到 ~/.dsh 的 preset persona prefix

存在理由：
  `verify_dsh_sync.py` 说明「patch 的 persona prefix 由外部渲染器生成（源仓库无该渲染器）」。
  于是改了 `agents/*.md` 运行时并不生效——必须先重建 prefix 块。

  本脚本就是那个缺失的渲染器（最小实现）：
    agents/<id>.md  →  "# 标题" + 语言铁律 + 正文  →  cordis.patch.yml 的 prefix 块

用法：
    python tools/sync_persona.py --agent sg-query-router --dry-run
    python tools/sync_persona.py --agent sg-query-router
    python tools/sync_persona.py --all
    python tools/sync_persona.py --check            # 只校验是否一致（不写盘）

退出码：0 成功/一致 ｜ 1 存在漂移（--check）｜ 2 输入错误
"""
import argparse
import io
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH = os.path.join(os.path.expanduser("~"), ".dsh", "profiles", "desktop", "cordis.patch.yml")
AGENTS = os.path.join(PKG, "agents")
IND = " " * 16
LANG_RULE = (
    "**语言铁律（最高优先级）**：面向用户的一切自然语言输出**始终使用简体中文**；"
    "代码、SQL、字段名、表名、文件路径保持原文不翻译。用户用中文提问时，"
    "禁止用英文整句作答，也不要用英文开头再补中文。"
)


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def build_prefix(md_path):
    md = io.open(md_path, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    while md and md[0].strip() == "":
        md.pop(0)
    if not md or not md[0].startswith("# "):
        raise SystemExit("FAIL: %s 首行不是 '# 标题'" % md_path)
    out = ["", md[0], ""]
    body = md[1:]
    while body and body[0].strip() == "":
        body.pop(0)
    # 语言铁律只注入一次（源 .md 若已含则不重复）
    if not any("语言铁律" in ln for ln in body[:5]):
        out += [LANG_RULE, ""]
    out += body
    while out and out[-1].strip() == "":
        out.pop()
    return [IND + ln if ln.strip() else "" for ln in out]


def load_yaml():
    sys.path.insert(0, os.path.join(PKG, "tools", "_vendor"))
    import yaml  # noqa
    return yaml


def sync_one(agent_id, raw, dry_run, check_only=False):
    """返回 (ok, msg)。ok=False 表示 --check 下检测到漂移。"""
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    try:
        p_start = next(i for i, l in enumerate(lines) if l.strip() == "- id: preset-" + agent_id)
    except StopIteration:
        return False, "patch 中找不到 preset-%s" % agent_id
    p_end = p_start + 1
    while p_end < len(lines) and not lines[p_end].startswith("    - id: "):
        p_end += 1
    if p_end >= len(lines):
        p_end = len(lines)

    try:
        pre = next(i for i in range(p_start, p_end) if lines[i].strip() == "prefix: |")
    except StopIteration:
        return False, "preset-%s 内无 'prefix: |'" % agent_id
    if not lines[pre].startswith(" " * 14):
        return False, "prefix 行缩进异常"
    pre_end = pre + 1
    while pre_end < p_end and (lines[pre_end].strip() == "" or lines[pre_end].startswith(IND)):
        pre_end += 1
    while pre_end > pre + 1 and lines[pre_end - 1].strip() == "":
        pre_end -= 1

    old_chars = sum(len(x) for x in lines[pre + 1:pre_end])
    new_block = build_prefix(os.path.join(AGENTS, agent_id + ".md"))
    new_chars = sum(len(x) for x in new_block)

    # 防膨胀护栏：.md 是「详细知识库」，patch prefix 是「浓缩操作手册」——两者本就不同。
    # 若 .md 体积远超当前 prefix（>1.5x），直接用 .md 覆盖会撑爆上下文，必须人工浓缩。
    if old_chars > 0 and new_chars > old_chars * 1.5:
        return False, ("拒绝：.md 渲染后 %d 字符 > 当前 prefix %d 的 1.5 倍"
                       "（.md 是详细知识库，prefix 是浓缩手册，请人工浓缩后再发布）"
                       % (new_chars, old_chars))

    same = lines[pre + 1:pre_end] == new_block
    if check_only:
        return same, ("一致（%d 字符）" % new_chars if same
                      else "漂移 %+d 字符（%d → %d）" % (new_chars - old_chars, old_chars, new_chars))

    new_lines = lines[:pre + 1] + new_block + lines[pre_end:]
    out = nl.join(new_lines)

    yaml = load_yaml()

    class L(yaml.SafeLoader):
        pass

    L.add_multi_constructor("!", lambda l, s, n: None)
    L.add_multi_constructor("tag:yaml.org,2002:js", lambda l, s, n: None)
    yaml.load(out, Loader=L)

    if not dry_run:
        io.open(PATCH, "w", encoding="utf-8", newline="").write(out)
    return True, ("%d → %d 字符（%+d）%s" % (old_chars, new_chars, new_chars - old_chars,
                                             "｜DRY-RUN 未写盘" if dry_run else "｜已写盘"))


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(description="agents/*.md → DSH preset prefix 单向发布")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--agent")
    g.add_argument("--all", action="store_true")
    g.add_argument("--check", action="store_true", help="只校验漂移，不写盘")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isfile(PATCH):
        print("FAIL: 找不到 %s" % PATCH)
        return 2
    raw = io.open(PATCH, encoding="utf-8", newline="").read()

    if args.check:
        ids = sorted(fn[:-3] for fn in os.listdir(AGENTS)
                     if fn.endswith(".md") and os.path.isfile(os.path.join(AGENTS, fn)))
    elif args.all:
        ids = sorted(fn[:-3] for fn in os.listdir(AGENTS)
                     if fn.endswith(".md") and os.path.isfile(os.path.join(AGENTS, fn)))
    else:
        ids = [args.agent]

    drift, fail = 0, 0
    for aid in ids:
        try:
            ok, msg = sync_one(aid, raw, args.dry_run, check_only=args.check)
        except SystemExit as e:
            print("  [FAIL] %-38s %s" % (aid, e))
            fail += 1
            continue
        if args.check:
            print("  [%s] %-38s %s" % ("OK  " if ok else "DRIFT", aid, msg))
            drift += 0 if ok else 1
        elif ok:
            if not args.dry_run:
                raw = io.open(PATCH, encoding="utf-8", newline="").read()
            print("  [OK  ] %-38s %s" % (aid, msg))
        else:
            print("  [FAIL] %-38s %s" % (aid, msg))
            fail += 1

    print()
    if args.check:
        print("✅ 全部一致" if drift == 0 else "⚠️ %d 个 agent 存在漂移 → 跑 --all 发布" % drift)
        return 0 if drift == 0 else 1
    print("✅ 发布完成（%d 个）" % (len(ids) - fail) if fail == 0 else "❌ %d 个失败" % fail)
    if not args.dry_run:
        print("⚠ 需重启 DSH 才对新会话生效")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
