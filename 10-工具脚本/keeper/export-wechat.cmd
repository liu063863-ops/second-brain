@echo off
setlocal
chcp 65001 >nul
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell.exe"

echo ============================================
echo  chatlog-keeper : local WeChat export
echo ============================================
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0wechat-export.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%1"=="" pause
exit /b %RC%
