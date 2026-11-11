# tools 目录整理

本次只整理 tools 源码，不改技能库与用户快捷键配置。保留原日常启动入口和模块名称，避免路径整理扩大为业务重构。

## 目标结构

```text
tools/
  workspace/              Puppet 主程序源码与内部 CLI
  hotkeys/                独立快捷键工具源码
  build/                  Python 打包脚本
  tests/                  回归与 EXE 验收
  快捷键工具/             保留原配置、原版和新版运行文件
  puppet_workspace.py     兼容入口
  puppet_workspace.cmd    原 CLI 入口
  puppet_workspace_ui.cmd 原窗口入口
  puppet_workspace_ui.vbs 原静默窗口入口
  build_exe.cmd           原打包入口
  _bootstrap.py           源码目录加载
  requirements.txt
```

## 执行与验收

- [ ] 对 22 个源码文件生成移动计划并完成无冲突预检。
- [ ] 使用文件操作执行器原位移动，校验字节一致；不删除目录。
- [ ] 保留 CLI 包装入口，调整源码根目录、打包路径与测试加载。
- [ ] 完整回归、CLI 帮助、配置只读校验和两类程序构建通过。
- [ ] 确认用户配置未变，更新当前目录说明。

## 常用命令

```text
python3 tools/puppet_workspace.py --help
python3 tools/hotkeys/puppet_hotkeys.py --check
python3 tools/build/build_hotkeys.py
python3 tools/build/build_workspace.py
python3 -m unittest discover -s tools/tests -v
```

原模块名保持不变，兼容入口和测试通过 _bootstrap.py 加载 workspace 与 hotkeys。冻结后的 EXE 继续从工作区定位配置，打包时显式声明两个源码搜索路径。
