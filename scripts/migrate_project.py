#!/usr/bin/env python3
"""Preview or apply a non-destructive v2 control-plane migration to v3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _common import project_root
from project_layout import CONTROL_DIR, LEGACY_CONTROL_DIR


MAX_FILES = 20_000
MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_plain_directory(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"migration refuses symlinked {label}: {path}")
    try:
        metadata = path.stat()
    except FileNotFoundError:
        raise ValueError(f"migration requires {label} directory: {path}") from None
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"migration requires an ordinary {label} directory: {path}")


def _scan(source: Path) -> list[tuple[Path, str, int]]:
    _require_plain_directory(source, "source")
    files: list[tuple[Path, str, int]] = []
    total = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"migration refuses symlink: {path}")
        if path.is_dir():
            continue
        stat = path.stat()
        if not path.is_file() or stat.st_nlink != 1:
            raise ValueError(f"migration requires an ordinary single-link file: {path}")
        total += stat.st_size
        if len(files) >= MAX_FILES or total > MAX_TOTAL_BYTES:
            raise ValueError("legacy control plane exceeds migration resource limits")
        files.append((path.relative_to(source), _sha256(path), stat.st_size))
    return files


def _scan_included(root: Path, included: list[str], label: str) -> dict[str, tuple[str, int]]:
    inventory: dict[str, tuple[str, int]] = {}
    total = 0
    for name in included:
        for relative, digest, size in _scan(root / name):
            path = (Path(name) / relative).as_posix()
            if path in inventory:
                raise ValueError(f"migration {label} scan contains a duplicate path: {path}")
            inventory[path] = (digest, size)
            total += size
            if len(inventory) > MAX_FILES or total > MAX_TOTAL_BYTES:
                raise ValueError(f"migration {label} inventory exceeds resource limits")
    return inventory


def _ordinary_manifest_file(root: Path, relative: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"migration verification requires an ordinary root directory: {root}")
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"migration manifest contains unsafe path: {relative}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"migration verification refuses symlink: {current}")
    try:
        metadata = current.stat()
    except FileNotFoundError:
        raise ValueError(f"migrated file is missing: {relative.as_posix()}") from None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError(
            f"migration verification requires an ordinary single-link file: {relative.as_posix()}"
        )
    return current


def _validate_existing_migration(root: Path, include_evolution: bool) -> dict[str, object]:
    destination = root / CONTROL_DIR
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError(f"migration destination must be an ordinary directory: {destination}")
    manifest_path = _ordinary_manifest_file(destination, Path("migration-v3.json"))
    if manifest_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("migration manifest exceeds the validation size limit")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid migration manifest: {exc}") from exc
    expected_fields = {
        "schema_version", "migration", "migrated_at", "source", "destination",
        "source_preserved", "included", "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        raise ValueError("migration manifest has unsupported or missing fields")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("migration") != "v2-control-plane-to-v3"
        or manifest.get("source") != str(LEGACY_CONTROL_DIR)
        or manifest.get("destination") != str(CONTROL_DIR)
        or manifest.get("source_preserved") is not True
    ):
        raise ValueError("migration manifest identity or source-preservation contract is invalid")
    migrated_at = manifest.get("migrated_at")
    if not isinstance(migrated_at, str) or not migrated_at.endswith("Z"):
        raise ValueError("migration manifest migrated_at must be a UTC Z timestamp")
    try:
        datetime.fromisoformat(migrated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("migration manifest migrated_at is invalid") from exc
    included = manifest.get("included")
    allowed = ["orchestration", "runs", "evolution"]
    if (
        not isinstance(included, list)
        or not included
        or any(not isinstance(item, str) or item not in allowed for item in included)
        or len(set(included)) != len(included)
        or included != [item for item in allowed if item in included]
        or not set(included) & {"orchestration", "runs"}
    ):
        raise ValueError("migration manifest included directories are invalid")
    if include_evolution and "evolution" not in included:
        raise ValueError(
            "existing migration did not include Evolution; it cannot be added by an idempotent re-run"
        )
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ValueError("migration manifest file inventory is invalid or exceeds limits")
    seen: set[str] = set()
    declared: dict[str, tuple[str, int]] = {}
    total = 0
    legacy = root / LEGACY_CONTROL_DIR
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise ValueError("migration manifest contains an invalid file record")
        raw_path, digest, size = item.get("path"), item.get("sha256"), item.get("size")
        if not isinstance(raw_path, str):
            raise ValueError("migration manifest file path must be a string")
        relative = Path(raw_path)
        normalized = relative.as_posix()
        if (
            normalized in seen
            or relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.parts[0] not in included
            or normalized != raw_path
        ):
            raise ValueError(f"migration manifest contains unsafe or duplicate path: {raw_path}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"migration manifest contains invalid SHA-256: {raw_path}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"migration manifest contains invalid size: {raw_path}")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("migration manifest exceeds the total-size limit")
        source_file = _ordinary_manifest_file(legacy, relative)
        destination_file = _ordinary_manifest_file(destination, relative)
        for label, path in (("source", source_file), ("destination", destination_file)):
            if path.stat().st_size != size or _sha256(path) != digest:
                raise ValueError(f"migrated {label} file failed integrity verification: {raw_path}")
        seen.add(normalized)
        declared[normalized] = (digest, size)
    for label, base in (("source", legacy), ("destination", destination)):
        actual = _scan_included(base, included, label)
        if actual != declared:
            missing = sorted(set(declared) - set(actual))
            extra = sorted(set(actual) - set(declared))
            changed = sorted(
                path for path in set(actual) & set(declared)
                if actual[path] != declared[path]
            )
            details = []
            if missing:
                details.append("missing=" + ",".join(missing[:10]))
            if extra:
                details.append("extra=" + ",".join(extra[:10]))
            if changed:
                details.append("changed=" + ",".join(changed[:10]))
            raise ValueError(
                f"migration {label} inventory does not exactly match the manifest"
                + (": " + "; ".join(details) if details else "")
            )
    return {
        "status": "ALREADY_MIGRATED",
        "source": str(LEGACY_CONTROL_DIR),
        "destination": str(CONTROL_DIR),
        "manifest": str(manifest_path.relative_to(root)),
        "verified_files": len(files),
        "source_preserved": True,
    }


def _git_ignored(root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", relative],
        capture_output=True,
        check=False,
        timeout=5,
    )
    return result.returncode == 0


def plan(root: Path, include_evolution: bool = False) -> dict[str, object]:
    root = root.resolve()
    legacy = root / LEGACY_CONTROL_DIR
    destination = root / CONTROL_DIR
    if destination.is_symlink():
        raise ValueError(f"migration refuses symlinked destination: {destination}")
    if destination.exists():
        return _validate_existing_migration(root, include_evolution)
    if legacy.is_symlink():
        raise ValueError(f"migration refuses symlinked legacy control root: {legacy}")
    if not legacy.is_dir():
        raise ValueError("no v2 .codex control root was found")
    selected: list[str] = []
    for name in ("orchestration", "runs"):
        candidate = legacy / name
        if candidate.is_symlink():
            raise ValueError(f"migration refuses symlinked source directory: {candidate}")
        if candidate.is_dir():
            selected.append(name)
        elif candidate.exists():
            raise ValueError(f"migration source path is not a directory: {candidate}")
    if not selected:
        raise ValueError("no v2 .codex/orchestration or .codex/runs control state was found")
    evolution = legacy / "evolution"
    if evolution.is_symlink():
        raise ValueError(f"migration refuses symlinked source directory: {evolution}")
    if include_evolution and evolution.is_dir():
        if not _git_ignored(root, ".dingxinglizi/evolution/manifest.json"):
            raise ValueError(
                "include-evolution requires .dingxinglizi/evolution/ to be ignored before migration"
            )
        selected.append("evolution")
    inventory: list[dict[str, object]] = []
    for name in selected:
        for relative, digest, size in _scan(legacy / name):
            inventory.append({
                "path": (Path(name) / relative).as_posix(),
                "sha256": digest,
                "size": size,
            })
    return {
        "status": "READY_TO_MIGRATE",
        "source": str(LEGACY_CONTROL_DIR),
        "destination": str(CONTROL_DIR),
        "included": selected,
        "files": inventory,
        "source_preserved": True,
        "rollback": "Remove .dingxinglizi only after backing it up; v2 .codex data is not changed.",
    }


def apply(root: Path, include_evolution: bool = False) -> dict[str, object]:
    migration = plan(root, include_evolution=include_evolution)
    if migration["status"] == "ALREADY_MIGRATED":
        return migration
    root = root.resolve()
    legacy = root / LEGACY_CONTROL_DIR
    destination = root / CONTROL_DIR
    _require_plain_directory(legacy, "legacy control root")
    for name in migration["included"]:
        _require_plain_directory(legacy / str(name), f"source {name}")
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"migration destination appeared after validation: {destination}")
    staging = Path(tempfile.mkdtemp(prefix=".dingxinglizi-migrate-", dir=str(root)))
    try:
        for name in migration["included"]:
            shutil.copytree(legacy / str(name), staging / str(name), copy_function=shutil.copy2)
        for item in migration["files"]:
            copied = staging / str(item["path"])
            if _sha256(copied) != item["sha256"] or copied.stat().st_size != item["size"]:
                raise ValueError(f"copied file verification failed: {item['path']}")
        manifest = {
            "schema_version": 1,
            "migration": "v2-control-plane-to-v3",
            "migrated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": str(LEGACY_CONTROL_DIR),
            "destination": str(CONTROL_DIR),
            "source_preserved": True,
            "included": migration["included"],
            "files": migration["files"],
        }
        (staging / "migration-v3.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"migration destination appeared before atomic promotion: {destination}")
        os.replace(staging, destination)
        staging = Path()
    finally:
        if staging != Path() and staging.exists():
            shutil.rmtree(staging)
    return {
        "status": "MIGRATED",
        "source": str(LEGACY_CONTROL_DIR),
        "destination": str(CONTROL_DIR),
        "source_preserved": True,
        "files_copied": len(migration["files"]),
        "manifest": str((destination / "migration-v3.json").relative_to(root)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--apply", action="store_true", help="Apply the verified copy; default is preview only")
    parser.add_argument(
        "--include-evolution",
        action="store_true",
        help="Also copy v2 Evolution data after the neutral destination is already git-ignored",
    )
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        result = apply(root, args.include_evolution) if args.apply else plan(root, args.include_evolution)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
