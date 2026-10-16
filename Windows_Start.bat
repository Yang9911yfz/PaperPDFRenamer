@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run Windows_Setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" paper_renamer.py %*
if errorlevel 1 pause
