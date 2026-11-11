"""目录约定的唯一代码来源；不依赖当前工作目录。"""
import sys
from pathlib import Path

REPOSITORY_CONFIG = Path("配置") / "技能仓库.yaml"
SETTINGS_CONFIG = Path("配置") / "工作区设置.yaml"
HOTKEY_CONFIG = Path("配置") / "快捷键工具.json"
RUNTIME = Path("运行数据")
LOGS = RUNTIME / "日志"
STATE = RUNTIME / "状态"
BACKUPS = RUNTIME / "备份"
ICONS = Path("资源") / "图标"
WORKSPACE_EXE = Path("发布") / "工作区" / "PuppetWorkspace.exe"
HOTKEY_EXE = Path("发布") / "快捷键工具" / "PuppetHotkeys" / "PuppetHotkeys.exe"


def workspace_root():
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parents[2]
    folder = Path(sys.executable).resolve().parent
    for candidate in (folder, *folder.parents):
        if (candidate / "配置" / "技能仓库.yaml").is_file():
            return candidate
    raise FileNotFoundError("无法定位工作区：程序所在目录的上级缺少 配置/技能仓库.yaml")


def hotkey_data_folder(config, kind):
    """用户显式指定外部配置时，运行数据仍隔离在该配置旁。"""
    config = Path(config).resolve()
    if config.name == HOTKEY_CONFIG.name and config.parent.name == "配置":
        return config.parent.parent / RUNTIME / kind / "快捷键工具"
    return config.parent / {"日志": "logs", "备份": "backups"}[kind]
