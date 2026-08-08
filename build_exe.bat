@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo .venv\Scripts\python.exe was not found.
  echo Create the development environment before building.
  exit /b 1
)

"%PYTHON_EXE%" -B "%~dp0scripts\check_release_licenses.py"
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON_EXE%" -B -m PyInstaller --noconfirm --clean ^
  --name RLMResearchPlanner ^
  --onefile ^
  --windowed ^
  --version-file "%~dp0resources\windows_version_info.txt" ^
  --distpath "%~dp0dist" ^
  --workpath "%~dp0build\RLMResearchPlanner" ^
  --specpath "%~dp0build" ^
  --paths "%~dp0src" ^
  --add-data "%~dp0data;data" ^
  --add-data "%~dp0resources;resources" ^
  --add-data "%~dp0licenses;licenses" ^
  --add-data "%~dp0LICENSE;." ^
  --add-data "%~dp0DATA_LICENSE.md;." ^
  "%~dp0main.py"
exit /b %ERRORLEVEL%
