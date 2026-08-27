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
tools\puppet_workspace.cmd repo pull work-vault
tools\puppet_workspace.cmd repo commit work-vault
tools\puppet_workspace.cmd repo push work-vault
tools\puppet_workspace.cmd ui
```

## 窗口启动

- 双击 `dist\PuppetWorkspace.exe`：打包后的正式窗口工具。
- 双击 `tools\puppet_workspace_ui.cmd`：打开窗口，保留控制台，便于看错误。
- 双击 `tools\puppet_workspace_ui.vbs`：静默打开窗口，不显示黑色控制台。
- 命令行启动：`tools\puppet_workspace.cmd ui`。

## 打包 EXE

```bat
tools\build_exe.cmd
```

产物输出到 `dist\PuppetWorkspace.exe`。EXE 放在 `dist` 下运行时，会自动把上一级目录识别为 `puppet-workspace` 工作区根。

## 设计边界

- `puppet-workspace` 不保存技能正文。
- ccSwitch 只是运行态导入目标，不是正本。
- 多个启用仓库合并导入时，出现同名 `puppet-*` 技能会停止导入并报告冲突。
- Git 推送默认手动触发，避免草稿或敏感内容被自动发布。
