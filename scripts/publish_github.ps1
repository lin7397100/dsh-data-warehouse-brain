# publish_github.ps1 —— 把本仓库推到 GitHub（纯 SSH，不碰任何密码/令牌）
#
# 前置：仓库必须已在 GitHub 上**创建为空仓**（不要勾 README/.gitignore/LICENSE），
#       且本机 SSH 公钥已加到 GitHub → Settings → SSH and GPG keys。
#       本机 ssh config 已把 github.com 指向 ssh.github.com:443（22 端口被封时用）。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\publish_github.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\publish_github.ps1 -Owner lin7397100 -Repo dsh-data-warehouse-brain
param(
  [string]$Owner = 'lin7397100',
  [string]$Repo  = 'dsh-data-warehouse-brain'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:GIT_TERMINAL_PROMPT = '0'
$remote = "git@github.com:$Owner/$Repo.git"

$existing = (git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $existing) {
  git remote add origin $remote
  Write-Host "已设置 origin → $remote"
} elseif ($existing -ne $remote) {
  git remote set-url origin $remote
  Write-Host "已改 origin → $remote（原：$existing）"
} else {
  Write-Host "origin 已是 $remote"
}

# 仓库不存在时这里会报 Repository not found，先建空仓再跑
$probe = (git ls-remote --heads $remote 2>&1)
if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ 远端不可用：$probe" -ForegroundColor Red
  Write-Host "   请先到 https://github.com/new 建空仓 $Repo（不要初始化 README）" -ForegroundColor Yellow
  exit 1
}

Write-Host "远端可达，开始推送…"
git push -u origin main
if ($LASTEXITCODE -ne 0) { Write-Host "❌ push 失败" -ForegroundColor Red; exit 1 }
git push --tags
if ($LASTEXITCODE -ne 0) { Write-Host "⚠ tag 推送失败（可忽略，或先 git tag v1.0.0）" -ForegroundColor Yellow }

Write-Host ""
Write-Host "✅ 完成：https://github.com/$Owner/$Repo" -ForegroundColor Green
Write-Host "   安装：设置 → 插件 → 安装插件 → https://github.com/$Owner/$Repo"
Write-Host "   或：  dsh plugin --profile web add github:$Owner/$Repo"
