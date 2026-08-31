from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_release_consistency import check  # noqa: E402


class ReleaseConsistencyTests(unittest.TestCase):
    def test_repository_release_metadata_is_consistent(self) -> None:
        self.assertEqual(check(ROOT), [])

    def test_missing_installed_guide_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (
                "VERSION", "README.md", "USAGE.md", "RELEASE_NOTES.md",
                "CHANGELOG.md", "SKILL.md", "agents/openai.yaml",
                ".github/workflows/release.yml",
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            errors = check(root)
            self.assertTrue(any("required installed guide is missing" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
