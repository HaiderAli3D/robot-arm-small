param([string]$ArduinoCli = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ArduinoCli) {
    $command = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if ($command) { $ArduinoCli = $command.Source }
    else { $ArduinoCli = Join-Path $env:ProgramFiles 'Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' }
}
if (-not (Test-Path -LiteralPath $ArduinoCli)) { throw 'Arduino CLI not found. Pass -ArduinoCli with its path.' }
Push-Location -LiteralPath $projectRoot
try {
    & $ArduinoCli compile --fqbn 'esp32:esp32:esp32c5:CDCOnBoot=default' --build-path (Join-Path $projectRoot 'build\esp32c5-tracking') (Join-Path $projectRoot 'ESP32C5_Tracking')
    if ($LASTEXITCODE -ne 0) { throw 'ESP32-C5 firmware compilation failed.' }
} finally { Pop-Location }
