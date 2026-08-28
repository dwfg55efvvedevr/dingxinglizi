#!/usr/bin/env python3
"""List, inspect, and safely apply versioned domain fact candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from _common import SKILL_ROOT, project_root
from state_io import atomic_write_json, atomic_write_text, load_json_object, utc_now


PACK_ROOT = SKILL_ROOT / "assets" / "domain-packs"
PACK_ID = __import__("re").compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def pack_path(pack_id: str) -> Path:
    if not PACK_ID.fullmatch(pack_id):
        raise ValueError(f"Invalid domain pack ID: {pack_id}")
    path = (PACK_ROOT / pack_id / "pack.json").resolve()
    try:
        path.relative_to(PACK_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Domain pack escapes bundled root: {pack_id}") from exc
    if not path.is_file():
        raise ValueError(f"Unknown domain pack: {pack_id}")
    return path


def load_pack(pack_id: str) -> dict[str, Any]:
    value = load_json_object(pack_path(pack_id))
    required = {"schema_version", "id", "version", "title", "objects", "lifecycles", "risk_signals", "completeness_additions", "test_scenarios"}
    missing = sorted(required - set(value))
    if missing or value.get("id") != pack_id:
        raise ValueError(f"Invalid domain pack {pack_id}; missing={missing}, embedded_id={value.get('id')}")
    return value


def list_packs() -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    if not PACK_ROOT.is_dir():
        return values
    for path in sorted(PACK_ROOT.glob("*/pack.json")):
        pack = load_pack(path.parent.name)
        values.append({"id": pack["id"], "version": str(pack["version"]), "title": str(pack["title"])})
    return values


def pack_hash(pack_id: str) -> str:
    return hashlib.sha256(pack_path(pack_id).read_bytes()).hexdigest()


def render_pack(pack: dict[str, Any], digest: str) -> str:
    def bullets(values: list[Any]) -> str:
        return "\n".join(f"- {value}" for value in values) or "- None"
    lifecycle_lines = []
    for name, states in pack["lifecycles"].items():
        lifecycle_lines.append(f"- **{name}**: {' → '.join(states)}")
    return f"""---
status: draft
version: 0.1
last_updated: {utc_now()}
owner: requirements
source_of_truth: false
---

# Domain pack candidates — {pack['title']}

> These are discovery candidates, not confirmed business facts. Requirements must classify every adopted item as `CONFIRMED`, `EVIDENCE_INFERRED`, `DEFAULT_ASSUMPTION`, `NOT_APPLICABLE`, or `BLOCKING_UNKNOWN` in the authoritative project documents.

- Pack: `{pack['id']}@{pack['version']}`
- SHA-256: `{digest}`
- Legal/compliance status: unverified; this pack never confirms legal conclusions.

## Candidate objects

{bullets(pack['objects'])}

## Candidate lifecycles

{chr(10).join(lifecycle_lines)}

## Risk signals

{bullets(pack['risk_signals'])}

## Product-completeness additions

{bullets(pack['completeness_additions'])}

## Test scenarios

{bullets(pack['test_scenarios'])}
"""


def apply_pack(root: Path, pack_id: str, dry_run: bool = False) -> dict[str, Any]:
    required_project_files = (
        root / "docs/project-status.json",
        root / ".codex/orchestration/role-routing-policy.json",
        root / ".codex/orchestration/model-routing-policy.json",
    )
    missing = [str(path.relative_to(root)) for path in required_project_files if not path.is_file()]
    if missing:
        raise ValueError(
            "Domain packs require an initialized project; missing: " + ", ".join(missing)
        )
    pack = load_pack(pack_id)
    digest = pack_hash(pack_id)
    doc = root / "docs/domain-pack.md"
    lock = root / ".codex/orchestration/domain-lock.json"
    proposed_lock = {
        "schema_version": 1,
        "pack_id": pack_id,
        "pack_version": pack["version"],
        "sha256": digest,
        "source": f"bundled:{pack_id}/pack.json",
        "applied_at": utc_now(),
        "status": "CANDIDATE_INPUT_ONLY",
    }
    if lock.is_file():
        current = load_json_object(lock)
        same = current.get("pack_id") == pack_id and current.get("pack_version") == pack["version"] and current.get("sha256") == digest
        if same and doc.is_file():
            return {"status": "ALREADY_APPLIED", "pack": pack_id, "document": str(doc), "lock": str(lock)}
        raise ValueError("A different or modified domain pack is already locked; review and migrate explicitly instead of overwriting it")
    if doc.exists():
        raise ValueError(f"Domain pack document already exists and will not be overwritten: {doc}")
    result = {"status": "DRY_RUN" if dry_run else "APPLIED", "pack": pack_id, "sha256": digest, "document": str(doc), "lock": str(lock)}
    if not dry_run:
        atomic_write_text(doc, render_pack(pack, digest))
        atomic_write_json(lock, proposed_lock)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("pack_id")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("project_dir")
    apply_parser.add_argument("pack_id")
    apply_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "list":
            value: Any = list_packs()
        elif args.command == "inspect":
            value = load_pack(args.pack_id)
        else:
            value = apply_pack(project_root(args.project_dir), args.pack_id, args.dry_run)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
