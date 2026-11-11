# -*- coding: utf-8 -*-
"""独立快捷键管理窗口；热键与配置切换由主线程串行处理。"""
import copy
import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from puppet_hotkeys.puppet_hotkey_config import read_config, save_config, validate_config
from puppet_hotkeys.puppet_hotkey_editor import ToolEditor
from puppet_hotkeys.puppet_hotkey_launch import launch_target
from puppet_hotkeys.puppet_hotkey_native import NativeWindow
from puppet_hotkeys.puppet_hotkey_registry import HotkeyRegistry
from puppet_hotkeys.puppet_hotkey_startup import set_startup, startup_enabled


class HotkeyApp:
    def __init__(self, path, title, silent=False, tray_enabled=True):
        self.path = path
        self.config, self.digest = read_config(path)
        self.events = queue.SimpleQueue()
        self.editor, self.tray, self.poll_id = None, None, None
        self.busy = False
        self.closed = False
        self.window = tk.Tk()
        self.window.title(title)
        self.window.geometry("990x580")
        self.window.minsize(760, 420)
        self.window.report_callback_exception = self.callback_error
        self.status = tk.StringVar(value="正在注册快捷键")
        self._build()
        self.native = NativeWindow(self.window, self.on_hotkey, self.on_drop)
        self.registry = HotkeyRegistry(self.native)
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        if tray_enabled:
            self._start_tray()
        registered = self.apply_current()
        self.poll_id = self.window.after(100, self.poll)
        if silent and self.tray is not None and registered:
            self.window.withdraw()

    def _build(self):
        box = ttk.Frame(self.window, padding=16)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Puppet 快捷键工具", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(box, text="全局热键打开程序、目录或网址；保存后立即生效。可直接拖入文件。", padding=(0, 8)).pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=10)
        for label, command in self.actions():
            ttk.Button(row, text=label, command=command).pack(side="left", padx=(0, 6))
        self.startup = tk.BooleanVar(value=startup_enabled())
        ttk.Checkbutton(box, text="新版工具开机自启", variable=self.startup,
                        command=self.toggle_startup).pack(anchor="w", pady=(0, 8))
        self.tree = ttk.Treeview(box, columns=("name", "key", "description", "path"), show="headings", selectmode="browse")
        for name, label, width in (("name", "名称", 150), ("key", "快捷键", 190),
                                   ("description", "说明", 150), ("path", "目标路径", 360)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda event: self.edit_selected())
        ttk.Label(box, textvariable=self.status, wraplength=920).pack(anchor="w", pady=(12, 0))
        self.refresh_rows()
        return True

    def actions(self):
        return [("打开", self.launch_selected), ("新增", self.open_editor),
                ("编辑", self.edit_selected), ("删除", self.delete_selected),
                ("主快捷键", self.edit_main), ("重新加载", self.reload),
                ("配置目录", self.open_folder), ("退出", self.quit)]

    def refresh_rows(self):
        for identity in self.tree.get_children():
            self.tree.delete(identity)
        for index, tool in enumerate(self.config["Tools"]):
            self.tree.insert("", "end", iid=str(index), values=(tool["Name"], tool["Hotkey"],
                             tool.get("Description", ""), tool["Path"]))
        return True

    def registration_status(self):
        self.status.set("已启用 %d 个热键；主窗口：%s。关闭窗口后驻留托盘。" %
                        (len(self.registry.active), self.config["MainHotkey"]))
        return True

    def apply_current(self):
        try:
            self.registry.apply(self.config)
            self.registration_status()
            return True
        except ValueError as exc:
            self.status.set("热键未启用，请退出占用热键的原版工具后点“重新加载”：%s" % exc)
            return False

    def commit(self, candidate):
        validate_config(candidate)
        self.registry.apply(candidate)
        try:
            digest, backup = save_config(self.path, candidate, self.digest)
        except (ValueError, OSError):
            self.registry.apply(self.config)
            raise
        self.config, self.digest = candidate, digest
        self.refresh_rows()
        self.registration_status()
        return True

    def reload(self):
        if self.editor is not None:
            return False
        try:
            candidate, digest = read_config(self.path)
            self.registry.apply(candidate)
            self.config, self.digest = candidate, digest
            self.refresh_rows()
            self.registration_status()
            return True
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def selected(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def edit_selected(self):
        index = self.selected()
        if index is not None:
            self.open_editor(index)
        return True

    def edit_main(self):
        return self.open_editor(main=True)

    def open_editor(self, index=None, dropped=None, main=False):
        if self.editor is not None:
            self.editor.window.lift()
            return False
        self.editor = ToolEditor(self, index, dropped, main)
        return True

    def on_drop(self, path):
        if self.editor is not None:
            return self.editor.fill_path(path)
        return self.open_editor(dropped=path)

    def delete_selected(self):
        index = self.selected()
        if index is None:
            return False
        name = self.config["Tools"][index]["Name"]
        if not messagebox.askyesno("删除工具", "从配置移除 %s？不会删除目标文件。" % name, parent=self.window):
            return False
        candidate = copy.deepcopy(self.config)
        del candidate["Tools"][index]
        try:
            return self.commit(candidate)
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def on_hotkey(self, identity):
        action = self.registry.actions.get(identity)
        if action is None or self.editor is not None:
            return False
        return self.show() if action[1] is None else self.launch(action[1])

    def launch_selected(self):
        index = self.selected()
        return False if index is None else self.launch(self.config["Tools"][index])

    def launch(self, tool):
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._launch_worker, args=(copy.deepcopy(tool),), daemon=True).start()
        return True

    def _launch_worker(self, tool):
        try:
            launch_target(tool, self.path.parent)
            self.events.put(("launched", tool["Name"]))
        except Exception as exc:
            logging.getLogger("puppet.hotkeys").exception("目标启动失败")
            self.events.put(("error", str(exc)))
        return True

    def poll(self):
        try:
            self.native.drain()
            if self.editor is not None:
                self.editor.native.drain()
            self._poll_events()
        except Exception as exc:
            self.error(exc)
        finally:
            if not self.closed:
                self.poll_id = self.window.after(100, self.poll)
        return True

    def _poll_events(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind in ("error", "launched"):
                self.busy = False
            if kind == "error":
                self.error(value)
            elif kind == "launched":
                self.status.set("已打开：%s" % value)
            elif kind == "show":
                self.show()
            elif kind == "quit":
                self.quit()
                return True
        return True

    def _start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
            image = Image.new("RGB", (64, 64), "#0f766e")
            ImageDraw.Draw(image).text((21, 18), "P", fill="white")
            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", lambda: self.events.put(("show", None)), default=True),
                pystray.MenuItem("退出", lambda: self.events.put(("quit", None))))
            self.tray = pystray.Icon("PuppetHotkeys", image, "Puppet 快捷键工具", menu)
            self.tray.run_detached()
        except Exception:
            self.tray = None
        return self.tray is not None

    def show(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        return True

    def hide(self):
        if self.tray is None:
            return self.quit()
        self.window.withdraw()
        return True

    def quit(self):
        if self.closed:
            return True
        self.closed = True
        if self.editor is not None:
            self.editor.close()
        self.registry.close()
        self.native.close()
        if self.poll_id is not None:
            self.window.after_cancel(self.poll_id)
        if self.tray is not None:
            self.tray.stop()
        self.status = None
        self.startup = None
        del self.window.report_callback_exception
        self.window.destroy()
        return True

    def open_folder(self):
        try:
            os.startfile(str(self.path.parent))
            return True
        except OSError as exc:
            self.error(exc)
            return False

    def toggle_startup(self):
        try:
            set_startup(self.startup.get(), self.path)
            self.status.set("开机自启设置已保存；旧版工具的自启需在原工具或系统启动项中关闭")
            return True
        except OSError as exc:
            self.startup.set(startup_enabled())
            self.error(exc)
            return False

    def error(self, exc):
        logging.getLogger("puppet.hotkeys").warning("操作失败：%s", exc)
        self.status.set(str(exc))
        messagebox.showerror("快捷键工具", str(exc), parent=self.window)
        return True

    def callback_error(self, kind, value, trace):
        logging.getLogger("puppet.hotkeys").error("界面回调异常", exc_info=(kind, value, trace))
        return self.error(value)

    def run(self):
        self.window.mainloop()
        return True
