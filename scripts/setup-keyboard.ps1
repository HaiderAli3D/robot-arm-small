$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install it, then rerun setup.' }
    }
    & .\.venv\Scripts\python.exe -m pip install pyserial==3.5
    if ($LASTEXITCODE -ne 0) { throw 'Serial dependency installation failed.' }
    & .\.venv\Scripts\python.exe -c "import serial; import tkinter; print('Keyboard controller dependencies are ready.')"
    if ($LASTEXITCODE -ne 0) { throw 'Install Python with Tcl/Tk support, then rerun setup.' }
    Write-Host 'Ready. Preview: .\scripts\run-keyboard.ps1'
    Write-Host 'Live after firmware upload: .\scripts\run-keyboard.ps1 -Port COM9'
    Write-Host 'Double-click Start Robot Arm Keyboard.cmd for future launches (default COM70).'
} finally { Pop-Location }
