# -*- coding: utf-8 -*-
"""
Puppet Workspace 的通俗化 tkinter 主窗口。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Set

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:  # pragma: no cover
    tk = None
    ttk = None
    messagebox = None
    filedialog = None
    simpledialog = None

from puppet_workspace.puppet_workspace_actions import WorkspaceActions
from puppet_workspace.puppet_workspace_support import OperationCoordinator, SingleInstanceLock
from puppet_workspace.puppet_workspace_core import load_settings, startup_status, status_payload, state_home
from puppet_workspace.puppet_workspace_pages import (
    build_backups, build_logs, build_overview, build_repos, build_settings,
    build_sync, build_targets,
)
from puppet_workspace.puppet_workspace_tray import TrayController
from puppet_workspace.puppet_workspace_tools import build_tools
from puppet_workspace.puppet_workspace_view import NAV_ITEMS, friendly_repo_status
from puppet_workspace.puppet_workspace_widgets import IconStore, clear, configure_theme, nav_button


class PuppetWorkspaceApp(WorkspaceActions):
    def __init__(self, root: Path, config_path: Path, ccswitch_root: Path, start_hidden: bool = False) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("当前 Python 环境不可用 tkinter")
        self.root_path = root
        self.config_path = config_path
        self.ccswitch_root = ccswitch_root
        self.settings = load_settings(root)
        self.last_alert_keys: Set[str] = set()
        self.log_items: list[str] = []
        self.current_page = "overview"
        self.payload: Dict[str, object] = {}
        self.exiting = False
        self.coordinator = OperationCoordinator()
        self.single_instance_lock = SingleInstanceLock(state_home(root) / "puppet_workspace.lock")
        if not self.single_instance_lock.acquire():
            messagebox.showwarning("实例运行中", "Puppet Workspace 已在运行中，请勿重复启动")
            raise RuntimeError("Puppet Workspace 已在运行中")
        self.window = tk.Tk()
        configure_theme(self.window)
        self.window.title("Puppet Workspace")
        self.window.geometry("1180x760")
        self.status_text = tk.StringVar(value="准备就绪")
        self.refresh_choice = tk.StringVar(value=str(self.settings.refresh_interval_minutes))
        self.close_to_tray_var = tk.BooleanVar(value=self.settings.close_to_tray)
        self.notifications_var = tk.BooleanVar(value=self.settings.notifications)
        self.startup_var = tk.BooleanVar(value=bool(startup_status(root)["enabled"]))
        self.icons = IconStore(root, self.window)
        self._build_shell()
        self.tray = self._build_tray()
        self.tray_running = self.tray.start()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        if start_hidden and self.tray_running:
            self.window.withdraw()
        self.refresh()
        self.schedule_background_refresh()

    def _build_shell(self) -> None:
        shell = ttk.Frame(self.window, style="App.TFrame", padding=10)
        shell.pack(fill="both", expand=True)
        self.nav = ttk.Frame(shell, style="Panel.TFrame", padding=10)
        self.nav.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(self.nav, text="Puppet", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 12))
        for page_id, label, icon_name in NAV_ITEMS:
            nav_button(self.nav, label, lambda target=page_id: self.select_page(target), self.icon(icon_name))
        self.content = ttk.Frame(shell, style="App.TFrame")
        self.content.pack(side="left", fill="both", expand=True)
        ttk.Label(shell, textvariable=self.status_text, style="Subtle.TLabel").pack(side="bottom", anchor="w")

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

    def icon(self, name: str) -> Optional["tk.PhotoImage"]:
        return self.icons.get(name)

    def select_page(self, page_id: str) -> None:
        self.current_page = page_id
        self.render_current_page()

    def render_current_page(self) -> None:
        clear(self.content)
        pages = {
            "overview": build_overview, "sync": build_sync, "repos": build_repos,
            "targets": build_targets, "backups": build_backups,
            "settings": build_settings, "logs": build_logs,
            "tools": build_tools,
        }
        pages.get(self.current_page, build_overview)(self, self.content)

    def refresh(self) -> None:
        try:
            self.payload = status_payload(self.root_path, self.config_path, self.ccswitch_root)
            self.status_text.set(self.short_status())
            self.write_log(json.dumps(self.payload, ensure_ascii=False, indent=2))
            self.render_current_page()
            self.notify_status()
        except Exception as exc:
            self.report_error("刷新失败", exc)

    def short_status(self) -> str:
        if self.payload.get("conflicts"):
            return "有同名技能，需要处理"
        count = sum(1 for repo in self.payload.get("repos", []) if isinstance(repo, dict) and friendly_repo_status(repo)[1] in {"warn", "danger"})
        return "状态正常" if count == 0 else f"{count} 个仓库待处理"

    def run(self) -> None:
        self.window.mainloop()
