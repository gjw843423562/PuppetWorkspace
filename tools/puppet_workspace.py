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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover - 无 UI 环境仍允许 CLI 使用
    tk = None
    ttk = None
    messagebox = None

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
    remote: str


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


def repo_status(repo: RepoConfig) -> RepoStatus:
    if not repo.path.is_dir():
        return RepoStatus(repo, False, "", "", False, "")
    branch = git_value(repo.path, ["branch", "--show-current"])
    head = git_value(repo.path, ["rev-parse", "--short", "HEAD"])
    remote = git_value(repo.path, ["remote", "get-url", "origin"])
    dirty = bool(git_value(repo.path, ["status", "--porcelain"]))
    return RepoStatus(repo, True, branch, head, dirty, remote)


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
    backup_root = backups_home(workspace_root) / "ccswitch" / now_text()
    backup_root.mkdir(parents=True, exist_ok=False)
    for target in targets:
        copy_tree_clean(target, backup_root / target.name)
    return backup_root


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
    return {
        "workspace_root": str(root),
        "config": str(config_path),
        "ccswitch": str(ccswitch_root),
        "repos": [status_to_dict(repo_status(repo)) for repo in repos],
        "skill_count": len(skills),
        "conflicts": conflict_names(conflicts),
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
        "remote": status.remote,
    }


def conflict_names(conflicts: Dict[str, List[SkillSource]]) -> Dict[str, List[str]]:
    return {name: [item.repo_id for item in sources] for name, sources in conflicts.items()}


def print_json(payload: Dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


class PuppetWorkspaceApp:
    def __init__(self, root: Path, config_path: Path, ccswitch_root: Path) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("当前 Python 环境不可用 tkinter")
        self.root_path = root
        self.config_path = config_path
        self.ccswitch_root = ccswitch_root
        self.window = tk.Tk()
        self.window.title("Puppet Workspace")
        self.window.geometry("980x620")
        self.status_text = tk.StringVar(value="准备就绪")
        self._build()
        self.refresh()

    def _build(self) -> None:
        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        self._build_buttons(frame)
        self.repo_tree = self._build_tree(frame)
        self.log = tk.Text(frame, height=12, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(frame, textvariable=self.status_text).pack(anchor=tk.W, pady=(6, 0))

    def _build_buttons(self, frame: "ttk.Frame") -> None:
        bar = ttk.Frame(frame)
        bar.pack(fill=tk.X, pady=(0, 8))
        buttons = [
            ("刷新状态", self.refresh),
            ("导入到 ccSwitch", self.import_ccswitch),
            ("拉取选中仓库", lambda: self.repo_op("pull")),
            ("提交选中仓库", lambda: self.repo_op("commit")),
            ("推送选中仓库", lambda: self.repo_op("push")),
            ("打开目录", self.open_selected_dir),
        ]
        for text, command in buttons:
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=(0, 6))

    def _build_tree(self, frame: "ttk.Frame") -> "ttk.Treeview":
        columns = ("label", "enabled", "exists", "branch", "head", "dirty", "path")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        headers = ["名称", "启用", "存在", "分支", "HEAD", "脏改动", "路径"]
        for column, header in zip(columns, headers):
            tree.heading(column, text=header)
            tree.column(column, width=110 if column != "path" else 360, anchor=tk.W)
        tree.pack(fill=tk.X)
        return tree

    def selected_repo_id(self) -> Optional[str]:
        selection = self.repo_tree.selection()
        return selection[0] if selection else None

    def refresh(self) -> None:
        try:
            payload = status_payload(self.root_path, self.config_path, self.ccswitch_root)
            self.render_status(payload)
        except Exception as exc:
            self.report_error("刷新失败", exc)

    def render_status(self, payload: Dict[str, object]) -> None:
        self.repo_tree.delete(*self.repo_tree.get_children())
        for item in payload.get("repos", []):
            repo = dict(item)
            self.repo_tree.insert("", tk.END, iid=str(repo["id"]), values=(
                repo["label"], repo["enabled"], repo["exists"], repo["branch"],
                repo["head"], repo["dirty"], repo["path"],
            ))
        conflicts = payload.get("conflicts", {})
        text = f"技能数: {payload.get('skill_count', 0)} | 冲突: {len(conflicts)}"
        self.status_text.set(text)
        self.write_log(json.dumps(payload, ensure_ascii=False, indent=2))

    def import_ccswitch(self) -> None:
        self.run_worker("导入中", lambda: import_ccswitch(self.root_path, self.config_path, self.ccswitch_root))

    def repo_op(self, action: str) -> None:
        repo_id = self.selected_repo_id()
        if not repo_id:
            messagebox.showwarning("Puppet Workspace", "请先选择一个仓库")
            return
        self.run_worker(f"{action} {repo_id}", lambda: repo_action(self.root_path, self.config_path, action, repo_id, None))

    def run_worker(self, label: str, func) -> None:
        self.status_text.set(label)
        threading.Thread(target=lambda: self.finish_worker(func), daemon=True).start()

    def finish_worker(self, func) -> None:
        try:
            result = func()
            self.window.after(0, lambda: self.show_result(result))
        except Exception as exc:
            self.window.after(0, lambda: self.report_error("操作失败", exc))

    def show_result(self, result: Dict[str, object]) -> None:
        self.write_log(json.dumps(result, ensure_ascii=False, indent=2))
        self.status_text.set("完成" if result.get("ok", False) else f"失败: {result.get('status', '')}")
        self.refresh()

    def open_selected_dir(self) -> None:
        repo_id = self.selected_repo_id()
        path = self.root_path if not repo_id else find_repo(load_repos(self.config_path, self.root_path), repo_id).path
        os.startfile(str(path))

    def report_error(self, title: str, exc: BaseException) -> None:
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        self.write_log(detail)
        self.status_text.set(detail)
        messagebox.showerror(title, detail)

    def write_log(self, text: str) -> None:
        self.log.insert(tk.END, text + "\n\n")
        self.log.see(tk.END)

    def run(self) -> None:
        self.window.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="puppet-workspace 管理工具")
    parser.add_argument("--workspace-root", default=str(workspace_root_from_script()))
    parser.add_argument("--config", default=None)
    parser.add_argument("--ccswitch-home", default=str(default_ccswitch_home()))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ui")
    subparsers.add_parser("status")
    subparsers.add_parser("import-ccswitch")
    repo = subparsers.add_parser("repo")
    repo.add_argument("action", choices=["pull", "commit", "push"])
    repo.add_argument("repo_id")
    repo.add_argument("--message", default=None)
    return parser


def resolve_args(args: argparse.Namespace) -> Tuple[Path, Path, Path]:
    root = Path(args.workspace_root).resolve()
    config = Path(args.config).resolve() if args.config else root / DEFAULT_CONFIG
    ccswitch = Path(args.ccswitch_home).absolute()
    return root, config, ccswitch


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["ui"]
    args = parser.parse_args(argv)
    root, config_path, ccswitch_root = resolve_args(args)
    if args.command == "ui":
        PuppetWorkspaceApp(root, config_path, ccswitch_root).run()
        return 0
    if args.command == "status":
        print_json(status_payload(root, config_path, ccswitch_root))
        return 0
    if args.command == "import-ccswitch":
        result = import_ccswitch(root, config_path, ccswitch_root)
        print_json(result)
        return 0 if result.get("ok") else 1
    result = repo_action(root, config_path, args.action, args.repo_id, args.message)
    print_json(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
