# Puppet 工具工作区

管理独立技能仓库，并提供可独立运行的 Windows 快捷键工具。现有 Python 3.8 环境保持兼容。

## 工具目录

| 工具 | 日常启动 | 配置 |
| --- | --- | --- |
| Puppet 工作区 | 根目录 `PuppetWorkspace.lnk`；正式程序 `发布/工作区/PuppetWorkspace.exe` | `配置/技能仓库.yaml`、`配置/工作区设置.yaml` |
| 快捷键工具 | Puppet 左侧“快捷工具”→“启动快捷键工具”；正式程序 `发布/快捷键工具/PuppetHotkeys/PuppetHotkeys.exe` | `配置/快捷键工具.json` |

目录式快捷键发布依赖同级 `_internal`，更新时应更新完整发布目录。退出 Puppet 不影响快捷键工具。关闭窗口是否隐藏到托盘遵循现有设置；需要退出时使用托盘菜单。整理不会开启或关闭用户自启偏好。

当前独立运行指不需要主窗口常驻；仍需保留工作区目录及 `配置/技能仓库.yaml` 定位标记、快捷键配置，暂不支持只拷走快捷键 EXE 目录作为便携版。

根目录的两个 `启动*.cmd` 是源码入口，需要 Python 和依赖；日常使用建议直接使用上面的正式程序。旧 `tools/` 仅保留兼容转发入口。

## 固定结构

```text
源码/          puppet_workspace、puppet_hotkeys、puppet_common
配置/          用户持久配置
资源/          图标、图片
构建/          独立构建脚本、依赖、结构检查器
发布/          工作区、快捷键工具（当前产物，不提交 Git）
测试/          单元测试和隔离 EXE 验收
文档/          开发规范、使用说明、历史记录
运行数据/      状态、日志、备份、构建缓存、整理记录、历史归档
skill-repos/   独立 Git 技能仓库，保持原位置
tools/         旧入口兼容层
```

新增工具和目录必须遵守 [协作约束](AGENTS.md) 与 [开发规范](文档/开发规范.md)。人可读分类路径、文档、界面使用简体中文，Python 标识和生态标准名称使用英文。运行数据和发布产物不提交 Git。

## 开发与验收

以下命令从仓库根目录执行；启动与构建脚本本身不依赖调用工作目录。`python3` 必须是 Python 3；本机 `python` 是旧版解释器，不使用。

```powershell
python3 -m pip install -r 构建/requirements.txt
python3 源码/启动工作区.py status
python3 源码/启动快捷键工具.py --check
python3 构建/check_structure.py
python3 -m unittest discover -s 测试 -q
python3 构建/build_workspace.py
python3 构建/build_hotkeys.py
python3 测试/smoke_workspace_exe.py
python3 测试/smoke_hotkey_exe.py
```

EXE 验收使用临时空配置，不启动用户七个真实目标。依赖暂未锁定，重建前需核对当前依赖环境；Ruff 配置已提供，未安装时不能声称 Ruff 检查通过。

更多说明：[快捷键工具](文档/hotkey-tool.md)、[整理验收记录](文档/整理验收记录.md)、[约束评估与优化路线](文档/约束评估与优化路线.md)。历史文档原文保存在 `文档/历史记录/`，其中旧路径和早期限制仅作追溯，现行用法以本文件为准。
