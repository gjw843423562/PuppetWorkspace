# puppet-workspace

`puppet-workspace` 是 Puppet 个人技能库的外层工具仓库。它只管理工具、配置、图标和文档；实际技能库放在 `skill-repos/` 下，由各自 Git 仓库独立管理。

## 目录

- `tools/`：命令行、ccSwitch 导入器、Git 管理器和 tkinter 管理窗口。
- `config/repos.yaml`：登记多个技能仓库。
- `skill-repos/`：本机技能仓库容器，外层 Git 忽略。
- `assets/icons/`：本地图标资源。
- `state/`、`logs/`、`backups/`：本机状态、日志和备份，外层 Git 忽略。

## 常用命令

```bat
tools\puppet_workspace.cmd status
tools\puppet_workspace.cmd import-ccswitch
tools\puppet_workspace.cmd tray
tools\puppet_workspace.cmd startup status
tools\puppet_workspace.cmd startup enable
tools\puppet_workspace.cmd startup disable
tools\puppet_workspace.cmd repo summary work-vault
tools\puppet_workspace.cmd repo pull work-vault
tools\puppet_workspace.cmd repo commit work-vault
tools\puppet_workspace.cmd repo push work-vault
tools\puppet_workspace.cmd repo add home-private-vault --remote https://example.invalid/home-private-vault.git
tools\puppet_workspace.cmd ui
```

## 窗口启动

- 双击 `PuppetWorkspace.exe`：打包后的正式窗口工具，位于仓库最外层。
- `PuppetWorkspace.exe --tray`：静默启动到系统托盘，用于开机自启。
- 双击 `tools\puppet_workspace_ui.cmd`：打开窗口，保留控制台，便于看错误。
- 双击 `tools\puppet_workspace_ui.vbs`：静默打开窗口，不显示黑色控制台。
- 命令行启动：`tools\puppet_workspace.cmd ui`。

## 仓库管理与托盘

- 窗口默认进入“总览”，只显示技能数、仓库状态、AI 同步状态和后台守护状态。
- 左侧导航包含：总览、技能同步、技能仓库、AI 位置、备份恢复、设置、高级日志。
- Git 的 HEAD、原始 JSON 和错误细节放在“高级日志”里，日常页面使用通俗状态文案。
- 窗口支持新增、编辑、启用/禁用、删除仓库配置；删除配置不会删除技能仓库目录。
- “备份恢复”页可打开或恢复最近的 AI 技能备份和配置备份，恢复前会二次确认。
- 修改 `config/repos.yaml` 前会备份到 `backups/config/<timestamp>/repos.yaml`。
- 后台刷新默认每 3 小时一次，可在窗口设置中调整为 1/3/6/12/24 小时。
- 关闭窗口默认最小化到托盘；托盘菜单可显示窗口、检查状态、同步到 AI、打开工作区、切换开机自启和退出。
- 开机自启通过当前用户 Startup 文件夹里的快捷方式实现，不写注册表。

## 图标美化

- 本地图标位于 `assets/icons/`，工具会优先加载同名 PNG。
- 可以从 iconfont 下载统一风格图标后覆盖同名文件，不需要改代码。
- 图标缺失时会自动降级为纯文字按钮。

## 打包 EXE

```bat
tools\build_exe.cmd
```

产物先输出到 `dist\PuppetWorkspace.exe`，随后自动复制到最外层 `PuppetWorkspace.exe`。EXE 放在仓库最外层或 `dist` 下运行时，都会自动识别 `puppet-workspace` 工作区根。

## 设计边界

- `puppet-workspace` 不保存技能正文。
- ccSwitch 只是运行态导入目标，不是正本。
- 多个启用仓库合并导入时，出现同名 `puppet-*` 技能会停止导入并报告冲突。
- Git 推送默认手动触发，避免草稿或敏感内容被自动发布。
