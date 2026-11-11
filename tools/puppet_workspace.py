# -*- coding: utf-8 -*-
"""
puppet-workspace 多仓库技能库管理工具入口。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

from puppet_workspace_core import *  # noqa: F401,F403
from puppet_workspace_app import PuppetWorkspaceApp
from puppet_workspace_codex import sync_codex

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="puppet-workspace 管理工具")
    parser.add_argument("--workspace-root", default=str(workspace_root_from_script()))
    parser.add_argument("--config", default=None)
    parser.add_argument("--ccswitch-home", default=str(default_ccswitch_home()))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ui")
    subparsers.add_parser("tray")
    subparsers.add_parser("status")
    subparsers.add_parser("import-ccswitch")
    codex = subparsers.add_parser("sync-codex", help="同步Puppet/SC技能并更新Codex入口")
    codex.add_argument("--codex-home", default=None, help="Codex技能目录，默认用户.codex/skills")
    codex.add_argument("--repo", default=None, help="仅同步指定仓库，保留其他仓库及未托管技能")
    repo = subparsers.add_parser("repo")
    repo_sub = repo.add_subparsers(dest="repo_action", required=True)
    for action in ("pull", "commit", "push", "summary", "enable", "disable"):
        command = repo_sub.add_parser(action)
        command.add_argument("repo_id")
        if action == "commit":
            command.add_argument("--message", default=None)
    add = repo_sub.add_parser("add")
    add.add_argument("repo_id")
    add.add_argument("--label", default=None)
    add.add_argument("--path", default=None)
    add.add_argument("--remote", default=None, help="远程URL；省略则登记或初始化纯本地Git仓库")
    add.add_argument("--branch", default="main")
    add.add_argument("--disabled", action="store_true")
    startup = subparsers.add_parser("startup")
    startup.add_argument("action", choices=["status", "enable", "disable"])
    return parser


def resolve_args(args: argparse.Namespace) -> Tuple[Path, Path, Path]:
    root = Path(args.workspace_root).resolve()
    config = Path(args.config).resolve() if args.config else root / DEFAULT_CONFIG
    ccswitch = Path(args.ccswitch_home).absolute()
    return root, config, ccswitch


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["ui"]
    if argv == ["--tray"]:
        argv = ["tray"]
    args = parser.parse_args(argv)
    root, config_path, ccswitch_root = resolve_args(args)
    if args.command in {"ui", "tray"}:
        PuppetWorkspaceApp(root, config_path, ccswitch_root, args.command == "tray").run()
        return 0
    if args.command == "status":
        print_json(status_payload(root, config_path, ccswitch_root))
        return 0
    if args.command == "import-ccswitch":
        result = import_ccswitch(root, config_path, ccswitch_root)
        print_json(result)
        return 0 if result.get("ok") else 1
    if args.command == "sync-codex":
        codex_root = Path(args.codex_home).absolute() if args.codex_home else None
        result = sync_codex(root, config_path, ccswitch_root, codex_root, args.repo)
        print_json(result)
        return 0 if result.get("ok") else 1
    if args.command == "startup":
        return handle_startup_command(root, args.action)
    return handle_repo_command(root, config_path, args)


if __name__ == "__main__":
    raise SystemExit(main())
