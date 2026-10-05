@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run START.cmd first to prepare Python.
  pause
  exit /b 1
)
if exist "config.local.yaml" goto login
if exist "config.yaml" goto login
".venv\Scripts\python.exe" -X utf8 main.py init
if errorlevel 1 goto failed
:login
".venv\Scripts\python.exe" -X utf8 main.py login --fresh
set "result=%errorlevel%"
goto end
:failed
set "result=1"
:end
if not "%EDUCODER_NO_PAUSE%"=="1" pause
exit /b %result%
