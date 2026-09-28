@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run START.cmd first to prepare Python.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 main.py login --fresh
set "result=%errorlevel%"
pause
exit /b %result%
