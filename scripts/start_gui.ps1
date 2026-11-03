#requires -Version 7.0
# CineSort 后台启动：起 PySide6 原生窗口（双击根目录 .cmd 即进入本脚本）
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$pythonw = Get-Command pythonw -ErrorAction SilentlyContinue
if ($pythonw) {
    Start-Process -FilePath $pythonw.Source -ArgumentList '-m', 'app.ui.main_window' -WorkingDirectory $root
} else {
    Start-Process -FilePath 'python' -ArgumentList '-m', 'app.ui.main_window' -WorkingDirectory $root
}
Write-Host "CineSort 原生窗口已启动，关闭窗口即退出。"
