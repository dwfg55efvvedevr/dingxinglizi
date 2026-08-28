#!/usr/bin/env python3
"""Platform adapters, runtime evidence, and model capability resolution.

The portable core never assumes that an installed executable is authenticated,
that a configured model is available, or that a rendered profile was launched.
Those are separate evidence claims represented in the runtime manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SKILL_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_ASSETS = SKILL_ROOT / "assets" / "platforms"
SKILL_INSTALL_NAME = "software-project-orchestrator"
PLATFORM_CHOICES: Tuple[str, ...] = ("codex", "cursor", "claude-code", "opencode")
OPENCODE_SCHEMAS: Tuple[str, ...] = ("auto", "v1", "v2")
CAPABILITY_TIERS: Tuple[str, ...] = ("ECONOMY", "STANDARD", "ADVANCED", "EXPERT", "EXCEPTIONAL")
REASONING_LEVELS: Tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
HIGH_RISK_FLAGS = {
    "security", "privacy", "financial", "payment", "compliance", "production",
    "migration", "permissions", "irreversible", "ai_safety", "regulated",
}
RUNTIME_EXECUTABLES: Mapping[str, Tuple[str, ...]] = {
    "codex": ("codex",),
    "cursor": ("cursor",),
    "claude-code": ("claude",),
    "opencode": ("opencode",),
}
ROLE_CATALOG_PATH = PLATFORM_ASSETS / "common" / "role-catalog.json"
COMMON_PROMPT_PATH = PLATFORM_ASSETS / "common" / "common-prompt.md"
MAX_MANIFEST_AGE = timedelta(hours=24)
MAX_MODEL_INVENTORY_BYTES = 16 * 1024 * 1024
MAX_AGENT_PROFILE_BYTES = 2 * 1024 * 1024
MAX_MODELS = 2_000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("Required JSON file is missing: %s" % path) from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON file %s: %s" % (path, exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object: %s" % path)
    return value


def _lexical_absolute(path_value: Path) -> Path:
    """Return an absolute path without resolving user-controlled path segments."""
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = Path(os.path.abspath(str(path)))
    # macOS exposes these stable system aliases as symlinks. Canonicalize only
    # the known aliases before applying the no-symlink rule to user segments.
    aliases = {Path("/var"): Path("/private/var"), Path("/tmp"): Path("/private/tmp")}
    for alias, canonical in aliases.items():
        try:
            relative = path.relative_to(alias)
        except ValueError:
            continue
        if alias.is_symlink() and alias.resolve() == canonical:
            path = canonical / relative
        break
    return path


def _reject_symlink_ancestors(path: Path, label: str, *, include_leaf: bool = True) -> None:
    current = Path(path.anchor)
    parts = path.parts[1:] if include_leaf else path.parts[1:-1]
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("%s path traverses a symlink: %s" % (label, current))


def _read_ordinary_file(path_value: Path, label: str, *, size_limit: int) -> Tuple[Path, bytes]:
    """Read one ordinary single-link file without following path symlinks."""
    path = _lexical_absolute(path_value)
    _reject_symlink_ancestors(path, label)
    try:
        parent_metadata = os.stat(path.parent, follow_symlinks=False)
        directory_fd = os.open(
            str(path.parent),
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        raise ValueError("%s file is missing: %s" % (label, path)) from None
    try:
        opened_parent = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or (parent_metadata.st_dev, parent_metadata.st_ino)
            != (opened_parent.st_dev, opened_parent.st_ino)
        ):
            raise ValueError("%s parent directory changed during validation" % label)
        try:
            file_fd = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            raise ValueError("%s file is missing: %s" % (label, path)) from None
        except OSError as exc:
            raise ValueError("%s file cannot be opened safely: %s" % (label, path)) from exc
        try:
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("%s must be an ordinary single-link file: %s" % (label, path))
            if before.st_size > size_limit:
                raise ValueError("%s exceeds the size limit" % label)
            chunks = []
            remaining = size_limit + 1
            while remaining > 0:
                chunk = os.read(file_fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(file_fd)
            if len(raw) > size_limit:
                raise ValueError("%s exceeds the size limit" % label)
            if (
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            ):
                raise ValueError("%s changed while it was being read" % label)
            return path, raw
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


def _read_local_input(path_value: Path, label: str) -> Tuple[Path, bytes]:
    return _read_ordinary_file(path_value, label, size_limit=MAX_MODEL_INVENTORY_BYTES)


def _ordinary_directory_under(root_value: Path, path_value: Path, label: str) -> bool:
    """Accept only a real non-symlink directory confined below root."""
    root = _lexical_absolute(root_value)
    path = _lexical_absolute(path_value)
    try:
        path.relative_to(root)
        _reject_symlink_ancestors(path, label)
        metadata = os.stat(path, follow_symlinks=False)
    except (OSError, ValueError):
        return False
    return stat.S_ISDIR(metadata.st_mode)


def platform_spec(platform: str) -> Dict[str, Any]:
    if platform not in PLATFORM_CHOICES:
        raise ValueError("platform must be one of: %s" % ", ".join(PLATFORM_CHOICES))
    spec = _read_json(PLATFORM_ASSETS / platform / "adapter.json")
    if spec.get("platform") != platform or spec.get("schema_version") != 1:
        raise ValueError("Adapter descriptor does not match platform %s" % platform)
    return spec


def load_role_catalog() -> List[Dict[str, Any]]:
    value = _read_json(ROLE_CATALOG_PATH)
    if value.get("schema_version") != 1 or not isinstance(value.get("roles"), list):
        raise ValueError("Unsupported role catalog schema")
    roles = value["roles"]
    seen = set()
    role_ids = set()
    for role in roles:
        if not isinstance(role, dict):
            raise ValueError("Every role catalog entry must be an object")
        role_id = role.get("id")
        if not isinstance(role_id, str) or not role_id or role_id in seen:
            raise ValueError("Role IDs must be unique non-empty strings")
        seen.add(role_id)
        role_ids.add(role_id)
        if role.get("category") not in {"primary", "professional", "worker"}:
            raise ValueError("Unsupported category for role %s" % role_id)
        if not isinstance(role.get("delegates_to"), list):
            raise ValueError("delegates_to must be a list for role %s" % role_id)
        for field in ("display_name", "description", "prompt"):
            if not isinstance(role.get(field), str) or not role[field].strip():
                raise ValueError("Role %s requires %s" % (role_id, field))
    expected_primary = [role["id"] for role in roles if role["category"] == "primary"]
    if expected_primary != ["orchestrator"]:
        raise ValueError("The catalog must contain exactly one primary Orchestrator")
    workers = {role["id"] for role in roles if role["category"] == "worker"}
    professionals = {role["id"] for role in roles if role["category"] == "professional"}
    for role in roles:
        unknown = set(role["delegates_to"]) - role_ids
        if unknown:
            raise ValueError("Role %s delegates to unknown roles: %s" % (role["id"], sorted(unknown)))
        if role["id"] == "orchestrator" and set(role["delegates_to"]) != professionals:
            raise ValueError("Orchestrator must be the sole coordinator of all professional roles")
        if role["id"] == "engineering_lead" and set(role["delegates_to"]) != workers:
            raise ValueError("Engineering Lead may delegate to implementation Workers only")
        if role["id"] not in {"orchestrator", "engineering_lead"} and role["delegates_to"]:
            raise ValueError("Only Orchestrator and Engineering Lead may delegate")
        if role["category"] == "worker" and role["delegates_to"]:
            raise ValueError("Workers may not delegate")
    return roles


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _role_body(role: Mapping[str, Any], common_prompt: str) -> str:
    return (
        common_prompt.rstrip() + "\n\n"
        + "## Role-specific contract\n\n"
        + "Canonical role ID: `%s`.\n\n" % role["id"]
        + str(role["prompt"]).strip() + "\n"
    )


def _host_role_id(role_id: str) -> str:
    return role_id.replace("_", "-")


def _render_codex(role: Mapping[str, Any], body: str) -> str:
    if '"""' in body:
        raise ValueError("Codex prompt contains an unsupported triple-quote sequence")
    return (
        "name = %s\n" % _toml_string(str(role["id"]))
        + "description = %s\n" % _toml_string(str(role["description"]))
        + 'developer_instructions = """\n%s"""\n' % body
    )


