# -*- coding: utf-8 -*-
"""
Puppet Workspace 的 tkinter 窗口与托盘交互。
"""
from __future__ import annotations

import json
import os
import threading
import traceback
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:  # pragma: no cover - 无 UI 环境仍允许 CLI 使用
    tk = None
    ttk = None
    messagebox = None
    filedialog = None
    simpledialog = None

from puppet_workspace_core import (
    RepoConfig,
    WorkspaceSettings,
    alert_keys_from_payload,
    alert_text,
    clone_repo,
    delete_repo_config,
    find_repo,
    import_ccswitch,
    load_repos,
    load_settings,
    repo_action,
    repo_summary,
    save_repo_config,
    save_settings,
    set_repo_enabled,
    startup_status,
    status_payload,
    validate_repo_config,
    validate_repo_path_for_save,
)
from puppet_workspace_support import disable_startup, enable_startup
from puppet_workspace_tray import TrayController

class PuppetWorkspaceApp:
    def __init__(self, root: Path, config_path: Path, ccswitch_root: Path, start_hidden: bool = False) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("当前 Python 环境不可用 tkinter")
        self.root_path = root
        self.config_path = config_path
        self.ccswitch_root = ccswitch_root
        self.settings = load_settings(root)
        self.last_alert_keys: Set[str] = set()
        self.exiting = False
        self.window = tk.Tk()
        self.window.title("Puppet Workspace")
        self.window.geometry("1180x760")
        self.status_text = tk.StringVar(value="准备就绪")
        self.refresh_choice = tk.StringVar(value=str(self.settings.refresh_interval_minutes))
        self.close_to_tray_var = tk.BooleanVar(value=self.settings.close_to_tray)
        self.notifications_var = tk.BooleanVar(value=self.settings.notifications)
        self.startup_var = tk.BooleanVar(value=bool(startup_status(root)["enabled"]))
        self._build()
        self.tray = self._build_tray()
        self.tray_running = self.tray.start()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        if start_hidden and self.tray_running:
            self.window.withdraw()
        self.refresh()
        self.schedule_background_refresh()

    def _build(self) -> None:
        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        self._build_settings(frame)
        self._build_buttons(frame)
        self.repo_tree = self._build_tree(frame)
        self.summary = tk.Text(frame, height=8, wrap=tk.WORD)
        self.summary.pack(fill=tk.X, pady=(8, 0))
        self.log = tk.Text(frame, height=10, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(frame, textvariable=self.status_text).pack(anchor=tk.W, pady=(6, 0))

    def _build_settings(self, frame: "ttk.Frame") -> None:
        bar = ttk.Frame(frame)
        bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(bar, text="刷新频率").pack(side=tk.LEFT)
        combo = ttk.Combobox(bar, textvariable=self.refresh_choice, width=8, values=("60", "180", "360", "720", "1440"))
        combo.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(bar, text="保存设置", command=self.save_ui_settings).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(bar, text="关闭到托盘", variable=self.close_to_tray_var).pack(side=tk.LEFT)
        ttk.Checkbutton(bar, text="通知", variable=self.notifications_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(bar, text="开机自启", variable=self.startup_var, command=self.toggle_startup).pack(side=tk.LEFT, padx=(8, 0))

    def _build_buttons(self, frame: "ttk.Frame") -> None:
        bar = ttk.Frame(frame)
        bar.pack(fill=tk.X, pady=(0, 8))
        buttons = [
            ("刷新状态", self.refresh), ("导入到 ccSwitch", self.import_ccswitch),
            ("新增仓库", self.add_repo), ("编辑仓库", self.edit_repo),
            ("启用/禁用", self.toggle_repo_enabled), ("删除配置", self.delete_repo),
            ("变更摘要", self.show_repo_summary), ("拉取", lambda: self.repo_op("pull")),
            ("提交", lambda: self.repo_op("commit")), ("推送", lambda: self.repo_op("push")),
            ("打开目录", self.open_selected_dir), ("打开工作区", self.open_workspace),
        ]
        for text, command in buttons:
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=(0, 6))

    def _build_tree(self, frame: "ttk.Frame") -> "ttk.Treeview":
        columns = ("label", "enabled", "branch", "head", "dirty", "ahead", "behind", "remote", "refreshed", "path")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        headers = ["名称", "启用", "分支", "HEAD", "改动", "ahead", "behind", "远程", "刷新", "路径"]
        for column, header in zip(columns, headers):
            tree.heading(column, text=header)
            tree.column(column, width=80 if column not in {"remote", "path"} else 210, anchor=tk.W)
        tree.bind("<<TreeviewSelect>>", lambda event: self.update_selected_summary())
        tree.pack(fill=tk.X)
        return tree

    def _build_tray(self) -> TrayController:
        return TrayController(
            lambda: self.call_on_ui(self.show_window),
            lambda: self.call_on_ui(self.refresh),
            lambda: self.call_on_ui(self.import_ccswitch),
            lambda: self.call_on_ui(self.open_workspace),
            lambda: self.call_on_ui(self.toggle_startup),
            self.is_startup_enabled,
            lambda: self.call_on_ui(self.exit_app),
        )

    def selected_repo_id(self) -> Optional[str]:
        selection = self.repo_tree.selection()
        return selection[0] if selection else None

    def selected_repo(self) -> RepoConfig:
        repo_id = self.selected_repo_id()
        if not repo_id:
            raise ValueError("请先选择一个仓库")
        return find_repo(load_repos(self.config_path, self.root_path), repo_id)

    def refresh(self) -> None:
        try:
            payload = status_payload(self.root_path, self.config_path, self.ccswitch_root)
            self.render_status(payload)
            self.notify_status(payload)
        except Exception as exc:
            self.report_error("刷新失败", exc)

    def render_status(self, payload: Dict[str, object]) -> None:
        self.repo_tree.delete(*self.repo_tree.get_children())
        for item in payload.get("repos", []):
            repo = dict(item)
            self.repo_tree.insert("", tk.END, iid=str(repo["id"]), values=self.repo_values(repo))
        conflicts = payload.get("conflicts", {})
        self.status_text.set(f"技能数: {payload.get('skill_count', 0)} | 冲突: {len(conflicts)}")
        self.write_log(json.dumps(payload, ensure_ascii=False, indent=2))
        self.update_selected_summary()

    def repo_values(self, repo: Dict[str, object]) -> Tuple[object, ...]:
        return (
            repo["label"], repo["enabled"], repo.get("branch"), repo.get("head"),
            repo.get("dirty_count"), repo.get("ahead"), repo.get("behind"),
            repo.get("remote"), repo.get("refreshed_at"), repo.get("path"),
        )

    def update_selected_summary(self) -> None:
        repo_id = self.selected_repo_id()
        if not repo_id:
            self.set_summary("未选择仓库")
            return
        try:
            result = repo_summary(self.root_path, self.config_path, repo_id)
            self.set_summary(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.set_summary("".join(traceback.format_exception_only(type(exc), exc)).strip())

    def set_summary(self, text: str) -> None:
        self.summary.delete("1.0", tk.END)
        self.summary.insert(tk.END, text)

    def notify_status(self, payload: Dict[str, object]) -> None:
        keys = alert_keys_from_payload(payload)
        new_keys = keys - self.last_alert_keys
        self.last_alert_keys = keys
        if new_keys and self.settings.notifications and self.tray_running:
            self.tray.notify("Puppet Workspace", alert_text(new_keys))

    def import_ccswitch(self) -> None:
        self.run_worker("导入中", lambda: import_ccswitch(self.root_path, self.config_path, self.ccswitch_root))

    def repo_op(self, action: str) -> None:
        try:
            repo_id, message = self.prepare_repo_op(action)
        except Exception as exc:
            self.report_error("操作取消", exc)
            return
        self.run_worker(f"{action} {repo_id}", lambda: repo_action(self.root_path, self.config_path, action, repo_id, message))

    def prepare_repo_op(self, action: str) -> Tuple[str, Optional[str]]:
        repo_id = self.selected_repo_id()
        if not repo_id:
            raise ValueError("请先选择一个仓库")
        if action != "commit":
            return repo_id, None
        summary = repo_summary(self.root_path, self.config_path, repo_id).get("changes", "")
        if not summary:
            raise ValueError("工作区干净，无需提交")
        if not messagebox.askokcancel("提交确认", f"将提交以下文件：\n\n{summary}"):
            raise ValueError("用户取消提交")
        message = simpledialog.askstring("提交信息", "请输入提交信息：")
        if not message:
            raise ValueError("提交信息不能为空")
        return repo_id, message

    def add_repo(self) -> None:
        repo = self.ask_repo_fields(None)
        if repo is None:
            return
        self.run_worker("保存仓库", lambda: self.save_and_maybe_clone(repo, None))

    def edit_repo(self) -> None:
        repo = self.selected_repo()
        updated = self.ask_repo_fields(repo)
        if updated is None:
            return
        self.run_worker("保存仓库", lambda: self.save_and_maybe_clone(updated, repo.id))

    def ask_repo_fields(self, repo: Optional[RepoConfig]) -> Optional[RepoConfig]:
        repo_id = simpledialog.askstring("仓库 ID", "repo-id：", initialvalue=repo.id if repo else "")
        if repo_id is None:
            return None
        label = simpledialog.askstring("仓库名称", "显示名称：", initialvalue=repo.label if repo else repo_id)
        branch = simpledialog.askstring("分支", "默认分支：", initialvalue=repo.branch if repo else "main")
        remote = simpledialog.askstring("远程地址", "remote URL：", initialvalue=repo.remote if repo else "")
        path = self.ask_repo_path(repo_id, repo.path if repo else None)
        if not label or not branch or remote is None or path is None:
            return None
        return RepoConfig(repo_id.strip(), label.strip(), path, remote.strip(), branch.strip(), True if repo is None else repo.enabled)

    def ask_repo_path(self, repo_id: str, current: Optional[Path]) -> Optional[Path]:
        if filedialog is None:
            return current or self.root_path / "skill-repos" / repo_id
        initial = str(current or self.root_path / "skill-repos")
        selected = filedialog.askdirectory(title="选择仓库目录，取消则使用默认路径", initialdir=initial)
        return Path(selected).resolve() if selected else self.root_path / "skill-repos" / repo_id

    def save_and_maybe_clone(self, repo: RepoConfig, old_id: Optional[str]) -> Dict[str, object]:
        validate_repo_config(repo, load_repos(self.config_path, self.root_path), old_id)
        validate_repo_path_for_save(repo)
        if repo.remote and not repo.path.exists():
            clone_repo(self.root_path, repo)
        return save_repo_config(self.root_path, self.config_path, repo, old_id)

    def toggle_repo_enabled(self) -> None:
        repo = self.selected_repo()
        self.run_worker("切换启用状态", lambda: set_repo_enabled(self.root_path, self.config_path, repo.id, not repo.enabled))

    def delete_repo(self) -> None:
        repo = self.selected_repo()
        if messagebox.askokcancel("删除配置", f"只删除配置，不删除目录：\n{repo.path}"):
            self.run_worker("删除配置", lambda: delete_repo_config(self.root_path, self.config_path, repo.id))

    def show_repo_summary(self) -> None:
        self.update_selected_summary()

    def save_ui_settings(self) -> None:
        self.settings = WorkspaceSettings(int(self.refresh_choice.get()), self.close_to_tray_var.get(), self.notifications_var.get(), True)
        save_settings(self.root_path, self.settings)
        self.status_text.set("设置已保存")

    def toggle_startup(self) -> None:
        try:
            result = disable_startup(self.root_path) if self.is_startup_enabled() else enable_startup(self.root_path)
            self.startup_var.set(bool(result["enabled"]))
            self.write_log(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.startup_var.set(self.is_startup_enabled())
            self.report_error("开机自启失败", exc)

    def is_startup_enabled(self) -> bool:
        return bool(startup_status(self.root_path)["enabled"])

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
        self.notify_result(result)
        self.refresh()

    def notify_result(self, result: Dict[str, object]) -> None:
        if result.get("ok", False) or not self.settings.notifications or not self.tray_running:
            return
        status = result.get("status") or result.get("action") or "操作失败"
        detail = result.get("stderr") or result.get("mismatches") or result.get("conflicts") or ""
        self.tray.notify("Puppet Workspace", f"{status}: {detail}")

    def schedule_background_refresh(self) -> None:
        minutes = max(1, self.settings.refresh_interval_minutes)
        self.window.after(minutes * 60 * 1000, self.background_refresh)

    def background_refresh(self) -> None:
        if not self.exiting:
            self.refresh()
            self.schedule_background_refresh()

    def call_on_ui(self, func) -> None:
        self.window.after(0, func)

    def show_window(self) -> None:
        self.window.deiconify()
        self.window.lift()

    def on_close(self) -> None:
        if self.settings.close_to_tray and self.tray_running:
            self.window.withdraw()
            return
        self.exit_app()

    def exit_app(self) -> None:
        self.exiting = True
        self.tray.stop()
        self.window.destroy()

    def open_workspace(self) -> None:
        os.startfile(str(self.root_path))

    def open_selected_dir(self) -> None:
        path = self.root_path if not self.selected_repo_id() else self.selected_repo().path
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


# 兼容旧导入路径；真实窗口实现已迁移到 puppet_workspace_app.py。
from puppet_workspace_app import PuppetWorkspaceApp  # noqa: E402,F401
