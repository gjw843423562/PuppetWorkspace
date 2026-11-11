@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
python3 "%~dp0build_workspace.py" %*
exit /b %ERRORLEVEL%
