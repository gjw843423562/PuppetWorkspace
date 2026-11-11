# -*- coding: utf-8 -*-
"""启动按钮反馈与免解包布局的回归。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "源码"))
from puppet_workspace import puppet_workspace_tools as entry
from puppet_hotkeys import puppet_hotkeys as standalone


class StartupFeedbackTests(unittest.TestCase):
    def app(self):
        app = Mock(root_path=Path("D:/puppet-workspace"))
        app.hotkey_launch_pending = False
        return app

    def test_pending_launch_prevents_multiple_processes(self):
        app = self.app()
        with patch.object(entry, "launch_hotkey_tool", return_value=Mock()) as launch:
            entry.start_hotkey_tool(app)
            entry.start_hotkey_tool(app)
        launch.assert_called_once()
        self.assertTrue(app.hotkey_launch_pending)
        app.hotkey_launch_button.configure.assert_called_with(state="disabled")

    def test_running_window_is_reused_without_polling(self):
        app = self.app()
        with patch.object(entry, "launch_hotkey_tool", return_value=None):
            entry.start_hotkey_tool(app)
        self.assertFalse(app.hotkey_launch_pending)
        app.window.after.assert_not_called()
        self.assertIn("已显示", app.status_text.set.call_args[0][0])

    def test_exit_before_window_reports_error_and_reenables_button(self):
        app = self.app()
        process = Mock()
        process.poll.return_value = 1
        with patch.object(entry, "find_window", return_value=None):
            entry.poll_launch(app, process, Path("config.json"), 0)
        app.report_error.assert_called_once()
        self.assertFalse(app.hotkey_launch_pending)
        app.hotkey_launch_button.configure.assert_called_with(state="normal")

    def test_window_ready_reports_elapsed_time(self):
        app = self.app()
        with patch.object(entry, "find_window", return_value=123), patch.object(entry, "wake_existing"), patch.object(entry.time, "perf_counter", return_value=2):
            entry.poll_launch(app, Mock(), Path("config.json"), 1.5)
        self.assertIn("0.5 秒", app.status_text.set.call_args[0][0])
        self.assertFalse(app.hotkey_launch_pending)

    def test_timeout_reports_visible_error(self):
        app = self.app()
        process = Mock()
        process.poll.return_value = None
        with patch.object(entry, "find_window", return_value=None), patch.object(entry.time, "perf_counter", return_value=16):
            entry.poll_launch(app, process, Path("config.json"), 0)
        self.assertIsInstance(app.report_error.call_args[0][1], TimeoutError)

    def test_onedir_resolves_existing_shared_config(self):
        with patch.object(standalone.sys, "frozen", True, create=True), patch.object(standalone.sys, "executable", "D:/puppet-workspace/发布/快捷键工具/PuppetHotkeys/PuppetHotkeys.exe"):
            self.assertEqual(standalone.default_config(), Path("D:/puppet-workspace/配置/快捷键工具.json"))


if __name__ == "__main__":
    unittest.main()
