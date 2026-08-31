# -*- coding: utf-8 -*-
"""
Puppet Workspace 主窗口动作逻辑。
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
    from tkinter import filedialog, messagebox, simpledialog
except Exception:  # pragma: no cover
    tk = None
    messagebox = None
    filedialog = None
    simpledialog = None

from puppet_workspace_core import (
    RepoConfig, WorkspaceSettings, alert_keys_from_payload, alert_text, clone_repo,
    delete_repo_config, find_repo, import_ccswitch, load_repos, repo_action,
    repo_summary, restore_backup, save_repo_config, save_settings, set_repo_enabled,
    startup_status, validate_repo_config, validate_repo_path_for_save,
)
from puppet_workspace_support import disable_startup, enable_startup
from puppet_workspace_view import friendly_repo_status, human_action_label


class WorkspaceActions:
    def selected_repo_id(self) -> Optional[str]:
        tree = getattr(self, "repo_tree", None)
        selection = tree.selection() if tree is not None else ()
        return selection[0] if selection else None

    def selected_repo(self) -> RepoConfig:
        repo_id = self.selected_repo_id()
        if not repo_id:
            raise ValueError("请先选择一个仓库")
        return find_repo(load_repos(self.config_path, self.root_path), repo_id)

    def update_selected_summary(self) -> None:
        summary = getattr(self, "summary", None)
        if summary is None:
            return
        repo_id = self.selected_repo_id()
        text = "未选择仓库" if not repo_id else self.repo_summary_text(repo_id)
        summary.delete("1.0", tk.END)
        summary.insert(tk.END, text)

    def repo_summary_text(self, repo_id: str) -> str:
        try:
            result = repo_summary(self.root_path, self.config_path, repo_id)
            status = result.get("status", {})
            friendly, _ = friendly_repo_status(status if isinstance(status, dict) else {})
            changes = result.get("changes") or "没有未保存改动。"
            return f"状态：{friendly}\n远程：{status.get('remote', '')}\n\n改动：\n{changes}"
        except Exception as exc:
            return "".join(traceback.format_exception_only(type(exc), exc)).strip()

    def commit_first_dirty(self) -> None:
        for repo in self.payload.get("repos", []):
            if isinstance(repo, dict) and int(repo.get("dirty_count", 0) or 0) > 0:
                self.select_repo_in_page(str(repo["id"]))
                self.repo_op("commit")
                return
        messagebox.showinfo("Puppet Workspace", "没有需要保存的改动")

    def select_repo_in_page(self, repo_id: str) -> None:
        self.current_page = "repos"
        self.render_current_page()
        self.repo_tree.selection_set(repo_id)
        self.update_selected_summary()

    def import_ccswitch(self) -> None:
        self.run_worker("正在同步到 AI", lambda: import_ccswitch(self.root_path, self.config_path, self.ccswitch_root))

    def repo_op(self, action: str) -> None:
        try:
            repo_id, message = self.prepare_repo_op(action)
        except Exception as exc:
            self.report_error("操作取消", exc)
            return
        label = human_action_label(action)
        self.run_worker(f"{label}: {repo_id}", lambda: repo_action(self.root_path, self.config_path, action, repo_id, message))

    def prepare_repo_op(self, action: str) -> Tuple[str, Optional[str]]:
        repo_id = self.selected_repo_id()
        if not repo_id:
            raise ValueError("请先选择一个仓库")
        if action != "commit":
            return repo_id, None
        summary = repo_summary(self.root_path, self.config_path, repo_id).get("changes", "")
        if not summary:
            raise ValueError("工作区干净，无需提交")
        if not messagebox.askokcancel("提交确认", f"将保存以下改动：\n\n{summary}"):
            raise ValueError("用户取消提交")
        message = simpledialog.askstring("提交信息", "这次改动叫什么？")
        if not message:
            raise ValueError("提交信息不能为空")
        return repo_id, message

    def add_repo(self) -> None:
        repo = self.ask_repo_fields(None)
        if repo is not None:
            self.run_worker("保存仓库", lambda: self.save_and_maybe_clone(repo, None))

    def edit_repo(self) -> None:
        repo = self.selected_repo()
        updated = self.ask_repo_fields(repo)
        if updated is not None:
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
        enabled = True if repo is None else repo.enabled
        return RepoConfig(repo_id.strip(), label.strip(), path, remote.strip(), branch.strip(), enabled)

    def ask_repo_path(self, repo_id: str, current: Optional[Path]) -> Optional[Path]:
        if filedialog is None:
            return current or self.root_path / "skill-repos" / repo_id
        selected = filedialog.askdirectory(title="选择仓库目录，取消则使用默认路径", initialdir=str(current or self.root_path / "skill-repos"))
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
        if messagebox.askokcancel("删除配置", f"只删除工具里的登记，不删除目录：\n{repo.path}"):
            self.run_worker("删除配置", lambda: delete_repo_config(self.root_path, self.config_path, repo.id))

    def show_repo_summary(self) -> None:
        self.update_selected_summary()

    def open_selected_backup(self) -> None:
        row = self.selected_backup_row()
        if row:
            os.startfile(row[2])

    def restore_selected_backup(self) -> None:
        row = self.selected_backup_row()
        if not row:
            messagebox.showwarning("Puppet Workspace", "请先选择一个备份")
            return
        kind = "ccswitch" if row[0] == "AI 技能备份" else "config"
        if messagebox.askokcancel("恢复备份", f"确认恢复这个备份？\n\n{row[2]}"):
            self.run_worker("恢复备份", lambda: restore_backup(self.root_path, self.config_path, self.ccswitch_root, kind, Path(row[2])))

    def selected_backup_row(self) -> Optional[Tuple[str, str, str]]:
        tree = getattr(self, "backup_tree", None)
        if tree is None or not tree.selection():
            return None
        values = tree.item(tree.selection()[0], "values")
        return tuple(values) if len(values) == 3 else None

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

    def notify_status(self) -> None:
        keys: Set[str] = alert_keys_from_payload(self.payload)
        new_keys = keys - self.last_alert_keys
        self.last_alert_keys = keys
        if new_keys and self.settings.notifications and self.tray_running:
            self.tray.notify("Puppet Workspace", alert_text(new_keys))

    def notify_result(self, result: Dict[str, object]) -> None:
        if result.get("ok", False) or not self.settings.notifications or not self.tray_running:
            return
        status = result.get("status") or result.get("action") or "操作失败"
        detail = result.get("stderr") or result.get("mismatches") or result.get("conflicts") or ""
        self.tray.notify("Puppet Workspace", f"{status}: {detail}")

    def schedule_background_refresh(self) -> None:
        self.window.after(max(1, self.settings.refresh_interval_minutes) * 60 * 1000, self.background_refresh)

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
        self.log_items.append(text)
        log = getattr(self, "log", None)
        if log is not None:
            log.insert(tk.END, text + "\n\n")
            log.see(tk.END)
