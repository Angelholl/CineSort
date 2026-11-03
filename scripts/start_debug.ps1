#requires -Version 7.0
# CineSort 调试启动：控制台前台运行，日志直出（额外参数透传给 app.ui.main_window）
# 同 start_gui.ps1：先探测带 PySide6 的解释器（复用共享探测脚本）。
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

. (Join-Path $PSScriptRoot '_pyside_probe.ps1')
$chosen = Select-PySide6Interpreter
if ($chosen) {
    if ($chosen[1]) { & $chosen[0] $chosen[1] -m app.ui.main_window @args }
    else { & $chosen[0] -m app.ui.main_window @args }
    exit $LASTEXITCODE
}
Write-Host "未找到带 PySide6 的 Python（需 py -3.12 或已装 PySide6 的 python）。" -ForegroundColor Red
exit 1
