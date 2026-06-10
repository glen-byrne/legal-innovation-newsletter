@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "DASHBOARD_ALLOW_NO_AUTH=true"
set "DASHBOARD_COOKIE_SECURE=false"
set "DASHBOARD_PORT=8002"

if not exist "%PYTHON_EXE%" (
  echo Could not find the bundled Codex Python runtime:
  echo %PYTHON_EXE%
  echo.
  echo Open this project in Codex once, or install Python and update this launcher.
  pause
  exit /b 1
)

echo Starting The Irish Legal Innovator dashboard...
echo.
echo Dashboard address:
echo http://127.0.0.1:%DASHBOARD_PORT%/
echo.
echo Leave this window open while using the dashboard.
echo Press Ctrl+C in this window when finished.
echo.

start "" "http://127.0.0.1:%DASHBOARD_PORT%/"
"%PYTHON_EXE%" -m uvicorn legal_innovator.dashboard.app:app --host 127.0.0.1 --port %DASHBOARD_PORT% --reload

pause
