# -*- coding: utf-8 -*-
"""scrub_secrets.py —— 把硬编码在内网凭据替换成环境变量引用（幂等）

背景：本包的若干技能脚本里原本直接内联了 5sApi clientSecret 与企微 token 应用
secret。这些值一旦随包公开（GitHub / npm），任何能访问内网的人都能冒用。
本脚本按**文件所属系统**把它们换成 `os.getenv("<变量名>", "")` 或占位符，
真实值改由 `$DSH_HOME/.env` 提供（见 docs/AUTH-SETUP.md）。

用法：
  python scripts/scrub_secrets.py            # 扫描 + 替换
  python scripts/scrub_secrets.py --check    # 只报告残留（exit 1 = 仍有明文）

退出码：0 干净/已清理；1 --check 发现残留；2 环境错误
"""
import io
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX32 = r"[A-Fa-f0-9]{32}"

# 路径关键字 → (环境变量名, 说明)
ROUTES = [
    ("sg-cbprod-procedure-analyzer", "EPLAT_CLIENT_SECRET_CB01", "日成本域 sgdw-cb01"),
    ("sg-gzprod-etl-analyzer", "EPLAT_CLIENT_SECRET_CS01", "管控抽数 sgdw-cs01"),
    ("freshness_gate", "EPLAT_CLIENT_SECRET_CS01", "ETL 日志 sgdw-cs01"),
    ("team/tools", "EPLAT_CLIENT_SECRET_CS01", "团队工具默认 ETL 凭据"),
    ("sg-morning-ppt-report", "EPLAT_CLIENT_SECRET_GZ01", "早会报表 sgdw-gz01"),
    ("sg-report-delivery", "WECOM_TOKEN_CLIENT_SECRET", "每日点检 token 应用 sgoc-oc01"),
    ("wecom_sender", "WECOM_TOKEN_CLIENT_SECRET", "每日点检 token 应用 sgoc-oc01"),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "_vendor"}


def route_for(path):
    low = path.replace("\\", "/")
    for key, env, label in ROUTES:
        if key in low:
            return env, label
    return None, None


def scrub_py(text, env):
    # "clientSecret": "<hex>"  /  "clientSecret":os.getenv("X","<hex>")
    text = re.sub(r'("clientSecret"\s*:\s*)"' + HEX32 + r'"',
                  r'\1os.getenv("%s", "")' % env, text)
    text = re.sub(r'("clientSecret"\s*:\s*)os\.getenv\("([A-Z_0-9]+)",\s*"' + HEX32 + r'"\)',
                  r'\1os.getenv("\2", "")', text)
    # TOKEN_CLIENT_SECRET = "<hex>"
    text = re.sub(r'(TOKEN_CLIENT_SECRET\s*=\s*)"' + HEX32 + r'"',
                  r'\1os.getenv("%s", "")' % env, text)
    # ("sgdw-xx", "<hex>")
    text = re.sub(r'(\("[A-Za-z0-9_\-]+",\s*)"' + HEX32 + r'"\)',
                  r'\1os.getenv("%s", ""))' % env, text)
    return text


def scrub_json(text, env):
    text = re.sub(r'("clientSecret"\s*:\s*)"' + HEX32 + r'"', r'\1""', text)
    return text


def scrub_md(text, env):
    text = re.sub(r'(clientSecret\s*[=:]\s*`?)' + HEX32,
                  r'\g<1>${%s}' % env, text)
    text = re.sub(r'(CLIENT_SECRET\s*\|\s*`?)' + HEX32,
                  r'\g<1>${%s}' % env, text)
    text = re.sub(r'("clientSecret"\s*:\s*")' + HEX32, r'\g<1>${%s}' % env, text)
    text = re.sub(r'(TOKEN_CLIENT_SECRET\s*=["\s]*`?)' + HEX32,
                  r'\g<1>${%s}' % env, text)
    return text


CRED_WORDS = ("clientsecret", "client_secret", "corpsecret", "secret", "password",
              "passwd", "lightcodegtw-token", "api_key", "apikey", "access_token")


def scan(text):
    """只把「出现在凭据上下文里的 32 位十六进制」当作泄露；EPLAT UUID/文档 id 不算。"""
    out = []
    for line in text.split("\n"):
        if not re.search(HEX32, line):
            continue
        low = line.lower()
        if any(w in low for w in CRED_WORDS):
            out.append(line)
    return out


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    check = "--check" in sys.argv
    residual = []
    fixed = []
    for base, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            if not fn.endswith((".py", ".json", ".md")):
                continue
            p = os.path.join(base, fn)
            if "_vendor" in p.replace("\\", "/"):
                continue
            rel = os.path.relpath(p, PKG)
            try:
                text = io.open(p, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            if not scan(text):
                continue
            env, label = route_for(rel)
            if not env:
                # 不属于已知凭据文件：只报告，不猜着改
                residual.append((rel, "未归类，需人工确认"))
                continue
            if fn.endswith(".py"):
                new = scrub_py(text, env)
            elif fn.endswith(".json"):
                new = scrub_json(text, env)
            else:
                new = scrub_md(text, env)
            if scan(new):
                residual.append((rel, "替换后仍有明文（格式特殊）"))
                if not check:
                    io.open(p, "w", encoding="utf-8").write(new)
                continue
            if new != text:
                fixed.append((rel, env, label))
                if not check:
                    io.open(p, "w", encoding="utf-8").write(new)

    for rel, env, label in fixed:
        print("  \u2705 %-58s → %s（%s）" % (rel[:58], env, label))
    for rel, why in residual:
        print("  \u26a0 %-58s %s" % (rel[:58], why))
    print()
    print("已清理 %d 个文件；待人工 %d 个" % (len(fixed), len(residual)))
    if check:
        return 0 if not residual else 1
    return 0 if not residual else 1


if __name__ == "__main__":
    sys.exit(main())
