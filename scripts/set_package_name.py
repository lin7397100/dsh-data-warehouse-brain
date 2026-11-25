# -*- coding: utf-8 -*-
"""set_package_name.py —— 一键改包名（范围包 / 去 scope），并同步所有引用

包名在四个地方必须一致，漏一个装完就不生效：
  1. package.json `name`
  2. cordis.patch.yml：每个 preset 的 bundedSkillDir 表达式 + 面板宿主行 `name:`
  3. client.js：浏览器半的模块工厂 id（DSH 按包名查找）
  4. panel/roster.json：meta.package（由构建脚本重算）

用法：
  python scripts/set_package_name.py @lin7397100/dsh-data-warehouse-brain
  python scripts/set_package_name.py dsh-data-warehouse-brain --dry-run

退出码：0 成功；1 校验失败；2 参数错误
"""
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
MANIFEST = os.path.join(PKG, "package.json")
PATCH = os.path.join(PKG, "cordis.patch.yml")
CLIENT = os.path.join(PKG, "client.js")

NAME_RE = re.compile(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$")
RESERVED = {"dsh", "node", "npm", "cordis", "deepseek", "deepseek-harness"}


def utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass


def read_json(path):
    return json.load(io.open(path, encoding="utf-8"))


def main():
    utf8()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) != 1:
        print("用法：python scripts/set_package_name.py <新包名> [--dry-run]")
        return 2
    new = args[0].strip()
    if not NAME_RE.match(new):
        print("FAIL: 包名不合法（小写字母/数字/-._，可带一个 @scope/）")
        return 1
    base = new.split("/")[-1]
    if base in RESERVED:
        print("FAIL: %s 是保留名" % base)
        return 1

    old = read_json(MANIFEST).get("name") or ""
    if not old:
        print("FAIL: package.json 缺 name")
        return 1
    if old == new:
        print("包名已是 %s，无需改动" % new)
        return 0
    print("改名：%s → %s" % (old, new))

    # 1) 清单
    man = read_json(MANIFEST)
    man["name"] = new
    if not dry:
        io.open(MANIFEST, "w", encoding="utf-8").write(
            json.dumps(man, ensure_ascii=False, indent=2) + "\n")

    # 2) patch：技能解析表达式 + 面板宿主行
    text = io.open(PATCH, encoding="utf-8").read()
    hits = text.count(old)
    text = text.replace(old, new)
    if not dry:
        io.open(PATCH, "w", encoding="utf-8").write(text)
    print("  patch 引用替换 %d 处" % hits)

    # 3) client.js 模块 id（交给 port_panel 的正则改写）
    ctext = io.open(CLIENT, encoding="utf-8").read()
    if not dry:
        ctext = re.sub(r"(?m)^  id: '[^']*',$", "  id: '%s'," % new, ctext, count=1)
        io.open(CLIENT, "w", encoding="utf-8").write(ctext)
    print("  client.js 模块 id → %s" % new)

    if dry:
        print("DRY-RUN 未写盘")
        return 0

    # 4) 重建 prefix + 名册，然后总校验
    for script in ("build_package.py", "port_panel.py", "verify_package.py"):
        r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                           cwd=PKG, capture_output=True, text=True, encoding="utf-8")
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        print("  %-20s exit=%d %s" % (script, r.returncode, tail[0]))
        if r.returncode != 0:
            print((r.stdout or "")[-1200:])
            print((r.stderr or "")[-600:])
            return 1
    print("✅ 改名完成；记得同步 README/docs 里的安装命令，并重发 npm / 重新打包")
    return 0


if __name__ == "__main__":
    sys.exit(main())
