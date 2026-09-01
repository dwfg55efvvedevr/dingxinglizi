from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_planning import build_review_plan  # noqa: E402
from review_repository import capture_git_snapshot, inventory_git_target  # noqa: E402


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


class ReviewPerformanceTests(unittest.TestCase):
    def test_ten_thousand_file_cross_cut_plan_is_linear_enough(self) -> None:
        count = 10_000
        inventory = {
            "manifest_fingerprint": "a" * 64,
            "entries": [
                {
                    "path": f"src/area-{index // 100:03d}/file-{index:05d}.py",
                    "size_bytes": 64,
                    "disposition": "INCLUDED",
                }
                for index in range(count)
            ],
            "modules": [{"module_id": "module-src", "root": "src"}],
            "disposition_counts": {"INCLUDED": count},
        }
        started = time.perf_counter()
        plan = build_review_plan(inventory, required_risks=["privacy"])
        elapsed = time.perf_counter() - started

        self.assertEqual(plan["status"], "READY")
        self.assertEqual(len(plan["file_coverage"]), count)
        self.assertEqual(sum(shard["file_count"] for shard in plan["cross_cut_shards"]), count)
        # This is deliberately generous for shared/CI machines while still
        # detecting the prior 100M-entry scan regression.
        self.assertLess(elapsed, 5.0, f"10k-file plan took {elapsed:.3f}s")

    def test_git_inventory_uses_one_batch_blob_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            git(root, "config", "user.email", "review@example.invalid")
            git(root, "config", "user.name", "Review Test")
            for index in range(50):
                path = root / "src" / f"file-{index:03d}.py"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"VALUE = {index}\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "fixture")
            commit = git(root, "rev-parse", "HEAD")
            snapshot = capture_git_snapshot(root, commit, commit)

            real_popen = subprocess.Popen
            batch_commands: list[list[str]] = []

            def recording_popen(command: list[str], *args: object, **kwargs: object):
                if "cat-file" in command and "--batch" in command:
                    batch_commands.append(command)
                return real_popen(command, *args, **kwargs)

            with mock.patch("review_repository.subprocess.Popen", side_effect=recording_popen):
                inventory = inventory_git_target(root, snapshot)

            self.assertEqual(inventory["entry_count"], 50)
            self.assertEqual(inventory["disposition_counts"], {"INCLUDED": 50})
            self.assertEqual(len(batch_commands), 1)


if __name__ == "__main__":
    unittest.main()
