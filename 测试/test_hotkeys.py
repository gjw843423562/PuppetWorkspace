# -*- coding: utf-8 -*-
"""快捷键配置、事务、启动参数与 Windows 消息的隔离验收。"""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "源码"))
from puppet_hotkeys import puppet_hotkey_config as config
from puppet_hotkeys import puppet_hotkey_launch as launch
from puppet_hotkeys.puppet_hotkey_registry import HotkeyRegistry


def sample():
    return {"MainHotkey": "Ctrl+Alt+F24", "Tools": [
        {"Name": "测试", "Path": "测试文件.exe", "Hotkey": "Ctrl+Alt+F23", "Args": ["中文 空格", "https://example.com"]}]}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="puppet-hotkey-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "中文 空格.json"
        self.data = sample()
        self.raw = ("// 原始注释\n" + json.dumps(self.data, ensure_ascii=False)).encode("utf-8")
        self.path.write_bytes(self.raw)

    def test_all_key_names_and_normalization(self):
        for name, code in config.KEYS.items():
            self.assertEqual(config.parse_hotkey("alt+CTRL+" + name)[:2], (3, code))
        self.assertEqual(config.parse_hotkey(" alt + CTRL + numpad3 ")[2], "Ctrl+Alt+Numpad3")

    def test_invalid_hotkeys(self):
        for value in ("", "Ctrl++A", "Ctrl+Ctrl+A", "Bogus+A", "Ctrl+F25", "Ctrl", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.parse_hotkey(value)

    def test_comments_url_and_unknown_fields_roundtrip(self):
        data, digest = config.read_config(self.path)
        data["Custom"] = {"preserve": True}
        data["Tools"][0]["extra"] = "保留"
        digest, backup = config.save_config(self.path, data, digest)
        self.assertEqual(backup.read_bytes(), self.raw)
        self.assertTrue(self.path.read_text(encoding="utf-8").startswith("// 原始注释"))
        loaded, latest = config.read_config(self.path)
        self.assertEqual(data, loaded)
        self.assertEqual(digest, latest)

    def test_main_tool_duplicate_is_rejected(self):
        self.data["Tools"][0]["Hotkey"] = "alt+ctrl+f24"
        with self.assertRaisesRegex(ValueError, "快捷键重复"):
            config.validate_config(self.data)

    def test_invalid_args_and_duplicate_json_fields(self):
        self.data["Tools"][0]["Args"] = "string"
        with self.assertRaises(ValueError):
            config.validate_config(self.data)
        with self.assertRaisesRegex(ValueError, "字段重复"):
            config.parse_config('{"MainHotkey":"F1","MainHotkey":"F2","Tools":[]}')

    def test_external_change_is_not_overwritten(self):
        data, digest = config.read_config(self.path)
        self.path.write_bytes(b"external")
        with self.assertRaisesRegex(ValueError, "其他程序修改"):
            config.save_config(self.path, data, digest)
        self.assertEqual(self.path.read_bytes(), b"external")

    def test_failed_replace_keeps_original_and_cleans_temporary(self):
        data, digest = config.read_config(self.path)
        with patch.object(config.os, "replace", side_effect=PermissionError("locked")), patch.object(config.time, "sleep"):
            with self.assertRaises(PermissionError):
                config.save_config(self.path, data, digest)
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(list(self.path.parent.glob(".tools-*.tmp")), [])

    def test_transient_replace_failure_retries(self):
        data, digest = config.read_config(self.path)
        replace = os.replace
        calls = []
        def transient(source, target):
            calls.append(source)
            if len(calls) == 1:
                raise PermissionError("locked")
            return replace(source, target)
        with patch.object(config.os, "replace", side_effect=transient), patch.object(config.time, "sleep"):
            config.save_config(self.path, data, digest)
        self.assertEqual(len(calls), 2)

    def test_external_write_during_retry_is_preserved(self):
        data, digest = config.read_config(self.path)
        def competing_write(source, target):
            self.path.write_bytes(b"new external content")
            raise PermissionError("locked")
        with patch.object(config.os, "replace", side_effect=competing_write), patch.object(config.time, "sleep"):
            with self.assertRaisesRegex(ValueError, "外部修改"):
                config.save_config(self.path, data, digest)
        self.assertEqual(self.path.read_bytes(), b"new external content")


class RegistryTests(unittest.TestCase):
    def test_new_conflict_releases_new_bindings_keeps_old(self):
        backend = Mock()
        registry = HotkeyRegistry(backend)
        registry.apply(sample())
        old, actions = dict(registry.active), dict(registry.actions)
        candidate = sample()
        candidate["MainHotkey"] = "Ctrl+Alt+F22"
        candidate["Tools"][0]["Hotkey"] = "Ctrl+Alt+F21"
        backend.register.side_effect = [True, OSError(1409, "occupied")]
        with self.assertRaisesRegex(ValueError, "原有热键保持不变"):
            registry.apply(candidate)
        self.assertEqual(registry.active, old)
        self.assertEqual(registry.actions, actions)
        backend.unregister.assert_called_once()

    def test_unchanged_keys_reuse_registration_and_update_target(self):
        backend = Mock()
        registry = HotkeyRegistry(backend)
        data = sample()
        registry.apply(data)
        backend.reset_mock()
        data["Tools"][0]["Path"] = "new.exe"
        registry.apply(data)
        backend.register.assert_not_called()
        self.assertIn("new.exe", [action[1]["Path"] for action in registry.actions.values() if action[1]])
        registry.close()
        self.assertEqual(backend.unregister.call_count, 2)
        self.assertEqual(registry.active, {})


class LaunchTests(unittest.TestCase):
    def test_exe_arguments_are_list_without_shell(self):
        with tempfile.TemporaryDirectory(prefix="puppet-launch-") as folder:
            path = Path(folder) / "中文 & 空格.exe"
            path.touch()
            tool = {"Path": str(path), "Args": ["space arg", "&literal", 'quote"arg']}
            with patch.object(launch.subprocess, "Popen") as popen:
                launch.launch_target(tool, folder)
            popen.assert_called_once_with([str(path)] + tool["Args"], cwd=str(path.parent), shell=False)

    def test_url_uses_browser_and_missing_path_errors(self):
        with patch.object(launch.webbrowser, "open", return_value=True) as browser:
            launch.launch_target({"Path": "https://example.com/a//b"}, ".")
        browser.assert_called_once_with("https://example.com/a//b")
        with self.assertRaises(FileNotFoundError):
            launch.launch_target({"Path": "missing-tool-52312.exe"}, tempfile.gettempdir())

    def test_puppet_entry_targets_new_exe_and_rejects_missing_config(self):
        from puppet_workspace import puppet_workspace_tools as entry
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, path = entry.hotkey_paths(root)
            self.assertEqual(exe.name, "PuppetHotkeys.exe")
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(entry.subprocess, "Popen") as process:
                with self.assertRaises(FileNotFoundError):
                    entry.launch_hotkey_tool(root)
                process.assert_not_called()
                path.parent.mkdir(parents=True)
                path.write_text("{}", encoding="utf-8")
                with patch.object(entry, "wake_existing", return_value=False):
                    entry.launch_hotkey_tool(root)
                process.assert_called_once_with([str(exe), "--config", str(path)], cwd=str(path.parent), shell=False)


@unittest.skipUnless(sys.platform == "win32", "需要 Windows")
class NativeTests(unittest.TestCase):
    def test_poll_reschedules_after_callback_error(self):
        from puppet_hotkeys.puppet_hotkey_ui import HotkeyApp
        app = HotkeyApp.__new__(HotkeyApp)
        app.native = Mock()
        app.native.drain.side_effect = ValueError("callback")
        app.error, app.window, app.closed = Mock(), Mock(), False
        app.poll()
        app.error.assert_called_once()
        app.window.after.assert_called_once_with(100, app.poll)

    def test_app_edit_commit_failure_restore_and_reload(self):
        from puppet_hotkeys.puppet_hotkey_ui import HotkeyApp
        from puppet_hotkeys.puppet_hotkey_editor import ToolEditor
        with tempfile.TemporaryDirectory(prefix="puppet-ui-") as folder:
            path = Path(folder) / "tools.json"
            data = sample()
            data["MainHotkey"] = "Ctrl+Alt+Shift+F24"
            data["Tools"][0]["Hotkey"] = "Ctrl+Alt+Shift+F23"
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(HotkeyApp, "_start_tray", return_value=False):
                app = HotkeyApp(path, "Puppet 隔离测试")
            try:
                self.assertEqual(len(app.registry.active), 2)
                app.window.withdraw()
                app.open_editor(0)
                self.assertEqual(len(app.registry.active), 0)
                app.editor.fields["Name"].set("更新名称")
                app.editor.save()
                self.assertIsNone(app.editor)
                self.assertEqual(len(app.registry.active), 2)
                self.assertEqual(config.read_config(path)[0]["Tools"][0]["Name"], "更新名称")
                old = copy.deepcopy(app.config)
                candidate = copy.deepcopy(old)
                candidate["MainHotkey"] = "Ctrl+Alt+Shift+F22"
                with patch("puppet_hotkeys.puppet_hotkey_ui.save_config", side_effect=PermissionError("locked")):
                    with self.assertRaises(PermissionError):
                        app.commit(candidate)
                self.assertEqual(app.config, old)
                self.assertEqual(set(app.registry.active), {(7, 135), (7, 134)})
                app.window.update()
            finally:
                app.quit()

    def test_real_register_dispatch_release_and_instance_wake(self):
        import ctypes
        import tkinter as tk
        from puppet_hotkeys.puppet_hotkey_native import InstanceGuard, NativeWindow, api
        from ctypes import wintypes
        with tempfile.TemporaryDirectory(prefix="puppet-native-") as folder:
            guard = InstanceGuard(Path(folder) / "tools.json")
            self.addCleanup(guard.close)
            window = tk.Tk()
            window.title(guard.title)
            window.withdraw()
            self.addCleanup(window.destroy)
            received = []
            native = NativeWindow(window, received.append, lambda value: None)
            self.addCleanup(native.close)
            try:
                native.register(12000, 7, 135)
            except OSError as exc:
                self.skipTest("隔离测试键 Ctrl+Alt+Shift+F24 已占用：%s" % exc)
            self.addCleanup(native.unregister, 12000)
            post = api(native.user, "PostMessageW", [wintypes.HWND, wintypes.UINT,
                       wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL)
            post(native.handle, 0x0312, 12000, 0)
            window.update()
            native.drain()
            self.assertEqual(received, [12000])
            other = InstanceGuard(Path(folder) / "tools.json")
            self.addCleanup(other.close)
            self.assertTrue(other.existing)
            self.assertTrue(other.wake())
            window.update()
            self.assertTrue(window.winfo_viewable())

    def test_drag_file_message_is_queued_without_tk_reentry(self):
        import ctypes
        import struct
        import tkinter as tk
        from ctypes import wintypes
        from puppet_hotkeys.puppet_hotkey_native import NativeWindow, api
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        dropped = []
        native = NativeWindow(window, lambda value: None, dropped.append)
        self.addCleanup(native.close)
        path = "D:\\中文 文件夹\\工具.exe"
        payload = struct.pack("IIIII", 20, 0, 0, 0, 1) + (path + "\0\0").encode("utf-16-le")
        kernel = ctypes.WinDLL("kernel32")
        allocate = api(kernel, "GlobalAlloc", [wintypes.UINT, ctypes.c_size_t], wintypes.HANDLE)
        lock = api(kernel, "GlobalLock", [wintypes.HANDLE], ctypes.c_void_p)
        unlock = api(kernel, "GlobalUnlock", [wintypes.HANDLE], wintypes.BOOL)
        handle = allocate(0x42, len(payload))
        ctypes.memmove(lock(handle), payload, len(payload))
        unlock(handle)
        native._dispatch(native.handle, 0x0233, handle, 0)
        self.assertEqual(dropped, [])
        native.drain()
        self.assertEqual(dropped, [path])


class StartupTests(unittest.TestCase):
    def test_startup_writes_only_own_value_with_quoted_args(self):
        from puppet_hotkeys import puppet_hotkey_startup as startup
        registry_key = Mock()
        registry_key.__enter__ = Mock(return_value=registry_key)
        registry_key.__exit__ = Mock(return_value=False)
        with patch.object(startup.winreg, "CreateKey", return_value=registry_key), patch.object(startup.winreg, "SetValueEx") as write:
            startup.set_startup(True, Path("D:/中文 空格/tools.json"))
        self.assertEqual(write.call_args[0][1], "PuppetHotkeys")
        self.assertIn('--silent', write.call_args[0][-1])
        self.assertIn('"D:', write.call_args[0][-1])


if __name__ == "__main__":
    unittest.main()
