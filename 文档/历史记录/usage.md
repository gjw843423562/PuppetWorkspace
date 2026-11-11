# 使用说明

## 仓库模型

外层 `puppet-workspace` 是工具仓库，负责窗口、命令、配置和本地状态。`skill-repos/` 下的每个目录是独立技能仓库，拥有自己的 `.git`、远程地址和提交历史。

## 窗口化入口

第一版窗口由 Python `tkinter` 实现，入口在 `tools/`：

- `PuppetWorkspace.exe`：打包后的正式窗口工具，位于仓库最外层，双击即可打开。
- `puppet_workspace_ui.cmd`：适合排查问题，启动窗口时保留控制台。
- `puppet_workspace_ui.vbs`：适合日常使用，启动窗口时不显示控制台。
- `puppet_workspace.cmd ui`：命令行等价入口。

窗口当前包含通俗化总览、仓库配置管理、技能同步、Git 拉取/提交/推送、备份恢复、托盘常驻和高级日志。

## 普通模式与高级日志

- 默认进入“总览”，只显示技能数、仓库状态、AI 同步状态和后台守护状态。
- 日常页面使用“有未保存改动”“有本地提交未上传”“远程有更新”等通俗文案。
- 原始 JSON、HEAD、remote、错误堆栈和 Git 输出放在“高级日志”页。
- “同步到 AI”目前对应 ccSwitch 目标，后续 Codex/Claude/Gemini 会作为独立目标接入。

## 仓库管理

- “新增仓库”会写入 `config/repos.yaml`；若填写 remote 且目标目录不存在，会 clone 到所选路径。
- “编辑仓库”可修改显示名称、路径、remote 和分支；启用状态由“启用/禁用”单独切换。
- “启用/禁用”只修改 manifest，不移动仓库目录。
- “删除配置”只删除 `repos.yaml` 中的登记项，不删除 `skill-repos/` 下的仓库目录。
- 每次修改 `repos.yaml` 前，都会备份到 `backups/config/<timestamp>/repos.yaml`。
- “查看改动”展示选中仓库的通俗状态、远程地址和改动清单；原始 Git 字段在“高级日志”页查看。

## 托盘、刷新与自启

- 关闭主窗口默认最小化到系统托盘；托盘菜单支持显示窗口、检查状态、同步到 AI、打开工作区、切换开机自启和退出。
- 后台状态刷新默认每 3 小时一次，可在窗口设置里调整为 1/3/6/12/24 小时。
- 提醒范围包括导入冲突、仓库未提交、仓库 ahead 未 push、仓库状态异常和导入哈希不一致。
- `PuppetWorkspace.exe --tray` 会静默驻留托盘，不弹主窗口；开机自启使用这个参数。
- 开机自启通过当前用户 Startup 文件夹中的 `PuppetWorkspace.lnk` 实现，不写注册表，不需要管理员权限。

```bat
tools\puppet_workspace.cmd tray
tools\puppet_workspace.cmd startup status
tools\puppet_workspace.cmd startup enable
tools\puppet_workspace.cmd startup disable
```

## 备份恢复

- “备份恢复”页会列出最近的 AI 技能备份和配置备份。
- “打开备份”只打开备份目录。
- “恢复备份”会二次确认；恢复 AI 技能备份时只替换 ccSwitch 下的 `puppet-*` 技能，恢复配置备份时只替换 `config/repos.yaml`。
- 恢复前会再次备份当前状态，方便反悔。

## 打包

运行：

```bat
tools\build_exe.cmd
```

脚本使用 PyInstaller 生成单文件窗口程序，先输出到 `dist\PuppetWorkspace.exe`，再复制到最外层 `PuppetWorkspace.exe`。`build/`、`dist/`、`PuppetWorkspace.exe` 和 `.spec` 文件属于本机打包产物，不进入外层工具仓 Git。

托盘依赖记录在 `tools/requirements.txt`：`pystray`、`Pillow`、`PyInstaller`。

## ccSwitch 导入

`import-ccswitch` 会读取 `config/repos.yaml` 中所有启用仓库，收集 `skills/puppet-*` 技能。若多个仓库存在同名技能，导入会在清理 ccSwitch 前停止。

导入成功路径：

1. 备份 `%USERPROFILE%\.cc-switch\skills\puppet-*` 到 `backups/ccswitch/<timestamp>/`。
2. 清理 ccSwitch 中旧的 `puppet-*` 技能目录。
3. 从启用技能仓库重新复制 `skills/puppet-*`。
4. 对比源目录和目标目录哈希，写入 `state/sync_state.json`。

## 图标

可以从 iconfont 下载同风格 PNG 后覆盖 `assets/icons/` 里的同名文件。工具运行只读取本地资源，不依赖在线地址；图标缺失时自动降级为纯文字按钮。