def _render_cursor(role: Mapping[str, Any], body: str) -> str:
    return (
        "---\n"
        + "name: %s\n" % _yaml_string(_host_role_id(str(role["id"])))
        + "description: %s\n" % _yaml_string(str(role["description"]))
        + "model: inherit\n"
        + "readonly: %s\n" % ("true" if role["read_only"] else "false")
        + "---\n\n"
        + body
    )


def _render_claude(role: Mapping[str, Any], body: str) -> str:
    lines = [
        "---",
        "name: %s" % _yaml_string(_host_role_id(str(role["id"]))),
        "description: %s" % _yaml_string(str(role["description"])),
        "model: inherit",
    ]
    if role["read_only"]:
        lines.append("permissionMode: plan")
    if not role["delegates_to"]:
        lines.extend(["disallowedTools:", "  - Agent"])
    lines.extend(["---", "", body.rstrip(), ""])
    return "\n".join(lines)


def _render_opencode_v1(role: Mapping[str, Any], body: str) -> str:
    role_id = str(role["id"])
    mode = "primary" if role_id == "orchestrator" else "subagent"
    lines = [
        "---",
        "description: %s" % _yaml_string(str(role["description"])),
        "mode: %s" % mode,
        "permission:",
        "  task:",
        '    "*": deny',
    ]
    for target in role["delegates_to"]:
        lines.append("    %s: allow" % _yaml_string(_host_role_id(str(target))))
    if role["read_only"]:
        lines.extend(["  edit: deny", "  bash: deny"])
    lines.extend(["---", "", body.rstrip(), ""])
    return "\n".join(lines)


def _render_opencode_v2(role: Mapping[str, Any], body: str) -> str:
    """Render OpenCode V2 ordered permission rules.

    V2 renamed the delegation action from ``task`` to ``subagent`` and uses
    an ordered ``permissions`` rule list.  The broad deny comes first and the
    exact allow rules follow because OpenCode V2 applies the last match.
    """
    role_id = str(role["id"])
    mode = "primary" if role_id == "orchestrator" else "subagent"
    lines = [
        "---",
        "description: %s" % _yaml_string(str(role["description"])),
        "mode: %s" % mode,
        "permissions:",
        "  - action: subagent",
        '    resource: "*"',
        "    effect: deny",
    ]
    for target in role["delegates_to"]:
        lines.extend([
            "  - action: subagent",
            "    resource: %s" % _yaml_string(_host_role_id(str(target))),
            "    effect: allow",
        ])
    if role["read_only"]:
        lines.extend([
            "  - action: edit",
            '    resource: "*"',
            "    effect: deny",
            "  - action: shell",
            '    resource: "*"',
            "    effect: deny",
        ])
    lines.extend(["---", "", body.rstrip(), ""])
    return "\n".join(lines)


def _opencode_major(version_output: str) -> Optional[int]:
    match = re.search(r"(?<![A-Za-z0-9])v?(\d+)\.\d+(?:\.\d+)?", version_output)
    return int(match.group(1)) if match else None


def resolve_opencode_schema(requested: str = "auto") -> str:
    """Resolve OpenCode's incompatible V1/V2 Agent configuration schema.

    Explicit selection supports deterministic offline generation.  Automatic
    selection is allowed only when an installed runtime returns a parseable
    major version; unknown and future major versions fail closed.
    """
    if requested not in OPENCODE_SCHEMAS:
        raise ValueError("opencode schema must be one of: %s" % ", ".join(OPENCODE_SCHEMAS))
    probe = _runtime_probe("opencode")
    major = _opencode_major(str(probe.get("version", "")))
    if requested != "auto":
        if major not in {None, 1, 2}:
            raise ValueError(
                "OpenCode major version %d is not supported by the v1/v2 adapter" % major
            )
        if major in {1, 2} and requested != "v%d" % major:
            raise ValueError(
                "OpenCode runtime is %d.x but --opencode-schema %s was requested"
                % (major, requested)
            )
        return requested
    if major == 1:
        return "v1"
    if major == 2:
        return "v2"
    if major is not None:
        raise ValueError(
            "OpenCode major version %d is not supported; pass a supported adapter only after verifying its schema"
            % major
        )
    raise ValueError(
        "OpenCode schema cannot be inferred from the installed runtime; "
        "pass --opencode-schema v1 or --opencode-schema v2 explicitly"
    )


