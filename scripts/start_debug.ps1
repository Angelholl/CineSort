#requires -Version 7.0
# CineSort 调试启动：控制台前台运行，日志直出（额外参数透传给 app.ui.main_window）
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m app.ui.main_window @args
