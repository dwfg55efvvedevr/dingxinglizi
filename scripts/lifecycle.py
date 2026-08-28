#!/usr/bin/env python3
"""Persist a validated canonical lifecycle transition."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import CANONICAL_STATES, project_root, read_text
from check_project_status import check as check_project_status
from state_io import atomic_write_json, atomic_write_text


def transition(root: Path, target: str) -> dict[str, Any]:
    root = root.resolve()
    if target not in CANONICAL_STATES:
        raise ValueError(
            "transition accepts canonical states only; BLOCKED and REWORK_* require their structured reason/defect records"
        )
    status_path = root / "docs/project-status.json"
    original_text = read_text(status_path)
    status = json.loads(original_text)
    current = status.get("current_state")
    if current == target:
        return {"status": "UNCHANGED", "from": current, "to": target, "warnings": []}
    if target == "BACKLOG":
        blocked_resume = (
            current == "BLOCKED"
            and isinstance(status.get("blocked"), dict)
            and status["blocked"].get("resume_state") == "BACKLOG"
        )
        if not blocked_resume:
            raise ValueError(
                f"Lifecycle transition {current} -> BACKLOG is blocked; start a new governed iteration instead of rewinding state"
            )
    errors, warnings = check_project_status(root, target)
    if errors:
        raise ValueError(
            f"Lifecycle transition {current} -> {target} is blocked: " + "; ".join(errors)
        )
    status["previous_state"] = current
    status["current_state"] = target
    status["updated_at"] = datetime.now(timezone.utc).isoformat()
    status["updated_by"] = "orchestrator"
    if current == "BLOCKED":
        status["blocked"] = None
    if isinstance(current, str) and current.startswith("REWORK_"):
        status["rework"] = None
    atomic_write_json(status_path, status)
    persisted_errors, persisted_warnings = check_project_status(root, None)
    if persisted_errors:
        atomic_write_text(status_path, original_text)
        raise RuntimeError(
            "Persisted lifecycle state failed validation: " + "; ".join(persisted_errors)
        )
    return {
        "status": "TRANSITIONED",
        "from": current,
        "to": target,
        "warnings": sorted(set(warnings + persisted_warnings)),
    }


def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--target", required=True, choices=CANONICAL_STATES)
    args = parser.parse_args()
    try:
        print(json.dumps(transition(project_root(args.project_dir), args.target), ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
