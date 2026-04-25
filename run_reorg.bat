@echo off
REM  Execute the reorganization (renames + merges).
REM  Copies originals to _archive_pre_reorg first.

setlocal
cd /d "%~dp0"
echo ============================================================
echo   WARNING: This will rename/merge folders under D:\Chamber
echo   Originals will be archived to D:\Chamber\_archive_pre_reorg
echo ============================================================
echo.
python reorganize.py --execute
echo.
pause
endlocal
