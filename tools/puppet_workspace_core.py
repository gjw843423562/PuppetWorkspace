# -*- coding: utf-8 -*-
"""
puppet-workspace 多仓库技能库管理工具。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from puppet_workspace_support import (
    WorkspaceSettings,
    backup_file,
    disable_startup,
    enable_startup,
    hidden_subprocess_kwargs,
    load_settings,
    save_settings,
    startup_status,
    unique_child_dir,
)

TZ = timezone(timedelta(hours=8))
SKILL_PREFIX = "puppet-"
DEFAULT_CONFIG = Path("config") / "repos.yaml"
IGNORE_DIRS = {"__pycache__", ".git"}
IGNORE_SUFFIXES = {".pyc"}

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class RepoConfig:
    id: str
    label: str
    path: Path
    remote: str
    branch: str
    enabled: bool


@dataclass
class SkillSource:
    name: str
    repo_id: str
    path: Path


@dataclass
class RepoStatus:
    repo: RepoConfig
    exists: bool
    branch: str
    head: str
    dirty: bool
    dirty_count: int
    ahead: int
    behind: int
    remote: str
    error: str
    refreshed_at: str


def now_text() -> str:
    return datetime.now(TZ).strftime("%Y%m%d-%H%M%S")


def workspace_root_from_script() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "dist":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parents[1]


def user_home() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))).absolute()


def default_ccswitch_home() -> Path:
    env = os.environ.get("CCSWITCH_SKILLS_HOME")
    return Path(env).absolute() if env else user_home() / ".cc-switch" / "skills"


def state_home(root: Path) -> Path:
    env = os.environ.get("PUPPET_WORKSPACE_STATE_HOME")
    return Path(env).absolute() if env else root / "state"


def backups_home(root: Path) -> Path:
    env = os.environ.get("PUPPET_WORKSPACE_BACKUPS_HOME")
    return Path(env).absolute() if env else root / "backups"


def log_home(root: Path) -> Path:
    env = os.environ.get("PUPPET_WORKSPACE_LOG_HOME")
    return Path(env).absolute() if env else root / "logs"


def strip_yaml_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def parse_bool(value: str) -> bool:
    return strip_yaml_value(value).lower() in {"true", "yes", "1", "on"}


def parse_key_value(text: str) -> Tuple[str, str]:
    if ":" not in text:
        return text.strip(), ""
    key, value = text.split(":", 1)
    return key.strip(), strip_yaml_value(value)


def load_repos(config_path: Path, root: Path) -> List[RepoConfig]:
    if not config_path.is_file():
        raise FileNotFoundError(f"repos.yaml 不存在: {config_path}")
    raw_items = parse_repo_items(config_path.read_text(encoding="utf-8").splitlines())
    return [repo_from_item(item, root) for item in raw_items]


def parse_repo_items(lines: Iterable[str]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    in_repos = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.strip() == "repositories:":
            in_repos = True
            continue
        if not in_repos:
            continue
        current = parse_repo_line(line, current, items)
    if current:
        items.append(current)
    return items


def parse_repo_line(line: str, current: Optional[Dict[str, str]], items: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    text = line.strip()
    if text.startswith("- "):
        if current:
            items.append(current)
        key, value = parse_key_value(text[2:])
        return {key: value} if key else {}
    if current is not None and ":" in text:
        key, value = parse_key_value(text)
        current[key] = value
    return current


def repo_from_item(item: Dict[str, str], root: Path) -> RepoConfig:
    required = ["id", "label", "path", "remote", "branch", "enabled"]
    missing = [key for key in required if key not in item]
    if missing:
        raise ValueError(f"repos.yaml 缺少字段: {', '.join(missing)}")
    repo_path = Path(os.path.expandvars(item["path"]))
    if not repo_path.is_absolute():
        repo_path = root / repo_path
    return RepoConfig(
        id=item["id"],
        label=item["label"],
        path=repo_path.resolve(),
        remote=item["remote"],
        branch=item["branch"],
        enabled=parse_bool(item["enabled"]),
    )


def repo_to_item(repo: RepoConfig, root: Path) -> Dict[str, str]:
    return {
        "id": repo.id,
        "label": repo.label,
        "path": path_for_config(repo.path, root),
        "remote": repo.remote,
        "branch": repo.branch,
        "enabled": str(repo.enabled).lower(),
    }


def path_for_config(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def validate_repo_config(repo: RepoConfig, repos: Iterable[RepoConfig], old_id: Optional[str] = None) -> None:
    if not repo.id or any(char in repo.id for char in "\\/:*?\"<>| "):
        raise ValueError("repo-id 只能使用不含空格的安全文件名字符")
    ids = [item.id for item in repos if item.id != old_id]
    if repo.id in ids:
        raise ValueError(f"repo-id 已存在: {repo.id}")
    if not repo.label.strip():
        raise ValueError("仓库名称不能为空")
    if not repo.branch.strip():
        raise ValueError("分支不能为空")


def validate_repo_path_for_save(repo: RepoConfig) -> None:
    if repo.path.exists() and not (repo.path / ".git").exists():
        raise ValueError(f"不是 Git 仓库: {repo.path}")
    if not repo.path.exists() and not repo.remote:
        raise ValueError("仓库目录不存在时必须填写 remote URL 以便 clone")


def write_repos(config_path: Path, root: Path, repos: List[RepoConfig]) -> None:
    backup_file(root, config_path, "config", now_text())
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["version: 1", "repositories:"]
    for repo in repos:
        item = repo_to_item(repo, root)
        lines.extend([
            f"  - id: {item['id']}",
            f"    label: {item['label']}",
            f"    path: {item['path']}",
            f"    remote: {item['remote']}",
            f"    branch: {item['branch']}",
            f"    enabled: {item['enabled']}",
        ])
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_repo_config(root: Path, config_path: Path, repo: RepoConfig, old_id: Optional[str] = None) -> Dict[str, object]:
    repos = load_repos(config_path, root)
    validate_repo_config(repo, repos, old_id)
    updated = replace_or_append_repo(repos, repo, old_id)
    write_repos(config_path, root, updated)
    result = {"ok": True, "repo": repo.id, "action": "save-config"}
    append_log(root, "repo-save-config", result)
    return result


def replace_or_append_repo(repos: List[RepoConfig], repo: RepoConfig, old_id: Optional[str]) -> List[RepoConfig]:
    target_id = old_id or repo.id
    updated: List[RepoConfig] = []
    replaced = False
    for item in repos:
        if item.id == target_id:
            updated.append(repo)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(repo)
    return updated


def set_repo_enabled(root: Path, config_path: Path, repo_id: str, enabled: bool) -> Dict[str, object]:
    repos = load_repos(config_path, root)
    repo = find_repo(repos, repo_id)
    updated = replace_or_append_repo(repos, RepoConfig(repo.id, repo.label, repo.path, repo.remote, repo.branch, enabled), repo.id)
    write_repos(config_path, root, updated)
    result = {"ok": True, "repo": repo_id, "enabled": enabled}
    append_log(root, "repo-enable" if enabled else "repo-disable", result)
    return result


def delete_repo_config(root: Path, config_path: Path, repo_id: str) -> Dict[str, object]:
    repos = load_repos(config_path, root)
    find_repo(repos, repo_id)
    write_repos(config_path, root, [repo for repo in repos if repo.id != repo_id])
    result = {"ok": True, "repo": repo_id, "action": "delete-config"}
    append_log(root, "repo-delete-config", result)
    return result


def run_git(repo: Path, args: Sequence[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_subprocess_kwargs(),
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def git_value(repo: Path, args: Sequence[str]) -> str:
    code, out, _ = run_git(repo, args)
    return out if code == 0 else ""


def git_status_lines(repo: Path) -> List[str]:
    text = git_value(repo, ["status", "--porcelain"])
    return [line for line in text.splitlines() if line.strip()]


def git_ahead_behind(repo: Path) -> Tuple[int, int]:
    code, out, _ = run_git(repo, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
    if code != 0 or not out:
        return 0, 0
    parts = out.split()
    if len(parts) != 2:
        return 0, 0
    return safe_int(parts[1]), safe_int(parts[0])


def safe_int(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0


def repo_status(repo: RepoConfig) -> RepoStatus:
    refreshed_at = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    if not repo.path.is_dir():
        return RepoStatus(repo, False, "", "", False, 0, 0, 0, "", "目录不存在", refreshed_at)
    if not (repo.path / ".git").exists():
        return RepoStatus(repo, True, "", "", False, 0, 0, 0, "", "不是 Git 仓库", refreshed_at)
    branch = git_value(repo.path, ["branch", "--show-current"])
    head = git_value(repo.path, ["rev-parse", "--short", "HEAD"])
    remote = git_value(repo.path, ["remote", "get-url", "origin"])
    dirty_lines = git_status_lines(repo.path)
    ahead, behind = git_ahead_behind(repo.path)
    return RepoStatus(repo, True, branch, head, bool(dirty_lines), len(dirty_lines), ahead, behind, remote, "", refreshed_at)


def repo_summary(root: Path, config_path: Path, repo_id: str) -> Dict[str, object]:
    repo = find_repo(load_repos(config_path, root), repo_id)
    if not repo.path.is_dir():
        raise FileNotFoundError(f"仓库目录不存在: {repo.path}")
    status = status_to_dict(repo_status(repo))
    code, out, err = run_git(repo.path, ["status", "--short"])
    return {"ok": code == 0, "repo": repo_id, "status": status, "changes": out, "stderr": err}


def clone_repo(root: Path, repo: RepoConfig) -> Dict[str, object]:
    if repo.path.exists():
        return {"ok": True, "repo": repo.id, "status": "exists", "path": str(repo.path)}
    repo.path.parent.mkdir(parents=True, exist_ok=True)
    code, out, err = subprocess_clone(root, repo)
    if code != 0:
        raise RuntimeError(err or out or f"clone 失败: {repo.remote}")
    return {"ok": True, "repo": repo.id, "status": "cloned", "path": str(repo.path)}


def subprocess_clone(root: Path, repo: RepoConfig) -> Tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "clone", "--branch", repo.branch, repo.remote, str(repo.path)],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_subprocess_kwargs(),
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def enabled_repos(repos: Iterable[RepoConfig]) -> List[RepoConfig]:
    return [repo for repo in repos if repo.enabled]


def list_repo_skills(repo: RepoConfig) -> List[SkillSource]:
    skills_root = repo.path / "skills"
    if not skills_root.is_dir():
        return []
    results = []
    for item in sorted(skills_root.iterdir(), key=lambda p: p.name.lower()):
        if item.is_dir() and item.name.startswith(SKILL_PREFIX) and (item / "SKILL.md").is_file():
            results.append(SkillSource(item.name, repo.id, item))
    return results


def collect_skills(repos: Iterable[RepoConfig]) -> Tuple[Dict[str, SkillSource], Dict[str, List[SkillSource]]]:
    skills: Dict[str, SkillSource] = {}
    conflicts: Dict[str, List[SkillSource]] = {}
    for repo in enabled_repos(repos):
        for skill in list_repo_skills(repo):
            add_skill_source(skills, conflicts, skill)
    return skills, conflicts


def add_skill_source(skills: Dict[str, SkillSource], conflicts: Dict[str, List[SkillSource]], skill: SkillSource) -> None:
    if skill.name not in skills:
        skills[skill.name] = skill
        return
    conflicts.setdefault(skill.name, [skills[skill.name]]).append(skill)


def is_safe_skill_target(target: Path, root: Path) -> bool:
    try:
        resolved = target.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return False
    return resolved != root_resolved and target.name.startswith(SKILL_PREFIX)


def existing_puppet_targets(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return [
        item for item in sorted(root.iterdir(), key=lambda p: p.name.lower())
        if item.is_dir() and item.name.startswith(SKILL_PREFIX)
    ]


def ensure_safe_targets(targets: Iterable[Path], root: Path) -> None:
    unsafe = [str(path) for path in targets if not is_safe_skill_target(path, root)]
    if unsafe:
        raise RuntimeError("目标路径不安全: " + "; ".join(unsafe))


def copy_tree_clean(source: Path, target: Path) -> None:
    shutil.copytree(
        str(source),
        str(target),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def safe_rmtree(target: Path, root: Path) -> None:
    if not target.exists():
        return
    if not is_safe_skill_target(target, root):
        raise RuntimeError(f"拒绝删除不安全路径: {target}")
    shutil.rmtree(str(target))


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_hash_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [name for name in dirnames if name not in IGNORE_DIRS]
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix.lower() not in IGNORE_SUFFIXES:
                yield path


def dir_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in iter_hash_files(root):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(file_digest(path).encode("ascii"))
    return digest.hexdigest()


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_log(root: Path, action: str, payload: Dict[str, object]) -> None:
    item = {"ts": datetime.now(TZ).isoformat(timespec="seconds"), "action": action, **payload}
    log_path = log_home(root) / "puppet_workspace.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def backup_targets(root: Path, targets: List[Path], workspace_root: Path) -> Optional[Path]:
    if not targets:
        return None
    backup_root = unique_child_dir(backups_home(workspace_root) / "ccswitch", now_text())
    for target in targets:
        copy_tree_clean(target, backup_root / target.name)
    return backup_root


def is_backup_path(root: Path, backup_path: Path) -> bool:
    try:
        backup_path.resolve().relative_to(backups_home(root).resolve())
    except (OSError, ValueError):
        return False
    return backup_path.is_dir()


def restore_backup(root: Path, config_path: Path, ccswitch_root: Path, backup_kind: str, backup_path: Path) -> Dict[str, object]:
    if not is_backup_path(root, backup_path):
        raise RuntimeError(f"备份路径不安全: {backup_path}")
    if backup_kind == "ccswitch":
        result = restore_ccswitch_backup(root, ccswitch_root, backup_path)
    elif backup_kind == "config":
        result = restore_config_backup(root, config_path, backup_path)
    else:
        raise ValueError(f"未知备份类型: {backup_kind}")
    append_log(root, "restore-backup", result)
    return result


def restore_ccswitch_backup(root: Path, ccswitch_root: Path, backup_path: Path) -> Dict[str, object]:
    ccswitch_root.mkdir(parents=True, exist_ok=True)
    sources = existing_puppet_targets(backup_path)
    targets = existing_puppet_targets(ccswitch_root)
    ensure_safe_targets(sources, backup_path)
    ensure_safe_targets(targets, ccswitch_root)
    current_backup = backup_targets(ccswitch_root, targets, root)
    for target in targets:
        safe_rmtree(target, ccswitch_root)
    copied, mismatches = copy_skills_to_target({path.name: SkillSource(path.name, "backup", path) for path in sources}, ccswitch_root)
    return {
        "ok": not mismatches,
        "status": "restored" if not mismatches else "hash_mismatch",
        "kind": "ccswitch",
        "source": str(backup_path),
        "current_backup": str(current_backup) if current_backup else "",
        "copied": copied,
        "mismatches": mismatches,
    }


def restore_config_backup(root: Path, config_path: Path, backup_path: Path) -> Dict[str, object]:
    source = backup_path / "repos.yaml"
    if not source.is_file():
        raise FileNotFoundError(f"备份中没有 repos.yaml: {source}")
    current_backup = backup_file(root, config_path, "config", now_text())
    shutil.copy2(str(source), str(config_path))
    return {
        "ok": True,
        "status": "restored",
        "kind": "config",
        "source": str(source),
        "current_backup": str(current_backup) if current_backup else "",
    }


def import_ccswitch(root: Path, config_path: Path, ccswitch_root: Path) -> Dict[str, object]:
    repos = load_repos(config_path, root)
    skills, conflicts = collect_skills(repos)
    if conflicts:
        return conflict_result(root, conflicts)
    ccswitch_root.mkdir(parents=True, exist_ok=True)
    old_targets = existing_puppet_targets(ccswitch_root)
    ensure_safe_targets(old_targets, ccswitch_root)
    backup_path = backup_targets(ccswitch_root, old_targets, root)
    for target in old_targets:
        safe_rmtree(target, ccswitch_root)
    copied, mismatches = copy_skills_to_target(skills, ccswitch_root)
    return import_success(root, ccswitch_root, copied, mismatches, backup_path)


def conflict_result(root: Path, conflicts: Dict[str, List[SkillSource]]) -> Dict[str, object]:
    detail = {
        name: [{"repo": item.repo_id, "path": str(item.path)} for item in sources]
        for name, sources in conflicts.items()
    }
    result = {"ok": False, "status": "conflict", "conflicts": detail}
    append_log(root, "import-ccswitch", result)
    return result


def copy_skills_to_target(skills: Dict[str, SkillSource], ccswitch_root: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    copied: List[Dict[str, str]] = []
    mismatches: List[str] = []
    for name, source in sorted(skills.items()):
        target = ccswitch_root / name
        ensure_safe_targets([target], ccswitch_root)
        copy_tree_clean(source.path, target)
        if dir_hash(source.path) != dir_hash(target):
            mismatches.append(name)
        copied.append({"name": name, "repo": source.repo_id, "source": str(source.path)})
    return copied, mismatches


def import_success(root: Path, target: Path, copied: List[Dict[str, str]], mismatches: List[str], backup: Optional[Path]) -> Dict[str, object]:
    result = {
        "ok": not mismatches,
        "status": "ok" if not mismatches else "hash_mismatch",
        "target": str(target),
        "backup": str(backup) if backup else "",
        "copied": copied,
        "mismatches": mismatches,
    }
    write_json(state_home(root) / "sync_state.json", result)
    append_log(root, "import-ccswitch", result)
    return result


def find_repo(repos: Iterable[RepoConfig], repo_id: str) -> RepoConfig:
    for repo in repos:
        if repo.id == repo_id:
            return repo
    raise KeyError(f"未找到技能仓库: {repo_id}")


def repo_action(root: Path, config_path: Path, action: str, repo_id: str, message: Optional[str]) -> Dict[str, object]:
    repo = find_repo(load_repos(config_path, root), repo_id)
    if not repo.path.is_dir():
        raise FileNotFoundError(f"仓库目录不存在: {repo.path}")
    if action == "pull":
        code, out, err = run_git(repo.path, ["pull", "--ff-only", "origin", repo.branch])
    elif action == "push":
        code, out, err = run_git(repo.path, ["push", "-u", "origin", repo.branch])
    elif action == "commit":
        code, out, err = commit_repo(repo, message)
    else:
        raise ValueError(f"未知 Git 操作: {action}")
    result = {"ok": code == 0, "repo": repo_id, "action": action, "stdout": out, "stderr": err}
    append_log(root, f"repo-{action}", result)
    return result


def commit_repo(repo: RepoConfig, message: Optional[str]) -> Tuple[int, str, str]:
    if not git_value(repo.path, ["status", "--porcelain"]):
        return 0, "工作区干净，无需提交", ""
    run_git(repo.path, ["add", "-A"])
    text = message or f"chore(sync): update {repo.id} {datetime.now(TZ):%Y-%m-%d}"
    return commit_with_file(repo.path, text)


def commit_with_file(repo_path: Path, message: str) -> Tuple[int, str, str]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as handle:
        handle.write(message)
        msg_path = Path(handle.name)
    try:
        return run_git(repo_path, ["commit", "-F", str(msg_path)])
    finally:
        try:
            msg_path.unlink()
        except OSError:
            pass


def status_payload(root: Path, config_path: Path, ccswitch_root: Path) -> Dict[str, object]:
    repos = load_repos(config_path, root)
    skills, conflicts = collect_skills(repos)
    settings = load_settings(root)
    return {
        "workspace_root": str(root),
        "config": str(config_path),
        "ccswitch": str(ccswitch_root),
        "repos": [status_to_dict(repo_status(repo)) for repo in repos],
        "skill_count": len(skills),
        "conflicts": conflict_names(conflicts),
        "settings": settings_to_dict(settings),
        "startup": startup_status(root),
    }


def status_to_dict(status: RepoStatus) -> Dict[str, object]:
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
        "error": status.error,
        "refreshed_at": status.refreshed_at,
    }


def conflict_names(conflicts: Dict[str, List[SkillSource]]) -> Dict[str, List[str]]:
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


def repo_config_from_args(root: Path, args: argparse.Namespace) -> RepoConfig:
    repo_path = Path(args.path).resolve() if args.path else root / "skill-repos" / args.repo_id
    return RepoConfig(
        id=args.repo_id,
        label=args.label or args.repo_id,
        path=repo_path,
        remote=args.remote or "",
        branch=args.branch,
        enabled=not args.disabled,
    )


def handle_repo_command(root: Path, config_path: Path, args: argparse.Namespace) -> int:
    action = args.repo_action
    if action in {"pull", "commit", "push"}:
        result = repo_action(root, config_path, action, args.repo_id, getattr(args, "message", None))
    elif action == "summary":
        result = repo_summary(root, config_path, args.repo_id)
    elif action == "add":
        result = add_repo_from_cli(root, config_path, args)
    elif action in {"enable", "disable"}:
        result = set_repo_enabled(root, config_path, args.repo_id, action == "enable")
    else:
        raise ValueError(f"未知仓库命令: {action}")
    print_json(result)
    return 0 if result.get("ok") else 1


def add_repo_from_cli(root: Path, config_path: Path, args: argparse.Namespace) -> Dict[str, object]:
    repo = repo_config_from_args(root, args)
    validate_repo_config(repo, load_repos(config_path, root))
    validate_repo_path_for_save(repo)
    if repo.remote and not repo.path.exists():
        clone_repo(root, repo)
    return save_repo_config(root, config_path, repo)


def handle_startup_command(root: Path, action: str) -> int:
    if action == "enable":
        result = enable_startup(root)
    elif action == "disable":
        result = disable_startup(root)
    else:
        result = startup_status(root)
    print_json(result)
    return 0 if result.get("ok") else 1
