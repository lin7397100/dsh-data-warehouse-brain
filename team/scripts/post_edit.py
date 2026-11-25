# -*- coding: utf-8 -*-
"""
专家包编辑后一键生效脚本（DSH 架构 · 唯一路径）

DSH（DeepSeek Harness）部署模型是**单向发布**：
    源仓库（本包 agents/ + skills/） → ~/.dsh/profiles/desktop/cordis.patch.yml
                                     → ~/.dsh/skills/
源仓库是唯一事实源，发布**单向**，运行时（~/.dsh）**禁回写**。

本脚本做的事（DSH 唯一序列，无回退分支）：
    调用 scripts/verify_dsh_sync.py --apply 发布 → 复检一致性 → 提示重启 DSH。

用法：
    python scripts/post_edit.py            # 发布 + 复检
    python scripts/post_edit.py --dry-run  # 只打印发布计划，不写盘
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _utf8_stdout():
    """Windows 控制台默认 GBK，强制 UTF-8，避免 ⚠ 等符号抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def run_dsh(dry_run):
    """DSH 单向发布：改源仓库 → verify_dsh_sync.py --apply → 重启 DSH。"""
    verifier = os.path.join(HERE, "scripts", "verify_dsh_sync.py")
    if not os.path.isfile(verifier):
        print("FAIL 找不到 %s" % verifier)
        return 2

    cmd = [sys.executable, verifier, "--apply"]
    if dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        print("FAIL 发布/复检未通过（退出码 %d），检查上方报告" % r.returncode)
        return r.returncode

    print("\n===== DSH 发布完成：源仓库 → ~/.dsh =====")
    print("⚠ 请**重启 DSH** 让新会话加载新 persona / 新技能（发布 ≠ 当前会话已生效）。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="专家包编辑后一键生效（DSH 单向发布：源仓库 → ~/.dsh）"
    )
    ap.add_argument("--dry-run", action="store_true", help="只打印发布计划，不写盘")
    args = ap.parse_args(argv)

    _utf8_stdout()
    print("[环境] DSH 单向发布模型（源仓库 → ~/.dsh）")
    return run_dsh(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
