@echo off
setlocal
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
python3 "%SCRIPT_DIR%..\构建\build_workspace.py" %*
exit /b %ERRORLEVEL%
