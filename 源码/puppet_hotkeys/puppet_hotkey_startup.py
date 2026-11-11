# -*- coding: utf-8 -*-
"""只在用户点击设置时修改当前用户的新版工具自启项。"""
import subprocess
import sys
import winreg
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PuppetHotkeys"


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def set_startup(enabled, config_path):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            command = [sys.executable]
            if not getattr(sys, "frozen", False):
                from puppet_common.paths import workspace_root
                command.append(str(workspace_root() / "源码" / "启动快捷键工具.py"))
            command += ["--config", str(config_path.resolve()), "--silent"]
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    return True
