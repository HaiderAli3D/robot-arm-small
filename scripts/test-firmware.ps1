param([string]$Compiler = 'C:\mingw64\bin\g++.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sketch = Join-Path $root 'ESP32C5_Tracking/ESP32C5_Tracking.ino'
$controller = Join-Path $root 'ESP32C5_Tracking/Controller.h'
if (!(Test-Path -LiteralPath $sketch) -or !(Test-Path -LiteralPath $controller)) {
    throw 'Canonical ESP32C5_Tracking firmware files are missing.'
}
if (!(Select-String -LiteralPath $sketch -SimpleMatch '#include "Controller.h"' -Quiet)) {
    throw 'Canonical tracking sketch must use the tested production Controller.h.'
}
$build = Join-Path $root 'build/firmware-tests'
New-Item -ItemType Directory -Force -Path $build | Out-Null
$binary = Join-Path $build 'controller_test.exe'
& $Compiler -std=c++11 -Wall -Wextra -Werror -pedantic (Join-Path $root 'tests/firmware/controller_test.cpp') -o $binary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $binary
exit $LASTEXITCODE
