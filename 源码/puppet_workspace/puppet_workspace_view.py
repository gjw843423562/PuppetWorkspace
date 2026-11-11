# -*- coding: utf-8 -*-
"""
Puppet Workspace 的通俗化展示组件与文案转换。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


COLORS = {
    "bg": "#eef2f6",
    "panel": "#ffffff",
    "ink": "#1f2937",
    "muted": "#64748b",
    "primary": "#0f766e",
    "primary_dark": "#115e59",
    "ok": "#15803d",
    "warn": "#b45309",
    "danger": "#b91c1c",
    "info": "#2563eb",
    "disabled": "#94a3b8",
}

NAV_ITEMS = [
    ("overview", "总览", "home"),
    ("sync", "技能同步", "sync"),
    ("repos", "技能仓库", "repo"),
    ("targets", "AI 位置", "ai"),
    ("tools", "快捷工具", "home"),
    ("backups", "备份恢复", "backup"),
    ("settings", "设置", "settings"),
    ("logs", "高级日志", "log"),
]


@dataclass
class CardInfo:
    title: str
    value: str
    detail: str
    tone: str


def friendly_repo_status(repo: Dict[str, object]) -> Tuple[str, str]:
    if not repo.get("enabled", True):
        return "未启用", "disabled"
    if repo.get("error"):
        return str(repo["error"]), "danger"
    if int(repo.get("behind", 0) or 0) > 0:
        return "远程有更新", "warn"
    if int(repo.get("ahead", 0) or 0) > 0:
        return "有本地提交未上传", "warn"
    if int(repo.get("dirty_count", 0) or 0) > 0:
        return "有未保存改动", "warn"
    if repo.get("local_only"):
        return "本地仓库，已保存", "ok"
    return "一切正常", "ok"


def overview_cards(payload: Dict[str, object], tray_running: bool) -> List[CardInfo]:
    repos = [repo for repo in payload.get("repos", []) if isinstance(repo, dict)]
    problem_count = sum(1 for repo in repos if friendly_repo_status(repo)[1] in {"warn", "danger"})
    conflicts = payload.get("conflicts", {})
    settings = payload.get("settings", {})
    return [
        CardInfo("技能库", f"{payload.get('skill_count', 0)} 个技能", enabled_repo_detail(repos), "info"),
        CardInfo("仓库状态", repo_status_value(problem_count), repo_status_detail(problem_count), "ok" if problem_count == 0 else "warn"),
        CardInfo("AI 同步", sync_value(conflicts), sync_detail(payload), "danger" if conflicts else "ok"),
        CardInfo("后台守护", "托盘运行中" if tray_running else "普通窗口", refresh_detail(settings), "ok" if tray_running else "disabled"),
    ]


def enabled_repo_detail(repos: Sequence[Dict[str, object]]) -> str:
    enabled = sum(1 for repo in repos if repo.get("enabled", True))
    return f"{enabled}/{len(repos)} 个仓库已启用"


def repo_status_value(problem_count: int) -> str:
    return "一切正常" if problem_count == 0 else f"{problem_count} 个仓库待处理"


def repo_status_detail(problem_count: int) -> str:
    return "没有发现未保存或未上传的内容" if problem_count == 0 else "点进技能仓库查看具体改动"


def sync_value(conflicts: object) -> str:
    return "有同名技能，需要处理" if conflicts else "可以同步"


def sync_detail(payload: Dict[str, object]) -> str:
    ccswitch = payload.get("ccswitch", "")
    return f"目标位置：{ccswitch}"


def refresh_detail(settings: object) -> str:
    minutes = 180
    if isinstance(settings, dict):
        minutes = int(settings.get("refresh_interval_minutes", 180) or 180)
    return f"每 {minutes // 60 if minutes >= 60 else minutes} {'小时' if minutes >= 60 else '分钟'} 检查一次"


def human_action_label(action: str) -> str:
    return {
        "pull": "检查更新",
        "commit": "保存我的改动",
        "push": "上传我的提交",
    }.get(action, action)


def icon_path(root: Path, name: str) -> Path:
    return root / "资源" / "图标" / f"{name}.png"


def recent_backups(root: Path, limit: int = 12) -> List[Tuple[str, str, str]]:
    backups_root = root / "运行数据" / "备份"
    if not backups_root.is_dir():
        return []
    rows: List[Tuple[str, str, str]] = []
    for bucket in ("ccswitch", "config"):
        bucket_root = backups_root / bucket
        if bucket_root.is_dir():
            rows.extend(backup_rows(bucket, bucket_root))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows[:limit]


def backup_rows(bucket: str, bucket_root: Path) -> List[Tuple[str, str, str]]:
    rows = []
    for item in bucket_root.iterdir():
        if item.is_dir():
            rows.append((bucket, item.name, str(item)))
    return rows
