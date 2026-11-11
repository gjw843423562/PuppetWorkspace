# -*- coding: utf-8 -*-
"""
Puppet Workspace 的导航页面布局。
"""
from __future__ import annotations

from typing import Dict
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None
    ttk = None

from puppet_workspace_view import friendly_repo_status, overview_cards, recent_backups
from puppet_workspace_widgets import action_button, card, panel, title


def build_overview(app, parent: "ttk.Frame") -> None:
    title(parent, "Puppet 技能库", "日常只看这里就够了：同步状态、仓库状态、后台守护。")
    actions = ttk.Frame(parent, style="App.TFrame")
    actions.pack(fill="x")
    action_button(actions, "同步到 AI", app.import_ccswitch, app.icon("sync"), True)
    action_button(actions, "检查状态", app.refresh, app.icon("refresh"))
    action_button(actions, "保存我的改动", app.commit_first_dirty, app.icon("save"))
    cards = ttk.Frame(parent, style="App.TFrame")
    cards.pack(fill="x", pady=(10, 10))
    for info in overview_cards(app.payload, app.tray_running):
        card(cards, info)
    work = panel(parent, "要处理的事")
    rows = problem_rows(app.payload)
    ttk.Label(work, text="\n".join(rows) if rows else "暂时没有需要处理的问题。", style="PanelText.TLabel").pack(anchor="w")


def build_sync(app, parent: "ttk.Frame") -> None:
    title(parent, "技能同步", "把启用仓库里的 Puppet / SC 技能同步到 Codex 可调用的位置。")
    actions = ttk.Frame(parent, style="App.TFrame")
    actions.pack(fill="x")
    app.sync_repo_ids = {"全部启用仓库": None}
    for repo in app.payload.get("repos", []):
        if isinstance(repo, dict) and repo.get("enabled", True):
            app.sync_repo_ids[f"{repo['label']} ({repo['id']})"] = repo["id"]
    app.sync_repo_choice = tk.StringVar(value="全部启用仓库")
    ttk.Label(actions, text="同步范围：").pack(side="left")
    ttk.Combobox(actions, textvariable=app.sync_repo_choice, values=list(app.sync_repo_ids), state="readonly", width=26).pack(side="left", padx=(0, 8))
    action_button(actions, "同步到 AI", app.import_ccswitch, app.icon("sync"), True)
    action_button(actions, "检查状态", app.refresh, app.icon("refresh"))
    conflicts = app.payload.get("conflicts", {})
    box = panel(parent, "同步检查")
    if conflicts:
        text = "\n".join([f"{name}：来自 {', '.join(repos)}" for name, repos in conflicts.items()])
    else:
        text = "没有同名技能冲突，可以同步。"
    ttk.Label(box, text=text, style="PanelText.TLabel", wraplength=760).pack(anchor="w")


def build_repos(app, parent: "ttk.Frame") -> None:
    title(parent, "技能仓库", "新增支持本地Git或远程仓库；本地仓库无需远程地址，可直接初始化。")
    actions = ttk.Frame(parent, style="App.TFrame")
    actions.pack(fill="x")
    for label, command, icon_name in repo_actions(app).values():
        action_button(actions, label, command, app.icon(icon_name))
    app.repo_tree = repo_tree(parent)
    for repo in app.payload.get("repos", []):
        if isinstance(repo, dict):
            app.repo_tree.insert("", "end", iid=str(repo["id"]), values=repo_row(repo))
    app.repo_tree.bind("<<TreeviewSelect>>", lambda event: app.update_selected_summary())
    app.summary = tk.Text(parent, height=7, wrap="word")
    app.summary.pack(fill="x", pady=(8, 0))
    app.update_selected_summary()


def build_targets(app, parent: "ttk.Frame") -> None:
    title(parent, "AI 位置", "这些是技能被同步过去、供 AI 调用的位置。")
    box = panel(parent, "ccSwitch")
    ttk.Label(box, text=f"当前目标：{app.payload.get('ccswitch', '')}", style="PanelText.TLabel", wraplength=760).pack(anchor="w")
    codex = panel(parent, "Codex")
    ttk.Label(codex, text=f"技能入口：{Path.home() / '.codex' / 'skills'}\n同步时建立目录入口，正本保留在各技能仓库。", style="PanelText.TLabel").pack(anchor="w")


