$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\setup.ps1 first.' }
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
    & (Join-Path $PSScriptRoot 'test-firmware.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Firmware native tests failed.' }
} finally { Pop-Location }
