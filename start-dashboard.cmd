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

"%PYTHON_EXE%" -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
  echo Dashboard packages are missing. Installing them now...
  echo.
  "%PYTHON_EXE%" -m pip install -e ".[dashboard]"
  if errorlevel 1 (
    echo.
    echo Dashboard package installation failed.
    pause
    exit /b 1
  )
  echo.
)

echo Starting the Legal Innovation Newsletter dashboard...
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
