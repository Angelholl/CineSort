#requires -Version 7.0
# CineSort 后台启动：起 PySide6 原生窗口（双击根目录 .cmd 即进入本脚本）
# 解释器探测复用共享脚本（PATH 首个 pythonw 可能装在无 PySide6 的环境）。
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

. (Join-Path $PSScriptRoot '_pyside_probe.ps1')
$chosen = Select-PySide6Interpreter
if (-not $chosen) {
    Write-Host "未找到带 PySide6 的 Python（需 py -3.12 或已装 PySide6 的 python）。" -ForegroundColor Red
    exit 1
}

# 窗口化：优先所选解释器同目录的 pythonw.exe（无控制台残留）
if ($chosen[1]) {
    $homeDir = (& $chosen[0] $chosen[1] -c "import sys,os; print(os.path.dirname(sys.executable))").Trim()
} else {
    $homeDir = (& $chosen[0] -c "import sys,os; print(os.path.dirname(sys.executable))").Trim()
}
$pythonw = Join-Path $homeDir 'pythonw.exe'
if (Test-Path $pythonw) {
    Start-Process -FilePath $pythonw -ArgumentList '-m', 'app.ui.main_window' -WorkingDirectory $root
} elseif ($chosen[1]) {
    Start-Process -FilePath $chosen[0] -ArgumentList $chosen[1], '-m', 'app.ui.main_window' -WorkingDirectory $root
} else {
    Start-Process -FilePath $chosen[0] -ArgumentList '-m', 'app.ui.main_window' -WorkingDirectory $root
}
Write-Host "CineSort 原生窗口已启动，关闭窗口即退出。"
