#requires -Version 7.0
# 共享探测：逐候选真实 import PySide6，取首个可用解释器（三处 dot-source 复用）
# 候选顺序：py -3.12 优先（与项目验证链同源），再 PATH 首个 python。
Set-StrictMode -Version Latest

function Test-PySide6([string]$Exe, [string]$Version) {
    if ($Version) { & $Exe $Version -c "import PySide6" 2>$null }
    else { & $Exe -c "import PySide6" 2>$null }
    return ($LASTEXITCODE -eq 0)
}

function Select-PySide6Interpreter {
    # 返回 @($exe, $ver)（$ver 为 '' 表示裸 python）；无可用者返回 $null
    foreach ($cand in @(@('py', '-3.12'), @('python', ''))) {
        if (Test-PySide6 $cand[0] $cand[1]) { return $cand }
    }
    return $null
}
