@echo off
setlocal
cd /d "%~dp0"
python preflight.py
pause
endlocal
