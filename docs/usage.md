# 使用说明

## 仓库模型

外层 `puppet-workspace` 是工具仓库，负责窗口、命令、配置和本地状态。`skill-repos/` 下的每个目录是独立技能仓库，拥有自己的 `.git`、远程地址和提交历史。

## 窗口化入口

第一版窗口由 Python `tkinter` 实现，入口在 `tools/`：

- `PuppetWorkspace.exe`：打包后的正式窗口工具，位于仓库最外层，双击即可打开。
- `puppet_workspace_ui.cmd`：适合排查问题，启动窗口时保留控制台。
- `puppet_workspace_ui.vbs`：适合日常使用，启动窗口时不显示控制台。
- `puppet_workspace.cmd ui`：命令行等价入口。

窗口当前包含仓库状态、ccSwitch 导入、Git 拉取/提交/推送、打开目录和操作日志。

## 打包

运行：

```bat
tools\build_exe.cmd
```

脚本使用 PyInstaller 生成单文件窗口程序，先输出到 `dist\PuppetWorkspace.exe`，再复制到最外层 `PuppetWorkspace.exe`。`build/`、`dist/`、`PuppetWorkspace.exe` 和 `.spec` 文件属于本机打包产物，不进入外层工具仓 Git。

## ccSwitch 导入

`import-ccswitch` 会读取 `config/repos.yaml` 中所有启用仓库，收集 `skills/puppet-*` 技能。若多个仓库存在同名技能，导入会在清理 ccSwitch 前停止。

导入成功路径：

1. 备份 `%USERPROFILE%\.cc-switch\skills\puppet-*` 到 `backups/ccswitch/<timestamp>/`。
2. 清理 ccSwitch 中旧的 `puppet-*` 技能目录。
3. 从启用技能仓库重新复制 `skills/puppet-*`。
4. 对比源目录和目标目录哈希，写入 `state/sync_state.json`。

## 图标

可以从 iconfont 下载 SVG/PNG 后放入 `assets/icons/`。工具运行只读取本地资源，不依赖在线地址。
