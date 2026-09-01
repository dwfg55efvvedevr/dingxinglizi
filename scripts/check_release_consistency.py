#!/usr/bin/env python3
"""Validate repository release metadata before creating a public tag."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_REFERENCES = (
    "references/dependencies.md",
    "references/task-mode-routing.md",
    "references/large-repository-review.md",
    "references/context-hygiene.md",
    "references/review-and-repair.md",
    "references/max-capability-guide.md",
)


def check(root: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    version_path = root / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return [f"VERSION is unreadable: {exc}"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z.-]+)?", version):
        errors.append(f"VERSION is invalid: {version!r}")

    expected = {
        "README.md": (f"v{version}",),
        "USAGE.md": (f"v{version}",),
        "RELEASE_NOTES.md": (f"v{version}",),
        "CHANGELOG.md": (version,),
        "SKILL.md": REQUIRED_REFERENCES,
        "agents/openai.yaml": ("large", "review"),
    }
    for relative, needles in expected.items():
        path = root / relative
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{relative} is unreadable: {exc}")
            continue
        lowered = content.lower()
        for needle in needles:
            if needle.lower() not in lowered:
                errors.append(f"{relative} does not reference {needle!r}")

    for relative in REQUIRED_REFERENCES:
        path = root / relative
        if not path.is_file():
            errors.append(f"required installed guide is missing: {relative}")

    workflow = root / ".github/workflows/release.yml"
    try:
        workflow_text = workflow.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"release workflow is unreadable: {exc}")
    else:
        if "Build and smoke-test release assets before tagging" not in workflow_text:
            errors.append("release workflow must validate the archive before tagging")
        if 'gh release edit "$TAG"' not in workflow_text:
            errors.append("release workflow must refresh notes on an existing release")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args()
    errors = check(Path(args.root))
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"FAIL: {len(errors)} release consistency error(s)")
        return 1
    print("PASS: release metadata, installed guides, and workflow safeguards are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
