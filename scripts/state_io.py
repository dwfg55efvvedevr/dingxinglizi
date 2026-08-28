#!/usr/bin/env python3
"""Safe, standard-library persistence helpers for orchestration state."""

from __future__ import annotations

import json
import os
import secrets
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_object(path: Path) -> dict[str, Any]:
    _validate_existing_file(path, "JSON input")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Required JSON file is missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"JSON file is not valid UTF-8: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def safe_project_path(root: Path, relative: str | Path) -> Path:
    """Resolve a path inside root and reject absolute, traversal, or symlink escape."""
    base = root.resolve()
    value = Path(relative)
    if value.is_absolute():
        raise ValueError(f"Path must be project-relative: {relative}")
    if ".." in value.parts:
        raise ValueError(f"Path escapes project root: {relative}")
    target = base / value
    current = base
    for index, part in enumerate(value.parts):
        current = current / part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Project path must not traverse a symlink: {current}")
        if index < len(value.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"Project path parent must be a directory: {current}")
    try:
        target.resolve().relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {relative}") from exc
    return target


def atomic_write_text(path: Path, content: str, *, allowed_root: Path | None = None) -> None:
    if allowed_root is not None:
        relative = path.relative_to(allowed_root.resolve())
        path = safe_project_path(allowed_root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = safe_project_path(allowed_root, relative)
        _atomic_write_confined(path, content.encode("utf-8"))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _validate_existing_file(path, "write target", allow_missing=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        _validate_existing_file(path, "write target", allow_missing=True)
        if allowed_root is not None:
            relative = path.relative_to(allowed_root.resolve())
            path = safe_project_path(allowed_root, relative)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _atomic_write_confined(path: Path, payload: bytes) -> None:
    """Write through a verified parent dirfd and reject link/race ambiguity."""
    parent_metadata = os.stat(path.parent, follow_symlinks=False)
    directory_fd = os.open(
        str(path.parent),
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = ".%s.%s" % (path.name, secrets.token_hex(12))
    temporary_created = False
    try:
        opened_parent = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or (parent_metadata.st_dev, parent_metadata.st_ino)
            != (opened_parent.st_dev, opened_parent.st_ino)
        ):
            raise ValueError("write target parent changed during validation")

        mode = 0o644
        try:
            existing = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1:
                raise ValueError(f"write target must be an ordinary single-link file: {path}")
            mode = stat.S_IMODE(existing.st_mode)

        file_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=directory_fd,
        )
        temporary_created = True
        try:
            view = memoryview(payload)
            while view:
                written = os.write(file_fd, view)
                view = view[written:]
            os.fsync(file_fd)
        finally:
            os.close(file_fd)

        current_parent = os.stat(path.parent, follow_symlinks=False)
        if (current_parent.st_dev, current_parent.st_ino) != (
            opened_parent.st_dev, opened_parent.st_ino,
        ):
            raise ValueError("write target parent changed before commit")
        try:
            current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and (
            not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
        ):
            raise ValueError(f"write target became unsafe before commit: {path}")
        os.replace(
            temporary_name, path.name,
            src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
        )
        temporary_created = False
        os.fsync(directory_fd)
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def atomic_write_json(
    path: Path,
    value: Any,
    *,
    allowed_root: Path | None = None,
) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        allowed_root=allowed_root,
    )


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    _validate_existing_file(path, "JSONL target", allow_missing=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    # Replace the project directory entry instead of writing through its inode.
    # Even a hard-link race cannot modify the external inode's contents.
    atomic_write_text(path, existing + payload)


def _validate_existing_file(path: Path, label: str, *, allow_missing: bool = False) -> None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        if allow_missing:
            return
        raise ValueError(f"{label} is missing: {path}") from None
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"{label} must not be a symlink: {path}")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError(f"{label} must be an ordinary single-link file: {path}")
