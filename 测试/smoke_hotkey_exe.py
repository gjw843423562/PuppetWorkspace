# -*- coding: utf-8 -*-
"""用临时配置验收打包 EXE，不使用用户的真实快捷键目标。"""
import argparse
import ctypes
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from ctypes import wintypes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "源码"))
from puppet_hotkeys.puppet_hotkey_native import InstanceGuard, api, wake_existing


def wait_window(process, title):
    user = ctypes.WinDLL("user32")
    find = api(user, "FindWindowW", [wintypes.LPCWSTR, wintypes.LPCWSTR], wintypes.HWND)
    for attempt in range(100):
        if process.poll() is not None:
            raise RuntimeError("打包程序提前退出：%s" % process.returncode)
        handle = find(None, title)
        if handle:
            return handle
        time.sleep(0.1)
    raise TimeoutError("10 秒内未找到测试窗口")


def exercise(executable, folder):
    config = folder / "tools.json"
    data = {"MainHotkey": "Ctrl+Alt+Shift+F24", "Tools": []}
    config.write_text(json.dumps(data), encoding="utf-8")
    subprocess.run([str(executable), "--config", str(config), "--check"], check=True, timeout=15)
    # 只获取标题；立即关闭 guard，不能由测试抢占正式实例。
    guard = InstanceGuard(config)
    title = guard.title
    guard.close()
    started = time.perf_counter()
    process = subprocess.Popen([str(executable), "--config", str(config), "--no-tray"])
    handle = None
    try:
        handle = wait_window(process, title)
        startup_seconds = time.perf_counter() - started
        time.sleep(0.5)
        wake_started = time.perf_counter()
        if wake_existing(config) is False:
            raise RuntimeError("已运行窗口未能直接唤醒")
        wake_seconds = time.perf_counter() - wake_started
        subprocess.run([str(executable), "--config", str(config)], check=True, timeout=15)
        if process.poll() is not None:
            raise RuntimeError("重复启动后主实例退出")
        log = (folder / "logs" / "hotkeys.log").read_text(encoding="utf-8")
        crash = (folder / "logs" / "crash.log").read_text(encoding="utf-8")
        if "ERROR" in log or "Traceback" in crash or "Fatal Python" in crash:
            raise RuntimeError("运行日志包含错误：%s\n%s" % (log, crash))
        print("EXE 验收通过：配置校验、窗口启动、重复启动唤醒、运行和崩溃日志", flush=True)
        print(json.dumps({"exe": str(executable), "window_seconds": round(startup_seconds, 3),
                          "direct_wake_seconds": round(wake_seconds, 4)}, ensure_ascii=False), flush=True)
    finally:
        if handle:
            user = ctypes.WinDLL("user32")
            post = api(user, "PostMessageW", [wintypes.HWND, wintypes.UINT,
                       wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL)
            post(handle, 0x0010, 0, 0)
        process.wait(timeout=10)
    return True


def main():
    parser = argparse.ArgumentParser(description="隔离验收快捷键 EXE")
    from puppet_common.paths import HOTKEY_EXE
    parser.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[1] / HOTKEY_EXE)
    args = parser.parse_args()
    if not args.exe.is_file():
        raise FileNotFoundError(str(args.exe))
    with tempfile.TemporaryDirectory(prefix="puppet-exe-smoke-") as folder:
        exercise(args.exe.resolve(), Path(folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
