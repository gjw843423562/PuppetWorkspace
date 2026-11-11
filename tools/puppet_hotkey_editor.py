# -*- coding: utf-8 -*-
"""工具编辑；录入时暂停全局快捷键，防止误启动。"""
import copy
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from puppet_hotkey_native import NativeWindow, capture_key


class ToolEditor:
    def __init__(self, app, index=None, dropped=None, main=False):
        self.app, self.index, self.main = app, index, main
        self.window = tk.Toplevel(app.window)
        self.window.title("主窗口快捷键" if main else "编辑工具")
        self.window.geometry("680x370")
        self.window.transient(app.window)
        self.window.grab_set()
        self.fields = {}
        self.original = {} if index is None else app.config["Tools"][index]
        self._build(dropped)
        self.native = NativeWindow(self.window, lambda identity: None, self.fill_path)
        app.registry.close()
        app.status.set("编辑期间暂停全局快捷键，关闭编辑窗口后恢复")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self, dropped):
        box = ttk.Frame(self.window, padding=16)
        box.pack(fill="both", expand=True)
        keys = [("Hotkey", "快捷键")] if self.main else [
            ("Name", "名称"), ("Path", "路径或网址"), ("Description", "说明"),
            ("Hotkey", "快捷键"), ("Args", "参数（JSON 数组）")]
        for row, (key, label) in enumerate(keys):
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", pady=7)
            value = self.app.config["MainHotkey"] if self.main else self.original.get(key, "")
            if key == "Args":
                value = json.dumps(self.original.get(key, []), ensure_ascii=False)
            self.fields[key] = tk.StringVar(value=value)
            entry = ttk.Entry(box, textvariable=self.fields[key], width=62)
            entry.grid(row=row, column=1, sticky="ew", padx=(8, 0))
            if key == "Hotkey":
                entry.bind("<KeyPress>", self.capture)
        box.columnconfigure(1, weight=1)
        self._buttons(box, len(keys))
        if dropped:
            self.fill_path(dropped)

    def _buttons(self, box, row):
        actions = ttk.Frame(box)
        actions.grid(row=row, column=0, columnspan=2, pady=14, sticky="w")
        if not self.main:
            ttk.Button(actions, text="选择文件", command=self.browse_file).pack(side="left", padx=4)
            ttk.Button(actions, text="选择目录", command=self.browse_folder).pack(side="left", padx=4)
        ttk.Button(actions, text="保存并生效", command=self.save).pack(side="left", padx=4)
        ttk.Button(actions, text="取消", command=self.close).pack(side="left", padx=4)
        ttk.Label(box, text="快捷键可直接按键录入或粘贴文本。支持将文件或目录拖入此窗口。", wraplength=610).grid(row=row+1, column=0, columnspan=2, sticky="w")
        return True

    def capture(self, event):
        if event.keysym.lower() == "v" and event.state & 4:
            return None
        text = capture_key(event)
        if text:
            self.fields["Hotkey"].set(text)
        return "break"

    def fill_path(self, path):
        if "Path" in self.fields:
            self.fields["Path"].set(path)
            if not self.fields["Name"].get().strip():
                self.fields["Name"].set(Path(path).stem)
        return True

    def browse_file(self):
        path = filedialog.askopenfilename(parent=self.window, title="选择工具文件")
        if path:
            self.fill_path(path)
        return True

    def browse_folder(self):
        path = filedialog.askdirectory(parent=self.window, title="选择目标目录")
        if path:
            self.fill_path(path)
        return True

    def save(self):
        try:
            candidate = copy.deepcopy(self.app.config)
            if self.main:
                candidate["MainHotkey"] = self.fields["Hotkey"].get().strip()
            else:
                self._update_tool(candidate)
            if self.app.commit(candidate) is True:
                self.close()
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法保存", str(exc), parent=self.window)
        return True

    def _update_tool(self, candidate):
        tool = copy.deepcopy(self.original)
        tool.update({key: variable.get().strip() for key, variable in self.fields.items() if key != "Args"})
        tool["Args"] = json.loads(self.fields["Args"].get())
        if self.index is None:
            candidate["Tools"].append(tool)
        else:
            candidate["Tools"][self.index] = tool
        return True

    def close(self):
        try:
            self.app.registry.apply(self.app.config)
            self.app.registration_status()
        except ValueError as exc:
            self.app.error(exc)
        self.native.close()
        self.fields.clear()
        self.window.grab_release()
        self.window.destroy()
        self.app.editor = None
        return True
