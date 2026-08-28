#!/usr/bin/env python3
"""Explicit, non-networked installation planner for platform adapters."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

from platform_runtime import (
    SKILL_INSTALL_NAME, SKILL_ROOT, platform_spec, render_adapter_files,
    resolve_opencode_schema, safe_write_target,
)


PACKAGE_FILES: Tuple[str, ...] = ("SKILL.md", "VERSION", "LICENSE")
PACKAGE_DIRECTORIES: Tuple[str, ...] = ("scripts", "references", "assets", "agents", "evals")
IGNORED_NAMES = {"__pycache__", ".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _portable_sources() -> Iterable[Tuple[Path, Path]]:
    """Yield (package-relative path, source) from a fixed allowlist."""
    for name in PACKAGE_FILES:
        source = SKILL_ROOT / name
        if source.is_file():
            yield Path(name), source
    for directory in PACKAGE_DIRECTORIES:
        source_root = SKILL_ROOT / directory
        if not source_root.is_dir():
            continue
        for source in sorted(source_root.rglob("*")):
            if source.is_symlink() or not source.is_file():
                continue
            relative = source.relative_to(SKILL_ROOT)
            if any(part in IGNORED_NAMES for part in relative.parts) or source.suffix in IGNORED_SUFFIXES:
                continue
            yield relative, source


def _install_files(
    target_root: Path,
    platform: str,
    scope: str,
    *,
    opencode_schema: str = "auto",
) -> Dict[Path, bytes]:
    spec = platform_spec(platform)
    skill_key = "project_skill_directory" if scope == "project" else "user_skill_directory"
    agent_key = "project_agent_directory" if scope == "project" else "user_agent_directory"
    skill_destination = target_root / str(spec[skill_key]) / SKILL_INSTALL_NAME
    files: Dict[Path, bytes] = {}
    for relative, source in _portable_sources():
        files[skill_destination / relative] = source.read_bytes()
    project_agent_prefix = Path(str(spec["project_agent_directory"]))
    agent_destination = target_root / str(spec[agent_key])
    for relative, content in render_adapter_files(
        platform, opencode_schema=opencode_schema
    ).items():
        role_relative = relative.relative_to(project_agent_prefix)
        files[agent_destination / role_relative] = content.encode("utf-8")
    return files


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def install_platform(
    target_root: Path,
    platform: str,
    *,
    scope: str,
    apply: bool = False,
    update: bool = False,
    opencode_schema: str = "auto",
) -> Dict[str, Any]:
    """Plan or apply a native install below an explicit user/project root.

    This function performs no network access, authentication, credential lookup,
    package-manager invocation, or write outside `target_root`.
    """
    if scope not in {"project", "user"}:
        raise ValueError("scope must be project or user")
    root = Path(target_root).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ValueError("Install target is not a directory: %s" % root)
    selected_schema = resolve_opencode_schema(opencode_schema) if platform == "opencode" else ""
    if platform != "opencode" and opencode_schema != "auto":
        raise ValueError("--opencode-schema applies only when --platform opencode")
    files = _install_files(
        root, platform, scope, opencode_schema=selected_schema or "auto"
    )
    creates = []
    updates = []
    unchanged = []
    conflicts = []
    for target, content in sorted(files.items(), key=lambda item: str(item[0])):
        if not safe_write_target(root, target):
            conflicts.append(target)
        elif not target.exists():
            creates.append(target)
        elif not target.is_file():
            conflicts.append(target)
        elif not stat.S_ISREG(os.lstat(target).st_mode) or os.lstat(target).st_nlink != 1:
            conflicts.append(target)
        elif target.read_bytes() == content:
            unchanged.append(target)
        elif update:
            updates.append(target)
        else:
            conflicts.append(target)
    status = "PLANNED"
    if conflicts:
        status = "BLOCKED_CONFLICT"
    elif apply:
        for target in creates + updates:
            _atomic_write_bytes(target, files[target])
        status = "INSTALLED"
    result = {
        "status": status,
        "platform": platform,
        "scope": scope,
        "target_root": str(root),
        "apply": apply,
        "update": update,
        "created": [str(path) for path in creates],
        "updated": [str(path) for path in updates],
        "unchanged": [str(path) for path in unchanged],
        "conflicts": [str(path) for path in conflicts],
        "selected_platform_only": True,
        "external_actions": [],
        "credential_access": False,
        "network_access": False,
    }
    if platform == "opencode":
        result["adapter_schema"] = selected_schema
    return result
