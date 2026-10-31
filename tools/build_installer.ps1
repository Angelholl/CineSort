#requires -Version 7.0
# 用 Inno Setup 6 把 dist\CineSort.exe 打成安装包（版本号经 /Dversion 注入，对齐 SubTrans）
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path "dist\CineSort.exe")) {
    throw "缺少 dist\CineSort.exe，请先运行 tools\build_exe.ps1"
}

$candidates = @()
foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if ($base) { $candidates += (Join-Path $base 'Inno Setup 6\ISCC.exe') }
}
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "未找到 Inno Setup 6（ISCC.exe）。" -ForegroundColor Yellow
    Write-Host "本机安装：winget install JRSoftware.InnoSetup 或 https://jrsoftware.org/isdl.php"
    Write-Host "免安装替代：推送 GitHub 后由 .github/workflows/release.yml 云端构建。"
    Write-Host "当前可先分发便携版 dist\CineSort.exe。"
    exit 1
}

$match = Select-String -Path "app\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"'
$ver = if ($match) { $match.Matches[0].Groups[1].Value } else { "0.4.0" }

& $iscc "/Dversion=$ver" "installer\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败（退出码 $LASTEXITCODE）" }

Write-Host ""
Write-Host "安装包输出: installer\Output\CineSort-setup-$ver.exe" -ForegroundColor Green
