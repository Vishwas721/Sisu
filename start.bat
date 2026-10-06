@echo off
REM ============================================================================
REM  Sisu - start everything with one command
REM  Checks PostgreSQL, sets up Python + dashboard dependencies (first run only),
REM  starts Ollama if LLM drafts are enabled, then launches the dashboard and
REM  opens it in your browser. Close this window or press Ctrl+C to stop.
REM ============================================================================
setlocal
cd /d "%~dp0"
title Sisu
set "PY=.venv\Scripts\python.exe"
set "PORT=3000"

echo.
echo  ==== Sisu: starting up ====
echo.

REM ---- 1. Config ---------------------------------------------------------------
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo  [!] Created .env from .env.example.
    echo      Open .env, set DB_PASSWORD ^(and SENDER_ADDRESS / GOOGLE_PLACES_API_KEY^), then run start.bat again.
    notepad ".env"
    goto :fail
)

REM ---- 2. Python environment ---------------------------------------------------
where python >nul 2>&1 || (
    echo  [x] Python not found. Install Python 3.10+ from python.org and tick "Add to PATH".
    goto :fail
)
if not exist "%PY%" (
    echo  [..] Creating Python virtual environment...
    python -m venv .venv || goto :fail
)
REM Reinstall only when requirements.txt changed since the last successful install
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
    echo  [..] Installing Python packages...
    "%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
    copy /y requirements.txt .venv\requirements.installed >nul
)
if not exist ".venv\playwright.installed" (
    echo  [..] Installing Chromium for the scraper ^(one time^)...
    "%PY%" -m playwright install chromium || goto :fail
    echo done> .venv\playwright.installed
)
echo  [ok] Python ready

REM ---- 3. PostgreSQL -----------------------------------------------------------
call :port_open 127.0.0.1 5432
if errorlevel 1 (
    echo  [..] PostgreSQL is not running, trying to start its Windows service...
    powershell -NoProfile -Command "Get-Service postgresql* | Start-Service" >nul 2>&1
    timeout /t 3 /nobreak >nul
    call :port_open 127.0.0.1 5432
    if errorlevel 1 (
        echo  [x] Could not start PostgreSQL. Start it from Services ^(services.msc^),
        echo      or right-click start.bat and choose "Run as administrator".
        goto :fail
    )
)
echo  [ok] PostgreSQL running

"%PY%" pipeline.py --init-db >nul 2>&1 || (
    echo  [x] Could not connect to the database. Check DB_USER / DB_PASSWORD / DB_NAME in .env.
    "%PY%" pipeline.py --init-db
    goto :fail
)
echo  [ok] Database schema up to date

REM ---- 4. Ollama (only when LLM drafts are switched on) -------------------------
findstr /r /i /c:"^USE_LLM_DRAFTS=true" .env >nul 2>&1
if not errorlevel 1 (
    call :port_open 127.0.0.1 11434
    if errorlevel 1 (
        where ollama >nul 2>&1 && (
            echo  [..] Starting Ollama...
            start "Ollama" /min ollama serve
        ) || echo  [!] USE_LLM_DRAFTS=true but Ollama is not installed; drafts will use templates.
    )
)

REM ---- 5. Dashboard ------------------------------------------------------------
where npm >nul 2>&1 || (
    echo  [x] Node.js not found. Install it from nodejs.org.
    goto :fail
)
if not exist "dashboard\node_modules" (
    echo  [..] Installing dashboard packages ^(one time^)...
    pushd dashboard
    call npm install || (popd & goto :fail)
    popd
)

call :port_open 127.0.0.1 %PORT%
if not errorlevel 1 (
    echo  [!] Something is already running on port %PORT%. Opening it in your browser.
    start "" "http://127.0.0.1:%PORT%"
    goto :end
)

REM Open the browser once the dev server answers
start "" /b powershell -NoProfile -WindowStyle Hidden -Command ^
    "while (-not (Test-NetConnection 127.0.0.1 -Port %PORT% -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Sleep 1 }; Start-Process 'http://127.0.0.1:%PORT%'"

echo.
echo  ==== Dashboard: http://127.0.0.1:%PORT%  (Ctrl+C to stop) ====
echo.
pushd dashboard
REM Bound to 127.0.0.1 only: the dashboard can start scraping runs and has no login
call npm run dev -- -H 127.0.0.1 -p %PORT%
popd
goto :end

REM ---- helpers -----------------------------------------------------------------
:port_open
REM errorlevel 0 if host %1 accepts connections on port %2
powershell -NoProfile -Command "$c = New-Object Net.Sockets.TcpClient; try { $c.Connect('%~1', %~2); exit 0 } catch { exit 1 } finally { $c.Dispose() }" >nul 2>&1
exit /b %errorlevel%

:fail
echo.
echo  Startup stopped. Fix the issue above and run start.bat again.
pause
exit /b 1

:end
endlocal
