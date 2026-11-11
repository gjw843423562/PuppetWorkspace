# -*- coding: utf-8 -*-
"""重建独立快捷键 EXE，保留原版与工具配置。"""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="构建 Puppet 独立快捷键工具")
    parser.add_argument("--layout", choices=("onedir", "onefile"), default="onedir", help="默认目录式发布，启动时无需解包")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--" + args.layout, "--windowed",
               "--name", "PuppetHotkeys", "--collect-submodules", "pystray",
               "--exclude-module", "numpy", "--exclude-module", "psutil",
               "--exclude-module", "PIL.ImageQt", "--exclude-module", "PIL.ImageTk",
               "--paths", str(root / "源码"),
               "--distpath", str(root / "发布" / "快捷键工具"),
               "--workpath", str(root / "运行数据" / "构建缓存" / "hotkeys"),
               "--specpath", str(root / "运行数据" / "构建缓存" / "hotkeys"),
               str(root / "源码" / "启动快捷键工具.py")]
    return subprocess.call(command, cwd=str(root))


if __name__ == "__main__":
    sys.exit(main())
