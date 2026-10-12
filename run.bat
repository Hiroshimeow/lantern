@echo off
setlocal
set "SCRIPT=%~dp0tools\run_lantern.ps1"
if not exist "%SCRIPT%" (
    echo [Lantern] Missing launcher: "%SCRIPT%"
    pause
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -RepoRoot "%~dp0." %*
set "STATUS=%ERRORLEVEL%"
if not "%STATUS%"=="0" (
    echo [Lantern] Startup failed. Press any key to close.
    pause >nul
)
exit /b %STATUS%
