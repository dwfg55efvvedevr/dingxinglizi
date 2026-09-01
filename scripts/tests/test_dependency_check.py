#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from dependency_check import dependency_report  # noqa: E402


class DependencyCheckTests(unittest.TestCase):
    def test_missing_pyyaml_never_blocks_runtime(self) -> None:
        report = dependency_report(
            version_info=(3, 11, 0),
            which=lambda executable: "/usr/bin/git" if executable == "git" else None,
            find_spec=lambda module: None,
        )
        self.assertEqual(report["status"], "RUNTIME_READY")
        self.assertTrue(report["runtime_ready"])
        self.assertEqual(report["development_dependencies"][0]["status"], "NOT_FOUND")
        self.assertFalse(report["development_dependencies"][0]["required_for_skill_runtime"])
        self.assertIn("runtime is unaffected", report["notices"][0]["message"])

    def test_missing_git_is_an_optional_feature_limitation(self) -> None:
        report = dependency_report(
            version_info=(3, 9, 0), which=lambda executable: None,
            find_spec=lambda module: object(),
        )
        self.assertTrue(report["runtime_ready"])
        git = next(item for item in report["optional_feature_dependencies"] if item["id"] == "git")
        self.assertEqual(git["status"], "NOT_FOUND")
        self.assertTrue(any(item["id"] == "optional.git" for item in report["notices"]))

    def test_old_python_blocks_runtime(self) -> None:
        report = dependency_report(
            version_info=(3, 8, 10), which=lambda executable: None,
            find_spec=lambda module: None,
        )
        self.assertEqual(report["status"], "BLOCKED_RUNTIME")
        self.assertFalse(report["runtime_ready"])

    def test_unified_cli_exposes_machine_readable_dependency_report(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrator.py"), "dependencies", "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["runtime_ready"])
        self.assertEqual(payload["runtime_dependencies"][1]["status"], "NONE_REQUIRED")

    def test_platform_install_preview_includes_dependency_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "orchestrator.py"), "platform", "install",
                    directory, "--platform", "codex", "--scope", "project",
                ],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["dependency_status"], "RUNTIME_READY")
        self.assertIn("dependency_notices", payload)


if __name__ == "__main__":
    unittest.main()
