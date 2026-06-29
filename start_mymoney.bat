@echo off
setlocal
cd /d "%~dp0"

python -m mymoney.gui
if errorlevel 1 (
    echo.
    echo Failed to start myMoney. Make sure Python is installed and available in PATH.
    echo You can also try: py -m mymoney.gui
    echo.
    pause
)
