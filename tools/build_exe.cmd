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
  --collect-submodules pystray ^
  --collect-submodules PIL ^
  --distpath dist ^
  --workpath build ^
  --specpath build ^
  tools\puppet_workspace.py
if errorlevel 1 exit /b %ERRORLEVEL%
echo 打包成功！EXE 产物已输出至 dist\PuppetWorkspace.exe
exit /b %ERRORLEVEL%