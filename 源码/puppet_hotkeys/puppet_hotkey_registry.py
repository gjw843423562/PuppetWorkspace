# -*- coding: utf-8 -*-
"""窗口线程内的热键事务；新注册失败时不改变原有注册。"""
from puppet_hotkeys.puppet_hotkey_config import parse_hotkey, validate_config


def bindings(config):
    validate_config(config)
    result = {parse_hotkey(config["MainHotkey"])[:2]: ("主窗口", None)}
    for tool in config["Tools"]:
        result[parse_hotkey(tool["Hotkey"])[:2]] = (tool["Name"], tool)
    return result


class HotkeyRegistry:
    def __init__(self, backend):
        self.backend = backend
        self.active = {}
        self.actions = {}

    def apply(self, config):
        desired = bindings(config)
        added = {}
        try:
            self._register_new(desired, added)
        except Exception:
            self._release(added)
            raise
        self._release({key: value for key, value in self.active.items() if key not in desired})
        self.active = {key: value for key, value in self.active.items() if key in desired}
        self.active.update(added)
        self.actions = {self.active[key]: action for key, action in desired.items()}
        return True

    def _register_new(self, desired, added):
        used = set(self.active.values())
        for key, action in desired.items():
            if key in self.active:
                continue
            identity = next(value for value in range(1, 0xBFFF) if value not in used)
            try:
                self.backend.register(identity, *key)
            except OSError as exc:
                raise ValueError("%s 的热键注册失败：%s。原有热键保持不变。" % (action[0], exc)) from exc
            used.add(identity)
            added[key] = identity
        return True

    def _release(self, entries):
        for identity in entries.values():
            self.backend.unregister(identity)
        return True

    def close(self):
        self._release(self.active)
        self.active.clear()
        self.actions.clear()
        return True