def _selected_opencode_schema(platform: str, requested: str) -> str:
    if platform != "opencode":
        if requested != "auto":
            raise ValueError("--opencode-schema applies only when --platform opencode")
        return ""
    return resolve_opencode_schema(requested)


def render_adapter_files(platform: str, *, opencode_schema: str = "auto") -> Dict[Path, str]:
    """Return relative native Agent paths and deterministic contents."""
    spec = platform_spec(platform)
    selected_opencode_schema = _selected_opencode_schema(platform, opencode_schema)
    common_prompt = COMMON_PROMPT_PATH.read_text(encoding="utf-8")
    roles = load_role_catalog()
    rendered: Dict[Path, str] = {}
    agent_dir = Path(str(spec["project_agent_directory"]))
    for role in roles:
        body = _role_body(role, common_prompt)
        if platform == "codex":
            filename = "%s.toml" % role["id"]
            content = _render_codex(role, body)
        elif platform == "cursor":
            filename = "%s.md" % _host_role_id(str(role["id"]))
            content = _render_cursor(role, body)
        elif platform == "claude-code":
            filename = "%s.md" % _host_role_id(str(role["id"]))
            content = _render_claude(role, body)
        else:
            filename = "%s.md" % _host_role_id(str(role["id"]))
            content = (
                _render_opencode_v1(role, body)
                if selected_opencode_schema == "v1"
                else _render_opencode_v2(role, body)
            )
        rendered[agent_dir / filename] = content
    return rendered


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def safe_write_target(root: Path, target: Path) -> bool:
    """Reject symlink traversal and lexical escapes below an explicit root."""
    try:
        relative = target.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    return True


def _write_rendered(root: Path, files: Mapping[Path, str], update: bool) -> Dict[str, Any]:
    conflicts = []
    unchanged = []
    creates = []
    updates = []
    for relative, content in sorted(files.items(), key=lambda item: str(item[0])):
        target = root / relative
        if not safe_write_target(root, target):
            conflicts.append(str(target))
            continue
        if not target.exists():
            creates.append((target, content))
            continue
        if not target.is_file():
            conflicts.append(str(target))
            continue
        existing = target.read_text(encoding="utf-8")
        if existing == content:
            unchanged.append(str(target))
        elif update:
            updates.append((target, content))
        else:
            conflicts.append(str(target))
    if conflicts:
        return {
            "status": "BLOCKED_CONFLICT",
            "created": [],
            "updated": [],
            "unchanged": unchanged,
            "conflicts": conflicts,
        }
    for target, content in creates + updates:
        _atomic_write(target, content)
    return {
        "status": "RENDERED",
        "created": [str(path) for path, _ in creates],
        "updated": [str(path) for path, _ in updates],
        "unchanged": unchanged,
        "conflicts": [],
    }


def render_project_adapter(
    project_root: Path,
    platform: str,
    *,
    update: bool = False,
    opencode_schema: str = "auto",
) -> Dict[str, Any]:
    """Render only the selected platform's native project Agent profiles."""
    root = Path(project_root).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ValueError("Project path is not a directory: %s" % root)
    selected_schema = _selected_opencode_schema(platform, opencode_schema)
    result = _write_rendered(
        root,
        render_adapter_files(platform, opencode_schema=selected_schema or "auto"),
        update,
    )
    result.update({"platform": platform, "scope": "project", "root": str(root)})
    if selected_schema:
        result["adapter_schema"] = selected_schema
    return result


def render_user_adapter(
    home_root: Path,
    platform: str,
    *,
    update: bool = False,
    opencode_schema: str = "auto",
) -> Dict[str, Any]:
    """Render native user profiles below an explicitly supplied home root."""
    home = Path(home_root).expanduser().resolve()
    spec = platform_spec(platform)
    project_prefix = Path(str(spec["project_agent_directory"]))
    user_prefix = Path(str(spec["user_agent_directory"]))
    selected_schema = _selected_opencode_schema(platform, opencode_schema)
    files = {
        user_prefix / relative.relative_to(project_prefix): content
        for relative, content in render_adapter_files(
            platform, opencode_schema=selected_schema or "auto"
        ).items()
    }
    result = _write_rendered(home, files, update)
    result.update({"platform": platform, "scope": "user", "root": str(home)})
    if selected_schema:
        result["adapter_schema"] = selected_schema
    return result


def _runtime_probe(platform: str) -> Dict[str, Any]:
    candidates = RUNTIME_EXECUTABLES[platform]
    executable = ""
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            executable = str(Path(found).resolve())
            break
    if not executable:
        return {
            "status": "NOT_FOUND",
            "executable": "",
            "version": "",
            "evidence_source": "PATH lookup",
        }
    try:
        completed = subprocess.run(
            [executable, "--version"], check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5,
        )
        output = completed.stdout.strip().replace("\x00", "")[:500]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "EXECUTABLE_FOUND_VERSION_UNVERIFIED",
            "executable": executable,
            "version": "",
            "evidence_source": "PATH lookup; version probe failed: %s" % type(exc).__name__,
        }
    return {
        "status": "VERIFIED" if completed.returncode == 0 and output else "EXECUTABLE_FOUND_VERSION_UNVERIFIED",
        "executable": executable,
        "version": output if completed.returncode == 0 else "",
        "evidence_source": "%s --version (exit %d)" % (executable, completed.returncode),
    }


