@echo off
setlocal
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
python3 "%SCRIPT_DIR%puppet_workspace.py" %*
if errorlevel 1 exit /b %ERRORLEVEL%
exit /b 0

