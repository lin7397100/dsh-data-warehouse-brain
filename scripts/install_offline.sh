#!/usr/bin/env bash
# install_offline.sh —— 在连不上 GitHub 的机器上，把数仓智脑专家团装进一个 DSH profile
#
# 为什么需要：`dsh plugin add github:user/repo` 会去 codeload.github.com 拉 tar 包，
# 内网/境内网络经常超时。本脚本改用**本地目录**安装，全程不走网络。
#
# 用法：
#   ./install_offline.sh <tgz|目录>                        # 装到当前用户 web profile
#   ./install_offline.sh <tgz|目录> --profile desktop
#   ./install_offline.sh <tgz|目录> --home /data/dsh-users/230012/.dsh
#   ./install_offline.sh <tgz|目录> --dry-run
#
# 退出码：0 成功；1 安装/校验失败；2 参数或环境错误
set -uo pipefail

PKG_NAME="@sansteel/dsh-data-warehouse-brain"
PKG_SLUG="sansteel-dsh-data-warehouse-brain"

say()  { printf '%s\n' "$*"; }
die()  { printf '❌ %s\n' "$*" >&2; exit 2; }

SPEC=""; PROFILE="web"; DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="${2:?}"; shift 2 ;;
    --home)    DSH_HOME_DIR="${2:?}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) die "未知参数 $1" ;;
    *)  SPEC="$1"; shift ;;
  esac
done
[ -n "$SPEC" ] || die "缺少参数：tgz 或已解包的目录"

# ---- 1. 归一化成「包目录」 ----
case "$SPEC" in
  *.tgz|*.tar.gz)
    [ -f "$SPEC" ] || die "找不到文件 $SPEC"
    STAGE="${TMPDIR:-/tmp}/dwb-install-$$"
    mkdir -p "$STAGE" || die "无法创建 $STAGE"
    say "解包 $SPEC → $STAGE"
    tar xzf "$SPEC" -C "$STAGE" || die "解包失败"
    PKG_DIR="$STAGE/package"
    ;;
  *) PKG_DIR="$SPEC" ;;
esac
[ -f "$PKG_DIR/package.json" ] || die "$PKG_DIR 不是 npm 包目录（缺 package.json）"
VER="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$PKG_DIR/package.json" | head -1)"
NAME="$(sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$PKG_DIR/package.json" | head -1)"
[ "$NAME" = "$PKG_NAME" ] || die "包名不符：期望 $PKG_NAME，实际 $NAME"
say "包目录：$PKG_DIR（$NAME@$VER）"

PROFILE_DIR="$DSH_HOME_DIR/profiles/$PROFILE"
[ -d "$PROFILE_DIR" ] || die "profile 不存在：$PROFILE_DIR（先在 DSH 里用过 $PROFILE，或检查 --home）"
[ -f "$PROFILE_DIR/package.json" ] || die "$PROFILE_DIR 缺 package.json"
say "目标 profile：$PROFILE_DIR"

# ---- 2. 装依赖：优先用 dsh（它自带 pnpm），否则用 pnpm，最后退化为直接铺 node_modules ----
run() { if [ "$DRY" = 1 ]; then say "[dry-run] $*"; else "$@"; fi; }

INSTALLED=0
if command -v dsh >/dev/null 2>&1; then
  say "用 dsh 安装（内部转发 pnpm）"
  if [ "$DRY" = 1 ]; then say "[dry-run] dsh plugin --profile $PROFILE add file:$PKG_DIR"; else
    DSH_HOME="$DSH_HOME_DIR" dsh plugin --profile "$PROFILE" add "file:$PKG_DIR" && INSTALLED=1
  fi
fi
if [ "$INSTALLED" = 0 ] && command -v pnpm >/dev/null 2>&1; then
  say "用 pnpm 安装"
  ( cd "$PROFILE_DIR" && run pnpm add "file:$PKG_DIR" ) && INSTALLED=1
fi
if [ "$INSTALLED" = 0 ]; then
  DEST="$PROFILE_DIR/node_modules/$PKG_NAME"
  HAVE_VER="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$DEST/package.json" 2>/dev/null | head -1)"
  if [ "$HAVE_VER" = "$VER" ]; then
    say "已是 $VER，跳过复制（如需重装先删 $DEST）"
  else
    say "⚠ 未找到 dsh / pnpm，退化为直接铺包到 node_modules（面板与 preset 可用，但依赖树需人工复核）"
    if [ "$DRY" = 0 ]; then
      mkdir -p "$(dirname "$DEST")" && rm -rf "$DEST" && cp -R "$PKG_DIR" "$DEST" || die "复制失败"
      say "已复制到 $DEST"
    fi
  fi
fi

# ---- 3. 选中组合包（命令行安装不会自动选中；图形界面会） ----
say "检查 dsh.profile.bundles…"
PYTHONIOENCODING=utf-8 python3 - "$PROFILE_DIR/package.json" "$PKG_NAME" "$DRY" <<'PY' || exit 1
import json, os, shutil, sys
path, name, dry = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
with open(path, encoding="utf-8") as f:
    doc = json.load(f)
doc.setdefault("dsh", dict()).setdefault("profile", dict()).setdefault("bundles", [])
if name in doc["dsh"]["profile"]["bundles"]:
    print("  已选中，无需改动")
    sys.exit(0)
doc["dsh"]["profile"]["bundles"].append(name)
if dry:
    print("  [dry-run] 将追加：" + name)
    sys.exit(0)
shutil.copyfile(path, path + ".bak-dwb")
with open(path, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("  已追加组合包：" + name + "（旧文件备份为 package.json.bak-dwb）")
PY

# ---- 4. 校验 ----
if command -v dsh >/dev/null 2>&1 && [ "$DRY" = 0 ]; then
  N="$(DSH_HOME="$DSH_HOME_DIR" dsh --profile "$PROFILE" --dump-config 2>/dev/null | grep -c '^- id: preset-')"
  say "组合后 preset 行数：${N:-0}（期望 ≥28：4 官方 + 24 我方）"
  if [ "${N:-0}" -lt 24 ]; then say "⚠ preset 数偏少，请贴 --dump-config 的 stderr 排查"; exit 1; fi
fi

TARGET="$PKG_DIR"
[ -d "$PROFILE_DIR/node_modules/$PKG_NAME" ] && TARGET="$PROFILE_DIR/node_modules/$PKG_NAME"
say ""
say "✅ 完成：$NAME@$VER → profile「$PROFILE」"
say "   包内技能目录：$(find -L "$TARGET/skills" -name SKILL.md 2>/dev/null | wc -l | tr -d ' ') 个"
say "   下一步：重启该用户的 DSH 实例（preset 与客户端插件在启动时装配）"
say "   验证：新会话 Agent 选择器应出现「冶衡 Axis · 首席数仓编排师」，左侧栏出现「数仓专家团」"
