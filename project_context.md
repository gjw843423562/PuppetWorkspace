# Puppet Workspace 当前上下文

## 项目入口

本地／远程技能仓库在 `config/repos.yaml` 登记，正本位于各自 `skill-repos/`，外层Git忽略技能正文。CLI为 `tools/puppet_workspace.py`；GUI源码与其共享仓库及同步实现，打包产物为 `dist/PuppetWorkspace.exe`。

## 2026-11-10 已完成能力

本地Git初始化／登记、SC前缀识别、按仓库Codex同步；实际sc仓库含HTML仿制与原平台转换两技能，无远程。测试和使用方式见 `docs/local-git-sc-sync.md`。原快捷键工具配置改动属于用户既有工作，不应随本轮提交。

## 纠正与踩坑记录

### 纠正记录 2026-11-11 | 验证实际启动入口

- 纠正前：只交付额外命名的更新 EXE，用户通过原入口继续运行旧版，按钮仍拉起原工具。
- 纠正后：以运行进程的实际路径和父进程验证入口；用户退出后，备份并更新 dist 与根目录的原 PuppetWorkspace.exe，不能把额外产物构建成功当作部署完成。
- 新快捷键运行路径为 tools/快捷键工具/PuppetHotkeys/PuppetHotkeys.exe，外层 tools.json 不变。按钮增加启动反馈、防连点、窗口／退出／超时检测及已有窗口直接唤醒。55 项回归通过，一次正常环境测量由 2.697 秒降至 0.565 秒，直接唤醒 0.0027 秒。

### 快捷键工具接入约定 2026-11-11

- 用户确认采用“Puppet 内提供入口，快捷键工具作为独立程序运行”。入口在“快捷工具”页，工具保留独立窗口、托盘和生命周期。
- 工作区 EXE 与用户指定原文件哈希一致，直接复用；工作区 tools.json 含用户新增工具，不能从原目录覆盖。原理分析与待验证优化项见 docs/hotkey-tool.md。

### 快捷键新版重建 2026-11-11

- 用户确认无原源码，明确授权按逻辑重建。新版 PuppetHotkeys.exe 独立运行，原 AutoHotKeyTool.exe 留作回退；Puppet 入口指向新版。
- 新版沿用当前 7 项配置，支持编辑、热键事务、冲突提示、托盘、单实例唤醒、原子保存与备份。源码 tools/puppet_hotkey_*.py，构建 tools/build_hotkeys.py。
- Windows 回调内调用 Tkinter after 在隔离用例中触发原生 fatal；回调只入队、由 Tkinter 定时处理后，真实注册与消息／编辑／拖放合成用例通过。以后保持此消息边界。
- 当前 49 项回归测试通过，打包 EXE 在正常用户环境下通过隔离启动、唤醒与退出验收；真实目标启动和物理按键体验未代用户执行。文档见 docs/hotkey-tool.md，任务清单见 docs/hotkey-rebuild-plan.md。
- 当前主程序占用 dist/PuppetWorkspace.exe，更新产物另存 dist/PuppetWorkspace-updated.exe；需先从托盘退出旧主程序再切换。受限沙箱可能导致 Tcl 无法读取 EXE 的临时解包库，打包验收应在正常用户环境执行。

### 纠正记录 2026-11-10 | 优先使用Puppet已有仓库入口

- 纠正前：先处理底层目录和Git，用户界面尚看不到仓库，容易造成绕开现有工具的误解。
- 纠正后：以Puppet的repo add作为登记入口，明确“Git初始化”和“工具登记”各自状态；只针对本地初始化与SC同步的真实缺口补功能。

### 成功路径 2026-11-10 | 本机Codex技能同步

- 采用Windows目录联接，避免符号链接特权依赖；同步前检查未知同名入口，按仓库范围执行并保留其他托管状态。
- CMD出现解析结构失真时停止该入口，改用同配方的Python参数调用，不继续叠加Shell转义。
