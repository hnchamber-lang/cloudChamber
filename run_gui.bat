@echo off
REM  Launch the Chamber Project Builder GUI.
REM  Double-click this file or run from a shortcut.

setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not on PATH.
    echo Install Python 3.10+ from https://www.python.org/ and re-run.
    pause
    exit /b 1
)

python -c "import PyQt5, yaml" 2>nul
if errorlevel 1 (
    echo [info] Installing required packages ^(pyyaml, PyQt5^) ...
    python -m pip install --quiet pyyaml PyQt5
    if errorlevel 1 (
        echo [ERROR] Package install failed.
        pause
        exit /b 1
    )
)

start "" pythonw chamber_gui.py
endlocal
