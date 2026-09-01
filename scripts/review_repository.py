#!/usr/bin/env python3
"""Deterministic, bounded repository snapshots for large-repository review."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

from state_io import utc_now


COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_COMMAND_TIMEOUT = 30
MAX_COMMAND_OUTPUT = 64 * 1024 * 1024
MAX_TRACKED_FILES = 250_000
MAX_MANIFEST_BYTES = 2 * 1024 * 1024 * 1024
MAX_CLASSIFY_BYTES = 1024 * 1024

VENDOR_PARTS = {
    "vendor", "vendors", "node_modules", "third_party", "third-party",
    "bower_components", ".venv", "venv",
}
GENERATED_PARTS = {
    "dist", "build", "coverage", ".next", ".nuxt", "target", "generated",
    "gen", "out",
}
GENERATED_SUFFIXES = {".min.js", ".min.css", ".map"}
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".a", ".o", ".class",
    ".jar", ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".mov", ".avi",
}
MANIFEST_NAMES = {
    "package.json": "node-package-manifest",
    "pyproject.toml": "python-project-manifest",
    "setup.py": "python-project-manifest",
    "go.mod": "go-module-manifest",
    "Cargo.toml": "rust-package-manifest",
    "pom.xml": "java-project-manifest",
    "build.gradle": "java-project-manifest",
    "build.gradle.kts": "java-project-manifest",
    "Gemfile": "ruby-project-manifest",
    "composer.json": "php-project-manifest",
}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run_git(
    root: Path,
    arguments: Iterable[str],
    *,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    output_limit: int = MAX_COMMAND_OUTPUT,
    check: bool = True,
) -> bytes:
    """Run Git without a shell, with a timeout and a strict captured-output limit."""
    command = ["git", "-C", str(root.resolve())] + [str(item) for item in arguments]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise ValueError(f"Git command timed out after {timeout}s: {' '.join(command[:4])}") from exc
    if len(stdout) > output_limit or len(stderr) > output_limit:
        raise ValueError(f"Git command exceeded the {output_limit}-byte output limit")
    if check and process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[:2000]
        raise ValueError(f"Git command failed ({process.returncode}): {detail}")
    return stdout


def is_git_repository(root: Path) -> bool:
    try:
        output = _run_git(root, ["rev-parse", "--is-inside-work-tree"], output_limit=4096)
    except (OSError, ValueError):
        return False
    return output.strip() == b"true"


def resolve_commit(root: Path, revision: str) -> str:
    if not revision or revision.startswith("-") or any(char in revision for char in "\x00\r\n"):
        raise ValueError("Git revision must be a non-option, single-line value")
    value = _run_git(
        root, ["rev-parse", "--verify", f"{revision}^{{commit}}"], output_limit=4096,
    ).decode("ascii", errors="strict").strip()
    if not COMMIT_PATTERN.fullmatch(value):
        raise ValueError(f"Git revision did not resolve to a 40-hex commit: {revision}")
    return value


def _is_ancestor(root: Path, baseline: str, target: str) -> bool:
    try:
        process = subprocess.run(
            ["git", "-C", str(root.resolve()), "merge-base", "--is-ancestor", baseline, target],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=DEFAULT_COMMAND_TIMEOUT,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Git ancestor check timed out") from exc
    if len(process.stdout) > 4096 or len(process.stderr) > 4096:
        raise ValueError("Git ancestor check produced unexpected output")
    if process.returncode not in {0, 1}:
        raise ValueError(
            "Git ancestor check failed: "
            + process.stderr.decode("utf-8", errors="replace").strip()[:1000]
        )
    return process.returncode == 0


def _worktree_status(root: Path) -> dict[str, Any]:
    raw = _run_git(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        output_limit=MAX_COMMAND_OUTPUT,
    )
    records: list[str] = []
    parts = raw.split(b"\0")
    index = 0
    while index < len(parts):
        item = parts[index]
        index += 1
        if not item:
            continue
        decoded = item.decode("utf-8", errors="surrogateescape")
        # Rename/copy status is followed by its second path in porcelain -z.
        if decoded[:2] in {"R ", " R", "C ", " C"} and index < len(parts):
            second = parts[index].decode("utf-8", errors="surrogateescape")
            index += 1
            decoded = decoded + " -> " + second
        path_field = decoded[3:] if len(decoded) >= 3 else decoded
        compared = path_field.split(" -> ")[-1]
        if compared == ".dingxinglizi" or compared.startswith(".dingxinglizi/"):
            continue
        if compared == ".codex" or compared.startswith(".codex/"):
            continue
        records.append(decoded)
    records.sort()
    return {
        "dirty": bool(records),
        "entry_count": len(records),
        "entries": records,
        "fingerprint": _canonical_hash(records),
    }


def capture_git_snapshot(root: Path, baseline: str, target: str) -> dict[str, Any]:
    root = root.resolve()
    baseline_commit = resolve_commit(root, baseline)
    target_commit = resolve_commit(root, target)
    if not _is_ancestor(root, baseline_commit, target_commit):
        raise ValueError("Baseline commit must be an ancestor of target commit")
    head_commit = resolve_commit(root, "HEAD")
    return {
        "schema_version": 1,
        "snapshot_kind": "GIT_COMMIT",
        "captured_at": utc_now(),
        "requested_baseline": baseline,
        "requested_target": target,
        "baseline_commit": baseline_commit,
        "target_commit": target_commit,
        "baseline_is_ancestor": True,
        "head_commit": head_commit,
        "target_is_head": target_commit == head_commit,
        "working_tree": _worktree_status(root),
        "conclusion_strength": "COMMIT_BOUND",
    }


def _git_blob_prefix(root: Path, target: str, path: str) -> bytes:
    # Path came from ls-tree, but still reject option/newline ambiguity.
    if path.startswith("-") or "\x00" in path or "\n" in path or "\r" in path:
        raise ValueError(f"Unsafe Git tree path: {path!r}")
    return _run_git(
        root, ["show", f"{target}:{path}"], output_limit=MAX_CLASSIFY_BYTES,
    )


class _GitBlobBatchReader:
    """Read pinned blobs through one bounded ``git cat-file --batch`` process.

    Object ids come from ``ls-tree`` and are revalidated before being written to
    the protocol.  Blob bytes are consumed exactly, so paths never enter a Git
    revision expression and repositories pay one process launch rather than one
    launch per classifiable file.
    """

    def __init__(self, root: Path, *, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self.process: subprocess.Popen[bytes] | None = None
        self.failure: str | None = None

    def __enter__(self) -> "_GitBlobBatchReader":
        self.process = subprocess.Popen(
            ["git", "-C", str(self.root), "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            bufsize=0,
        )
        return self

    def _read_ready(self, size: int, deadline: float) -> bytes:
        if not self.process or not self.process.stdout:
            raise ValueError("Git blob batch process is not available")
        chunks: list[bytes] = []
        remaining = size
        descriptor = self.process.stdout.fileno()
        while remaining:
            wait = deadline - time.monotonic()
            if wait <= 0:
                raise ValueError(f"Git blob batch read timed out after {self.timeout}s")
            readable, _, _ = select.select([descriptor], [], [], wait)
            if not readable:
                raise ValueError(f"Git blob batch read timed out after {self.timeout}s")
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ValueError("Git blob batch process ended before returning the object")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _readline(self, deadline: float, *, limit: int = 4096) -> bytes:
        value = bytearray()
        while len(value) < limit:
            byte = self._read_ready(1, deadline)
            value.extend(byte)
            if byte == b"\n":
                return bytes(value)
        raise ValueError("Git blob batch returned an oversized protocol header")

    def read(self, object_id: str, expected_size: int) -> bytes:
        if self.failure:
            raise ValueError(f"Git blob batch is unavailable after an earlier failure: {self.failure}")
        try:
            return self._read(object_id, expected_size)
        except (OSError, UnicodeError, ValueError) as exc:
            # Treat a protocol/read failure as process-wide. Continuing to send
            # requests after framing is uncertain can misassociate blob content
            # with paths, so later files fail immediately and explicitly.
            self.failure = str(exc)
            raise

    def _read(self, object_id: str, expected_size: int) -> bytes:
        if not COMMIT_PATTERN.fullmatch(object_id):
            raise ValueError(f"Invalid Git object id in tree inventory: {object_id!r}")
        if expected_size < 0 or expected_size > MAX_CLASSIFY_BYTES:
            raise ValueError("Git blob classification size is outside the allowed limit")
        if not self.process or not self.process.stdin:
            raise ValueError("Git blob batch process is not available")
        deadline = time.monotonic() + self.timeout
        try:
            self.process.stdin.write(object_id.encode("ascii") + b"\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ValueError("Git blob batch process rejected the object request") from exc
        header = self._readline(deadline).rstrip(b"\n")
        fields = header.split(b" ")
        if len(fields) == 2 and fields[1] == b"missing":
            raise ValueError(f"Git object disappeared during inventory: {object_id}")
        if len(fields) != 3:
            raise ValueError("Git blob batch returned an invalid protocol header")
        returned_id, object_type, size_bytes = fields
        try:
            returned_size = int(size_bytes)
        except ValueError as exc:
            raise ValueError("Git blob batch returned an invalid object size") from exc
        if returned_id.decode("ascii", errors="strict") != object_id or object_type != b"blob":
            raise ValueError("Git blob batch returned an unexpected object")
        if returned_size != expected_size or returned_size > MAX_CLASSIFY_BYTES:
            raise ValueError(
                f"Git blob size changed during inventory ({returned_size} != {expected_size})"
            )
        content = self._read_ready(returned_size, deadline)
        if self._read_ready(1, deadline) != b"\n":
            raise ValueError("Git blob batch returned an invalid object terminator")
        return content

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self.process:
            return
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        stderr = b""
        if self.process.stderr:
            stderr = self.process.stderr.read(MAX_COMMAND_OUTPUT + 1)
            self.process.stderr.close()
        if self.process.stdout:
            self.process.stdout.close()
        if len(stderr) > MAX_COMMAND_OUTPUT and exc_type is None:
            raise ValueError("Git blob batch exceeded the stderr output limit")
        if self.process.returncode != 0 and exc_type is None:
            detail = stderr.decode("utf-8", errors="replace").strip()[:2000]
            raise ValueError(f"Git blob batch failed ({self.process.returncode}): {detail}")


def _path_disposition(path: str, mode: str, object_type: str) -> tuple[str, list[str]]:
    parts = Path(path).parts
    lowered = {part.lower() for part in parts[:-1]}
    name_lower = Path(path).name.lower()
    if mode == "160000" or object_type == "commit":
        return "SUBMODULE", ["git-mode-160000"]
    if mode == "120000":
        return "SYMLINK", ["git-mode-120000"]
    vendor = sorted(lowered & VENDOR_PARTS)
    if vendor:
        return "EXCLUDED_VENDOR", [f"path-segment:{vendor[0]}"]
    generated = sorted(lowered & GENERATED_PARTS)
    if generated:
        return "EXCLUDED_GENERATED", [f"path-segment:{generated[0]}"]
    for suffix in GENERATED_SUFFIXES:
        if name_lower.endswith(suffix):
            return "EXCLUDED_GENERATED", [f"generated-suffix:{suffix}"]
    if Path(path).suffix.lower() in BINARY_SUFFIXES:
        return "EXCLUDED_BINARY", [f"binary-extension:{Path(path).suffix.lower()}"]
    return "INCLUDED", ["tracked-source-candidate"]


def _classify_blob_content(entry: dict[str, Any], content: bytes) -> None:
    """Apply content-derived classification to an already bounded blob."""
    if entry["disposition"] != "INCLUDED":
        return
    if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
        entry["disposition"] = "EXCLUDED_LFS"
        entry["classification_notes"].append("git-lfs-pointer")
    elif b"\x00" in content[:8192]:
        entry["disposition"] = "EXCLUDED_BINARY"
        entry["classification_notes"].append("nul-byte-in-prefix")
    elif Path(entry["path"]).name == "package.json":
        try:
            value = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            entry["classification_notes"].append("package-manifest-unparseable")
        else:
            workspaces = value.get("workspaces", []) if isinstance(value, dict) else []
            if isinstance(workspaces, dict):
                workspaces = workspaces.get("packages", [])
            if isinstance(workspaces, list) and all(isinstance(item, str) for item in workspaces):
                entry["workspace_patterns"] = sorted(set(workspaces))
                if workspaces:
                    entry["classification_notes"].append("workspace-manifest")


def inventory_git_target(root: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    target = str(snapshot.get("target_commit", ""))
    if not COMMIT_PATTERN.fullmatch(target):
        raise ValueError("Snapshot has no valid target commit")
    raw = _run_git(
        root,
        ["ls-tree", "-r", "-z", "--long", target],
        output_limit=MAX_COMMAND_OUTPUT,
    )
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for raw_record in raw.split(b"\0"):
        if not raw_record:
            continue
        try:
            metadata, path_bytes = raw_record.split(b"\t", 1)
            mode_b, type_b, object_b, size_b = metadata.split(b" ", 3)
            path = path_bytes.decode("utf-8", errors="strict")
            mode = mode_b.decode("ascii")
            object_type = type_b.decode("ascii")
            object_id = object_b.decode("ascii")
            size_text = size_b.decode("ascii").strip()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Unable to parse deterministic git tree inventory") from exc
        if path.startswith("/") or ".." in Path(path).parts or "\x00" in path:
            raise ValueError(f"Git tree contains unsafe path: {path!r}")
        size = 0 if size_text == "-" else int(size_text)
        total_bytes += size
        disposition, notes = _path_disposition(path, mode, object_type)
        entry = {
            "path": path,
            "mode": mode,
            "object_type": object_type,
            "object_id": object_id,
            "size_bytes": size,
            "disposition": disposition,
            "classification_notes": notes,
        }
        entries.append(entry)
        if len(entries) > MAX_TRACKED_FILES:
            raise ValueError(f"Repository exceeds tracked-file limit ({MAX_TRACKED_FILES})")
        if total_bytes > MAX_MANIFEST_BYTES:
            raise ValueError(f"Repository exceeds manifest-byte limit ({MAX_MANIFEST_BYTES})")

    # Classify all bounded source candidates through one persistent Git process.
    # A failed read is explicit and fail-closed for that file; it is never silently
    # treated as text. Large files retain the pre-existing deterministic skip.
    classifiable = [entry for entry in entries if entry["disposition"] == "INCLUDED"]
    if classifiable and os.name == "nt":
        # ``select`` cannot wait on anonymous pipes on Windows. Preserve safe,
        # bounded classification there and make the process-count degradation
        # observable in every affected inventory entry.
        for entry in classifiable:
            size = int(entry.get("size_bytes") or 0)
            if size > MAX_CLASSIFY_BYTES:
                entry["classification_notes"].append("content-classification-skipped:size-limit")
                continue
            entry["classification_notes"].append("content-read-mode:per-object-platform-fallback")
            try:
                content = _git_blob_prefix(root, target, str(entry["path"]))
            except ValueError as exc:
                entry["disposition"] = "BLOCKED_UNCLASSIFIED"
                entry["classification_notes"].append(f"content-read-failed:{exc}")
                continue
            _classify_blob_content(entry, content)
    elif classifiable:
        with _GitBlobBatchReader(root) as reader:
            for entry in classifiable:
                size = int(entry.get("size_bytes") or 0)
                if size > MAX_CLASSIFY_BYTES:
                    entry["classification_notes"].append("content-classification-skipped:size-limit")
                    continue
                try:
                    content = reader.read(str(entry["object_id"]), size)
                except (OSError, UnicodeError, ValueError) as exc:
                    entry["disposition"] = "BLOCKED_UNCLASSIFIED"
                    entry["classification_notes"].append(f"batch-content-read-failed:{exc}")
                    continue
                _classify_blob_content(entry, content)
    entries.sort(key=lambda item: item["path"])
    disposition_counts: dict[str, int] = {}
    for entry in entries:
        key = str(entry["disposition"])
        disposition_counts[key] = disposition_counts.get(key, 0) + 1
    modules = discover_modules(entries)
    manifest_core = {
        "snapshot_kind": "GIT_COMMIT",
        "target_commit": target,
        "entries": entries,
        "modules": modules,
    }
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "snapshot_kind": "GIT_COMMIT",
        "target_commit": target,
        "entry_count": len(entries),
        "total_bytes": total_bytes,
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "entries": entries,
        "modules": modules,
        "manifest_fingerprint": _canonical_hash(manifest_core),
        "completeness_claim": "DETERMINISTIC_TRACKED_TREE_INVENTORY_NOT_SEMANTIC_COMPLETENESS",
    }


def _ordinary_worktree_files(root: Path) -> list[Path]:
    values: list[Path] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directories):
            child = current_path / name
            metadata = os.lstat(child)
            if stat.S_ISLNK(metadata.st_mode):
                values.append(child)
                continue
            relative = child.relative_to(root).as_posix()
            if relative in {".git", ".dingxinglizi", ".codex"}:
                continue
            kept.append(name)
        directories[:] = kept
        for name in sorted(files):
            child = current_path / name
            values.append(child)
    return sorted(values, key=lambda item: item.relative_to(root).as_posix())


def _hash_file(path: Path) -> tuple[str, bytes]:
    digest = hashlib.sha256()
    prefix = bytearray()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            if len(prefix) < 8192:
                prefix.extend(chunk[:8192 - len(prefix)])
    return digest.hexdigest(), bytes(prefix)


def capture_worktree_snapshot(root: Path, *, explicit: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    if not explicit:
        raise ValueError("Non-Git review requires explicit WORKTREE_SNAPSHOT acknowledgement")
    root = root.resolve()
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for path in _ordinary_worktree_files(root):
        relative = path.relative_to(root).as_posix()
        metadata = os.lstat(path)
        if stat.S_ISLNK(metadata.st_mode):
            entry = {
                "path": relative, "mode": "symlink", "object_type": "symlink",
                "object_id": None, "size_bytes": 0, "disposition": "SYMLINK",
                "classification_notes": ["worktree-symlink"],
            }
        elif not stat.S_ISREG(metadata.st_mode):
            entry = {
                "path": relative, "mode": oct(stat.S_IMODE(metadata.st_mode)),
                "object_type": "special", "object_id": None, "size_bytes": 0,
                "disposition": "BLOCKED_SPECIAL_FILE",
                "classification_notes": ["non-regular-worktree-entry"],
            }
        elif metadata.st_nlink != 1:
            entry = {
                "path": relative, "mode": oct(stat.S_IMODE(metadata.st_mode)),
                "object_type": "blob", "object_id": None, "size_bytes": metadata.st_size,
                "disposition": "BLOCKED_UNSAFE_HARDLINK",
                "classification_notes": [f"hardlink-count:{metadata.st_nlink}"],
            }
        else:
            size = metadata.st_size
            if total_bytes + size > MAX_MANIFEST_BYTES:
                raise ValueError("Worktree snapshot exceeds repository inventory resource limits")
            total_bytes += size
            digest, content = _hash_file(path)
            disposition, notes = _path_disposition(relative, "100644", "blob")
            if disposition == "INCLUDED" and b"\x00" in content:
                disposition, notes = "EXCLUDED_BINARY", notes + ["nul-byte-in-prefix"]
            entry = {
                "path": relative, "mode": "100644", "object_type": "blob",
                "object_id": digest, "size_bytes": size, "disposition": disposition,
                "classification_notes": notes,
            }
        entries.append(entry)
        if len(entries) > MAX_TRACKED_FILES or total_bytes > MAX_MANIFEST_BYTES:
            raise ValueError("Worktree snapshot exceeds repository inventory resource limits")
    modules = discover_modules(entries)
    core = {"snapshot_kind": "WORKTREE_SNAPSHOT", "entries": entries, "modules": modules}
    fingerprint = _canonical_hash(core)
    inventory = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "snapshot_kind": "WORKTREE_SNAPSHOT",
        "target_commit": None,
        "entry_count": len(entries),
        "total_bytes": total_bytes,
        "disposition_counts": _counts(entries),
        "entries": entries,
        "modules": modules,
        "manifest_fingerprint": fingerprint,
        "completeness_claim": "EXPLICIT_POINT_IN_TIME_WORKTREE_INVENTORY_NOT_COMMIT_BOUND_OR_SEMANTICALLY_COMPLETE",
    }
    snapshot = {
        "schema_version": 1,
        "snapshot_kind": "WORKTREE_SNAPSHOT",
        "captured_at": utc_now(),
        "baseline_commit": None,
        "target_commit": None,
        "manifest_fingerprint": fingerprint,
        "conclusion_strength": "REDUCED_NON_GIT_WORKTREE",
        "limitations": ["No immutable Git commit lineage", "Concurrent file changes can invalidate this snapshot"],
    }
    return snapshot, inventory


def _effective_entries(root: Path) -> list[dict[str, Any]]:
    _, inventory = capture_worktree_snapshot(root, explicit=True)
    return [
        entry for entry in inventory.get("entries", [])
        if not any(
            str(entry.get("path", "")) == prefix
            or str(entry.get("path", "")).startswith(prefix + "/")
            for prefix in ("evidence", "tasks")
        )
    ]


def effective_source_snapshot(
    root: Path,
    *,
    excluded_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Fingerprint current source while excluding review evidence/control artifacts.

    This binds repair and re-review to observable local source content. It does not
    claim a commit identity and deliberately ignores the generated `evidence/`
    tree so writing proof cannot invalidate the source snapshot it describes.
    """
    excluded = set(excluded_paths)
    entries = [
        entry for entry in _effective_entries(root)
        if str(entry.get("path", "")) not in excluded
    ]
    modules = discover_modules(entries)
    core = {
        "snapshot_kind": "EFFECTIVE_SOURCE_WORKTREE",
        "entries": entries,
        "modules": modules,
    }
    return {
        "schema_version": 1,
        "snapshot_kind": "EFFECTIVE_SOURCE_WORKTREE",
        "captured_at": utc_now(),
        "entry_count": len(entries),
        "total_bytes": sum(int(entry.get("size_bytes", 0)) for entry in entries),
        "disposition_counts": _counts(entries),
        "fingerprint": _canonical_hash(core),
        "ignored_roots": [".codex", ".dingxinglizi", ".git", "evidence", "tasks"],
        "excluded_paths": sorted(excluded),
        "conclusion_strength": "LOCAL_CONTENT_BOUND_NOT_COMMIT_BOUND",
    }


