@echo off
echo ===================================================
echo  Chamber Reorganization - Integrity Verifier
echo ===================================================
echo This will check that all files in the archive backup
echo perfectly match files in the active folders.
echo This may take a few minutes depending on disk speed.
echo.
python verify_integrity.py
pause
