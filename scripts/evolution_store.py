#!/usr/bin/env python3
"""Fail-closed, project-local persistence primitives for Evolution Core."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from state_io import utc_now
from project_layout import control_path, control_relative, control_root


GENERATOR_VERSION = "3.0.0"
POLICY_VERSION = "evolution-1.0.0"
SCHEMA_VERSION = 1
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_LEDGER_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_LEDGER_RECORDS = 100_000
EVOLUTION_REL = Path(".dingxinglizi/evolution")
PROTECTED_INVARIANTS = sorted([
    "single_orchestrator", "worker_non_delegation", "development_qa_separation",
    "project_docs_source_of_truth", "no_silent_assumptions", "no_fake_evidence",
    "least_privilege", "external_action_authorization", "candidate_non_execution",
    "formal_eval_isolation", "stage_gate_non_weakening", "acceptance_non_weakening",
    "release_gate_non_weakening", "evolution_policy_non_self_modification",
])


class EvolutionBlocked(RuntimeError):
    """A valid request that must fail closed without being a user-argument error."""

    def __init__(self, reason_code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {"status": "BLOCKED", "reason_code": self.reason_code, "message": self.message, **self.details}


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(text: str, source: str) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise EvolutionBlocked("CORRUPT_ARTIFACT", f"Invalid strict JSON in {source}: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_utc_timestamp(value: Any, label: str, *, reason_code: str = "CORRUPT_ARTIFACT") -> None:
    """Require parseable ISO-8601 with an explicit zero UTC offset."""
    if not isinstance(value, str) or not value:
        raise EvolutionBlocked(reason_code, f"{label} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise EvolutionBlocked(reason_code, f"{label} is not a parseable ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EvolutionBlocked(reason_code, f"{label} must include an explicit UTC offset of zero")


def deterministic_id(prefix: str, digest: str) -> str:
    return f"{prefix}-{digest[:20].upper()}"


def require_exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    actual = set(value)
    if actual != keys:
        missing, unknown = sorted(keys - actual), sorted(actual - keys)
        raise EvolutionBlocked("CORRUPT_ARTIFACT", f"{label} keys are invalid", missing=missing, unknown=unknown)


def _lstat_chain(root: Path, relative: Path, *, require_file: bool = True) -> tuple[Path, os.stat_result]:
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"Path must be a non-empty project-relative path without traversal: {relative}")
    base = root.resolve()
    current = base
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            raise ValueError(f"Path does not exist: {relative}") from None
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Symlink paths are forbidden: {relative}")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Path parent is not a directory: {relative}")
    resolved = current.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {relative}") from exc
    if require_file and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise ValueError(f"Path must be an ordinary, singly-linked file: {relative}")
    return resolved, info


def strict_file(root: Path, relative: str | Path, *, max_bytes: int = MAX_JSON_BYTES) -> tuple[Path, bytes]:
    rel = Path(relative)
    path, before = _lstat_chain(root, rel)
    if before.st_size > max_bytes:
        raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"File exceeds size limit: {rel}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        signature = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns)
        if signature(before) != signature(opened):
            raise EvolutionBlocked("BLOCKED_SOURCE_CHANGED", f"Source changed before read: {rel}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"File exceeds size limit: {rel}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if signature(opened) != signature(after):
            raise EvolutionBlocked("BLOCKED_SOURCE_CHANGED", f"Source changed during read: {rel}")
        return path, b"".join(chunks)
    finally:
        os.close(descriptor)


def stable_hash_file(root: Path, relative: str | Path, *, max_bytes: int) -> tuple[str, int]:
    """Hash an ordinary project file without loading it into memory or accepting races."""
    rel = Path(relative)
    path, before = _lstat_chain(root, rel)
    if before.st_size > max_bytes:
        raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"File exceeds size limit: {rel}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    total = 0
    try:
        opened = os.fstat(descriptor)
        signature = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns)
        if signature(before) != signature(opened):
            raise EvolutionBlocked("BLOCKED_SOURCE_CHANGED", f"Source changed before hashing: {rel}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"File exceeds size limit: {rel}")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if signature(opened) != signature(after):
            raise EvolutionBlocked("BLOCKED_SOURCE_CHANGED", f"Source changed during hashing: {rel}")
    finally:
        os.close(descriptor)
    return digest.hexdigest(), total


def load_json_file(root: Path, relative: str | Path, *, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    _, raw = strict_file(root, relative, max_bytes=max_bytes)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvolutionBlocked("CORRUPT_ARTIFACT", f"JSON is not UTF-8: {relative}") from exc
    value = parse_json(text, str(relative))
    if not isinstance(value, dict):
        raise EvolutionBlocked("CORRUPT_ARTIFACT", f"JSON root must be an object: {relative}")
    return value


def load_strict_jsonl(path: Path, validator: Callable[[dict[str, Any]], None], label: str) -> list[dict[str, Any]]:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise EvolutionBlocked("CORRUPT_LEDGER", f"Missing ledger: {path.name}") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise EvolutionBlocked("CORRUPT_LEDGER", f"Ledger is not an ordinary singly-linked file: {path.name}")
    if info.st_size > MAX_LEDGER_BYTES:
        raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"Ledger exceeds 32 MiB: {path.name}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        signature = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns)
        if signature(info) != signature(opened):
            raise EvolutionBlocked("BLOCKED_SOURCE_CHANGED", f"Ledger changed before read: {path.name}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_LEDGER_BYTES:
                raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"Ledger exceeds 32 MiB: {path.name}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if signature(opened) != signature(after):
            raise EvolutionBlocked("BLOCKED_SOURCE_CHANGED", f"Ledger changed during read: {path.name}")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise EvolutionBlocked("CORRUPT_LEDGER", f"Ledger has a truncated final line: {path.name}")
    lines = raw.splitlines()
    if len(lines) > MAX_LEDGER_RECORDS:
        raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"Ledger has too many records: {path.name}")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    digests: set[str] = set()
    for number, raw_line in enumerate(lines, 1):
        if not raw_line or len(raw_line) > MAX_LINE_BYTES:
            raise EvolutionBlocked("CORRUPT_LEDGER", f"Invalid line size in {path.name}:{number}")
        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvolutionBlocked("CORRUPT_LEDGER", f"Invalid UTF-8 in {path.name}:{number}") from exc
        try:
            value = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise EvolutionBlocked("CORRUPT_LEDGER", f"Invalid JSON in {path.name}:{number}: {exc}") from exc
        if not isinstance(value, dict):
            raise EvolutionBlocked("CORRUPT_LEDGER", f"Non-object record in {path.name}:{number}")
        try:
            validator(value)
        except EvolutionBlocked as exc:
            raise EvolutionBlocked("CORRUPT_LEDGER", f"Invalid {label} at {path.name}:{number}: {exc.message}") from exc
        except (TypeError, KeyError, ValueError) as exc:
            raise EvolutionBlocked("CORRUPT_LEDGER", f"Invalid nested {label} type at {path.name}:{number}: {exc}") from exc
        record_id = str(value.get("outcome_id") or value.get("feedback_id") or "")
        digest = str(value.get("fingerprint") or "")
        if record_id in ids or digest in digests:
            raise EvolutionBlocked("CORRUPT_LEDGER", f"Duplicate ID or fingerprint in {path.name}:{number}")
        ids.add(record_id)
        digests.add(digest)
        result.append(value)
    return result


def _atomic_text(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary: Path | None = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        temporary = Path(name)
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def atomic_json(path: Path, value: Any) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")


def atomic_append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    existing = path.read_bytes() if path.exists() else b""
    addition = b"".join((canonical_json(item) + "\n").encode("utf-8") for item in records)
    if len(existing) + len(addition) > MAX_LEDGER_BYTES:
        raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"Ledger would exceed 32 MiB: {path.name}")
    if (existing.count(b"\n") if existing else 0) + len(records) > MAX_LEDGER_RECORDS:
        raise EvolutionBlocked("RESOURCE_LIMIT_EXCEEDED", f"Ledger would exceed 100,000 records: {path.name}")
    _atomic_text(path, (existing + addition).decode("utf-8"))


def validate_project_root(root: Path) -> Path:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Project root is not an existing directory: {root}")
    status = load_json_file(root, Path("docs/project-status.json"))
    if not isinstance(status.get("schema_version"), int) or not isinstance(status.get("current_state"), str):
        raise ValueError("Project status does not match the initialized v2 contract")
    role_plan_path = control_path(root, "orchestration/role-plan.json")
    role_plan = load_json_file(root, role_plan_path.relative_to(root.resolve()))
    # The v2.0 role-plan contract is versioned by policy_version rather than schema_version.
    if role_plan.get("policy_version") not in {"1.2.0", "1.3.0"} or role_plan.get("status") not in {"NOT_ROUTED", "ROUTED"}:
        raise ValueError("Role plan does not match the initialized v2 contract")
    return root


def evolution_root(root: Path) -> Path:
    return control_path(root, "evolution")


def evolution_rel(root: Path) -> Path:
    return control_relative(root, "evolution")


def _manifest_value() -> dict[str, Any]:
    instance = str(uuid.uuid4())
    return {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "policy_version": POLICY_VERSION,
        "project_instance_id": instance,
        "project_fingerprint": hashlib.sha256(instance.encode("utf-8")).hexdigest(),
        "initialized_at": utc_now(),
        "protected_invariants": PROTECTED_INVARIANTS,
    }


def validate_manifest(value: dict[str, Any]) -> None:
    keys = {"schema_version", "generator_version", "policy_version", "project_instance_id", "project_fingerprint", "initialized_at", "protected_invariants"}
    if set(value) != keys:
        raise EvolutionBlocked("CORRUPT_MANIFEST", "Manifest keys are invalid")
    if value["schema_version"] != 1:
        raise EvolutionBlocked("UNSUPPORTED_SCHEMA", "Unsupported Evolution manifest schema")
    if value["generator_version"] != GENERATOR_VERSION or value["policy_version"] != POLICY_VERSION:
        raise EvolutionBlocked("UNSUPPORTED_SCHEMA", "Unsupported Evolution generator or policy version")
    try:
        uuid.UUID(value["project_instance_id"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise EvolutionBlocked("CORRUPT_MANIFEST", "Invalid project_instance_id") from exc
    expected = hashlib.sha256(value["project_instance_id"].encode("utf-8")).hexdigest()
    if value["project_fingerprint"] != expected or value["protected_invariants"] != PROTECTED_INVARIANTS:
        raise EvolutionBlocked("CORRUPT_MANIFEST", "Manifest fingerprint or protected registry mismatch")
    require_utc_timestamp(value["initialized_at"], "Manifest initialized_at", reason_code="CORRUPT_MANIFEST")


def load_manifest(root: Path) -> dict[str, Any]:
    workspace = evolution_root(root)
    if not workspace.exists():
        raise EvolutionBlocked("NOT_INITIALIZED", "Evolution workspace is not initialized")
    if not workspace.is_dir() or workspace.is_symlink():
        raise EvolutionBlocked("BLOCKED_PARTIAL_INIT", "Evolution workspace path is invalid")
    manifest = workspace / "manifest.json"
    if not manifest.is_file():
        raise EvolutionBlocked("BLOCKED_PARTIAL_INIT", "Evolution workspace has no commit-marker manifest")
    try:
        value = load_json_file(root, evolution_rel(root) / "manifest.json")
        validate_manifest(value)
    except EvolutionBlocked as exc:
        if exc.reason_code == "CORRUPT_ARTIFACT":
            raise EvolutionBlocked("CORRUPT_MANIFEST", exc.message) from exc
        raise
    for name in ("outcomes.jsonl", "feedback.jsonl"):
        if not (workspace / name).is_file():
            raise EvolutionBlocked("BLOCKED_PARTIAL_INIT", f"Evolution workspace is missing {name}")
    for name in ("retrospectives", "candidates", "eval-candidates"):
        path = workspace / name
        if not path.is_dir() or path.is_symlink():
            raise EvolutionBlocked("BLOCKED_PARTIAL_INIT", f"Evolution workspace directory is invalid: {name}")
    return value


def _lock_payload(operation: str) -> dict[str, Any]:
    return {"schema_version": 1, "operation": operation, "pid": os.getpid(), "hostname": socket.gethostname(), "created_at": utc_now(), "nonce": uuid.uuid4().hex}


@contextmanager
def exclusive_lock(path: Path, operation: str) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise EvolutionBlocked("BLOCKED_LOCKED", f"Evolution operation lock already exists: {path.name}") from None
    try:
        payload = (canonical_json(_lock_payload(operation)) + "\n").encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def initialize_workspace(root: Path) -> dict[str, Any]:
    root = validate_project_root(root)
    control = control_root(root)
    control.mkdir(exist_ok=True)
    workspace = evolution_root(root)
    lock = control / ".evolution-init-lock"
    with exclusive_lock(lock, "init"):
        if workspace.exists():
            manifest = load_manifest(root)
            return {"status": "ALREADY_INITIALIZED", "reason_code": "OK", "project_fingerprint": manifest["project_fingerprint"], "workspace": evolution_rel(root).as_posix(), **git_exposure(root)}
        staging = control / f".evolution-staging-{uuid.uuid4().hex}"
        try:
            staging.mkdir(mode=0o700)
            for directory in ("retrospectives", "candidates", "eval-candidates"):
                (staging / directory).mkdir(mode=0o700)
            for ledger in ("outcomes.jsonl", "feedback.jsonl"):
                fd = os.open(staging / ledger, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            manifest = _manifest_value()
            atomic_json(staging / "manifest.json", manifest)
            os.replace(staging, workspace)
            staging = Path()
        finally:
            if staging != Path() and staging.exists():
                shutil.rmtree(staging)
        return {"status": "INITIALIZED", "reason_code": "OK", "project_fingerprint": manifest["project_fingerprint"], "workspace": evolution_rel(root).as_posix(), **git_exposure(root)}


def git_exposure(root: Path) -> dict[str, Any]:
    try:
        probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"git_state": "INDETERMINATE", "git_reason_code": "GIT_EXPOSURE_RISK"}
    if probe.returncode != 0:
        if "not a git repository" in probe.stderr.lower():
            return {"git_state": "NOT_A_REPOSITORY", "git_reason_code": "OK"}
        return {"git_state": "INDETERMINATE", "git_reason_code": "GIT_EXPOSURE_RISK"}
    try:
        relative = evolution_rel(root).as_posix()
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", f"{relative}/manifest.json"], capture_output=True, timeout=5, check=False)
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--", relative], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"git_state": "INDETERMINATE", "git_reason_code": "GIT_EXPOSURE_RISK"}
    if ignored.returncode not in (0, 1) or tracked.returncode != 0:
        return {"git_state": "INDETERMINATE", "git_reason_code": "GIT_EXPOSURE_RISK"}
    tracked_paths = [line for line in tracked.stdout.splitlines() if line.strip()]
    if ignored.returncode != 0:
        return {"git_state": "UNIGNORED", "git_reason_code": "GIT_EXPOSURE_RISK", "tracked_paths": tracked_paths}
    if tracked_paths:
        return {"git_state": "TRACKED", "git_reason_code": "GIT_EXPOSURE_RISK", "tracked_paths": tracked_paths}
    return {"git_state": "SAFE", "git_reason_code": "OK", "tracked_paths": []}


def require_git_safe(root: Path) -> None:
    state = git_exposure(root)
    if state["git_reason_code"] != "OK":
        raise EvolutionBlocked("GIT_EXPOSURE_RISK", "Evolution writes require the active control-plane evolution directory to be ignored and untracked", **state)
