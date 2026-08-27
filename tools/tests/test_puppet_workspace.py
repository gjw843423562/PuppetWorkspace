# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "puppet_workspace.py"
SPEC = importlib.util.spec_from_file_location("puppet_workspace", MODULE_PATH)
puppet_workspace = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["puppet_workspace"] = puppet_workspace
SPEC.loader.exec_module(puppet_workspace)


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


if __name__ == "__main__":
    unittest.main()
