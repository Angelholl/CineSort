#requires -Version 7.0
# CineSort 后台启动：无窗口运行 GUI，自动打开浏览器（双击根目录 .cmd 即进入本脚本）
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$pythonw = Get-Command pythonw -ErrorAction SilentlyContinue
if ($pythonw) {
    Start-Process -FilePath $pythonw.Source -ArgumentList '-m', 'app.main_gui' -WorkingDirectory $root
} else {
    Start-Process -FilePath 'python' -ArgumentList '-m', 'app.main_gui' -WorkingDirectory $root
}
Write-Host "CineSort 已在后台启动，浏览器将自动打开（关闭系统托盘 pythonw 或任务管理器结束进程即退出）。"
