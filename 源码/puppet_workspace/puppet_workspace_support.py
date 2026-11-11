# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple


from puppet_common.paths import SETTINGS_CONFIG, BACKUPS, WORKSPACE_EXE, LOGS

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
    return root / SETTINGS_CONFIG


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
    target_dir = unique_child_dir(workspace_root / BACKUPS / bucket, stamp)
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
    return root / WORKSPACE_EXE


def startup_status(root: Path) -> Dict[str, object]:
    shortcut = startup_shortcut_path()
    return {
        "enabled": shortcut.is_file(),
        "shortcut": str(shortcut),
        "target": str(startup_target(root)),
    }


def enable_startup(root: Path) -> Dict[str, object]:
    shortcut = startup_shortcut_path()
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    target = startup_target(root)
    code, out, err = create_windows_shortcut(
        shortcut,
        target,
        "--tray",
        root,
    )
    if code != 0:
        raise RuntimeError(f"创建开机自启快捷方式失败: {err or out}")
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
        f"$link = $shell.CreateShortcut('{ps_quote(shortcut)}')",
        f"$link.TargetPath = '{ps_quote(target)}'",
        f"$link.Arguments = '{ps_quote_text(arguments)}'",
        f"$link.WorkingDirectory = '{ps_quote(cwd)}'",
        "$link.WindowStyle = 7",
        "$link.Save()",
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


TZ = timezone(timedelta(hours=8))


class SingleInstanceLock:
    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self.handle = None

    def acquire(self) -> bool:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = open(self.lock_file, "a+b")
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (IOError, OSError):
            if self.handle:
                try:
                    self.handle.close()
                except Exception:
                    pass
                self.handle = None
            return False

    def release(self) -> None:
        if self.handle:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self.handle.close()
            except Exception:
                pass
            self.handle = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("another instance is running")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


class OperationCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_op = None
        self._active_count = 0

    def begin_op(self, label: str) -> bool:
        with self._lock:
            if self._active_op is not None:
                return False
            self._active_op = label
            self._active_count += 1
            return True

    def end_op(self) -> None:
        with self._lock:
            self._active_op = None
            if self._active_count > 0:
                self._active_count -= 1

    def active_op(self) -> Optional[str]:
        with self._lock:
            return self._active_op

    def wait_active_ops(self, timeout: float = 5.0) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._lock:
                if self._active_count == 0 and self._active_op is None:
                    return True
            time.sleep(0.1)
        with self._lock:
            return self._active_count == 0 and self._active_op is None


def managed_targets_path(state_dir: Path) -> Path:
    return state_dir / "managed_targets.json"


def load_managed_targets(state_dir: Path) -> Set[str]:
    path = managed_targets_path(state_dir)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        skills = data.get("skills", {})
        if isinstance(skills, dict):
            return set(skills.keys())
        if isinstance(skills, list):
            return set(skills)
    except Exception:
        pass
    return set()


def save_managed_targets(state_dir: Path, skill_names: Iterable[str]) -> None:
    path = managed_targets_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "skills": {name: {"managed": True} for name in sorted(skill_names)},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def now_text() -> str:
    return datetime.now(TZ).strftime("%Y%m%d-%H%M%S")


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_log(root: Path, action: str, payload: Dict[str, object]) -> None:
    item = {"ts": datetime.now(TZ).isoformat(timespec="seconds"), "action": action, **payload}
    log_path = log_home(root) / "puppet_workspace.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def log_home(root: Path) -> Path:
    env = os.environ.get("PUPPET_WORKSPACE_LOG_HOME")
    return Path(env).absolute() if env else root / LOGS


def status_to_dict(status: object) -> Dict[str, object]:
    return {
        "id": status.repo.id,
        "label": status.repo.label,
        "path": str(status.repo.path),
        "enabled": status.repo.enabled,
        "exists": status.exists,
        "branch": status.branch,
        "head": status.head,
        "dirty": status.dirty,
        "dirty_count": status.dirty_count,
        "ahead": status.ahead,
        "behind": status.behind,
        "remote": status.remote,
        "local_only": not status.repo.remote,
        "error": status.error,
        "refreshed_at": status.refreshed_at,
    }


def conflict_names(conflicts: Dict[str, list]) -> Dict[str, List[str]]:
    return {name: [item.repo_id for item in sources] for name, sources in conflicts.items()}


def settings_to_dict(settings: WorkspaceSettings) -> Dict[str, object]:
    return {
        "refresh_interval_minutes": settings.refresh_interval_minutes,
        "close_to_tray": settings.close_to_tray,
        "notifications": settings.notifications,
        "start_minimized_to_tray": settings.start_minimized_to_tray,
    }


def alert_keys_from_payload(payload: Dict[str, object]) -> Set[str]:
    keys: Set[str] = set()
    conflicts = payload.get("conflicts", {})
    if isinstance(conflicts, dict) and conflicts:
        keys.add("import-conflict:" + ",".join(sorted(conflicts.keys())))
    for repo in payload.get("repos", []):
        if isinstance(repo, dict):
            add_repo_alert_keys(keys, repo)
    return keys


def add_repo_alert_keys(keys: Set[str], repo: Dict[str, object]) -> None:
    repo_id = str(repo.get("id", ""))
    if repo.get("error"):
        keys.add(f"repo-error:{repo_id}:{repo.get('error')}")
    if int(repo.get("dirty_count", 0) or 0) > 0:
        keys.add(f"repo-dirty:{repo_id}:{repo.get('dirty_count')}")
    if int(repo.get("ahead", 0) or 0) > 0:
        keys.add(f"repo-ahead:{repo_id}:{repo.get('ahead')}")


def alert_text(keys: Set[str]) -> str:
    if not keys:
        return "状态正常"
    return "；".join(sorted(keys))


def print_json(payload: Dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
