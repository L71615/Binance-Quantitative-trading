@echo off
REM ============================================================================
REM  Binance Spot Grid Trading Platform — one-shot launcher.
REM  - Activate / create Python venv
REM  - Install Python + frontend deps if missing
REM  - Start uvicorn :8000 and Vite :5173 in separate windows
REM  - Open browser to the UI
REM ============================================================================

setlocal

REM Always operate from this script's directory so paths resolve no matter where
REM the user double-clicks from.
cd /d "%~dp0"

REM ---------- Python venv ----------------------------------------------------
if not exist venv\Scripts\python.exe (
  echo [run.bat] Creating venv...
  python -m venv venv || goto :fail
  call venv\Scripts\activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt || goto :fail
) else (
  call venv\Scripts\activate
)

REM ---------- Frontend deps --------------------------------------------------
REM The frontend was renamed from web/ to frontend/ in commit ef75119. Keep the
REM launcher aligned with the on-disk folder; the spec example still says web/.
if not exist frontend\node_modules (
  echo [run.bat] Installing frontend deps...
  cd frontend
  call npm install || goto :fail
  cd ..
)

REM ---------- Data dir -------------------------------------------------------
if not exist data mkdir data

REM ---------- Start servers --------------------------------------------------
echo [run.bat] Starting uvicorn on :8000 ...
start "uvicorn" cmd /k "call venv\Scripts\activate && python -m uvicorn app.main:app --reload --port 8000"

REM Give uvicorn a moment to bind the port before Vite starts proxying to it.
timeout /t 3 /nobreak > nul

echo [run.bat] Starting Vite dev server on :5173 ...
start "vite" cmd /k "cd frontend && npm run dev"

REM Give Vite a moment to print its local URL before the browser opens.
timeout /t 4 /nobreak > nul

echo [run.bat] Opening browser ...
start "" http://localhost:5173

echo [run.bat] Done. Close the uvicorn / vite windows to stop the app.
exit /b 0

:fail
echo.
echo [run.bat] Setup failed. Check the messages above and rerun.
exit /b 1
