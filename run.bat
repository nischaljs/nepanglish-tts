@echo off
REM Double-click entry point for Windows users. Forwards to run.ps1
REM and pauses on exit so any error message stays visible.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
echo.
echo (Press any key to close this window.)
pause >nul
