# -*- coding: utf-8 -*-
"""Puppet 独立快捷键工具入口。"""
import argparse
import logging
import sys
from pathlib import Path
from puppet_hotkey_config import read_config


def default_config():
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).resolve().parent
        if folder.name == "PuppetHotkeys":
            folder = folder.parent
        return folder / "tools.json"
    return Path(__file__).resolve().parent / "快捷键工具" / "tools.json"


def main():
    parser = argparse.ArgumentParser(description="Puppet 独立快捷键工具")
    parser.add_argument("--config", type=Path, default=default_config(), help="配置文件路径")
    parser.add_argument("--silent", action="store_true", help="热键成功注册后隐藏到托盘")
    parser.add_argument("--check", action="store_true", help="只校验配置，不注册热键、不保存")
    parser.add_argument("--no-tray", action="store_true", help="调试模式：关闭窗口即退出")
    args = parser.parse_args()
    if args.check:
        config, _ = read_config(args.config)
        print("配置校验通过：%d 个工具" % len(config["Tools"]), flush=True)
        return 0
    from puppet_hotkey_native import InstanceGuard
    from puppet_hotkey_ui import HotkeyApp
    from puppet_hotkey_diagnostics import configure_logging
    configure_logging(args.config.resolve().parent / "logs")
    guard = InstanceGuard(args.config)
    try:
        if guard.existing:
            if guard.wake() is False:
                raise RuntimeError("已有实例正在启动，请稍后再次打开")
            return 0
        app = HotkeyApp(args.config.resolve(), guard.title, args.silent, not args.no_tray)
        app.run()
        return 0
    finally:
        guard.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        logging.getLogger("puppet.hotkeys").exception("启动失败")
        import tkinter as tk
        from tkinter import messagebox
        window = tk.Tk()
        window.withdraw()
        messagebox.showerror("快捷键工具启动失败", str(error), parent=window)
        window.destroy()
        sys.exit(1)
