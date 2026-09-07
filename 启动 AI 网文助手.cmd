@echo off
setlocal
cd /d "%~dp0"

start "AIWebNovel Browser Opener" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\open_aiwebnovel_when_ready.ps1" -Port 8000
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start_integrated.ps1"

if errorlevel 1 (
  echo.
  echo AI 网文助手启动失败。请保留本窗口并把上面的错误信息发给维护者。
  pause
)
endlocal
