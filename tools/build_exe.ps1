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

& $exe $ver -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name CineSort `
    --add-data "config.example.toml;." `
    run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败（退出码 $LASTEXITCODE）" }

Write-Host ""
Write-Host "构建完成: dist\CineSort\CineSort.exe" -ForegroundColor Green
