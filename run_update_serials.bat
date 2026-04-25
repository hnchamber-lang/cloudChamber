@echo off
REM  After editing instruments.yaml to fill in previously-unknown serials,
REM  run this to rename folders under 01_instruments/ to match.

setlocal
cd /d "%~dp0"
python reorganize.py --update-serials
echo.
pause
endlocal
