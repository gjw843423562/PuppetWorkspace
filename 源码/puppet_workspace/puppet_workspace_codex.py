# -*- coding: utf-8 -*-
"""通过现有Puppet同步流程生成Codex技能入口，不覆盖未知入口。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from puppet_workspace.puppet_workspace_core import collect_skills, find_repo, import_ccswitch, load_repos


def codex_conflicts(skills: Dict, ccswitch_root: Path, codex_root: Path) -> list:
    conflicts = []
    for name in sorted(skills):
        entry = codex_root / name
        target = ccswitch_root / name
        if os.path.lexists(str(entry)) and entry.resolve() != target.resolve():
            conflicts.append(str(entry))
    return conflicts


def create_skill_link(entry: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(entry))
    else:
        entry.symlink_to(target, target_is_directory=True)
    if entry.resolve() != target.resolve():
        raise RuntimeError(f"Codex入口校验失败: {entry}")


def sync_codex(root: Path, config_path: Path, ccswitch_root: Path,
               codex_root: Optional[Path] = None,
               repo_id: Optional[str] = None) -> Dict[str, object]:
    """先检查入口冲突，再复用镜像同步及摘要校验，最后建立技能链接。"""
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    codex_root = codex_root or home / ".codex" / "skills"
    repos = load_repos(config_path, root)
    skills, duplicate_names = collect_skills([find_repo(repos, repo_id)] if repo_id else repos)
    if duplicate_names:
        return {"ok": False, "status": "conflict", "conflicts": list(duplicate_names)}
    conflicts = codex_conflicts(skills, ccswitch_root, codex_root)
    if conflicts:
        return {"ok": False, "status": "codex_conflict", "conflicts": conflicts}
    result = import_ccswitch(root, config_path, ccswitch_root, repo_id)
    if not result.get("ok"):
        return result
    codex_root.mkdir(parents=True, exist_ok=True)
    links = []
    for name in sorted(skills):
        entry = codex_root / name
        target = ccswitch_root / name
        if not os.path.lexists(str(entry)):
            create_skill_link(entry, target)
        links.append({"name": name, "entry": str(entry), "target": str(target)})
    result["codex_links"] = links
    return result
