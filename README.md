# Puppet 工具箱与技能库 (puppet-workspace)

puppet-workspace 是 Puppet 个人技能库与外层辅助工具包的总控仓库。它负责统一管理 Puppet 技能库、快捷小工具、配置文件、图标图片资源及相关文档。

---

## 📁 目录结构

`	ext
puppet-workspace/
├── PuppetWorkspace.lnk   # 快捷启动入口（指向 dist/PuppetWorkspace.exe）
├── README.md             # 本说明文档
├── assets/               # 资源目录
│   ├── icons/            # 界面图标资源 (.png)
│   └── images/           # 工作空间美化图片与背景素材
├── config/               # 配置文件
│   └── repos.yaml        # 技能仓库登记表
├── dist/                 # 应用程序编译打包输出目录
│   └── PuppetWorkspace.exe
├── skill-repos/          # 本机技能仓库容器（各 Git 仓库独立管理）
├── tools/                # 常用辅助工具与源码
│   ├── 快捷键工具/       # 键盘全局快捷键调起工具 (AutoHotKeyTool + tools.json)
│   ├── build_exe.cmd     # EXE 打包脚本
│   └── puppet_workspace*.py # GUI 与核心功能源码
├── state/                # 运行状态数据（Git 已忽略）
├── logs/                 # 运行日志（Git 已忽略）
└── backups/              # 配置与技能备份（Git 已忽略）
`

---

## 🚀 启动方式

启动修复已回写原主程序入口。当前快捷键运行文件为 `tools/快捷键工具/PuppetHotkeys/PuppetHotkeys.exe`（目录式免解包发布，保留 `_internal`）；Puppet 按钮会显示启动状态并直接唤醒已有窗口。外层同名 EXE 为此前单文件构建，以下历史路径说明以本段为准。

- **Puppet 内快捷工具入口**：左侧“快捷工具”可启动独立快捷键程序、打开配置目录及查看[原理与优化方案](docs/hotkey-tool.md)。
- **可维护快捷键新版**：`tools/快捷键工具/PuppetHotkeys.exe` 支持热键冲突提示、保存即时生效、原子保存与备份、重复启动唤醒。源码在 `tools/puppet_hotkey_*.py`，构建入口为 `python3 tools/build_hotkeys.py`；原 EXE 保留，首次使用新版请退出旧版以释放热键。

- **快捷启动**：双击根目录下的 PuppetWorkspace.lnk 快捷方式。
- **打包产物**：双击 dist\PuppetWorkspace.exe（直接启动，后台自动定位工作区）。
- **命令行启动**：在终端运行 	ools\puppet_workspace.cmd ui。
- **控制台调试启动**：双击 	ools\puppet_workspace_ui.cmd（保留控制台，便于排查日志）。
- **快捷键小工具**：进入 	ools\快捷键工具\ 运行 AutoHotKeyTool.exe，可通过全局热键迅速调起常用工具。

---

## 🛠️ 常见操作

快捷键工具说明：前文 AutoHotKeyTool.exe 保留为旧版回退入口；当前新版为同目录 PuppetHotkeys.exe，也可从新版 Puppet 的“快捷工具”页启动。

本轮更新版主程序为 `dist/PuppetWorkspace-updated.exe`（原主程序运行中无法覆盖）。从托盘退出旧 Puppet 后再打开此更新版；独立快捷键新版也可直接运行，无需先启动 Puppet。

`at
:: 查看仓库状态
tools\puppet_workspace.cmd status

:: 同步技能到 AI (ccSwitch)
tools\puppet_workspace.cmd import-ccswitch

:: 管理与更新技能仓库
tools\puppet_workspace.cmd repo summary work-vault
tools\puppet_workspace.cmd repo pull work-vault
tools\puppet_workspace.cmd repo push work-vault

:: 重新编译打包 EXE
tools\build_exe.cmd
`

---

## 🎨 界面与美化资源

- **图标文件**：位于 ssets\icons\，工具会自动优先加载同名 PNG 图标。
- **图片素材**：位于 ssets\images\，用于后续工作区视觉美化与背景更换。
