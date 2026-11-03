#requires -Version 7.0
# 构建 Windows 单文件 exe（与 SubTrans 同链：PyInstaller → Inno Setup 6）
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name CineSort `
    --add-data "config.example.toml;." `
    run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败（退出码 $LASTEXITCODE）" }

Write-Host ""
Write-Host "构建完成: dist\CineSort.exe" -ForegroundColor Green
