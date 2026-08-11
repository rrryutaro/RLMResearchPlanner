@echo off
setlocal
set "TOOL_DIR=%~dp0"
set "REPO_PYTHON=%TOOL_DIR%..\..\.venv\Scripts\python.exe"

if exist "%REPO_PYTHON%" (
  "%REPO_PYTHON%" -B "%TOOL_DIR%main.py"
) else (
  py -3 -B "%TOOL_DIR%main.py"
)

if errorlevel 1 pause
