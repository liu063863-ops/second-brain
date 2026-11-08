@echo off
setlocal
chcp 65001 >nul
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
echo ============================================
echo  WeChat export - main account (targeted)
echo  Will close WeChat, relaunch a debugged copy,
echo  and wait for you to scan the QR code.
echo ============================================
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0wechat-export.ps1" -Method targeted -Days 3650
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%