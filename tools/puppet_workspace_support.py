# -*- coding: utf-8 -*-
"""
Puppet Workspace 的设置、自启与通用 Windows 支撑能力。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple


DEFAULT_SETTINGS = {
    "refresh_interval_minutes": "180",
    "close_to_tray": "true",
    "notifications": "true",
    "start_minimized_to_tray": "true",
}


@dataclass
class WorkspaceSettings:
    refresh_interval_minutes: int = 180
    close_to_tray: bool = True
    notifications: bool = True
    start_minimized_to_tray: bool = True


def hidden_subprocess_kwargs() -> Dict[str, object]:
    if os.name != "nt":
        return {}
    kwargs: Dict[str, object] = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    startupinfo_class = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_class and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
        startupinfo = startupinfo_class()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    return kwargs


def run_hidden(args: Sequence[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_subprocess_kwargs(),
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def settings_path(root: Path) -> Path:
    return root / "config" / "settings.yaml"


def parse_bool(value: str) -> bool:
    return value.strip().strip("'\"").lower() in {"true", "yes", "1", "on"}


def load_key_values(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return dict(DEFAULT_SETTINGS)
    values = dict(DEFAULT_SETTINGS)
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or ":" not in text:
            continue
        key, value = text.split(":", 1)
        if key.strip() != "version":
            values[key.strip()] = value.strip().strip("'\"")
    return values


def load_settings(root: Path) -> WorkspaceSettings:
    values = load_key_values(settings_path(root))
    return WorkspaceSettings(
        refresh_interval_minutes=parse_int(values["refresh_interval_minutes"], 180),
        close_to_tray=parse_bool(values["close_to_tray"]),
        notifications=parse_bool(values["notifications"]),
        start_minimized_to_tray=parse_bool(values["start_minimized_to_tray"]),
    )


def parse_int(value: str, default: int) -> int:
    try:
        result = int(value)
    except ValueError:
        return default
    return result if result > 0 else default


def save_settings(root: Path, settings: WorkspaceSettings) -> None:
    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join([
        "version: 1",
        f"refresh_interval_minutes: {settings.refresh_interval_minutes}",
        f"close_to_tray: {str(settings.close_to_tray).lower()}",
        f"notifications: {str(settings.notifications).lower()}",
        f"start_minimized_to_tray: {str(settings.start_minimized_to_tray).lower()}",
        "",
    ])
    path.write_text(text, encoding="utf-8")


def backup_file(workspace_root: Path, source: Path, bucket: str, stamp: str) -> Optional[Path]:
    if not source.is_file():
        return None
    target_dir = unique_child_dir(workspace_root / "backups" / bucket, stamp)
    target = target_dir / source.name
    shutil.copy2(str(source), str(target))
    return target


def unique_child_dir(parent: Path, name: str) -> Path:
    for index in range(100):
        suffix = "" if index == 0 else f"-{index:02d}"
        candidate = parent / f"{name}{suffix}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"备份目录连续撞名: {parent / name}")


def startup_folder() -> Path:
    env = os.environ.get("PUPPET_WORKSPACE_STARTUP_HOME")
    if env:
        return Path(env).absolute()
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return Path.home()
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_shortcut_path() -> Path:
    return startup_folder() / "PuppetWorkspace.lnk"


def startup_target(root: Path) -> Path:
    return root / "PuppetWorkspace.exe"


def startup_status(root: Path) -> Dict[str, object]:
    shortcut = startup_shortcut_path()
    return {
        "ok": True,
        "enabled": shortcut.is_file(),
        "shortcut": str(shortcut),
        "target": str(startup_target(root)),
        "arguments": "--tray",
    }


def enable_startup(root: Path) -> Dict[str, object]:
    target = startup_target(root)
    if not target.is_file():
        raise FileNotFoundError(f"开机自启目标不存在: {target}")
    shortcut = startup_shortcut_path()
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    code, out, err = create_windows_shortcut(shortcut, target, "--tray", root)
    if code != 0:
        raise RuntimeError(err or out or "创建开机自启快捷方式失败")
    return startup_status(root)


def disable_startup(root: Path) -> Dict[str, object]:
    shortcut = startup_shortcut_path()
    if shortcut.exists():
        shortcut.unlink()
    return startup_status(root)


def create_windows_shortcut(shortcut: Path, target: Path, arguments: str, cwd: Path) -> Tuple[int, str, str]:
    if os.name != "nt":
        return 1, "", "当前平台不支持 Windows Startup 快捷方式"
    script = "; ".join([
        "$shell = New-Object -ComObject WScript.Shell",
        f"$shortcut = $shell.CreateShortcut('{ps_quote(shortcut)}')",
        f"$shortcut.TargetPath = '{ps_quote(target)}'",
        f"$shortcut.Arguments = '{ps_quote_text(arguments)}'",
        f"$shortcut.WorkingDirectory = '{ps_quote(cwd)}'",
        "$shortcut.WindowStyle = 7",
        "$shortcut.Save()",
    ])
    return run_hidden([
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ])


def ps_quote(path: Path) -> str:
    return str(path).replace("'", "''")


def ps_quote_text(text: str) -> str:
    return text.replace("'", "''")


def json_ready(payload: Dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
