# -*- coding: utf-8 -*-
"""构建 Puppet 主程序；显式包含分类后的源码搜索路径。"""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="构建 Puppet Workspace")
    parser.add_argument("--dist-dir", type=Path, default=root / "发布" / "工作区", help="EXE 输出目录")
    parser.add_argument("--name", default="PuppetWorkspace", help="EXE 文件名")
    args = parser.parse_args()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
               "--name", args.name, "--collect-submodules", "pystray", "--collect-submodules", "PIL",
               "--paths", str(root / "源码"),
               "--distpath", str(args.dist_dir), "--workpath", str(root / "运行数据" / "构建缓存" / "workspace"),
               "--specpath", str(root / "运行数据" / "构建缓存" / "workspace"), str(root / "源码" / "启动工作区.py")]
    return subprocess.call(command, cwd=str(root))


if __name__ == "__main__":
    sys.exit(main())
