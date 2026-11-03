#requires -Version 7.0
# CineSort 调试启动：控制台前台运行，日志直出（额外参数透传给 app.ui.main_window）
# 同 start_gui.ps1：先探测带 PySide6 的解释器（PATH 首个 python 未必可用）。
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Test-PySide6([string]$Exe, [string]$Version) {
    if ($Version) { & $Exe $Version -c "import PySide6" 2>$null }
    else { & $Exe -c "import PySide6" 2>$null }
    return ($LASTEXITCODE -eq 0)
}

foreach ($cand in @(@('py', '-3.12'), @('python', ''))) {
    if (Test-PySide6 $cand[0] $cand[1]) {
        if ($cand[1]) { & $cand[0] $cand[1] -m app.ui.main_window @args }
        else { & $cand[0] -m app.ui.main_window @args }
        exit $LASTEXITCODE
    }
}
Write-Host "未找到带 PySide6 的 Python（需 py -3.12 或已装 PySide6 的 python）。" -ForegroundColor Red
exit 1
