# -*- coding: utf-8 -*-
"""保留原 CLI／窗口入口，真实实现位于 workspace。"""
from _bootstrap import configure_source_paths

configure_source_paths()

from puppet_workspace.puppet_workspace_cli import *  # noqa: E402,F401,F403


if __name__ == "__main__":
    raise SystemExit(main())
