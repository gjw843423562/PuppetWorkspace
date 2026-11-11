"""首次部署尚无运行数据目录时，也能记录日志和备份配置。"""
import faulthandler
import logging
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "源码"))
from puppet_common.paths import hotkey_data_folder
from puppet_hotkeys import puppet_hotkey_diagnostics as diagnostics
from puppet_hotkeys.puppet_hotkey_config import read_config, save_config


class CleanRuntimeTests(unittest.TestCase):
    def test_first_log_and_save_create_runtime_parents(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "配置" / "快捷键工具.json"
            config.parent.mkdir()
            config.write_text('{"MainHotkey":"Ctrl+Alt+F24","Tools":[]}', encoding="utf-8")
            data, expected = read_config(config)
            logs = hotkey_data_folder(config, "日志")
            self.assertFalse(logs.parent.exists())
            logger = logging.getLogger("puppet.hotkeys")
            previous_handlers = list(logger.handlers)
            try:
                diagnostics.configure_logging(logs)
                self.assertTrue((logs / "hotkeys.log").is_file())
                self.assertTrue((logs / "crash.log").is_file())
                saved, backup = save_config(config, data, expected)
                self.assertEqual(backup.read_bytes(), b'{"MainHotkey":"Ctrl+Alt+F24","Tools":[]}')
                self.assertEqual(read_config(config)[1], saved)
                self.assertEqual(backup.parent, hotkey_data_folder(config, "备份"))
            finally:
                faulthandler.disable()
                if diagnostics.CRASH_STREAM:
                    diagnostics.CRASH_STREAM.close()
                    diagnostics.CRASH_STREAM = None
                for handler in list(logger.handlers):
                    if handler not in previous_handlers:
                        logger.removeHandler(handler)
                        handler.close()


if __name__ == "__main__":
    unittest.main()
