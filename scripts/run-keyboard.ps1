param([string]$Port = '', [switch]$DryRun, [switch]$ListPorts)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        throw 'Run .\scripts\setup-keyboard.ps1 first.'
    }
    if ($DryRun -and $Port) { throw 'Choose either -DryRun or -Port, not both.' }
    if ($ListPorts -and ($Port -or $DryRun)) { throw 'Use -ListPorts on its own.' }
    $appArguments = @('-m', 'arm_control.keyboard_only')
    if ($ListPorts) {
        $appArguments += '--list-ports'
    } elseif ($Port) {
        $appArguments += @('--port', $Port)
    } else {
        $appArguments += '--dry-run'
    }
    & .\.venv\Scripts\python.exe @appArguments
    if ($LASTEXITCODE -ne 0) { throw "Keyboard controller exited with code $LASTEXITCODE." }
} finally { Pop-Location }
