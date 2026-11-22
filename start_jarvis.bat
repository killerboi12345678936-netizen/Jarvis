@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe

if not exist %PY% (
  echo Python venv not found. Create it first:
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

echo ==============================================
echo           JARVIS v1.1 - starting
echo ==============================================
echo.

for /f "usebackq delims=" %%i in (`%PY% scripts\launcher_info.py`) do (
  for /f "tokens=1,2 delims==" %%a in ("%%i") do set "%%a=%%b"
)

if "%SCHEME%"=="" set SCHEME=http
if "%LANIP%"=="" set LANIP=127.0.0.1

echo Laptop LAN IP found : %LANIP%
echo Device code         : %TOKEN%
echo Access type         : %SCHEME% (HTTPS when dev certificates exist)

if "%OLLAMA%"=="up" (
  echo Ollama service      : running [%OLLAMA_MODELS%]
) else (
  echo Ollama service      : NOT RUNNING - chat will fail until you start Ollama.
)

echo.

REM The backend always listens on plain HTTP locally; the Vite dev
REM server terminates HTTPS (when certs exist) and proxies /api to
REM it, so the browser only ever sees one trusted origin.
echo Starting Jarvis backend on port 8000...
start "Jarvis Backend" cmd /k "%PY% -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"

echo Starting Jarvis frontend on port 5173...
start "Jarvis Frontend" cmd /k "cd frontend\web && npm run dev"

echo Waiting for the backend to become healthy...
%PY% scripts\wait_backend.py http
if errorlevel 1 (
  echo.
  echo WARNING: backend did not become healthy in 30 seconds.
  echo Check the "Jarvis Backend" window for the error.
) else (
  echo Backend is READY.
)

start "" %SCHEME%://localhost:5173/

echo.
echo ==============================================
echo    HOW TO CONNECT
echo ==============================================
echo.
echo  DESKTOP (this laptop):
echo    %SCHEME%://localhost:5173/
echo    First visit on HTTPS: click through the certificate warning
echo    (Chrome: type "thisisunsafe" on the warning page if needed).
echo.
echo  PHONE / ANDROID (same Wi-Fi):
echo    1. Connect the phone to the same home Wi-Fi network.
echo    2. Open  %SCHEME%://%LANIP%:5173/
echo    3. When asked, enter the device code shown above
echo       (also saved in data\device_token.txt).
echo    4. Install the app: Chrome menu ^> "Add to Home screen".
echo.
echo    Microphone on the phone needs HTTPS. If data\certs\dev.crt
echo    exists it is already used; for warning-free access install
echo    data\certs\dev.crt on the phone as a CA certificate once.
echo    Run  %PY% scripts\make_dev_cert.py  if you need to create it.
echo.
echo  SECURITY NOTES:
echo    - Every device must present the device code; unauthorized
echo      requests are rejected with 401 / WS close 4401.
echo    - If Windows Firewall asks about Python or Node, allow access
echo      for PRIVATE networks only (do not allow public networks).
echo    - Nothing is exposed to the internet; this works only on
echo      your home Wi-Fi.
echo.
echo  Two new windows are open. Keep BOTH running; closing them
echo  stops Jarvis. If the page says "Backend offline", wait a few
echo  seconds - it reconnects automatically.
echo.
pause
