# -*- coding: utf-8 -*-
"""
Puppet Workspace 的系统托盘封装。
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - 托盘依赖缺失时允许主窗口继续运行
    pystray = None
    Image = None
    ImageDraw = None


class TrayController:
    def __init__(
        self,
        show_window: Callable[[], None],
        refresh_status: Callable[[], None],
        import_ccswitch: Callable[[], None],
        open_workspace: Callable[[], None],
        toggle_startup: Callable[[], None],
        startup_enabled: Callable[[], bool],
        exit_app: Callable[[], None],
    ) -> None:
        self.show_window = show_window
        self.refresh_status = refresh_status
        self.import_ccswitch = import_ccswitch
        self.open_workspace = open_workspace
        self.toggle_startup = toggle_startup
        self.startup_enabled = startup_enabled
        self.exit_app = exit_app
        self.icon: Optional["pystray.Icon"] = None
        self.thread: Optional[threading.Thread] = None

    @property
    def available(self) -> bool:
        return pystray is not None and Image is not None and ImageDraw is not None

    def start(self) -> bool:
        if not self.available:
            return False
        self.icon = pystray.Icon("PuppetWorkspace", self._image(), "Puppet Workspace", self._menu())
        if hasattr(self.icon, "run_detached"):
            self.icon.run_detached()
            return True
        self.thread = threading.Thread(target=self.icon.run, daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None

    def notify(self, title: str, message: str) -> None:
        if self.icon is not None and hasattr(self.icon, "notify"):
            self.icon.notify(message, title)

    def _menu(self) -> "pystray.Menu":
        return pystray.Menu(
            pystray.MenuItem("显示窗口", lambda: self.show_window()),
            pystray.MenuItem("检查状态", lambda: self.refresh_status()),
            pystray.MenuItem("同步到 AI", lambda: self.import_ccswitch()),
            pystray.MenuItem("打开工作区", lambda: self.open_workspace()),
            pystray.MenuItem("开机自启", lambda: self.toggle_startup(), checked=lambda item: self.startup_enabled()),
            pystray.MenuItem("退出", lambda: self.exit_app()),
        )

    def _image(self) -> "Image.Image":
        image = Image.new("RGBA", (64, 64), (32, 34, 42, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((7, 7, 57, 57), radius=12, fill=(72, 111, 255, 255))
        draw.ellipse((20, 14, 44, 38), fill=(255, 255, 255, 255))
        draw.rectangle((18, 38, 46, 50), fill=(255, 255, 255, 255))
        return image
