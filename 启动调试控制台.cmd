@echo off
rem CineSort 调试控制台（双击垫片，逻辑在 scripts\start_debug.ps1，需 PowerShell 7）
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_debug.ps1" %*
pause