def detect_platforms(preferred: Optional[str] = None) -> Dict[str, Any]:
    if preferred is not None and preferred not in PLATFORM_CHOICES:
        raise ValueError("platform must be one of: %s" % ", ".join(PLATFORM_CHOICES))
    probes = {platform: _runtime_probe(platform) for platform in PLATFORM_CHOICES}
    found = [platform for platform, probe in probes.items() if probe["status"] != "NOT_FOUND"]
    selected = ""
    reason = "no supported runtime executable was found"
    if preferred:
        selected = preferred if preferred in found else ""
        reason = "explicit platform detected" if selected else "explicit platform executable not found"
    elif len(found) == 1:
        selected = found[0]
        reason = "only one supported runtime executable was found"
    elif len(found) > 1:
        reason = "multiple runtimes found; select a platform explicitly"
    return {
        "schema_version": 1,
        "detected_at": utc_now(),
        "selected_platform": selected,
        "selection_reason": reason,
        "platforms": probes,
    }


def _normalize_models(value: Any, evidence_verified: bool) -> List[Dict[str, Any]]:
    models = value.get("models") if isinstance(value, dict) else value
    if not isinstance(models, list):
        raise ValueError("Model inventory must be a list or an object containing a models list")
    if len(models) > MAX_MODELS:
        raise ValueError("Model inventory exceeds the model-count limit")
    normalized = []
    seen = set()
    for item in models:
        if not isinstance(item, dict):
            raise ValueError("Every model inventory entry must be an object")
        model_id = item.get("id")
        provider = item.get("provider", "")
        tier = str(item.get("capability_tier", "")).upper()
        efforts = item.get("reasoning_efforts", [])
        if (
            not isinstance(model_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,499}", model_id)
            or model_id in seen
        ):
            raise ValueError("Model IDs must be unique, non-empty, normalized identifiers")
        if (
            not isinstance(provider, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,199}", provider)
        ):
            raise ValueError("provider must be a non-empty normalized identifier for model %s" % model_id)
        if tier not in CAPABILITY_TIERS:
            raise ValueError("Invalid capability_tier for model %s" % model_id)
        if not isinstance(efforts, list) or any(effort not in REASONING_LEVELS for effort in efforts):
            raise ValueError("Invalid reasoning_efforts for model %s" % model_id)
        seen.add(model_id)
        normalized.append({
            "id": model_id,
            "provider": provider,
            "capability_tier": tier,
            "reasoning_efforts": list(dict.fromkeys(efforts)),
            "evidence_status": "VERIFIED" if evidence_verified else "DECLARED_UNVERIFIED",
        })
    return normalized


def _execution_receipt_fingerprint(receipt: Mapping[str, Any]) -> str:
    value = dict(receipt)
    value.pop("receipt_fingerprint", None)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _sha256_bytes(payload)


