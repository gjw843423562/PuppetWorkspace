@echo off
setlocal
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "%ROOT_DIR%"
python3 -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name PuppetWorkspace ^
  --distpath dist ^
  --workpath build ^
  --specpath build ^
  tools\puppet_workspace.py
exit /b %ERRORLEVEL%

