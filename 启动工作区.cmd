@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
python3 "%~dp0源码\启动工作区.py" %*
exit /b %ERRORLEVEL%