def selected_source_snapshot(root: Path, paths: Iterable[str]) -> dict[str, Any]:
    """Fingerprint an exact bounded path set, retaining missing-path evidence."""
    root = root.resolve()
    entries: list[dict[str, Any]] = []
    for relative in sorted(set(paths)):
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not relative:
            raise ValueError(f"Unsafe selected source path: {relative}")
        path = root / candidate
        if not path.exists():
            entries.append({"path": candidate.as_posix(), "disposition": "MISSING"})
            continue
        metadata = os.lstat(path)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"Selected source path must be an ordinary single-link file: {relative}")
        digest, _ = _hash_file(path)
        entries.append({
            "path": candidate.as_posix(),
            "disposition": "PRESENT",
            "size_bytes": metadata.st_size,
            "sha256": digest,
        })
    return {
        "schema_version": 1,
        "paths": sorted(set(paths)),
        "entries": entries,
        "fingerprint": _canonical_hash(entries),
    }


def _counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for entry in entries:
        key = str(entry["disposition"])
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def discover_modules(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discover reproducible module candidates; this is evidence, not semantic proof."""
    included = [entry for entry in entries if entry.get("disposition") == "INCLUDED"]
    path_set = {str(entry["path"]) for entry in included}
    candidates: dict[str, dict[str, Any]] = {}
    for path in sorted(path_set):
        name = Path(path).name
        if name in MANIFEST_NAMES:
            entry = next(item for item in included if item["path"] == path)
            parent = Path(path).parent.as_posix()
            root = "." if parent == "." else parent
            candidates[root] = {
                "module_id": _module_id(root),
                "root": root,
                "evidence": [f"manifest:{path}", MANIFEST_NAMES[name]] + [
                    f"workspace-pattern:{pattern}" for pattern in entry.get("workspace_patterns", [])
                ],
                "confidence": "HIGH",
                "discovery_basis": "workspace-manifest" if entry.get("workspace_patterns") else "manifest",
            }
    top_level = sorted({Path(path).parts[0] for path in path_set if len(Path(path).parts) > 1})
    if not candidates and top_level:
        for directory in top_level:
            candidates[directory] = {
                "module_id": _module_id(directory),
                "root": directory,
                "evidence": [f"top-level-directory:{directory}"],
                "confidence": "LOW",
                "discovery_basis": "directory-heuristic",
            }
    if not candidates:
        candidates["."] = {
            "module_id": "module-root", "root": ".",
            "evidence": ["single-root-fallback"], "confidence": "LOW",
            "discovery_basis": "fallback",
        }
    roots = sorted(candidates, key=lambda item: (-len(Path(item).parts), item))
    assignments: dict[str, list[str]] = {root: [] for root in candidates}
    for path in sorted(path_set):
        selected = None
        for root in roots:
            if root == "." or path == root or path.startswith(root + "/"):
                selected = root
                break
        if selected is None:
            selected = "."
            if selected not in candidates:
                candidates[selected] = {
                    "module_id": "module-root", "root": ".",
                    "evidence": ["unassigned-root-files"], "confidence": "LOW",
                    "discovery_basis": "directory-heuristic",
                }
                assignments[selected] = []
        assignments[selected].append(path)
    modules: list[dict[str, Any]] = []
    for root in sorted(candidates):
        item = dict(candidates[root])
        item["file_count"] = len(assignments.get(root, []))
        item["assigned_files"] = assignments.get(root, [])
        modules.append(item)
    return modules


def _module_id(root: str) -> str:
    if root == ".":
        return "module-root"
    normalized = re.sub(r"[^a-z0-9]+", "-", root.lower()).strip("-")
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:8]
    return f"module-{normalized[:40]}-{digest}"


def validate_snapshot_unchanged(
    root: Path,
    snapshot: dict[str, Any],
    inventory: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any] | None]:
    """Recompute immutable inputs. Any target, manifest, or worktree drift is stale."""
    reasons: list[str] = []
    current_inventory: dict[str, Any] | None = None
    if snapshot.get("snapshot_kind") == "GIT_COMMIT":
        requested = str(snapshot.get("requested_target", ""))
        try:
            current_target = resolve_commit(root, requested)
        except ValueError as exc:
            return False, [f"target-resolution-drift:{exc}"], None
        if current_target != snapshot.get("target_commit"):
            reasons.append("target-ref-drift")
        current_inventory = inventory_git_target(root, snapshot)
        if current_inventory.get("manifest_fingerprint") != inventory.get("manifest_fingerprint"):
            reasons.append("target-manifest-drift")
        current_worktree = _worktree_status(root)
        prior = snapshot.get("working_tree", {})
        if current_worktree.get("fingerprint") != prior.get("fingerprint"):
            reasons.append("working-tree-drift")
    elif snapshot.get("snapshot_kind") == "WORKTREE_SNAPSHOT":
        _, current_inventory = capture_worktree_snapshot(root, explicit=True)
        if current_inventory.get("manifest_fingerprint") != inventory.get("manifest_fingerprint"):
            reasons.append("worktree-manifest-drift")
    else:
        reasons.append("unknown-snapshot-kind")
    return not reasons, reasons, current_inventory
