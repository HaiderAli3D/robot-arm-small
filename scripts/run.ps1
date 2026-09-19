param([string]$Port = '', [int]$Camera = -1, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        throw 'Run .\scripts\setup.ps1 first.'
    }
    if ($DryRun -and $Port) { throw 'Choose either -DryRun or -Port, not both.' }
    $appArguments = @('-m', 'arm_control')
    if ($Port) { $appArguments += @('--port', $Port) } else { $appArguments += '--dry-run' }
    if ($Camera -ge 0) { $appArguments += @('--camera', [string]$Camera) }
    & .\.venv\Scripts\python.exe @appArguments
    if ($LASTEXITCODE -ne 0) { throw "Robot-arm app exited with code $LASTEXITCODE." }
} finally { Pop-Location }
