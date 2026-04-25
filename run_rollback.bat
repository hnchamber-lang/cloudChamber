@echo off
REM  Restore original layout from _archive_pre_reorg.
REM  Only works if --execute was run AND the archive has not been deleted.

setlocal
cd /d "%~dp0"
echo ============================================================
echo   ROLLBACK: restoring from D:\Chamber\_archive_pre_reorg
echo ============================================================
python reorganize.py --rollback
pause
endlocal
