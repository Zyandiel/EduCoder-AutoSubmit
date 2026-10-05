@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:use_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -c "import playwright.sync_api, yaml" >nul 2>nul
if not errorlevel 1 goto run
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:run
if exist "config.local.yaml" goto configured
if exist "config.yaml" goto configured
".venv\Scripts\python.exe" -X utf8 main.py init
if errorlevel 1 goto failed
echo Edit config.local.yaml and prepare your solutions, then run START.cmd again.
set "result=0"
goto end
:configured
".venv\Scripts\python.exe" -X utf8 main.py auto %*
set "result=%errorlevel%"
echo.
if "%result%"=="0" (echo Finished. See logs for details.) else (echo Stopped or incomplete. See the messages above and logs.)
goto end
:no_python
echo Install Python 3.11 or newer, then run START.cmd again.
goto failed
:failed
set "result=1"
echo Setup failed. Check Python, network, and requirements.txt.
:end
if not "%EDUCODER_NO_PAUSE%"=="1" pause
exit /b %result%
