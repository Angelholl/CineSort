#requires -Version 7.0
# 构建 Windows onedir 应用目录（与 SubTrans 同链：PyInstaller → Inno Setup 6）
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

. (Join-Path $PSScriptRoot '..\scripts\_pyside_probe.ps1')
$chosen = Select-PySide6Interpreter
if (-not $chosen) {
    Write-Host "未找到带 PySide6 的 Python（需 py -3.12 或已装 PySide6 的 python）。" -ForegroundColor Red
    exit 1
}
$exe, $ver = $chosen

# PyInstaller COLLECT 会整删 dist\CineSort，先备份实机测试产物（config + runtime
# 自学习/会话数据），构建后原样归还，避免每次重打包都从头开始（owner 2026-11-25）。
$appDir = Join-Path $root 'dist\CineSort'
$keepDir = Join-Path $root 'build\_user_data_keep'
$keepFiles = @('config.toml')
$keepDirs = @('runtime')
$backuped = $false
if (Test-Path $appDir) {
    $hasKeep = @($keepFiles | Where-Object { Test-Path (Join-Path $appDir $_) }).Count -gt 0 -or
               @($keepDirs | Where-Object { Test-Path (Join-Path $appDir $_) }).Count -gt 0
    if ($hasKeep) {
        if (Test-Path $keepDir) { Remove-Item $keepDir -Recurse -Force }
        New-Item $keepDir -ItemType Directory | Out-Null
        foreach ($f in $keepFiles) {
            $src = Join-Path $appDir $f
            if (Test-Path $src) { Copy-Item $src (Join-Path $keepDir $f) }
        }
        foreach ($d in $keepDirs) {
            $src = Join-Path $appDir $d
            if (Test-Path $src) { Copy-Item $src (Join-Path $keepDir $d) -Recurse -Force }
        }
        $backuped = $true
    }
}

& $exe $ver -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name CineSort `
    --add-data "config.example.toml;." `
    --icon "assets/icon/cinesort.ico" `
    --add-data "assets/icon/cinesort.ico;assets/icon" `
    run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败（退出码 $LASTEXITCODE）" }

if ($backuped) {
    foreach ($f in $keepFiles) {
        $b = Join-Path $keepDir $f
        if (Test-Path $b) { Copy-Item $b (Join-Path $appDir $f) -Force }
    }
    foreach ($d in $keepDirs) {
        $b = Join-Path $keepDir $d
        if (Test-Path $b) { Copy-Item $b (Join-Path $appDir $d) -Recurse -Force }
    }
    Remove-Item $keepDir -Recurse -Force
    Write-Host "已保留实机数据: config.toml + runtime\（自学习/会话）" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "构建完成: dist\CineSort\CineSort.exe" -ForegroundColor Green
