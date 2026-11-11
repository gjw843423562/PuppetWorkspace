@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
python3 "%~dp0源码\启动快捷键工具.py" %*
exit /b %ERRORLEVEL%
