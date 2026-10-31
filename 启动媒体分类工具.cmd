@echo off
rem CineSort 后台启动（双击垫片，逻辑在 scripts\start_gui.ps1，需 PowerShell 7）
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_gui.ps1"
