# -*- coding: utf-8 -*-
"""本地Git管理及SC技能Codex同步的行为回归。"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "源码"))
from puppet_workspace import puppet_workspace_core as core
from puppet_workspace.puppet_workspace_codex import sync_codex
from puppet_workspace.puppet_workspace_view import friendly_repo_status
from puppet_workspace import puppet_workspace_actions as actions


class LocalScCodexTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="puppet-local-sc-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "工作区"
        self.root.mkdir()
        self.config = self.root / "config" / "repos.yaml"
        self.config.parent.mkdir()
        self.config.write_text("version: 1\nrepositories:\n", encoding="utf-8")
        self.ccswitch = self.root / "镜像"
        self.codex = self.root / "Codex技能"

    def local_repo(self, repo_id: str = "sc"):
        repo = core.RepoConfig(repo_id, "本地技能", self.root / repo_id, "", "main", True)
        core.prepare_repo(self.root, repo)
        core.save_repo_config(self.root, self.config, repo)
        return repo

    def add_skill(self, repo, name: str) -> Path:
        skill = repo.path / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n中文内容\n", encoding="utf-8")
        return skill

    def test_local_repo_initializes_without_remote_and_keeps_existing_files(self):
        repo_path = self.root / "新本地仓库"
        repo_path.mkdir()
        original = repo_path / "原文件.txt"
        original.write_text("保留", encoding="utf-8")
        args = argparse.Namespace(repo_id="sc", label="本地", path=str(repo_path), remote=None, branch="main", disabled=False)
        result = core.add_repo_from_cli(self.root, self.config, args)
        self.assertTrue(result["ok"])
        self.assertTrue((repo_path / ".git").is_dir())
        self.assertEqual(core.git_value(repo_path, ["remote"]), "")
        self.assertEqual(original.read_text(encoding="utf-8"), "保留")

    def test_existing_git_registration_does_not_reinitialize(self):
        repo = self.local_repo()
        before = (repo.path / ".git" / "config").read_bytes()
        with patch.object(core.subprocess, "run") as run:
            core.prepare_repo(self.root, repo)
        run.assert_not_called()
        self.assertEqual(before, (repo.path / ".git" / "config").read_bytes())

    def test_remote_source_still_uses_clone(self):
        repo = core.RepoConfig("remote", "远程", self.root / "remote", "https://example.invalid/a.git", "main", True)
        with patch.object(core, "clone_repo") as clone:
            core.prepare_repo(self.root, repo)
        clone.assert_called_once_with(self.root, repo)

    def test_local_pull_and_push_do_not_run_network_git(self):
        self.local_repo()
        with patch.object(core, "run_git") as run:
            for action in ("pull", "push"):
                result = core.repo_action(self.root, self.config, action, "sc", None)
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"], "local_only")
        run.assert_not_called()

    def test_sc_import_preserves_unmanaged_sc_skill_on_first_sync(self):
        repo = self.local_repo()
        source = self.add_skill(repo, "sc-html-replica")
        unmanaged = self.ccswitch / "sc-unmanaged"
        unmanaged.mkdir(parents=True)
        (unmanaged / "SKILL.md").write_text("原有技能", encoding="utf-8")
        result = core.import_ccswitch(self.root, self.config, self.ccswitch)
        self.assertTrue(result["ok"])
        self.assertEqual(core.dir_hash(source), core.dir_hash(self.ccswitch / source.name))
        self.assertEqual((unmanaged / "SKILL.md").read_text(encoding="utf-8"), "原有技能")

    def test_codex_sync_creates_usable_link_and_can_repeat(self):
        repo = self.local_repo()
        source = self.add_skill(repo, "sc-html-replica")
        for _ in range(2):
            result = sync_codex(self.root, self.config, self.ccswitch, self.codex)
            self.assertTrue(result["ok"])
            self.assertEqual((self.codex / source.name).resolve(), (self.ccswitch / source.name).resolve())
            self.assertEqual((self.codex / source.name / "SKILL.md").read_bytes(), (source / "SKILL.md").read_bytes())

    def test_codex_conflict_does_not_replace_user_directory_or_copy_mirror(self):
        repo = self.local_repo()
        self.add_skill(repo, "sc-html-replica")
        conflict = self.codex / "sc-html-replica"
        conflict.mkdir(parents=True)
        original = conflict / "私有.txt"
        original.write_text("不能覆盖", encoding="utf-8")
        result = sync_codex(self.root, self.config, self.ccswitch, self.codex)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "codex_conflict")
        self.assertEqual(original.read_text(encoding="utf-8"), "不能覆盖")
        self.assertFalse(self.ccswitch.exists())

    def test_sc_duplicate_blocks_sync_and_unmanaged_prefix_is_not_collected(self):
        first = self.local_repo("sc")
        second = self.local_repo("other")
        self.add_skill(first, "sc-same")
        self.add_skill(second, "sc-same")
        self.add_skill(first, "unrelated-skill")
        skills, conflicts = core.collect_skills(core.load_repos(self.config, self.root))
        self.assertNotIn("unrelated-skill", skills)
        self.assertIn("sc-same", conflicts)
        result = sync_codex(self.root, self.config, self.ccswitch, self.codex)
        self.assertFalse(result["ok"])
        self.assertFalse(self.ccswitch.exists())

    def test_clean_local_repo_is_displayed_as_local(self):
        self.assertEqual(friendly_repo_status({"local_only": True})[0], "本地仓库，已保存")

    def test_sc_only_sync_keeps_other_repos_and_conflicting_unmanaged_entries(self):
        repo = self.local_repo()
        source = self.add_skill(repo, "sc-html-replica")
        other = self.local_repo("work-vault")
        self.add_skill(other, "puppet-other")
        for root in (self.ccswitch, self.codex):
            preserved = root / "puppet-other"
            preserved.mkdir(parents=True)
            (preserved / "SKILL.md").write_text("原有私有内容", encoding="utf-8")
        core.save_managed_targets(self.root / "运行数据" / "状态", {"puppet-other"})
        result = sync_codex(self.root, self.config, self.ccswitch, self.codex, "sc")
        self.assertTrue(result["ok"])
        self.assertEqual((self.ccswitch / "puppet-other" / "SKILL.md").read_text(encoding="utf-8"), "原有私有内容")
        self.assertEqual((self.codex / "puppet-other" / "SKILL.md").read_text(encoding="utf-8"), "原有私有内容")
        self.assertTrue((self.codex / source.name / "SKILL.md").is_file())
        self.assertEqual(core.load_managed_targets(self.root / "运行数据" / "状态"), {"puppet-other", source.name})

    def test_gui_local_mode_does_not_ask_for_remote(self):
        instance = actions.WorkspaceActions()
        with patch.object(actions.messagebox, "askyesnocancel", return_value=True):
            with patch.object(actions.simpledialog, "askstring") as ask:
                self.assertEqual(instance.ask_repo_remote(None), "")
        ask.assert_not_called()

    def test_gui_remote_mode_does_not_silently_become_local(self):
        instance = actions.WorkspaceActions()
        with patch.object(actions.messagebox, "askyesnocancel", return_value=False):
            with patch.object(actions.simpledialog, "askstring", return_value=""):
                self.assertIsNone(instance.ask_repo_remote(None))


if __name__ == "__main__":
    unittest.main()
