# -*- coding: utf-8 -*-
"""Puppet 独立小工具入口；进程与配置由各工具自行管理。"""
from pathlib import Path
import os
import subprocess
import time

from tkinter import ttk
from puppet_workspace_widgets import action_button, panel, title
from puppet_hotkey_native import find_window, wake_existing


def hotkey_paths(root: Path):
    folder = root / "tools" / "快捷键工具"
    return folder / "PuppetHotkeys" / "PuppetHotkeys.exe", folder / "tools.json"


def launch_hotkey_tool(root: Path):
    executable, config = hotkey_paths(root)
    for path in (executable, config):
        if not path.is_file():
            raise FileNotFoundError(f"快捷键工具文件缺失：{path}")
    if wake_existing(config):
        return None
    return subprocess.Popen([str(executable), "--config", str(config)], cwd=str(config.parent), shell=False)


def finish_launch(app, text, error=None):
    app.hotkey_launch_pending = False
    button = getattr(app, "hotkey_launch_button", None)
    if button is not None and button.winfo_exists():
        button.configure(state="normal")
    app.status_text.set(text)
    if error is not None:
        app.report_error("快捷键工具启动失败", error)
    return True


def poll_launch(app, process, config, started):
    if find_window(config):
        wake_existing(config)
        return finish_launch(app, "快捷键窗口已打开（%.1f 秒）" % (time.perf_counter() - started))
    code = process.poll()
    if code is not None:
        error = RuntimeError("程序退出，退出码 %s；请查看快捷键工具 logs/hotkeys.log" % code)
        return finish_launch(app, "快捷键工具启动失败", error)
    if time.perf_counter() - started >= 15:
        error = TimeoutError("等待窗口超过 15 秒；请查看快捷键工具 logs/hotkeys.log")
        return finish_launch(app, "等待窗口超时", error)
    app.window.after(100, lambda: poll_launch(app, process, config, started))
    return True


def start_hotkey_tool(app):
    if getattr(app, "hotkey_launch_pending", False) is True:
        app.status_text.set("正在启动快捷键工具，请稍候…")
        return False
    app.hotkey_launch_pending = True
    app.status_text.set("正在启动快捷键工具，请稍候…")
    button = getattr(app, "hotkey_launch_button", None)
    if button is not None and button.winfo_exists():
        button.configure(state="disabled")
    try:
        started = time.perf_counter()
        process = launch_hotkey_tool(app.root_path)
        if process is None:
            return finish_launch(app, "已显示正在运行的快捷键窗口")
        config = hotkey_paths(app.root_path)[1]
        app.window.after(100, lambda: poll_launch(app, process, config, started))
        return True
    except OSError as exc:
        return finish_launch(app, "快捷键工具启动失败", exc)


def open_tool_target(app, target: str) -> None:
    try:
        executable, config = hotkey_paths(app.root_path)
        if target == "launch":
            start_hotkey_tool(app)
            return
        path = config.parent if target == "folder" else app.root_path / "docs" / "hotkey-tool.md"
        if not path.exists():
            raise FileNotFoundError(f"文件或目录缺失：{path}")
        os.startfile(str(path))
    except OSError as exc:
        app.report_error("快捷键工具操作失败", exc)


def build_tools(app, parent) -> None:
    title(parent, "快捷工具", "独立运行的日常工具。")
    box = panel(parent, "Puppet 全局快捷键工具")
    executable, config = hotkey_paths(app.root_path)
    ready = executable.is_file() and config.is_file()
    text = "已就绪" if ready else "工具文件不完整，请检查目录"
    ttk.Label(box, text=f"{text}\n用全局快捷键打开程序、目录和网址。", style="PanelText.TLabel").pack(anchor="w")
    actions = ttk.Frame(box, style="Panel.TFrame")
    actions.pack(fill="x", pady=(12, 0))
    app.hotkey_launch_button = action_button(actions, "启动快捷键工具", lambda: open_tool_target(app, "launch"), app.icon("home"), True)
    if getattr(app, "hotkey_launch_pending", False) is True:
        app.hotkey_launch_button.configure(state="disabled")
    action_button(actions, "打开配置目录", lambda: open_tool_target(app, "folder"), app.icon("folder"))
    action_button(actions, "原理与优化方案", lambda: open_tool_target(app, "docs"), app.icon("log"))
    ttk.Label(box, text="支持冲突提示、即时生效和配置备份。首次使用请退出旧版，释放相同热键。", style="PanelText.TLabel", wraplength=760).pack(anchor="w", pady=(10, 0))
