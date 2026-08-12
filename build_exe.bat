@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo A repository or product .venv\Scripts\python.exe was not found.
  echo Create the development environment before building.
  exit /b 1
)
set "PYINSTALLER_CONFIG_DIR=%~dp0build\PyInstallerCache"

"%PYTHON_EXE%" -B "%~dp0scripts\check_release_licenses.py" --final --exact-runtime
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
  --add-data "%~dp0data\buildings;data\buildings" ^
  --add-data "%~dp0data\talents;data\talents" ^
  --add-data "%~dp0data\ocr;data\ocr" ^
  --add-data "%~dp0data\research\catalog.json;data\research" ^
  --add-data "%~dp0data\research\master.json;data\research" ^
  --add-data "%~dp0data\research\locales;data\research\locales" ^
  --add-data "%~dp0dataset\generated;dataset\generated" ^
  --add-data "%~dp0resources;resources" ^
  --add-data "%~dp0licenses;licenses" ^
  --add-data "%~dp0LICENSE;." ^
  --add-data "%~dp0DATA_LICENSE.md;." ^
  "%~dp0main.py"
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON_EXE%" -B "%~dp0scripts\write_release_checksum.py" ^
  "%~dp0dist\RLMResearchPlanner.exe"
exit /b %ERRORLEVEL%
