@echo off
setlocal
title TeachDesk setup and launcher
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Creating a Python 3.12 environment...
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)
if not exist ".venv\teachdesk-0.1.1.ready" (
    echo Installing TeachDesk requirements. Please wait...
    ".venv\Scripts\python.exe" -m pip install -c constraints.txt -e . pytest==9.1.1
    if errorlevel 1 goto failed
    ".venv\Scripts\python.exe" -m pip check
    if errorlevel 1 goto failed
    > ".venv\teachdesk-0.1.1.ready" echo installed
)
echo Starting TeachDesk. Keep this window open while the app runs.
".venv\Scripts\python.exe" -m teachdesk.ui
if errorlevel 1 goto failed
popd
exit /b 0
:failed
echo.
echo Setup or startup failed. Keep this error output for troubleshooting.
echo Python 3.12 must be installed. Close any other TeachDesk instance.
pause
popd
exit /b 1
