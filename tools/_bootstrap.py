# -*- coding: utf-8 -*-
"""保持旧模块名，集中加载分类后的两个源码目录。"""
import sys
from pathlib import Path


def configure_source_paths():
    tools = Path(__file__).resolve().parent
    for name in ("源码",):
        source = tools.parent / name
        if source.is_dir() and str(source) not in sys.path:
            sys.path.insert(0, str(source))
    return True
