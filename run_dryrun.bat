@echo off
REM  Generate rename_plan.csv (no filesystem changes).

setlocal
cd /d "%~dp0"
python reorganize.py --dry-run
echo.
echo Review:  %~dp0rename_plan.csv
pause
endlocal
