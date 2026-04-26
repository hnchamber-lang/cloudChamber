@echo off
REM Chamber Reorganization - Integrity Verifier
REM Force UTF-8 console + Python I/O so logs are consistent regardless of
REM how the user redirected output (cmd vs PowerShell vs Windows Terminal).

setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

cd /d "%~dp0"

echo ===================================================
echo  Chamber Reorganization - Integrity Verifier
echo ===================================================
echo This will check that all files in the archive backup
echo perfectly match files in the active folders.
echo This may take a few minutes depending on disk speed.
echo.

python verify_integrity.py %*
pause
endlocal
