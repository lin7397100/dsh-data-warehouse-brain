# -*- coding: utf-8 -*-
"""toggle_strip.py —— 开关「构建时是否剥离 preset 内 MCP 行」

背景（B 方案）：服务器 DSH 是 0.2.1-rc.3，没有 dsh-mcp-manager（npm 最低 0.2.2-rc.2），
面板托管通道不存在。此时 preset 必须**保留** mcp-client 行，否则专家团彻底没有取数通道。

用法：
  python scripts/toggle_strip.py off   # 保留 MCP 行（默认，适配 0.2.1）
  python scripts/toggle_strip.py on    # 剥离（适配 0.2.2+ 且装了 mcp-manager）
  python scripts/toggle_strip.py       # 查看当前状态
"""
import io
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(PKG, "scripts", "build_package.py")

KEEP_BLOCK = """        # B 方案：preset 保留 MCP 行（0.2.1 无 mcp-manager，删了就断通道）
        n_mcp = 0"""
STRIP_BLOCK = """        text, n_mcp = strip_preset_mcp(text)"""
KEEP_BLOCK2 = """        n_mcp = 0  # 保留 preset 内 MCP 行"""
STRIP_BLOCK2 = """        if n_mcp:
            print("已从 preset 移除 %d 个 mcp-* 行" % n_mcp)"""


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    text = io.open(BUILD, encoding="utf-8").read()
    keeping = KEEP_BLOCK in text and KEEP_BLOCK2 in text
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    print("当前：%s" % ("保留 preset 内 MCP 行（B 方案）" if keeping else "剥离 preset 内 MCP 行（托管方案）"))

    if arg == "off" and not keeping:
        text = text.replace(STRIP_BLOCK, KEEP_BLOCK, 1)
        text = text.replace(STRIP_BLOCK2, KEEP_BLOCK2, 1)
        io.open(BUILD, "w", encoding="utf-8").write(text)
        print("已切到：保留 MCP 行")
    elif arg == "on" and keeping:
        text = text.replace(KEEP_BLOCK, STRIP_BLOCK, 1)
        text = text.replace(KEEP_BLOCK2, STRIP_BLOCK2, 1)
        io.open(BUILD, "w", encoding="utf-8").write(text)
        print("已切到：剥离 MCP 行")
    elif arg in ("on", "off"):
        print("已是目标状态，无需改动")
    elif arg:
        print("FAIL: 只接受 on / off")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
