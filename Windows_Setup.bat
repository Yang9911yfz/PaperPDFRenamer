@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python setup.py
) else (
  py -3 setup.py
)
if errorlevel 1 echo Setup failed. Install Python from https://www.python.org/downloads/ and try again.
pause