def _valid_execution_receipt(
    value: Any,
    platform: str,
    models: Sequence[Mapping[str, Any]],
    probe: Mapping[str, Any],
) -> bool:
    expected_fields = {
        "schema_version", "type", "platform", "task_id", "agent",
        "actual_provider", "actual_model", "actual_reasoning", "runtime_version",
        "evidence_source", "recorded_at", "attestation", "receipt_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return False
    if value.get("schema_version") != 1 or value.get("type") != "platform_execution_receipt":
        return False
    if value.get("platform") != platform or value.get("attestation") != "VERIFIED_RUNTIME":
        return False
    if value.get("agent") not in {role["id"] for role in load_role_catalog()}:
        return False
    if not isinstance(value.get("task_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value["task_id"]):
        return False
    for field in ("actual_provider", "actual_model", "runtime_version", "evidence_source"):
        if not isinstance(value.get(field), str) or not value[field].strip() or len(value[field]) > 500:
            return False
    if value.get("actual_reasoning") not in REASONING_LEVELS:
        return False
    if not isinstance(value.get("recorded_at"), str) or not value["recorded_at"].endswith("Z"):
        return False
    try:
        recorded_at = datetime.fromisoformat(value["recorded_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    if recorded_at.utcoffset() != timedelta(0) or recorded_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        return False
    if value.get("receipt_fingerprint") != _execution_receipt_fingerprint(value):
        return False
    if probe.get("status") != "VERIFIED" or value.get("runtime_version") != probe.get("version"):
        return False
    matching_models = [
        model for model in models
        if model.get("evidence_status") == "VERIFIED"
        and model.get("id") == value.get("actual_model")
        and model.get("provider") == value.get("actual_provider")
    ]
    return bool(
        matching_models
        and value.get("actual_reasoning") in matching_models[0].get("reasoning_efforts", [])
    )


def _dispatch_consistent(manifest: Mapping[str, Any]) -> bool:
    dispatch = manifest.get("dispatch_evidence", {})
    facts = dispatch.get("facts", {}) if isinstance(dispatch, Mapping) else {}
    runtime = manifest.get("runtime", {})
    inventory = manifest.get("model_inventory", {})
    models = inventory.get("models", []) if isinstance(inventory, Mapping) else []
    if (
        not isinstance(dispatch, Mapping)
        or dispatch.get("status") != "VERIFIED"
        or dispatch.get("consistency") != "CROSS_CHECKED"
        or not isinstance(facts, Mapping)
        or set(facts) != {
            "task_id", "agent", "actual_provider", "actual_model",
            "actual_reasoning", "runtime_version", "recorded_at", "evidence_source",
        }
        or runtime.get("status") != "VERIFIED"
        or facts.get("runtime_version") != runtime.get("version")
        or inventory.get("evidence", {}).get("status") != "VERIFIED"
    ):
        return False
    return any(
        isinstance(model, Mapping)
        and model.get("evidence_status") == "VERIFIED"
        and model.get("id") == facts.get("actual_model")
        and model.get("provider") == facts.get("actual_provider")
        and isinstance(model.get("reasoning_efforts"), list)
        and facts.get("actual_reasoning") in model.get("reasoning_efforts", [])
        for model in models
    )


def build_runtime_manifest(
    platform: str,
    *,
    models_file: Optional[Path] = None,
    evidence_source: str = "",
    models_verified: bool = False,
    dispatch_receipt: Optional[Path] = None,
) -> Dict[str, Any]:
    """Capture local executable evidence and an explicitly sourced model inventory.

    `models_verified` is accepted only with an existing inventory file and a named
    evidence source. It attests the inventory source, not an actual launch.
    """
    platform_spec(platform)
    probe = _runtime_probe(platform)
    models: List[Dict[str, Any]] = []
    inventory_evidence: Dict[str, Any] = {
        "status": "NOT_PROVIDED",
        "source": "",
        "sha256": "",
    }
    if models_verified and (models_file is None or not evidence_source.strip()):
        raise ValueError("--models-verified requires --models-file and --evidence-source")
    if models_file is not None:
        path, raw = _read_local_input(models_file, "Model inventory")
        try:
            source_value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid model inventory %s: %s" % (path, exc)) from exc
        models = _normalize_models(source_value, models_verified)
        inventory_evidence = {
            "status": "VERIFIED" if models_verified else "DECLARED_UNVERIFIED",
            "source": evidence_source.strip() or str(path),
            "path": str(path),
            "sha256": _sha256_bytes(raw),
        }
    dispatch: Dict[str, Any] = {
        "status": "NOT_PROVIDED", "path": "", "sha256": "",
        "consistency": "NOT_CHECKED", "facts": {},
    }
    if dispatch_receipt is not None:
        receipt_path, raw_receipt = _read_local_input(dispatch_receipt, "Dispatch receipt")
        try:
            receipt_value = json.loads(raw_receipt.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid dispatch receipt %s: %s" % (receipt_path, exc)) from exc
        valid_receipt = _valid_execution_receipt(receipt_value, platform, models, probe)
        fact_fields = (
            "task_id", "agent", "actual_provider", "actual_model", "actual_reasoning",
            "runtime_version", "recorded_at", "evidence_source",
        )
        dispatch = {
            "status": "VERIFIED" if valid_receipt else "UNVERIFIED",
            "path": str(receipt_path),
            "sha256": _sha256_bytes(raw_receipt),
            "consistency": "CROSS_CHECKED" if valid_receipt else "FAILED",
            "facts": {field: receipt_value[field] for field in fact_fields} if valid_receipt else {},
        }
    status = "UNAVAILABLE"
    if probe["status"] == "VERIFIED":
        status = "VERIFIED_WITH_MODEL_INVENTORY" if inventory_evidence["status"] == "VERIFIED" else "RUNTIME_VERIFIED_MODELS_UNVERIFIED"
    elif probe["status"] != "NOT_FOUND":
        status = "PARTIAL"
    return {
        "schema_version": 1,
        "platform": platform,
        "captured_at": utc_now(),
        "status": status,
        "runtime": probe,
        "model_inventory": {
            "evidence": inventory_evidence,
            "models": models,
        },
        "dispatch_evidence": dispatch,
        "claims": {
            "authenticated": "UNKNOWN",
            "native_dispatch_completed": dispatch["status"] == "VERIFIED",
            "actual_model_used": "ATTESTED_BY_RECEIPT" if dispatch["status"] == "VERIFIED" else "UNKNOWN",
        },
    }


def _utc_manifest_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Runtime manifest %s must be a UTC Z timestamp" % field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Runtime manifest %s is invalid" % field) from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Runtime manifest %s must use UTC" % field)
    return parsed


def _read_bound_evidence(path_value: Any, expected_sha256: Any, label: str) -> Tuple[Path, bytes]:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("Runtime manifest %s evidence path is missing" % label)
    path = Path(path_value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Runtime manifest %s evidence path must be absolute and normalized" % label)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError("Runtime manifest %s evidence path traverses a symlink" % label)
    try:
        metadata = path.stat()
    except FileNotFoundError:
        raise ValueError("Runtime manifest %s evidence file is missing" % label) from None
    if not path.is_file() or metadata.st_nlink != 1:
        raise ValueError("Runtime manifest %s evidence must be an ordinary single-link file" % label)
    if metadata.st_size > MAX_MODEL_INVENTORY_BYTES:
        raise ValueError("Runtime manifest %s evidence exceeds the size limit" % label)
    raw = path.read_bytes()
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Runtime manifest %s evidence SHA-256 is invalid" % label)
    if _sha256_bytes(raw) != expected_sha256:
        raise ValueError("Runtime manifest %s evidence SHA-256 does not match" % label)
    return path, raw


def validate_runtime_manifest(manifest: Mapping[str, Any]) -> None:
    expected_top = {
        "schema_version", "platform", "captured_at", "status", "runtime",
        "model_inventory", "dispatch_evidence", "claims",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != expected_top:
        raise ValueError("Runtime manifest has unsupported or missing top-level fields")
    platform = manifest.get("platform")
    if manifest.get("schema_version") != 1 or platform not in PLATFORM_CHOICES:
        raise ValueError("Unsupported runtime manifest schema or platform")
    captured_at = _utc_manifest_time(manifest.get("captured_at"), "captured_at")
    now = datetime.now(timezone.utc)
    if captured_at > now + timedelta(minutes=5):
        raise ValueError("Runtime manifest captured_at is in the future")
    if now - captured_at > MAX_MANIFEST_AGE:
        raise ValueError("Runtime manifest is stale; capture fresh runtime evidence")

    runtime = manifest.get("runtime")
    runtime_fields = {"status", "executable", "version", "evidence_source"}
    if not isinstance(runtime, Mapping) or set(runtime) != runtime_fields:
        raise ValueError("Runtime manifest runtime probe has invalid fields")
    if runtime.get("status") not in {
        "NOT_FOUND", "EXECUTABLE_FOUND_VERSION_UNVERIFIED", "VERIFIED",
    } or any(not isinstance(runtime.get(field), str) for field in runtime_fields):
        raise ValueError("Runtime manifest runtime probe has invalid types or status")
    current_probe = _runtime_probe(str(platform))
    for field in ("status", "executable", "version"):
        if runtime.get(field) != current_probe.get(field):
            raise ValueError("Runtime manifest probe no longer matches current host: %s" % field)

    inventory = manifest.get("model_inventory")
    if not isinstance(inventory, Mapping) or set(inventory) != {"evidence", "models"}:
        raise ValueError("Runtime manifest model_inventory is invalid")
    evidence = inventory.get("evidence")
    models = inventory.get("models")
    if not isinstance(evidence, Mapping) or not isinstance(models, list) or len(models) > MAX_MODELS:
        raise ValueError("Runtime manifest model inventory evidence or model count is invalid")
    evidence_status = evidence.get("status")
    if evidence_status == "NOT_PROVIDED":
        if set(evidence) != {"status", "source", "sha256"} or evidence != {
            "status": "NOT_PROVIDED", "source": "", "sha256": "",
        } or models:
            raise ValueError("Runtime manifest NOT_PROVIDED inventory is inconsistent")
    elif evidence_status in {"DECLARED_UNVERIFIED", "VERIFIED"}:
        if set(evidence) != {"status", "source", "path", "sha256"}:
            raise ValueError("Runtime manifest model inventory evidence fields are invalid")
        if not isinstance(evidence.get("source"), str) or not evidence.get("source", "").strip():
            raise ValueError("Runtime manifest model inventory evidence source is missing")
        _, raw_inventory = _read_bound_evidence(
            evidence.get("path"), evidence.get("sha256"), "model inventory",
        )
        try:
            source_value = json.loads(raw_inventory.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Runtime manifest model inventory source is invalid") from exc
        normalized = _normalize_models(source_value, evidence_status == "VERIFIED")
        if normalized != models:
            raise ValueError("Runtime manifest normalized models do not match bound inventory evidence")
    else:
        raise ValueError("Runtime manifest model inventory evidence status is invalid")

    expected_status = "UNAVAILABLE"
    if runtime.get("status") == "VERIFIED":
        expected_status = (
            "VERIFIED_WITH_MODEL_INVENTORY"
            if evidence_status == "VERIFIED" else "RUNTIME_VERIFIED_MODELS_UNVERIFIED"
        )
    elif runtime.get("status") != "NOT_FOUND":
        expected_status = "PARTIAL"
    if manifest.get("status") != expected_status:
        raise ValueError("Runtime manifest overall status is inconsistent with its evidence")

    dispatch = manifest.get("dispatch_evidence")
    dispatch_fields = {"status", "path", "sha256", "consistency", "facts"}
    if not isinstance(dispatch, Mapping) or set(dispatch) != dispatch_fields:
        raise ValueError("Runtime manifest dispatch evidence fields are invalid")
    dispatch_status = dispatch.get("status")
    if dispatch_status == "NOT_PROVIDED":
        if dispatch != {
            "status": "NOT_PROVIDED", "path": "", "sha256": "",
            "consistency": "NOT_CHECKED", "facts": {},
        }:
            raise ValueError("Runtime manifest absent dispatch evidence is inconsistent")
    elif dispatch_status in {"VERIFIED", "UNVERIFIED"}:
        _, raw_receipt = _read_bound_evidence(
            dispatch.get("path"), dispatch.get("sha256"), "dispatch receipt",
        )
        try:
            receipt = json.loads(raw_receipt.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Runtime manifest dispatch receipt source is invalid") from exc
        valid_receipt = _valid_execution_receipt(receipt, str(platform), models, runtime)
        if valid_receipt != (dispatch_status == "VERIFIED"):
            raise ValueError("Runtime manifest dispatch status does not match receipt evidence")
        expected_consistency = "CROSS_CHECKED" if valid_receipt else "FAILED"
        fact_fields = (
            "task_id", "agent", "actual_provider", "actual_model", "actual_reasoning",
            "runtime_version", "recorded_at", "evidence_source",
        )
        expected_facts = {field: receipt[field] for field in fact_fields} if valid_receipt else {}
        if dispatch.get("consistency") != expected_consistency or dispatch.get("facts") != expected_facts:
            raise ValueError("Runtime manifest dispatch facts are inconsistent")
    else:
        raise ValueError("Runtime manifest dispatch status is invalid")

    dispatch_valid = _dispatch_consistent(manifest)
    expected_claims = {
        "authenticated": "UNKNOWN",
        "native_dispatch_completed": dispatch_valid,
        "actual_model_used": "ATTESTED_BY_RECEIPT" if dispatch_valid else "UNKNOWN",
    }
    if manifest.get("claims") != expected_claims:
        raise ValueError("Runtime manifest claims are inconsistent with validated evidence")


def load_runtime_manifest(path: Path) -> Dict[str, Any]:
    target, raw = _read_ordinary_file(
        path, "Runtime manifest", size_limit=MAX_MODEL_INVENTORY_BYTES,
    )
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON file %s: %s" % (target, exc)) from exc
    if not isinstance(manifest, dict):
        raise ValueError("JSON root must be an object: %s" % target)
    validate_runtime_manifest(manifest)
    return manifest


def resolve_model(
    manifest: Mapping[str, Any],
    capability_tier: str,
    *,
    reasoning_effort: str = "medium",
    risk_flags: Iterable[str] = (),
    risk_level: str = "normal",
) -> Dict[str, Any]:
    tier = capability_tier.upper()
    if tier not in CAPABILITY_TIERS:
        raise ValueError("capability_tier must be one of: %s" % ", ".join(CAPABILITY_TIERS))
    if reasoning_effort not in REASONING_LEVELS:
        raise ValueError("Unsupported reasoning effort: %s" % reasoning_effort)
    if risk_level not in {"low", "normal", "high"}:
        raise ValueError("risk_level must be low, normal, or high")
    normalized_flags = sorted({flag.strip().lower() for flag in risk_flags if flag.strip()})
    high_risk = risk_level == "high" or bool(set(normalized_flags) & HIGH_RISK_FLAGS)
    original_tier = tier
    if high_risk and CAPABILITY_TIERS.index(tier) < CAPABILITY_TIERS.index("EXPERT"):
        tier = "EXPERT"
    platform = manifest.get("platform")
    if platform not in PLATFORM_CHOICES:
        raise ValueError("Runtime manifest platform is invalid")
    inventory = manifest.get("model_inventory", {})
    evidence = inventory.get("evidence", {}) if isinstance(inventory, dict) else {}
    inventory_verified = evidence.get("status") == "VERIFIED"
    runtime_verified = manifest.get("runtime", {}).get("status") == "VERIFIED"
    reasons = ["requested-tier:%s" % original_tier, "platform:%s" % platform]
    if tier != original_tier:
        reasons.append("high-risk-capability-floor:EXPERT")
    if high_risk and (not runtime_verified or not inventory_verified):
        return {
            "status": "BLOCKED_UNVERIFIED_HIGH_RISK_RUNTIME",
            "platform": platform,
            "requested_capability_tier": tier,
            "requested_reasoning_effort": reasoning_effort,
            "selected_model": "",
            "selected_provider": "",
            "selected_capability_tier": "",
            "selected_reasoning_effort": "",
            "risk_flags": normalized_flags,
            "high_risk": True,
            "actual_model_attested": False,
            "reasons": reasons + ["high-risk-routing-requires-verified-runtime-and-model-inventory"],
        }
    models = inventory.get("models", []) if isinstance(inventory, dict) else []
    candidates = []
    requested_index = CAPABILITY_TIERS.index(tier)
    for model in models:
        if not isinstance(model, dict):
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,499}", str(model.get("id", ""))):
            raise ValueError("Runtime manifest contains an invalid model identifier")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,199}", str(model.get("provider", ""))):
            raise ValueError("Runtime manifest contains an invalid provider identifier")
        if model.get("capability_tier") not in CAPABILITY_TIERS:
            continue
        model_index = CAPABILITY_TIERS.index(model["capability_tier"])
        if model_index >= requested_index:
            candidates.append(model)
    candidates.sort(key=lambda item: (CAPABILITY_TIERS.index(item["capability_tier"]), item.get("provider", ""), item.get("id", "")))
    if not candidates:
        return {
            "status": "BLOCKED_MODEL_UNAVAILABLE",
            "platform": platform,
            "requested_capability_tier": tier,
            "requested_reasoning_effort": reasoning_effort,
            "selected_model": "",
            "selected_provider": "",
            "selected_capability_tier": "",
            "selected_reasoning_effort": "",
            "risk_flags": normalized_flags,
            "high_risk": high_risk,
            "actual_model_attested": False,
            "reasons": reasons + ["no-runtime-model-meets-capability-floor"],
        }
    exact_effort = [model for model in candidates if reasoning_effort in model.get("reasoning_efforts", [])]
    selected = (exact_effort or candidates)[0]
    selected_effort = reasoning_effort if reasoning_effort in selected.get("reasoning_efforts", []) else ""
    if high_risk and not selected_effort:
        return {
            "status": "BLOCKED_REASONING_EFFORT_UNAVAILABLE",
            "platform": platform,
            "requested_capability_tier": tier,
            "requested_reasoning_effort": reasoning_effort,
            "selected_model": "",
            "selected_provider": "",
            "selected_capability_tier": "",
            "selected_reasoning_effort": "",
            "risk_flags": normalized_flags,
            "high_risk": True,
            "actual_model_attested": False,
            "reasons": reasons + ["high-risk-routing-requires-requested-reasoning-effort"],
        }
    limitations = []
    if not runtime_verified:
        limitations.append("runtime-executable-unverified")
    if not inventory_verified or selected.get("evidence_status") != "VERIFIED":
        limitations.append("model-inventory-unverified")
    if not selected_effort:
        limitations.append("reasoning-effort-not-bound")
    status = "ROUTED_WITH_LIMITATIONS" if limitations else "ROUTED"
    return {
        "status": status,
        "platform": platform,
        "requested_capability_tier": tier,
        "requested_reasoning_effort": reasoning_effort,
        "selected_model": selected.get("id", ""),
        "selected_provider": selected.get("provider", ""),
        "selected_capability_tier": selected.get("capability_tier", ""),
        "selected_reasoning_effort": selected_effort,
        "risk_flags": normalized_flags,
        "high_risk": high_risk,
        "actual_model_attested": False,
        "limitations": limitations,
        "reasons": reasons + (["controlled-upward-capability-selection"] if selected.get("capability_tier") != tier else ["exact-capability-tier"]),
    }


def _agent_root(target_root: Path, platform: str, scope: str) -> Path:
    spec = platform_spec(platform)
    key = "project_agent_directory" if scope == "project" else "user_agent_directory"
    return target_root / str(spec[key])


def doctor_platform(
    platform: str,
    target_root: Path,
    *,
    scope: str = "project",
    manifest: Optional[Mapping[str, Any]] = None,
    opencode_schema: str = "auto",
) -> Dict[str, Any]:
    if scope not in {"project", "user"}:
        raise ValueError("scope must be project or user")
    root = Path(target_root).expanduser().resolve()
    spec = platform_spec(platform)
    checks = []
    skill_key = "project_skill_directory" if scope == "project" else "user_skill_directory"
    installed_skill = root / str(spec[skill_key]) / SKILL_INSTALL_NAME
    skill_file = installed_skill / "SKILL.md"
    try:
        _read_ordinary_file(skill_file, "Installed Skill", size_limit=MAX_AGENT_PROFILE_BYTES)
        skill_ok = _ordinary_directory_under(root, installed_skill, "Installed Skill directory")
    except ValueError:
        skill_ok = False
    checks.append({
        "id": "portable-skill", "status": "PASS" if skill_ok else "FAIL",
        "path": str(installed_skill),
    })
    core_ok = skill_ok and all(
        _ordinary_directory_under(root, installed_skill / name, "Portable core directory")
        for name in ("scripts", "assets", "references")
    )
    checks.append({"id": "portable-core", "status": "PASS" if core_ok else "FAIL"})
    selected_schema = _selected_opencode_schema(platform, opencode_schema)
    expected_files = render_adapter_files(
        platform, opencode_schema=selected_schema or "auto"
    )
    prefix = Path(str(spec["project_agent_directory"] if scope == "project" else spec["user_agent_directory"]))
    project_prefix = Path(str(spec["project_agent_directory"]))
    expected_names = [relative.relative_to(project_prefix) for relative in expected_files]
    agent_root = _agent_root(root, platform, scope)
    missing = []
    drifted = []
    unsafe = []
    for relative, expected_content in expected_files.items():
        name = relative.relative_to(project_prefix)
        target = agent_root / name
        if not os.path.lexists(str(target)):
            missing.append(str(target))
            continue
        try:
            _, raw = _read_ordinary_file(
                target, "Native Agent profile", size_limit=MAX_AGENT_PROFILE_BYTES,
            )
        except ValueError:
            unsafe.append(str(target))
            continue
        try:
            actual_content = raw.decode("utf-8")
        except UnicodeDecodeError:
            drifted.append(str(target))
            continue
        if actual_content != expected_content:
            drifted.append(str(target))
    profiles_ok = (
        _ordinary_directory_under(root, agent_root, "Native Agent directory")
        and not missing and not drifted and not unsafe
    )
    checks.append({
        "id": "native-agent-profiles", "status": "PASS" if profiles_ok else "FAIL",
        "missing": missing, "drifted": drifted, "unsafe": unsafe,
    })
    probe = _runtime_probe(platform)
    runtime_ok = probe["status"] == "VERIFIED"
    checks.append({"id": "runtime-executable", "status": "PASS" if runtime_ok else "UNVERIFIED", "evidence": probe})
    inventory_ok = bool(
        manifest
        and manifest.get("platform") == platform
        and manifest.get("model_inventory", {}).get("evidence", {}).get("status") == "VERIFIED"
        and manifest.get("model_inventory", {}).get("models")
    )
    checks.append({"id": "runtime-model-inventory", "status": "PASS" if inventory_ok else "UNVERIFIED"})
    dispatch_ok = bool(manifest and _dispatch_consistent(manifest))
    checks.append({"id": "native-dispatch-evidence", "status": "PASS" if dispatch_ok else "NOT_ATTESTED"})
    level = "L0"
    if skill_ok:
        level = "L1"
    if skill_ok and core_ok:
        level = "L2"
    if skill_ok and core_ok and profiles_ok and runtime_ok and inventory_ok:
        level = "L3"
    if level == "L3" and dispatch_ok:
        level = "L4"
    limitations = [check["id"] for check in checks if check["status"] not in {"PASS"}]
    result = {
        "schema_version": 1,
        "platform": platform,
        "scope": scope,
        "target_root": str(root),
        "compatibility_level": level,
        "level_meaning": {
            "L0": "portable package unavailable",
            "L1": "Skill is structurally discoverable",
            "L2": "portable workflow, documents, and scripts are available",
            "L3": "native profiles and verified runtime model inventory are available",
            "L4": "a local native-execution declaration is structurally valid and cross-checked against verified runtime inventory",
        }[level],
        "checks": checks,
        "limitations": limitations,
        "claim_boundary": (
            "L4 is an unsigned local consistency claim, not cryptographic proof that a session launched. "
            "A rendered profile or self-authored receipt is not independent execution evidence."
        ),
    }
    if selected_schema:
        result["adapter_schema"] = selected_schema
    return result


def write_json_non_overwriting(
    path: Path,
    value: Mapping[str, Any],
    *,
    update: bool = False,
    allowed_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Atomically write JSON without following symlinks or modifying hard links."""
    target = _lexical_absolute(path)
    if not target.name:
        raise ValueError("Output path must name a file")
    if allowed_root is not None:
        root = _lexical_absolute(allowed_root)
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError("Output path escapes the allowed root: %s" % target) from None
        _reject_symlink_ancestors(root, "Output root")
    _reject_symlink_ancestors(target, "Output")
    content = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        parent_metadata = os.stat(target.parent, follow_symlinks=False)
    except FileNotFoundError:
        raise ValueError("Output parent directory is missing: %s" % target.parent) from None
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise ValueError("Output parent is not an ordinary directory: %s" % target.parent)
    try:
        directory_fd = os.open(
            str(target.parent),
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise ValueError("Output parent cannot be opened safely: %s" % target.parent) from exc
    temporary_name = ".%s.%s.tmp" % (target.name, secrets.token_hex(12))
    temporary_created = False
    try:
        opened_parent = os.fstat(directory_fd)
        if (parent_metadata.st_dev, parent_metadata.st_ino) != (opened_parent.st_dev, opened_parent.st_ino):
            raise ValueError("Output parent directory changed during validation")

        existed = False
        try:
            metadata = os.stat(target.name, dir_fd=directory_fd, follow_symlinks=False)
            existed = True
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("Output must be an ordinary single-link file: %s" % target)
            read_fd = os.open(
                target.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            try:
                current = b""
                while True:
                    chunk = os.read(read_fd, 1024 * 1024)
                    if not chunk:
                        break
                    current += chunk
                    if len(current) > MAX_MODEL_INVENTORY_BYTES:
                        raise ValueError("Existing output exceeds the size limit")
            finally:
                os.close(read_fd)
            if current == content:
                return {"status": "UNCHANGED", "path": str(target)}
            if not update:
                return {"status": "BLOCKED_CONFLICT", "path": str(target)}

        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        temporary_created = True
        try:
            with os.fdopen(temporary_fd, "wb", closefd=True) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            raise

        # Recheck the destination before replacement. os.replace is relative to
        # the already-open directory, so a swapped parent path cannot redirect it.
        try:
            current_metadata = os.stat(target.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            current_metadata = None
        if current_metadata is not None and (
            not stat.S_ISREG(current_metadata.st_mode) or current_metadata.st_nlink != 1
        ):
            raise ValueError("Output changed to a non-ordinary or linked file before commit")
        if existed and current_metadata is None:
            raise ValueError("Output disappeared before commit")
        if not existed and current_metadata is not None:
            raise ValueError("Output appeared before commit")
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_created = False
        os.fsync(directory_fd)
        return {"status": "UPDATED" if existed else "CREATED", "path": str(target)}
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)
