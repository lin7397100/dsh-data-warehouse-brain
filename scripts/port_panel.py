# -*- coding: utf-8 -*-
"""port_panel.py —— 把面板宿主半改造成「组合包形态」（幂等）

原 `panel/dwb-team-panel/routes.js` 是绑在本机手工版上的：
  - 默认团队根 = ~/Documents/deepseek-harness/data-warehouse-brain-team
  - 默认 patch  = ~/.dsh/profiles/desktop/cordis.patch.yml
  - Python 解释器写死 D:\\Programs\\DeepSeek Harness\\...
本脚本把它们改成组合包形态（$DSH_HOME/dwb-team、包内 patch、按 PATH 找 python），
并补一条 GET /dwb-team/api/root 让专家与面板都能发现团队根。

用法：python scripts/port_panel.py [--check]
退出码：0 已就位/已改；1 --check 发现未改造
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROUTES = os.path.join(PKG, "routes.js")
CLIENT = os.path.join(PKG, "client.js")

# 浏览器半必须用「包名」作为模块工厂 id（DSH 按包名查找 client 模块），
# 旧的 @local/dwb-team-panel 会让本包的 client 永远不被加载。
CLIENT_EDITS = (
    ("  id: '@local/dwb-team-panel',", "  id: '@sansteel/dsh-data-warehouse-brain',", "client 模块 id → 包名"),
    ("var PANEL_ID = 'dwb-team';", "var PANEL_ID = 'dwb-team-brain';", "面板 slot id 去重"),
    ("var STYLE_ID = 'dwb-team-panel/styles';", "var STYLE_ID = 'dwb-team-brain/styles';", "样式 id 去重"),
)

OLD_ROOT_FN = """function defaultTeamRoot() {
  return path.join(os.homedir(), 'Documents', 'deepseek-harness', 'data-warehouse-brain-team');
}"""
NEW_ROOT_FN = """const PKG_DIR = path.dirname(fileURLToPath(import.meta.url));

function defaultTeamRoot() {
  const home = process.env.DSH_HOME || path.join(os.homedir(), '.dsh');
  return path.join(home, 'dwb-team');
}"""

OLD_PATCH_FN = """function resolvePatchPath(config) {
  if (config && typeof config.patchPath === 'string' && config.patchPath.trim()) {
    return config.patchPath.trim();
  }
  return path.join(os.homedir(), '.dsh', 'profiles', 'desktop', 'cordis.patch.yml');
}"""
NEW_PATCH_FN = """function resolvePatchPath(config) {
  if (config && typeof config.patchPath === 'string' && config.patchPath.trim()) {
    return config.patchPath.trim();
  }
  // 组合包自带 patch：写回只改包自己的声明，不碰用户 profile
  return path.join(PKG_DIR, 'cordis.patch.yml');
}"""

_OLD_PY_LITERAL = "D:" + "\\\\Programs\\\\DeepSeek Harness\\\\resources\\\\runtime\\\\" \
                  "primary-runtime\\\\dependencies\\\\python\\\\python.exe"

OLD_PY = """  const candidates = [
    process.env.DSH_PYTHON,
    '%s',
    'python',
    'python3',
  ].filter(Boolean);""" % _OLD_PY_LITERAL
NEW_PY = """  const candidates = [
    process.env.DSH_PYTHON,
    path.join(process.env.DSH_INSTALL_DIR || '', '..', 'runtime', 'primary-runtime',
      'dependencies', 'python', 'python.exe'),
    'python',
    'python3',
  ].filter(Boolean);"""

ROOT_ROUTE_ANCHOR = "  // 专家头像缩略图（96x96 PNG）；缺头像的 preset 回退 team.png"
ROOT_ROUTE = """  // 团队根 / 供给状态：专家排障与面板展示都用得到
  route('/root', ['GET'], async () => {
    const s = services || {};
    let prov = null;
    try {
      prov = s.provision ? await s.provision() : null;
    } catch (error) {
      prov = { error: String((error && error.message) || error) };
    }
    return {
      ok: true,
      root,
      packageDir: s.packageDir || PKG_DIR,
      patchPath: resolvePatchPath(config),
      rosterExists: fssync.existsSync(rosterPath),
      provision: prov,
    };
  });

""" + ROOT_ROUTE_ANCHOR


def port_file(path, edits, label):
    text = io.open(path, encoding="utf-8").read()
    todo = []
    for old, new, what in edits:
        if new in text:
            continue
        if old not in text:
            print("FAIL: %s 找不到锚点「%s」" % (label, what))
            return 2
        todo.append((old, new, what))
    if not todo:
        print("%s 已就位" % label)
        return 0
    for old, new, what in todo:
        text = text.replace(old, new, 1)
        print("  + %s → %s" % (label, what))
    io.open(path, "w", encoding="utf-8").write(text)
    return 0


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    check = "--check" in sys.argv
    if not os.path.isfile(ROUTES):
        print("FAIL: 找不到 routes.js")
        return 2
    text = io.open(ROUTES, encoding="utf-8").read()
    todo = []
    for old, new, label in (
        (OLD_ROOT_FN, NEW_ROOT_FN, "默认团队根"),
        (OLD_PATCH_FN, NEW_PATCH_FN, "默认 patch 路径"),
        (OLD_PY, NEW_PY, "Python 解释器解析"),
        (ROOT_ROUTE_ANCHOR, ROOT_ROUTE, "/api/root 路由"),
    ):
        if new in text:
            continue
        if old not in text:
            print("FAIL: 找不到锚点「%s」，面板源码可能已变" % label)
            return 2
        todo.append((old, new, label))

    if not todo:
        print("routes.js 已就位（无需改动）")
    elif check:
        print("routes.js 未改造：%s" % ", ".join(t[2] for t in todo))
        return 1
    else:
        for old, new, label in todo:
            text = text.replace(old, new, 1)
            print("  + %s" % label)
        io.open(ROUTES, "w", encoding="utf-8").write(text)
        print("routes.js 已改造")

    rc = port_file(CLIENT, CLIENT_EDITS, "client.js")
    return rc


if __name__ == "__main__":
    sys.exit(main())
