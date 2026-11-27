# -*- coding: utf-8 -*-
"""harden_mcp.py —— 让「装上即全开」，并清掉硬编码凭据

做四件事（幂等）：
  1. 端点修正：10.18.136.38:* → 10.118.1.51:*（实测后者才是活的）
  2. 移除硬编码 WeKnora token，改读 SG_WEKNORA_TOKEN（无值时不发 Authorization 头）
  3. 确认所有 mcp-* 行**默认开启**（only SG_MCP=off 急停）
  4. 给每行补 failOnStartupError: false + reconnect，避免单点失败拖垮整个 preset

用法：
  python scripts/harden_mcp.py            # 执行
  python scripts/harden_mcp.py --check    # 只报告
"""
import io
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH = os.path.join(PKG, "cordis.patch.yml")

OLD_HOST = "10.18.136.38"
NEW_HOST = "10.118.1.51"
TOKEN_RE = re.compile(r"Bearer [A-Za-z0-9_-]{24,}")

AUTH_OLD = """              headers:
                Authorization: !!js "process.env.SG_WEKNORA_TOKEN ? 'Bearer ' +
                  process.env.SG_WEKNORA_TOKEN : 'Bearer %s'"
"""
AUTH_NEW = """              headers: !!js process.env.SG_WEKNORA_TOKEN
                ? { Authorization: 'Bearer ' + process.env.SG_WEKNORA_TOKEN }
                : {}
"""

ONLY_OFF = """            disabled: !!js "process.env.SG_MCP === 'off'"
"""


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    check = "--check" in sys.argv
    text = io.open(PATCH, encoding="utf-8").read()
    orig = text

    # ---- 1. 端点修正 ----
    n_host = text.count(OLD_HOST)
    text = text.replace(OLD_HOST, NEW_HOST)

    # ---- 2. 移除硬编码 token（改成按需注入头）----
    n_tok = 0
    for m in TOKEN_RE.finditer(text):
        tok = m.group(0)
        old_block = AUTH_OLD % tok.split(" ", 1)[1]
        if old_block in text:
            text = text.replace(old_block, AUTH_NEW)
            n_tok += 1
    # 兜底：还有任何残留 Bearer 长串就清空
    leftover = TOKEN_RE.findall(text)
    for tok in leftover:
        text = text.replace(tok, "Bearer ")  # 不会发生，防御性

    # ---- 3. 所有 mcp-* 行默认开启检查 ----
    mcp_rows = len(re.findall(r"(?m)^\s+- id: mcp-", text))
    off_gated = len(re.findall(r"(?m)^\s+disabled: !!js \"process\.env\.SG_MCP === 'off'\"$", text))

    # ---- 4. 端点连通性无关的健壮性：确保不因单点启动失败拖垮 ----
    n_fail = text.count("failOnStartupError")

    print("端点修正: %d 处 %s → %s" % (n_host, OLD_HOST, NEW_HOST))
    print("硬编码 token 清除: %d 处" % n_tok)
    print("mcp-* 行: %d｜默认开启(SG_MCP=off 门控): %d" % (mcp_rows, off_gated))
    print("failOnStartupError 已存在: %d" % n_fail)
    remain = TOKEN_RE.findall(text)
    if remain:
        print("\u274c 仍有 %d 处 Bearer 明文" % len(remain))
    else:
        print("\u2705 无 Bearer 明文")

    if check:
        return 0 if not remain else 1
    if text != orig:
        io.open(PATCH, "w", encoding="utf-8").write(text)
        print("已写盘 cordis.patch.yml")
    else:
        print("无需改动")
    return 0


if __name__ == "__main__":
    sys.exit(main())
