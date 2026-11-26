#!/usr/bin/env bash
# diagnose-panel.sh —— 面板报「响应不是 JSON」时，10 秒定位是"后端没挂"还是"代理吞了"
#
# 面板前端（client.js）与后端（index.js 注册的 /dwb-team/api/*）是两半：
#   前端能显示页签 = 插件 bundle 已选中、client 已加载
#   后端返回非 JSON（404 空体 / 反代回落到 index.html）= host 半没挂上
# 本脚本逐项打点，直接把结论打出来。
#
# 用法：
#   ./diagnose-panel.sh                       # 默认 http://127.0.0.1:5000
#   ./diagnose-panel.sh http://10.233.2.32:5000
#   ./diagnose-panel.sh http://127.0.0.1:3301 --cookie 'xxx=yyy'
#
# 退出码：0 全部正常；1 发现问题（看输出的 ❌ 行）
set -uo pipefail

BASE="${1:-http://127.0.0.1:5000}"
COOKIE=""
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --cookie) COOKIE="${2:?}"; shift 2 ;;
    *) shift ;;
  esac
done

CURL=(curl -sS --max-time 15)
[ -n "$COOKIE" ] && CURL+=(-H "Cookie: $COOKIE")

pass=0; fail=0
ok()   { printf '  ✅ %s\n' "$*"; pass=$((pass+1)); }
bad()  { printf '  ❌ %s\n' "$*"; fail=$((fail+1)); }
info() { printf '  ℹ  %s\n' "$*"; }

probe() { # probe <path> → 打印 "HTTP|CTYPE|是否JSON|前120字"
  local path="$1" out code ctype body
  out=$("${CURL[@]}" -o /tmp/dwbprobe.$$ -w '%{http_code}|%{content_type}' "$BASE$path" 2>&1) || out="000|"
  code="${out%%|*}"; ctype="${out#*|}"
  body=$(head -c 400 /tmp/dwbprobe.$$ 2>/dev/null | tr -d '\r')
  rm -f /tmp/dwbprobe.$$
  local isjson="no"
  case "$body" in
    \{*|\[*) isjson="yes" ;;
  esac
  printf '%s|%s|%s|%s' "$code" "$ctype" "$isjson" "$(printf '%s' "$body" | head -c 120 | tr '\n' ' ')"
}

printf '=== 1. 面板后端是否挂上（关键）===\n'
IFS='|' read -r code ctype isjson snippet <<<"$(probe /dwb-team/api/root)"
if [ "$code" = "200" ] && [ "$isjson" = "yes" ]; then
  ok "GET /dwb-team/api/root → 200 JSON"
  info "$snippet"
elif [ "$code" = "401" ]; then
  ok "路由已挂，但需要登录态（401 JSON）——浏览器里带 cookie 才有数据"
  info "浏览器打开 http://<host>:<port>/?token=... 后刷新即可"
elif [ "$code" = "404" ] && [ "$isjson" = "no" ]; then
  bad "GET /dwb-team/api/root → 404 且非 JSON：**host 半没有注册路由**"
  info "常见原因：装了包但没重启 / bundle 没被选中 / 与其它实例抢同一 DSH_HOME"
elif printf '%s' "$snippet" | grep -qi '<!doctype\|<html'; then
  bad "返回的是 HTML（反代回落 index.html）——**代理没转发 /dwb-team/**"
  info "结论：前置 nginx 的 try_files 把未知路径回落到前端了，需要加 location /dwb-team/"
else
  bad "GET /dwb-team/api/root → HTTP $code（$ctype）"
  info "$snippet"
fi

printf '\n=== 2. 其余 API ===\n'
for p in /roster /overview /registry /chains /mcp; do
  IFS='|' read -r code ctype isjson snippet <<<"$(probe "/dwb-team/api$p")"
  if [ "$code" = "200" ] && [ "$isjson" = "yes" ]; then
    ok "$p → 200"
  elif [ "$code" = "401" ]; then
    info "$p → 401（未登录，属正常）"
  else
    bad "$p → $code 非JSON=$( [ "$isjson" = no ] && echo yes || echo no )"
  fi
done

printf '\n=== 3. 客户端插件是否下发 ===\n'
IFS='|' read -r code ctype isjson snippet <<<"$(probe /)"
if [ "$code" = "200" ]; then
  if "${CURL[@]}" "$BASE/" 2>/dev/null | grep -q 'dsh-data-warehouse-brain/client.js'; then
    ok "首页启动图包含本插件 client.js"
  else
    bad "首页启动图里没有 @sansteel/dsh-data-warehouse-brain/client.js"
    info "→ bundle 未被选中（dsh.profile.bundles 里缺这一行），或需重启"
  fi
else
  bad "首页 HTTP $code"
fi

printf '\n=== 4. 团队根供给 ===\n'
ROOT="${DSH_HOME:-$HOME/.dsh}/dwb-team"
if [ -d "$ROOT" ]; then
  ok "团队根存在：$ROOT"
  for f in agents skills tools scripts panel/roster.json .dwb-version; do
    [ -e "$ROOT/$f" ] && info "  $f ✓" || bad "  $f 缺失"
  done
  [ -f "$ROOT/.dwb-version" ] && info "  版本标记：$(cat "$ROOT/.dwb-version")"
else
  bad "团队根不存在：$ROOT（host 半从未激活过）"
fi

printf '\n=== 5. 同机多实例检查 ===\n'
if command -v ps >/dev/null 2>&1; then
  n=$(ps -eo args 2>/dev/null | grep -c '[l]ib/bin.js --profile' || true)
  [ "${n:-0}" -le 1 ] && ok "本机 DSH 进程数：${n:-0}" || {
    bad "本机有 $n 个 DSH 实例在跑"
    info "多实例共享同一 DSH_HOME 会互相覆盖 bundle 选择，建议每实例独立 --profile"
  }
fi

printf '\n--------------------------------------------\n'
if [ "$fail" -eq 0 ]; then
  printf '✅ 全部正常（%d 项通过）\n' "$pass"; exit 0
else
  printf '❌ %d 项异常（%d 项通过）\n' "$fail" "$pass"
  printf '\n修复顺序建议：\n'
  printf '  1) 确认 dsh.profile.bundles 含 @sansteel/dsh-data-warehouse-brain 并重启该实例\n'
  printf '  2) 若走 nginx：加 location /dwb-team/ { proxy_pass http://127.0.0.1:<dsh端口>; }\n'
  printf '  3) 同机多实例：给每个实例独立 DSH_HOME 或独立 profile\n'
  exit 1
fi
