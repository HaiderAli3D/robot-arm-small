@echo off
setlocal
title Robot Arm Keyboard Controller
rem Change COM70 here if Windows assigns your ESP32 a different port.
set "ROBOT_ARM_PORT=COM70"
if not "%~1"=="" set "ROBOT_ARM_PORT=%~1"

echo Starting keyboard-only Robot Arm on %ROBOT_ARM_PORT%...
echo Click the controller window to use the keys. Space starts or pauses; Q quits.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-keyboard.ps1" -Port "%ROBOT_ARM_PORT%"
if errorlevel 1 (
    echo.
    echo The controller could not start or stopped with an error. See the message above.
    pause
    exit /b 1
)
endlocal
