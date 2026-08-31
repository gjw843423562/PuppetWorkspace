# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "puppet_workspace.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("puppet_workspace", MODULE_PATH)
puppet_workspace = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["puppet_workspace"] = puppet_workspace
SPEC.loader.exec_module(puppet_workspace)
import puppet_workspace_view
import puppet_workspace_ui


class PuppetWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="puppet-workspace-test-"))
        self.workspace = self.tmp / "workspace"
        self.ccswitch = self.tmp / "ccswitch" / "skills"
        self.workspace.mkdir()
        (self.workspace / "config").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(str(self.tmp))

    def write_config(self, items: str) -> Path:
        config = self.workspace / "config" / "repos.yaml"
        config.write_text("version: 1\nrepositories:\n" + items, encoding="utf-8")
        return config

    def make_repo(self, repo_id: str, skills: list[str]) -> Path:
        repo = self.workspace / "skill-repos" / repo_id
        for skill in skills:
            root = repo / "skills" / skill
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(f"---\nname: {skill}\n---\n", encoding="utf-8")
        return repo

    def test_import_backs_up_and_reimports(self) -> None:
        self.make_repo("a", ["puppet-one"])
        old = self.ccswitch / "puppet-old"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("old", encoding="utf-8")
        config = self.write_config(
            "  - id: a\n"
            "    label: A\n"
            "    path: skill-repos/a\n"
            "    remote: https://example.invalid/a.git\n"
            "    branch: main\n"
            "    enabled: true\n"
        )
        result = puppet_workspace.import_ccswitch(self.workspace, config, self.ccswitch)
        self.assertTrue(result["ok"])
        self.assertTrue((self.ccswitch / "puppet-one" / "SKILL.md").is_file())
        self.assertFalse((self.ccswitch / "puppet-old").exists())
        self.assertTrue(Path(result["backup"], "puppet-old", "SKILL.md").is_file())

    def test_conflict_stops_before_cleanup(self) -> None:
        self.make_repo("a", ["puppet-same"])
        self.make_repo("b", ["puppet-same"])
        old = self.ccswitch / "puppet-old"
        old.mkdir(parents=True)
        config = self.write_config(
            "  - id: a\n    label: A\n    path: skill-repos/a\n    remote: x\n    branch: main\n    enabled: true\n"
            "  - id: b\n    label: B\n    path: skill-repos/b\n    remote: y\n    branch: main\n    enabled: true\n"
        )
        result = puppet_workspace.import_ccswitch(self.workspace, config, self.ccswitch)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "conflict")
        self.assertTrue(old.exists())

    def test_gitignore_ignores_skill_repos(self) -> None:
        gitignore = Path(__file__).resolve().parents[2] / ".gitignore"
        text = gitignore.read_text(encoding="utf-8")
        self.assertIn("skill-repos/**", text)
        self.assertIn("state/**", text)
        self.assertIn("backups/**", text)

    def test_status_reads_repo_without_touching_outer_git(self) -> None:
        repo = self.make_repo("a", ["puppet-one"])
        subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
        config = self.write_config(
            "  - id: a\n    label: A\n    path: skill-repos/a\n    remote: x\n    branch: main\n    enabled: true\n"
        )
        status = puppet_workspace.status_payload(self.workspace, config, self.ccswitch)
        self.assertEqual(status["repos"][0]["id"], "a")
        self.assertEqual(status["skill_count"], 1)
        self.assertEqual(status["settings"]["refresh_interval_minutes"], 180)

    def test_repo_enable_writes_config_backup(self) -> None:
        self.make_repo("a", ["puppet-one"])
        config = self.write_config(
            "  - id: a\n    label: A\n    path: skill-repos/a\n    remote: x\n    branch: main\n    enabled: true\n"
        )
        result = puppet_workspace.set_repo_enabled(self.workspace, config, "a", False)
        self.assertTrue(result["ok"])
        self.assertIn("enabled: false", config.read_text(encoding="utf-8"))
        backups = list((self.workspace / "backups" / "config").glob("*/repos.yaml"))
        self.assertEqual(len(backups), 1)

    def test_repo_path_validation_rejects_non_git_directory(self) -> None:
        repo = self.make_repo("a", ["puppet-one"])
        config = puppet_workspace.RepoConfig("a", "A", repo, "", "main", True)
        with self.assertRaises(ValueError):
            puppet_workspace.validate_repo_path_for_save(config)

    def test_startup_status_and_disable_use_env_folder(self) -> None:
        startup = self.tmp / "startup"
        startup.mkdir()
        old = os.environ.get("PUPPET_WORKSPACE_STARTUP_HOME")
        os.environ["PUPPET_WORKSPACE_STARTUP_HOME"] = str(startup)
        try:
            (startup / "PuppetWorkspace.lnk").write_text("fake", encoding="utf-8")
            self.assertTrue(puppet_workspace.startup_status(self.workspace)["enabled"])
            result = puppet_workspace.disable_startup(self.workspace)
            self.assertFalse(result["enabled"])
        finally:
            if old is None:
                os.environ.pop("PUPPET_WORKSPACE_STARTUP_HOME", None)
            else:
                os.environ["PUPPET_WORKSPACE_STARTUP_HOME"] = old

    def test_alert_keys_cover_dirty_ahead_and_conflict(self) -> None:
        payload = {
            "conflicts": {"puppet-same": ["a", "b"]},
            "repos": [{"id": "a", "dirty_count": 2, "ahead": 1, "error": ""}],
        }
        keys = puppet_workspace.alert_keys_from_payload(payload)
        self.assertIn("import-conflict:puppet-same", keys)
        self.assertIn("repo-dirty:a:2", keys)
        self.assertIn("repo-ahead:a:1", keys)

    def test_friendly_repo_status_uses_plain_language(self) -> None:
        self.assertEqual(puppet_workspace_view.friendly_repo_status({"dirty_count": 1})[0], "有未保存改动")
        self.assertEqual(puppet_workspace_view.friendly_repo_status({"ahead": 1})[0], "有本地提交未上传")
        self.assertEqual(puppet_workspace_view.friendly_repo_status({"behind": 1})[0], "远程有更新")

    def test_recent_backups_lists_known_buckets(self) -> None:
        (self.workspace / "backups" / "ccswitch" / "20260101-010101").mkdir(parents=True)
        (self.workspace / "backups" / "config" / "20260101-020202").mkdir(parents=True)
        rows = puppet_workspace_view.recent_backups(self.workspace)
        self.assertEqual(rows[0][0], "config")
        self.assertEqual(rows[1][0], "ccswitch")

    def test_restore_config_backup_replaces_manifest(self) -> None:
        config = self.write_config(
            "  - id: old\n    label: Old\n    path: skill-repos/old\n    remote: x\n    branch: main\n    enabled: true\n"
        )
        backup = self.workspace / "backups" / "config" / "20260101-010101"
        backup.mkdir(parents=True)
        (backup / "repos.yaml").write_text(
            "version: 1\nrepositories:\n  - id: new\n    label: New\n    path: skill-repos/new\n    remote: y\n    branch: main\n    enabled: true\n",
            encoding="utf-8",
        )
        result = puppet_workspace.restore_backup(self.workspace, config, self.ccswitch, "config", backup)
        self.assertTrue(result["ok"])
        self.assertIn("id: new", config.read_text(encoding="utf-8"))

    def test_restore_ccswitch_backup_replaces_puppet_skills(self) -> None:
        backup_skill = self.workspace / "backups" / "ccswitch" / "20260101-010101" / "puppet-new"
        backup_skill.mkdir(parents=True)
        (backup_skill / "SKILL.md").write_text("new", encoding="utf-8")
        old = self.ccswitch / "puppet-old"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("old", encoding="utf-8")
        backup = backup_skill.parent
        result = puppet_workspace.restore_backup(self.workspace, self.workspace / "config" / "repos.yaml", self.ccswitch, "ccswitch", backup)
        self.assertTrue(result["ok"])
        self.assertFalse(old.exists())
        self.assertTrue((self.ccswitch / "puppet-new" / "SKILL.md").is_file())

    def test_old_ui_import_points_to_new_app(self) -> None:
        self.assertEqual(puppet_workspace_ui.PuppetWorkspaceApp.__module__, "puppet_workspace_app")


if __name__ == "__main__":
    unittest.main()
