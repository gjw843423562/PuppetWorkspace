# -*- coding: utf-8 -*-
"""
Puppet Workspace 的 tkinter 小组件封装。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None
    ttk = None

from puppet_workspace.puppet_workspace_view import COLORS, CardInfo, icon_path


class IconStore:
    def __init__(self, root: Path, master: "tk.Misc") -> None:
        self.root = root
        self.master = master
        self.cache: Dict[str, "tk.PhotoImage"] = {}

    def get(self, name: str) -> Optional["tk.PhotoImage"]:
        if tk is None:
            return None
        if name not in self.cache:
            path = icon_path(self.root, name)
            if path.is_file():
                self.cache[name] = tk.PhotoImage(master=self.master, file=str(path))
        return self.cache.get(name)


def configure_theme(window: "tk.Tk") -> None:
    window.configure(bg=COLORS["bg"])
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure("App.TFrame", background=COLORS["bg"])
    style.configure("Panel.TFrame", background=COLORS["panel"])
    style.configure("Nav.TButton", padding=(12, 10), anchor="w")
    style.configure("Primary.TButton", padding=(14, 9), foreground="#ffffff", background=COLORS["primary"])
    style.map("Primary.TButton", background=[("active", COLORS["primary_dark"])])
    style.configure("Soft.TButton", padding=(12, 8))
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=("Microsoft YaHei UI", 18, "bold"))
    style.configure("Subtle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
    style.configure("PanelTitle.TLabel", background=COLORS["panel"], foreground=COLORS["ink"], font=("Microsoft YaHei UI", 13, "bold"))
    style.configure("PanelText.TLabel", background=COLORS["panel"], foreground=COLORS["muted"])
    style.configure("CardValue.TLabel", background=COLORS["panel"], foreground=COLORS["ink"], font=("Microsoft YaHei UI", 17, "bold"))
    style.configure("Treeview", rowheight=28)


def clear(frame: "ttk.Frame") -> None:
    for child in frame.winfo_children():
        child.destroy()


def title(parent: "ttk.Frame", text: str, detail: str = "") -> None:
    ttk.Label(parent, text=text, style="Title.TLabel").pack(anchor="w")
    if detail:
        ttk.Label(parent, text=detail, style="Subtle.TLabel").pack(anchor="w", pady=(4, 14))


def action_button(parent: "ttk.Frame", text: str, command: Callable[[], None], icon: Optional["tk.PhotoImage"], primary: bool = False) -> "ttk.Button":
    button = ttk.Button(parent, text=text, image=icon, compound="left", command=command, style="Primary.TButton" if primary else "Soft.TButton")
    button.pack(side="left", padx=(0, 8), pady=(0, 8))
    return button


def nav_button(parent: "ttk.Frame", text: str, command: Callable[[], None], icon: Optional["tk.PhotoImage"]) -> "ttk.Button":
    button = ttk.Button(parent, text=text, image=icon, compound="left", command=command, style="Nav.TButton")
    button.pack(fill="x", pady=(0, 6))
    return button


def card(parent: "ttk.Frame", info: CardInfo) -> "ttk.Frame":
    frame = ttk.Frame(parent, style="Panel.TFrame", padding=14)
    ttk.Label(frame, text=info.title, style="PanelText.TLabel").pack(anchor="w")
    ttk.Label(frame, text=info.value, style="CardValue.TLabel").pack(anchor="w", pady=(8, 4))
    ttk.Label(frame, text=info.detail, style="PanelText.TLabel", wraplength=230).pack(anchor="w")
    frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
    return frame


def panel(parent: "ttk.Frame", title_text: str) -> "ttk.Frame":
    frame = ttk.Frame(parent, style="Panel.TFrame", padding=14)
    frame.pack(fill="both", expand=True, pady=(0, 10))
    ttk.Label(frame, text=title_text, style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 8))
    return frame
