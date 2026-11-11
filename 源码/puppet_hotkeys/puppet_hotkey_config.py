# -*- coding: utf-8 -*-
"""快捷键配置与安全保存；兼容原工具的整行注释配置。"""
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path


MODIFIERS = {"CTRL": 2, "ALT": 1, "SHIFT": 4, "WIN": 8}
KEYS = {
    "Backspace": 8, "Tab": 9, "Enter": 13, "Esc": 27, "Space": 32,
    "CapsLock": 20, "Pause": 19, "PrintScreen": 44, "Insert": 45,
    "Delete": 46, "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
    "Left": 37, "Up": 38, "Right": 39, "Down": 40, "NumLock": 144,
    "ScrollLock": 145, "LWin": 91, "RWin": 92, "Apps": 93,
    "NumpadMultiply": 106, "NumpadAdd": 107, "NumpadSeparator": 108,
    "NumpadSubtract": 109, "NumpadDecimal": 110, "NumpadDivide": 111,
    "Semicolon": 186, "Equal": 187, "Comma": 188, "Minus": 189,
    "Period": 190, "Slash": 191, "Backquote": 192, "LBracket": 219,
    "Backslash": 220, "RBracket": 221, "Quote": 222,
}
KEYS.update({chr(code): code for code in range(65, 91)})
KEYS.update({str(number): 48 + number for number in range(10)})
KEYS.update({"F%d" % number: 111 + number for number in range(1, 25)})
KEYS.update({"Numpad%d" % number: 96 + number for number in range(10)})
KEY_LOOKUP = {name.upper(): (name, code) for name, code in KEYS.items()}
KEY_NAMES = {code: name for name, code in KEYS.items()}


def parse_hotkey(text):
    if not isinstance(text, str):
        raise ValueError("快捷键必须是字符串")
    parts = [part.strip().upper() for part in text.split("+")]
    if not parts or any(not part for part in parts):
        raise ValueError("快捷键不能为空或包含空键名")
    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIERS or modifiers & MODIFIERS[part]:
            raise ValueError("修饰键无效或重复：%s" % text)
        modifiers |= MODIFIERS[part]
    if parts[-1] not in KEY_LOOKUP:
        raise ValueError("不支持的键名：%s" % parts[-1])
    name, code = KEY_LOOKUP[parts[-1]]
    prefix = [key.title() if key != "CTRL" else "Ctrl"
              for key in MODIFIERS if modifiers & MODIFIERS[key]]
    return modifiers, code, "+".join(prefix + [name])


def reject_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("配置字段重复：%s" % key)
        result[key] = value
    return result


def parse_config(text):
    clean = "\n".join(line for line in text.lstrip("\ufeff").splitlines()
                      if not line.lstrip().startswith("//"))
    data = json.loads(clean, object_pairs_hook=reject_duplicate_fields)
    validate_config(data)
    return data


def check_tool(tool, index):
    if not isinstance(tool, dict):
        raise ValueError("第 %d 项工具必须是对象" % index)
    for key in ("Name", "Path", "Hotkey"):
        if not isinstance(tool.get(key), str) or not tool[key].strip():
            raise ValueError("第 %d 项工具的 %s 不能为空" % (index, key))
    if not isinstance(tool.get("Description", ""), str):
        raise ValueError("工具说明必须是字符串")
    args = tool.get("Args", [])
    if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
        raise ValueError("%s 的 Args 必须是字符串数组" % tool["Name"])
    if any("\x00" in arg for arg in args) or "\x00" in tool["Path"]:
        raise ValueError("路径或参数不能包含空字符")
    return True


def validate_config(data):
    if not isinstance(data, dict) or not isinstance(data.get("Tools"), list):
        raise ValueError("配置必须包含 Tools 数组")
    main = parse_hotkey(data.get("MainHotkey", ""))[:2]
    seen = {main: "主窗口"}
    names = set()
    for index, tool in enumerate(data["Tools"], 1):
        check_tool(tool, index)
        name = tool["Name"].strip()
        if name in names:
            raise ValueError("工具名称重复：%s" % name)
        names.add(name)
        key = parse_hotkey(tool["Hotkey"])[:2]
        if key in seen:
            raise ValueError("快捷键重复：%s 与 %s" % (name, seen[key]))
        seen[key] = name
    return True


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def read_config(path):
    raw = Path(path).read_bytes()
    return parse_config(raw.decode("utf-8-sig")), fingerprint(raw)


def serialize_config(data, original):
    validate_config(data)
    comments = [line for line in original.decode("utf-8-sig").splitlines()
                if line.lstrip().startswith("//")]
    body = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return ("\n".join(comments) + ("\n" if comments else "") + body).encode("utf-8")


def replace_with_retry(source, target, expected):
    for attempt in range(3):
        if fingerprint(Path(target).read_bytes()) != expected:
            raise ValueError("重试保存时检测到外部修改，已取消写入")
        try:
            os.replace(str(source), str(target))
            return True
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.1 * (attempt + 1))


def save_config(path, data, expected):
    path = Path(path)
    original = path.read_bytes()
    if fingerprint(original) != expected:
        raise ValueError("配置已被其他程序修改，请先重新加载，避免覆盖")
    content = serialize_config(data, original)
    from puppet_common.paths import hotkey_data_folder
    backup_dir = hotkey_data_folder(path, "备份")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / ("tools-" + stamp + ".json")
    backup.write_bytes(original)
    descriptor, temporary = tempfile.mkstemp(prefix=".tools-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if fingerprint(path.read_bytes()) != expected:
            raise ValueError("保存前检测到外部修改，已取消写入")
        replace_with_retry(temporary, path, expected)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return fingerprint(content), backup
