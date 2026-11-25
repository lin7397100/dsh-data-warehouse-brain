# publish_npm.ps1 —— 发布到 npm（前置自检 + 发布 + 验证）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\publish_npm.ps1            # 交互确认
#   powershell -ExecutionPolicy Bypass -File scripts\publish_npm.ps1 -Yes       # 跳过确认
#   powershell -ExecutionPolicy Bypass -File scripts\publish_npm.ps1 -Otp 123456
#
# 前置：npm login 已在本机完成（npm whoami 能出名字）；包名 scope 归你所有。
# 安全：本脚本不接受、不保存任何 token；登录请在终端里自己做。
param(
  [switch]$Yes,
  [string]$Otp = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Fail($msg) { Write-Host "`n❌ $msg" -ForegroundColor Red; exit 1 }

Write-Host "== 1. 登录状态 =="
$who = (npm whoami 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $who) { Fail "未登录：先在本机终端运行 npm login，再重跑本脚本" }
Write-Host "  已登录：$who"

Write-Host "== 2. 清单 =="
$man = Get-Content package.json -Raw | ConvertFrom-Json
$name = $man.name
$version = $man.version
Write-Host "  $name@$version"
if (-not $man.publishConfig -or $man.publishConfig.access -ne 'public') {
  Fail 'package.json 缺 publishConfig.access="public"（scoped 包否则会被当成私有）'
}

Write-Host "== 3. 包名一致性 + 发行校验 =="
python scripts/verify_package.py | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "verify_package.py 未通过，先修再发" }
Write-Host "  verify 通过"

Write-Host "== 4. 名字/版本占用 =="
$existing = (npm view "$name@$version" version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -eq 0 -and $existing) { Fail "$name@$version 已存在于 npm，请先 npm version patch" }
$scope = if ($name.StartsWith('@')) { $name.Split('/')[0].TrimStart('@') } else { '' }
if ($scope) { Write-Host "  scope=@$scope（必须归你所有，否则发布报 E404/E403）" }

Write-Host "== 5. 入包清单 =="
$packJson = (npm pack --dry-run --json 2>$null | Out-String) | ConvertFrom-Json
$files = $packJson[0].files
$size = [math]::Round($packJson[0].size / 1KB, 0)
Write-Host "  $($files.Count) 个文件，约 $size KB"
if ($files.Count -lt 300) { Fail "文件数异常（$($files.Count)），检查 package.json 的 files" }

if (-not $Yes) {
  Write-Host ""
  Write-Host "即将发布 $name@$version 到 https://registry.npmjs.org （公开）" -ForegroundColor Yellow
  $ans = Read-Host "输入 yes 继续"
  if ($ans -ne 'yes') { Write-Host '已取消'; exit 0 }
}

Write-Host "== 6. 发布 =="
$args = @('publish', '--access', 'public')
if ($Otp) { $args += @('--otp', $Otp) }
& npm @args
if ($LASTEXITCODE -ne 0) { Fail "npm publish 失败（见上方输出；2FA 需 -Otp，scope 不是你的会 E404/E403）" }

Write-Host "== 7. 验证 =="
$published = (npm view "$name" version 2>&1 | Out-String).Trim()
Write-Host "  registry 上的最新版：$published"
Write-Host ""
Write-Host "✅ 发布完成：https://www.npmjs.com/package/$name" -ForegroundColor Green
Write-Host "   用户安装：dsh plugin --profile web add $name@$version"
if ($scope) {
  Write-Host "   内网镜像：在用户 profile 的 .npmrc 写 @$scope`:registry=https://registry.npmmirror.com/"
}
