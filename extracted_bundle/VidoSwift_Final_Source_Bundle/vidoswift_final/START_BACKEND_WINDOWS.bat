@echo off
setlocal
cd /d "%~dp0backend"
set "PY=D:\python-3.12.8-amd64\python.exe"
if not exist "%PY%" (
  echo Python portable path not found: %PY%
  echo Edit this file and set PY to your python.exe path.
  pause
  exit /b 1
)
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto failed
"%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
exit /b 0
:failed
echo Backend dependencies could not be installed. Check internet access and pip output.
pause
exit /b 1
