param([switch]$SkipModels)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install it, then rerun setup.' }
    }
    & .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .\.venv\Scripts\python.exe -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency validation failed.' }
    if (-not $SkipModels) {
        & .\.venv\Scripts\python.exe -m arm_control --download-models
        if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
    }
    Write-Host 'Ready. Preview: .\scripts\run.ps1'
    Write-Host 'Live after firmware upload: .\scripts\run.ps1 -Port COM9'
} finally { Pop-Location }
