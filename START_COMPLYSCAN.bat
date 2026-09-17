@echo off
setlocal EnableExtensions
 title COMPLYSCAN Local Launcher

set "ROOT=%~dp0"
set "API_DIR=%ROOT%apps\api"
set "WEB_DIR=%ROOT%apps\web"

echo.
echo ============================================================
echo   COMPLYSCAN - Local Fixture/Demo Launcher
echo ============================================================
echo.

rem ---- Verify Python 3.12+ ----
set "PY_CMD=py -3.12"
%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 (
    set "PY_CMD=python"
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python 3.12 or newer was not found.
        echo Install Python 3.12 from https://www.python.org/downloads/
        echo During installation, enable "Add Python to PATH".
        goto :failed
    )
)

rem ---- Verify Node.js 20+ and npm ----
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js was not found.
    echo Install Node.js 20 LTS or newer from https://nodejs.org/
    goto :failed
)
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js 20 or newer is required.
    echo Install a current LTS release from https://nodejs.org/
    goto :failed
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm.cmd was not found. Reinstall Node.js with npm enabled.
    goto :failed
)

echo [1/5] Preparing the Python environment...
if not exist "%API_DIR%\.venv\Scripts\python.exe" (
    pushd "%API_DIR%"
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        popd
        echo [ERROR] Python virtual-environment creation failed.
        goto :failed
    )
    popd
)

"%API_DIR%\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%API_DIR%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed.
    goto :failed
)

if not exist "%API_DIR%\.env" (
    >"%API_DIR%\.env" (
        echo APP_ENV=development
        echo AUTH_MODE=demo
        echo VISION_PROVIDER=fixture
        echo ALLOW_MEMORY_FALLBACK=true
        echo DATABASE_URL=
        echo CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
    )
)

echo [2/5] Preparing the Next.js environment...
if not exist "%WEB_DIR%\.env.local" copy /Y "%WEB_DIR%\.env.local.example" "%WEB_DIR%\.env.local" >nul
pushd "%WEB_DIR%"
call npm.cmd install --no-audit --no-fund
if errorlevel 1 (
    popd
    echo [ERROR] Frontend dependency installation failed.
    goto :failed
)
popd

rem ---- Detect already-running local services ----
set "API_RUNNING=0"
set "WEB_RUNNING=0"
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 set "API_RUNNING=1"
netstat -ano | findstr /R /C:":3000 .*LISTENING" >nul 2>&1
if not errorlevel 1 set "WEB_RUNNING=1"

echo [3/5] Starting FastAPI on http://127.0.0.1:8000 ...
if "%API_RUNNING%"=="0" (
    start "COMPLYSCAN API - Ctrl+C to stop" /D "%API_DIR%" cmd.exe /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
) else (
    echo       Port 8000 is already in use; keeping the existing service.
)

echo [4/5] Starting Next.js on http://127.0.0.1:3000 ...
if "%WEB_RUNNING%"=="0" (
    start "COMPLYSCAN WEB - Ctrl+C to stop" /D "%WEB_DIR%" cmd.exe /k "npm.cmd run dev -- --hostname 127.0.0.1 --port 3000"
) else (
    echo       Port 3000 is already in use; keeping the existing service.
)

echo [5/5] Waiting for COMPLYSCAN to become ready...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddMinutes(3); $api=$false; $web=$false; do { try { $api=((Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3).StatusCode -eq 200) } catch { $api=$false }; try { $web=((Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 5).StatusCode -eq 200) } catch { $web=$false }; if($api -and $web){ exit 0 }; Start-Sleep -Seconds 2 } while((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo.
    echo [ERROR] COMPLYSCAN did not become ready within three minutes.
    echo Read the COMPLYSCAN API and COMPLYSCAN WEB windows for the exact error.
    goto :failed
)

echo.
echo COMPLYSCAN is ready.
echo Opening http://127.0.0.1:3000 ...
start "" "http://127.0.0.1:3000"
echo.
echo Keep the API and WEB windows open while using the app.
echo Press Ctrl+C inside each server window when you want to stop it.
echo.
pause
exit /b 0

:failed
echo.
echo Startup was not completed. Fix the message above and run
 echo START_COMPLYSCAN.bat again.
echo.
pause
exit /b 1
