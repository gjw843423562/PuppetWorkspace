"""临时空工作区验收正式 EXE，不触碰用户仓库和配置。"""
import ctypes
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from smoke_hotkey_exe import wait_window

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "源码"))
from puppet_common.paths import WORKSPACE_EXE
from puppet_hotkeys.puppet_hotkey_native import api


def workspace_windows():
    user = ctypes.WinDLL("user32")
    handles = set()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    title = api(user, "GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)

    def collect(handle, unused):
        text = ctypes.create_unicode_buffer(256)
        title(handle, text, len(text))
        if text.value == "Puppet Workspace":
            handles.add(handle)
        return True

    callback = callback_type(collect)
    api(user, "EnumWindows", [callback_type, wintypes.LPARAM], wintypes.BOOL)(callback, 0)
    return handles


def new_window(process, before):
    for attempt in range(150):
        created = workspace_windows() - before
        if created:
            return created.pop()
        if process.poll() is not None:
            raise RuntimeError("测试实例提前退出")
        time.sleep(0.1)
    raise TimeoutError("测试实例未创建窗口")


def exercise(root):
    config = root / "配置" / "技能仓库.yaml"
    config.parent.mkdir()
    config.write_text("version: 1\nrepositories:\n", encoding="utf-8")
    (config.parent / "工作区设置.yaml").write_text(
        "version: 1\nclose_to_tray: false\nstart_minimized_to_tray: false\n", encoding="utf-8"
    )
    executable = Path(__file__).resolve().parents[1] / WORKSPACE_EXE
    command = [str(executable), "--workspace-root", str(root), "--ccswitch-home", str(root / "ccswitch"), "ui"]
    before = workspace_windows()
    process = subprocess.Popen(command)
    handle = None
    try:
        handle = new_window(process, before)
        print("工作区 EXE 验收通过：中文配置路径、独立测试窗口启动", flush=True)
    finally:
        if handle:
            post = api(ctypes.WinDLL("user32"), "PostMessageW", [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL)
            post(handle, 0x0010, 0, 0)
        process.wait(timeout=15)
        if process.returncode:
            raise RuntimeError("窗口退出失败: %s" % process.returncode)
        print("工作区测试窗口已正常退出", flush=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="puppet-workspace-exe-") as folder:
        exercise(Path(folder))
