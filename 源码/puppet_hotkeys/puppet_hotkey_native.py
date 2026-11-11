# -*- coding: utf-8 -*-
"""Windows 消息适配；热键与文件拖放均由 Tkinter 窗口线程处理。"""
import ctypes
import hashlib
import queue
import time
from ctypes import wintypes


def api(dll, name, args, result):
    function = getattr(dll, name)
    function.argtypes = args
    function.restype = result
    return function


def window_title(config_path):
    token = hashlib.sha256(str(config_path.resolve()).casefold().encode("utf-8")).hexdigest()[:20]
    return "Puppet 快捷键工具 | " + token


def find_window(config_path):
    user = ctypes.WinDLL("user32", use_last_error=True)
    find = api(user, "FindWindowW", [wintypes.LPCWSTR, wintypes.LPCWSTR], wintypes.HWND)
    return find(None, window_title(config_path))


def wake_existing(config_path):
    handle = find_window(config_path)
    if not handle:
        return False
    user = ctypes.WinDLL("user32", use_last_error=True)
    show = api(user, "ShowWindow", [wintypes.HWND, ctypes.c_int], wintypes.BOOL)
    foreground = api(user, "SetForegroundWindow", [wintypes.HWND], wintypes.BOOL)
    show(handle, 9)
    foreground(handle)
    return True


class InstanceGuard:
    def __init__(self, config_path):
        self.config_path = config_path
        self.title = window_title(config_path)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = api(kernel, "CreateMutexW", [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE)
        self.close_handle = api(kernel, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL)
        token = self.title.rsplit(" | ", 1)[1]
        self.handle = create(None, False, "Local\\PuppetHotkeys-" + token)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.existing = ctypes.get_last_error() == 183

    def wake(self):
        for attempt in range(10):
            if wake_existing(self.config_path):
                return True
            time.sleep(0.1)
        return False

    def close(self):
        if self.handle:
            self.close_handle(self.handle)
            self.handle = None
        return True


class NativeWindow:
    def __init__(self, window, on_hotkey, on_drop):
        self.window = window
        self.on_hotkey = on_hotkey
        self.on_drop = on_drop
        self.events = queue.SimpleQueue()
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.shell = ctypes.WinDLL("shell32", use_last_error=True)
        self._configure()
        window.update_idletasks()
        ancestor = api(self.user, "GetAncestor", [wintypes.HWND, wintypes.UINT], wintypes.HWND)
        self.handle = ancestor(window.winfo_id(), 2)
        self.callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                                                wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        self.callback = self.callback_type(self._dispatch)
        ctypes.set_last_error(0)
        self.previous = self.set_proc(self.handle, -4, ctypes.cast(self.callback, ctypes.c_void_p))
        if not self.previous and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        self.drag_accept(self.handle, True)

    def _configure(self):
        self.set_proc = api(self.user, "SetWindowLongPtrW",
                            [wintypes.HWND, ctypes.c_int, ctypes.c_void_p], ctypes.c_void_p)
        self.call_proc = api(self.user, "CallWindowProcW", [ctypes.c_void_p, wintypes.HWND,
                             wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], ctypes.c_ssize_t)
        self.register_api = api(self.user, "RegisterHotKey", [wintypes.HWND, ctypes.c_int,
                                 wintypes.UINT, wintypes.UINT], wintypes.BOOL)
        self.unregister_api = api(self.user, "UnregisterHotKey", [wintypes.HWND, ctypes.c_int], wintypes.BOOL)
        self.drag_accept = api(self.shell, "DragAcceptFiles", [wintypes.HWND, wintypes.BOOL], None)
        self.drag_query = api(self.shell, "DragQueryFileW", [wintypes.HANDLE, wintypes.UINT,
                               wintypes.LPWSTR, wintypes.UINT], wintypes.UINT)
        self.drag_finish = api(self.shell, "DragFinish", [wintypes.HANDLE], None)
        return True

    def _dispatch(self, handle, message, wparam, lparam):
        try:
            if message == 0x0312:
                self.events.put(("hotkey", int(wparam)))
                return 0
            if message == 0x0233:
                self._drop(wparam)
                return 0
        except Exception as exc:
            self.events.put(("error", exc))
        return self.call_proc(self.previous, handle, message, wparam, lparam)

    def _drop(self, handle):
        try:
            size = self.drag_query(handle, 0, None, 0)
            if size:
                buffer = ctypes.create_unicode_buffer(size + 1)
                self.drag_query(handle, 0, buffer, size + 1)
                self.events.put(("drop", buffer.value))
        finally:
            self.drag_finish(handle)
        return True

    def drain(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == "hotkey":
                self.on_hotkey(value)
            elif kind == "drop":
                self.on_drop(value)
            else:
                raise value
        return True

    def register(self, identity, modifiers, key):
        if not self.register_api(self.handle, identity, modifiers | 0x4000, key):
            error = ctypes.get_last_error()
            reason = "组合已被其他程序占用" if error == 1409 else ctypes.FormatError(error)
            raise OSError(error, reason)
        return True

    def unregister(self, identity):
        return bool(self.unregister_api(self.handle, identity))

    def close(self):
        if self.previous:
            self.drag_accept(self.handle, False)
            self.set_proc(self.handle, -4, self.previous)
            self.previous = None
        self.on_hotkey = None
        self.on_drop = None
        self.window = None
        return True


def capture_key(event):
    from puppet_hotkeys.puppet_hotkey_config import KEY_NAMES
    user = ctypes.WinDLL("user32")
    state = api(user, "GetKeyState", [ctypes.c_int], ctypes.c_short)
    code = event.keycode
    if code in (16, 17, 18, 91, 92):
        return ""
    name = KEY_NAMES.get(code)
    if not name:
        return ""
    modifiers = [name for key, name in ((17, "Ctrl"), (18, "Alt"), (16, "Shift")) if state(key) & 0x8000]
    if state(91) & 0x8000 or state(92) & 0x8000:
        modifiers.append("Win")
    # NumLock 关闭时虚拟键变为导航键，Tk 的 KP_ 名称保留小键盘来源。
    keypad = {"KP_Insert": "Numpad0", "KP_End": "Numpad1", "KP_Down": "Numpad2",
              "KP_Next": "Numpad3", "KP_Left": "Numpad4", "KP_Begin": "Numpad5",
              "KP_Right": "Numpad6", "KP_Home": "Numpad7", "KP_Up": "Numpad8",
              "KP_Prior": "Numpad9", "KP_Delete": "NumpadDecimal"}
    return "+".join(modifiers + [keypad.get(event.keysym, name)])
