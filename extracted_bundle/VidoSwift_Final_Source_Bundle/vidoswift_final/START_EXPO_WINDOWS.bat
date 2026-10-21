@echo off
setlocal
cd /d "%~dp0app"
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js LTS and npm are required. Install Node.js, then retry.
  pause
  exit /b 1
)
if not exist node_modules (
  echo Installing Expo dependencies. This needs an internet connection and may take a few minutes...
  call npm install
  if errorlevel 1 goto failed
)
call npx expo start
pause
exit /b 0
:failed
echo npm install failed. Check the network and npm output, then retry.
pause
exit /b 1
