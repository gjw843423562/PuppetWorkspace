# -*- coding: utf-8 -*-
"""启动目标时保持路径与参数边界，不使用命令字符串拼接。"""
import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit


def target_path(text, base):
    expanded = os.path.expandvars(os.path.expanduser(text.strip()))
    path = Path(expanded)
    return path if path.is_absolute() else Path(base) / path


def launch_target(tool, base):
    raw = tool["Path"].strip()
    args = tool.get("Args", [])
    if urlsplit(raw).scheme.lower() in ("http", "https"):
        if args:
            raise ValueError("网址目标不接收 Args；请将网址放入浏览器工具的 Args")
        if webbrowser.open(raw) is False:
            raise OSError("没有可用的默认浏览器")
        return True
    path = target_path(raw, base)
    if not path.exists():
        raise FileNotFoundError("目标不存在：%s" % path)
    if path.is_dir():
        if args:
            raise ValueError("目录目标不能附带 Args")
        os.startfile(str(path))
        return True
    if path.suffix.lower() in (".exe", ".com"):
        subprocess.Popen([str(path)] + args, cwd=str(path.parent), shell=False)
        return True
    # ShellExecute 的参数与文件名分开传入，支持原配置中的 CMD/BAT 和关联文件。
    parameters = subprocess.list2cmdline(args) if args else None
    if parameters:
        import ctypes
        from ctypes import wintypes
        execute = ctypes.windll.shell32.ShellExecuteW
        execute.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                            wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
        execute.restype = ctypes.c_ssize_t
        if execute(None, "open", str(path), parameters, str(path.parent), 1) <= 32:
            raise OSError("无法启动目标：%s" % path)
        return True
    os.startfile(str(path))
    return True
