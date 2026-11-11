# -*- coding: utf-8 -*-
"""独立工具运行与原生崩溃日志。"""
import faulthandler
import logging
from logging.handlers import RotatingFileHandler


CRASH_STREAM = None


def configure_logging(folder):
    global CRASH_STREAM
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(str(folder / "hotkeys.log"), maxBytes=1024*1024,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("puppet.hotkeys")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    CRASH_STREAM = (folder / "crash.log").open("a", encoding="utf-8")
    faulthandler.enable(file=CRASH_STREAM, all_threads=True)
    logger.info("启动独立快捷键工具")
    return True
