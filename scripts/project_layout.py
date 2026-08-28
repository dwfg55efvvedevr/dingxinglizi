#!/usr/bin/env python3
"""Platform-neutral project control paths with non-destructive v2 compatibility."""

from __future__ import annotations

import os
from pathlib import Path


CONTROL_DIR = Path(".dingxinglizi")
LEGACY_CONTROL_DIR = Path(".codex")
CONTROL_SCHEMA_VERSION = 2


def _lexists(path: Path) -> bool:
    return os.path.lexists(str(path))


def _validate_control_root(path: Path, label: str) -> None:
    if not _lexists(path):
        return
    if path.is_symlink():
        raise ValueError(f"{label} control root must not be a symlink: {path}")
    if not path.is_dir():
        raise ValueError(f"{label} control root must be an ordinary directory: {path}")


def _validate_control_path(root: Path, target: Path) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise ValueError(f"control-plane path escapes its root: {target}") from None
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if not _lexists(current):
            continue
        if current.is_symlink():
            raise ValueError(f"control-plane path must not traverse a symlink: {current}")
        if index < len(relative.parts) - 1 and not current.is_dir():
            raise ValueError(f"control-plane parent must be a directory: {current}")
        if index == len(relative.parts) - 1 and current.is_file():
            metadata = os.lstat(current)
            if metadata.st_nlink != 1:
                raise ValueError(f"control-plane file must be an ordinary single-link file: {current}")


def uses_legacy_layout(root: Path) -> bool:
    """Return true only when a v2 control plane exists and v3 has not been created."""
    root = root.resolve()
    platform_root = root / CONTROL_DIR
    legacy = root / LEGACY_CONTROL_DIR
    _validate_control_root(platform_root, "v3")
    if _lexists(platform_root):
        return False
    _validate_control_root(legacy, "legacy-v2")
    return any(_lexists(legacy / name) for name in ("orchestration", "runs", "evolution"))


def control_root(root: Path) -> Path:
    """Choose one control root for the whole command; never mix v2 and v3 state."""
    root = root.resolve()
    return root / (LEGACY_CONTROL_DIR if uses_legacy_layout(root) else CONTROL_DIR)


def control_path(root: Path, relative: str | Path) -> Path:
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe control-plane path: {relative}")
    selected = control_root(root)
    target = selected / relative
    _validate_control_path(selected, target)
    return target


def control_relative(root: Path, relative: str | Path) -> Path:
    return control_path(root, relative).relative_to(root.resolve())


def layout_report(root: Path) -> dict[str, object]:
    selected = control_root(root)
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "layout": "legacy-v2" if selected.name == LEGACY_CONTROL_DIR.name else "platform-neutral-v3",
        "control_root": str(selected.relative_to(root.resolve())),
        "legacy_available": (root.resolve() / LEGACY_CONTROL_DIR / "orchestration").is_dir(),
        "migration_available": uses_legacy_layout(root),
    }
