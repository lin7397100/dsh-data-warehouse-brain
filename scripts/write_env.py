# -*- coding: utf-8 -*-
"""write_env.py —— 一键填报凭据到 $DSH_HOME/.env（备份 + 合并 + 脱敏显示）

为什么需要：团队要填 20 多个内网凭据，手改 .env 容易漏、容易把明文贴到别处。
本脚本把「写入 / 查看 / 删除」做成一条命令，并且**永不回显明文**（只显示前 4 位）。

用法：
  python scripts/write_env.py --set EPLAT_CLIENT_SECRET_CB01=xxx --set WECOM_CORPSECRET=yyy
  python scripts/write_env.py --from-file mysecret.env      # 批量导入 KEY=VALUE
  python scripts/write_env.py --status                      # 哪些已配/缺失
  python scripts/write_env.py --unset WECOM_DOCID
  python scripts/write_env.py --path                        # 打印 .env 实际路径

退出码：0 成功；1 有缺失（--status 时）；2 参数/路径错误
"""
import io
import os
import re
import sys
import time

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(PKG, ".env.example")

# 与 docs/AUTH-SETUP.md 对齐的分组（用于 --status 报告）
GROUPS = {
    "EPLAT 5sApi": ["EPLAT_CLIENT_ID_CB01", "EPLAT_CLIENT_SECRET_CB01",
                    "EPLAT_CLIENT_ID_CS01", "EPLAT_CLIENT_SECRET_CS01",
                    "EPLAT_CLIENT_ID_GZ01", "EPLAT_CLIENT_SECRET_GZ01"],
    "企微": ["WECOM_TOKEN_CLIENT_ID", "WECOM_TOKEN_CLIENT_SECRET",
             "WECOM_CORPID", "WECOM_CORPSECRET"],
    "DB2 通道": ["SGDW_LIGHTCODE_TOKEN", "SGDW_USER_ID", "SGDW_CLIENT_ID"],
    "MCP": ["DWB_INTERNAL_MCP", "SG_EPLAT_MCP_URL", "SG_WEKNORA_MCP_URL", "SG_WEKNORA_TOKEN"],
    "报表": ["FINEREPORT_URL"],
}
SECRET_HINT = ("SECRET", "TOKEN", "PASSWORD", "CORPSECRET")


def utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass


def env_path():
    home = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
    return os.path.join(home, ".env")


def read_env(path):
    pairs, order = dict(), []
    if not os.path.isfile(path):
        return pairs, order
    for line in io.open(path, encoding="utf-8").read().split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
            continue
        pairs[k] = v.strip()
        if k not in order:
            order.append(k)
    return pairs, order


def write_env(path, pairs, order):
    lines = ["# 由 scripts/write_env.py 维护；填写指引见 docs/AUTH-SETUP.md",
             "# 本文件含明文凭据，权限应为 600，禁止提交到仓库", ""]
    written = set()
    for k in order:
        if k in pairs and k not in written:
            lines.append("%s=%s" % (k, pairs[k]))
            written.add(k)
    for k in sorted(set(pairs) - written):
        lines.append("%s=%s" % (k, pairs[k]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        bak = path + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        io.open(bak, "w", encoding="utf-8").write(io.open(path, encoding="utf-8").read())
        print("  已备份 → %s" % os.path.basename(bak))
    io.open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mask(k, v):
    if not v:
        return "（空）"
    if not any(h in k.upper() for h in SECRET_HINT) and len(v) <= 24:
        return v
    return v[:4] + "***（%d 位）" % len(v)


def do_status(pairs):
    missing_required = 0
    for group, keys in GROUPS.items():
        print("\n[%s]" % group)
        for k in keys:
            v = pairs.get(k, "")
            ok = bool(v) and v not in ("1",) or k == "DWB_INTERNAL_MCP"
            if k == "DWB_INTERNAL_MCP":
                state = "启用" if v == "1" else "关闭"
                print("  %-30s %s" % (k, state))
                continue
            print("  %-30s %s" % (k, mask(k, v)))
            if not v:
                missing_required += 1
    print()
    if missing_required:
        print("⚠ %d 项未填。按 docs/AUTH-SETUP.md 补齐后重跑本命令。" % missing_required)
    else:
        print("✅ 主要凭据已齐；建议再按 AUTH-SETUP 第 4 节做连通性校验。")
    return 0 if not missing_required else 1


def main():
    utf8()
    args = sys.argv[1:]
    path = env_path()
    if not args or "--help" in args:
        print(__doc__)
        return 0
    if "--path" in args:
        print(path)
        return 0

    pairs, order = read_env(path)

    if "--status" in args:
        print("凭据文件：%s" % path)
        return do_status(pairs)

    changed = 0
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--set" and i + 1 < len(args):
            kv = args[i + 1]
            k, sep, v = kv.partition("=")
            if not sep or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k.strip()):
                print("FAIL: --set 需要 KEY=VALUE，收到 %r" % kv)
                return 2
            k = k.strip()
            if k not in pairs:
                order.append(k)
            pairs[k] = v.strip()
            changed += 1
            i += 2
            continue
        if a == "--unset" and i + 1 < len(args):
            k = args[i + 1].strip()
            if k in pairs:
                del pairs[k]
                changed += 1
            i += 2
            continue
        if a == "--from-file" and i + 1 < len(args):
            fp = args[i + 1]
            if not os.path.isfile(fp):
                print("FAIL: 找不到 %s" % fp)
                return 2
            for line in io.open(fp, encoding="utf-8").read().split("\n"):
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                k = k.strip()
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
                    continue
                if k not in pairs:
                    order.append(k)
                pairs[k] = v.strip()
                changed += 1
            i += 2
            continue
        i += 1

    if not changed:
        print("没有需要写入的改动；用 --set K=V / --from-file / --status")
        return 2

    write_env(path, pairs, order)
    print("✅ 已写入 %d 项 → %s" % (changed, path))
    print("   提醒：重启 DSH 后新值才会被注入进程环境。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
