# 迁移记录

## 2026-08-27 初始落地

- 外层工具仓库已创建在 `D:\puppet-workspace`。
- 当前技能仓库已完整复制到 `D:\puppet-workspace\skill-repos\work-vault`，保留 `.git`、远程配置和未跟踪文件。
- 由于当前 Codex 会话占用了 `D:\puppet-vault`，Windows 拒绝直接移动旧目录；旧目录暂时保留为回滚副本。
- ccSwitch 已从 `work-vault` 重新导入 13 个 `puppet-*` 技能。
- 旧 ccSwitch `puppet-*` 技能备份位于 `D:\puppet-workspace\backups\ccswitch\20260827-112518`。

## 后续处理

确认新工具链稳定后，可以在关闭占用 `D:\puppet-vault` 的编辑器、终端和 Agent 会话后，手动删除旧目录。删除前请确认新路径 `D:\puppet-workspace\skill-repos\work-vault` 可正常 `git status` 并包含所需未提交内容。

