@echo off
rem ===== Guga Penguin launcher (ASCII-only, safe under any codepage) =====
rem ===== Auto-elevate to admin (required for netcut / disconnect feature) =====

rem --- check admin (fltmc requires admin privileges) ---
fltmc >nul 2>&1 || (
    rem --- not admin: request UAC elevation ---
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

cd /d "%~dp0"
rem Existing apps are left running; close an old pet through its tray if needed.

rem ----- find python: python / py / full paths (must actually RUN, ignore Store alias) -----
set "PYTHON="
for %%C in (python py) do (
    if not defined PYTHON (
        where %%C >nul 2>&1 && %%C --version >nul 2>&1 && set "PYTHON=%%C"
    )
)
if not defined PYTHON if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYTHON if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"

if not defined PYTHON (
    echo [ERROR] Python 3.8+ not found. Install it and retry.
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)

rem ----- derive pythonw -----
if "%PYTHON%"=="python" (
    where pythonw >nul 2>&1 && set "PYTHONW=pythonw" || set "PYTHONW=python"
) else if "%PYTHON%"=="py" (
    set "PYTHONW=pyw"
) else (
    set "PYTHONW=%PYTHON:\python.exe=\pythonw.exe%"
)

echo [1/2] Checking dependencies...
"%PYTHON%" -c "import PyQt5, edge_tts" >nul 2>&1
if errorlevel 1 (
    echo [2/2] First run: installing dependencies, please wait...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency install failed. Check network and retry.
        pause
        exit /b 1
    )
)

echo Starting Guga Penguin (admin mode)...
start "" "%PYTHONW%" launcher.py
exit