def build_backups(app, parent: "ttk.Frame") -> None:
    title(parent, "备份恢复", "同步或修改配置前留下的备份都在这里。恢复前会再次确认。")
    actions = ttk.Frame(parent, style="App.TFrame")
    actions.pack(fill="x")
    action_button(actions, "打开备份", app.open_selected_backup, app.icon("folder"))
    action_button(actions, "恢复备份", app.restore_selected_backup, app.icon("backup"))
    app.backup_tree = backup_tree(parent)
    for kind, stamp, path in recent_backups(app.root_path):
        app.backup_tree.insert("", "end", values=(backup_kind_label(kind), stamp, path))


def build_settings(app, parent: "ttk.Frame") -> None:
    title(parent, "设置", "控制后台守护、提醒和开机自启。")
    box = panel(parent, "日常行为")
    row = ttk.Frame(box, style="Panel.TFrame")
    row.pack(fill="x")
    ttk.Label(row, text="检查频率", style="PanelText.TLabel").pack(side="left")
    ttk.Combobox(row, textvariable=app.refresh_choice, width=8, values=("60", "180", "360", "720", "1440")).pack(side="left", padx=(8, 16))
    ttk.Checkbutton(row, text="关闭到托盘", variable=app.close_to_tray_var).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(row, text="提醒我", variable=app.notifications_var).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(row, text="开机自启", variable=app.startup_var, command=app.toggle_startup).pack(side="left")
    action_button(box, "保存设置", app.save_ui_settings, app.icon("settings"))


def build_logs(app, parent: "ttk.Frame") -> None:
    title(parent, "高级日志", "这里保留原始输出，排查问题时再看。")
    app.log = tk.Text(parent, height=26, wrap="word")
    app.log.pack(fill="both", expand=True)
    app.log.insert("end", "\n\n".join(app.log_items[-30:]))
    app.log.see("end")


def problem_rows(payload: Dict[str, object]) -> list[str]:
    rows = []
    if payload.get("conflicts"):
        rows.append("有同名技能，需要先处理冲突。")
    for repo in payload.get("repos", []):
        if isinstance(repo, dict):
            text, tone = friendly_repo_status(repo)
            if tone in {"warn", "danger"}:
                rows.append(f"{repo.get('label') or repo.get('id')}：{text}")
    return rows


def repo_actions(app) -> Dict[str, tuple]:
    return {
        "add": ("新增", app.add_repo, "repo"),
        "edit": ("编辑", app.edit_repo, "settings"),
        "toggle": ("启用/禁用", app.toggle_repo_enabled, "ok"),
        "delete": ("删除配置", app.delete_repo, "danger"),
        "summary": ("查看改动", app.show_repo_summary, "log"),
        "pull": ("检查更新", lambda: app.repo_op("pull"), "refresh"),
        "commit": ("保存改动", lambda: app.repo_op("commit"), "save"),
        "push": ("上传提交", lambda: app.repo_op("push"), "sync"),
        "open": ("打开目录", app.open_selected_dir, "folder"),
    }


def repo_tree(parent: "ttk.Frame") -> "ttk.Treeview":
    columns = ("label", "state", "enabled", "branch", "changes", "path")
    tree = ttk.Treeview(parent, columns=columns, show="headings", height=12)
    for column, header, width in [
        ("label", "名称", 140), ("state", "状态", 170), ("enabled", "启用", 70),
        ("branch", "分支", 90), ("changes", "改动", 70), ("path", "路径", 420),
    ]:
        tree.heading(column, text=header)
        tree.column(column, width=width, anchor="w")
    tree.pack(fill="x", pady=(6, 0))
    return tree


def repo_row(repo: Dict[str, object]) -> tuple:
    status, _ = friendly_repo_status(repo)
    return (
        repo.get("label"), status, "是" if repo.get("enabled") else "否",
        repo.get("branch"), repo.get("dirty_count"), repo.get("path"),
    )


def backup_tree(parent: "ttk.Frame") -> "ttk.Treeview":
    columns = ("kind", "time", "path")
    tree = ttk.Treeview(parent, columns=columns, show="headings", height=14)
    for column, header, width in [("kind", "类型", 120), ("time", "时间", 180), ("path", "路径", 580)]:
        tree.heading(column, text=header)
        tree.column(column, width=width, anchor="w")
    tree.pack(fill="both", expand=True, pady=(6, 0))
    return tree


def backup_kind_label(kind: str) -> str:
    return "AI 技能备份" if kind == "ccswitch" else "配置备份"
