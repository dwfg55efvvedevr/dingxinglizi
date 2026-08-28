#!/usr/bin/env python3
"""Resolve and safely provision allowlisted project-local Skills and HTTP MCP servers."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from _common import SKILL_ROOT, project_root, read_text
from project_layout import control_path
from platform_runtime import PLATFORM_CHOICES, platform_spec, safe_write_target
from state_io import atomic_write_json, atomic_write_text


MANAGED_START = "# BEGIN software-project-orchestrator managed MCP"
MANAGED_END = "# END software-project-orchestrator managed MCP"
CODE_SUFFIXES = {
    ".py", ".pyc", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".sh", ".bash", ".zsh",
    ".rb", ".pl", ".php", ".java", ".go", ".rs", ".ps1", ".bat", ".cmd",
    ".exe", ".bin", ".jar", ".dll", ".dylib", ".so", ".wasm",
}
CAPABILITY_ID = re.compile(r"[A-Za-z0-9_-]+")


def product_version() -> str:
    path = SKILL_ROOT / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else "unknown"


def validate_capability_id(capability_id: str) -> None:
    if not CAPABILITY_ID.fullmatch(capability_id):
        raise ValueError(
            f"Invalid capability id {capability_id!r}; use only letters, digits, underscore, and hyphen"
        )


def valid_skill_manifest(path: Path, capability_id: str) -> bool:
    manifest = path / "SKILL.md"
    if not manifest.is_file():
        return False
    try:
        text = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    lines = text[4:end].splitlines()
    metadata: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith((" ", "\t")) or ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value in {"|", ">", "|-", ">-", "|+", ">+"}:
            block: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith((" ", "\t")) or not lines[index].strip()):
                block.append(lines[index].strip())
                index += 1
            metadata[key] = " ".join(item for item in block if item).strip()
            continue
        metadata[key] = value.strip('"').strip("'")
        index += 1
    return metadata.get("name") == capability_id and bool(metadata.get("description", "").strip())


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def active_platform(root: Path) -> str:
    manifest = control_path(root, "orchestration/runtime-manifest.json")
    if manifest.is_file():
        value = load_json(manifest)
        platform = value.get("platform")
        if platform in PLATFORM_CHOICES:
            return str(platform)
    directories = {
        platform: root / str(platform_spec(platform)["project_agent_directory"])
        for platform in PLATFORM_CHOICES
    }
    present = [platform for platform, directory in directories.items() if directory.is_dir()]
    if len(present) == 1:
        return present[0]
    if "codex" in present:
        return "codex"
    return ""


def installed_skill(root: Path, capability_id: str, platform: str = "") -> Path | None:
    validate_capability_id(capability_id)
    platform = platform or active_platform(root)
    project_root = root.resolve()
    home_root = Path.home().resolve()
    candidates = [
        (project_root, project_root / ".agents" / "skills" / capability_id),
        (home_root, home_root / ".agents" / "skills" / capability_id),
        (home_root, home_root / ".codex" / "skills" / capability_id),
    ]
    if platform in PLATFORM_CHOICES:
        spec = platform_spec(platform)
        candidates = [
            (project_root, project_root / str(spec["project_skill_directory"]) / capability_id),
            (home_root, home_root / str(spec["user_skill_directory"]) / capability_id),
            *candidates,
        ]
    for base, candidate in candidates:
        if safe_write_target(base, candidate) and valid_skill_manifest(candidate, capability_id):
            return candidate
    return None


def runtime_capabilities(root: Path) -> tuple[set[str], set[str], bool]:
    """Return capability IDs the current host explicitly proved discoverable.

    A file on disk or an MCP config entry is only a prepared artifact. It is not
    evidence that an already-running Codex session discovered the capability.
    """
    inventory = load_json(control_path(root, "orchestration/runtime-inventory.json"))
    skills = inventory.get("available_skills")
    mcp_servers = inventory.get("available_mcp_servers")
    if not isinstance(skills, list) or not all(isinstance(item, str) for item in skills):
        raise ValueError("runtime-inventory.json available_skills must be a list of capability IDs")
    if not isinstance(mcp_servers, list) or not all(isinstance(item, str) for item in mcp_servers):
        raise ValueError("runtime-inventory.json available_mcp_servers must be a list of capability IDs")
    for capability_id in [*skills, *mcp_servers]:
        validate_capability_id(capability_id)
    return set(skills), set(mcp_servers), inventory.get("status") == "VERIFIED"


def existing_mcp(root: Path, capability_id: str) -> bool:
    validate_capability_id(capability_id)
    return mcp_config_details(root, capability_id) is not None


def mcp_config_details(root: Path, capability_id: str) -> dict[str, Any] | None:
    validate_capability_id(capability_id)
    root = root.resolve()
    path = root / ".codex" / "config.toml"
    if not safe_write_target(root, path):
        raise ValueError("Codex MCP config path traverses a symlink or escapes the project")
    if not path.is_file():
        return None
    text = read_text(path)
    pattern = rf"(?ms)^\[mcp_servers\.{re.escape(capability_id)}\]\s*\n(.*?)(?=^\[|\Z|^# END software-project-orchestrator managed MCP)"
    matches = list(re.finditer(pattern, text))
    if not matches:
        return None
    match = matches[0]
    body = match.group(1)
    url_match = re.search(r'(?m)^url\s*=\s*("(?:[^"\\]|\\.)*")\s*$', body)
    tools_match = re.search(r"(?m)^enabled_tools\s*=\s*(\[[^\n]*\])\s*$", body)
    try:
        url = json.loads(url_match.group(1)) if url_match else None
        tools = json.loads(tools_match.group(1)) if tools_match else None
    except json.JSONDecodeError:
        url, tools = None, None
    before = text.rfind(MANAGED_START, 0, match.start())
    end_before = text.rfind(MANAGED_END, 0, match.start())
    after = text.find(MANAGED_END, match.end())
    managed = before >= 0 and before > end_before and after >= 0
    return {
        "url": url,
        "enabled_tools": sorted(tools) if isinstance(tools, list) and all(isinstance(item, str) for item in tools) else None,
        "managed": managed,
        "section_count": len(matches),
    }


def validate_candidate(capability_id: str, candidate: dict[str, Any], policy: dict[str, Any]) -> str | None:
    validate_capability_id(capability_id)
    kind = candidate.get("kind")
    source = candidate.get("source", {})
    if kind == "skill" and source.get("type") == "github":
        repository = source.get("repository", "")
        commit = source.get("commit", "")
        if repository not in policy.get("allowed_github_repositories", []):
            return "BLOCKED_TRUST: repository is not allowlisted"
        if policy.get("require_full_commit_sha", True) and not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
            return "BLOCKED_TRUST: source must use a full 40-character commit SHA"
        if candidate.get("license") not in policy.get("allowed_licenses", []):
            return "BLOCKED_LICENSE: license is not allowlisted"
        if policy.get("require_archive_sha256", True) and not re.fullmatch(r"[0-9a-fA-F]{64}", source.get("archive_sha256", "")):
            return "BLOCKED_TRUST: archive_sha256 is required"
        if candidate.get("contains_executable_code") and not policy.get("allow_executable_files", False):
            return "BLOCKED_EXECUTABLE: candidate contains executable code"
        return None
    if kind == "mcp_http":
        url = source.get("url", "")
        if not url.startswith("https://"):
            return "BLOCKED_TRUST: HTTP MCP URL must use HTTPS"
        if source.get("credential_mode", "none") != "none":
            return "BLOCKED_AUTH: OAuth, secrets, and account connection require user authorization"
        if candidate.get("permission", "read") != "read":
            return "BLOCKED_PERMISSION: automatic MCP setup is read-only only"
        tools = candidate.get("allowed_tools")
        if not isinstance(tools, list) or not tools or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", str(item)) for item in tools):
            return "BLOCKED_PERMISSION: read-only MCP candidates require an explicit allowed_tools list"
        if not policy.get("auto_configure_credential_free_http_mcp", False):
            return "BLOCKED_POLICY: automatic MCP configuration is disabled"
        return None
    return "BLOCKED_UNSUPPORTED: source type is not safely auto-provisionable"


def download_skill(
    root: Path,
    capability_id: str,
    candidate: dict[str, Any],
    policy: dict[str, Any],
    platform: str = "",
) -> dict[str, Any]:
    validate_capability_id(capability_id)
    source = candidate["source"]
    repository, commit = source["repository"], source["commit"]
    url = f"https://codeload.github.com/{repository}/zip/{commit}"
    request = urllib.request.Request(url, headers={"User-Agent": f"software-project-orchestrator/{product_version()}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            archive = response.read(int(policy.get("maximum_archive_bytes", 10485760)) + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError(f"Download failed for {capability_id}: {exc}") from exc
    if len(archive) > int(policy.get("maximum_archive_bytes", 10485760)):
        raise ValueError(f"Archive exceeds maximum size for {capability_id}")
    digest = hashlib.sha256(archive).hexdigest()
    if digest.lower() != source["archive_sha256"].lower():
        raise ValueError(f"Archive SHA-256 mismatch for {capability_id}")

    destination_root = Path(".agents/skills")
    if platform in PLATFORM_CHOICES:
        destination_root = Path(str(platform_spec(platform)["project_skill_directory"]))
    root = root.resolve()
    destination = root / destination_root / capability_id
    if not safe_write_target(root, destination):
        raise ValueError(f"Capability destination traverses a symlink or escapes the project: {destination}")
    if os.path.lexists(destination):
        raise ValueError(f"Destination already exists and will not be overwritten: {destination}")
    subdirectory = PurePosixPath(source.get("subdirectory", ""))
    selected: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    try:
        bundle = zipfile.ZipFile(io.BytesIO(archive))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError(f"Invalid ZIP archive for {capability_id}: {exc}") from exc
    with bundle:
        members = bundle.infolist()
        files = [member for member in members if not member.is_dir()]
        if len(files) > int(policy.get("maximum_files", 1000)):
            raise ValueError(f"Archive contains too many files for {capability_id}")
        if sum(member.file_size for member in files) > int(policy.get("maximum_extracted_bytes", 52428800)):
            raise ValueError(f"Archive extracted size exceeds policy for {capability_id}")
        if any(member.file_size > int(policy.get("maximum_member_bytes", 5242880)) for member in files):
            raise ValueError(f"Archive contains an oversized member for {capability_id}")
        for member in members:
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"Unsafe archive path in {capability_id}: {member.filename}")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Symbolic links are not allowed in capability archives: {member.filename}")
            if mode & 0o111 and not policy.get("allow_executable_files", False):
                raise ValueError(f"Executable archive member is blocked by policy: {member.filename}")
            relative_parts = path.parts[1:]
            if subdirectory.parts:
                if tuple(relative_parts[: len(subdirectory.parts)]) != subdirectory.parts:
                    continue
                relative_parts = relative_parts[len(subdirectory.parts) :]
            if not relative_parts or member.is_dir():
                continue
            relative = PurePosixPath(*relative_parts)
            if relative.suffix.lower() in CODE_SUFFIXES and not policy.get("allow_executable_files", False):
                raise ValueError(f"Executable/code file is blocked by policy: {relative}")
            selected.append((member, relative))
        if not any(str(relative) == "SKILL.md" for _, relative in selected):
            raise ValueError(f"Selected GitHub directory does not contain SKILL.md for {capability_id}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not safe_write_target(root, destination):
            raise ValueError(f"Capability destination became unsafe: {destination}")
        staging = Path(tempfile.mkdtemp(prefix=f".{capability_id}-staging-", dir=str(destination.parent)))
        try:
            for member, relative in selected:
                target = staging.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    content = bundle.read(member)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise ValueError(f"Failed to extract {relative} for {capability_id}: {exc}") from exc
                target.write_bytes(content)
            if not valid_skill_manifest(staging, capability_id):
                raise ValueError(
                    f"Installed Skill manifest must have non-empty frontmatter with name: {capability_id} and description"
                )
            if not safe_write_target(root, destination) or os.path.lexists(destination):
                raise ValueError(f"Capability destination changed before promotion: {destination}")
            parent_metadata = os.lstat(destination.parent)
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            parent_fd = os.open(destination.parent, flags)
            try:
                opened_parent = os.fstat(parent_fd)
                if (
                    not stat.S_ISDIR(parent_metadata.st_mode)
                    or (parent_metadata.st_dev, parent_metadata.st_ino)
                    != (opened_parent.st_dev, opened_parent.st_ino)
                ):
                    raise ValueError("Capability destination parent changed before promotion")
                os.replace(
                    staging.name, destination.name,
                    src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                )
            finally:
                os.close(parent_fd)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return {"source_url": url, "commit": commit, "archive_sha256": digest, "path": str(destination)}


def configure_mcp(root: Path, capability_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    validate_capability_id(capability_id)
    root = root.resolve()
    config = root / ".codex" / "config.toml"
    if not safe_write_target(root, config):
        raise ValueError("Codex MCP config path traverses a symlink or escapes the project")
    config.parent.mkdir(parents=True, exist_ok=True)
    if not safe_write_target(root, config):
        raise ValueError("Codex MCP config path became unsafe")
    current = config.read_text(encoding="utf-8") if config.exists() else ""
    outside = current
    if MANAGED_START in current and MANAGED_END in current:
        before, remainder = current.split(MANAGED_START, 1)
        _, after = remainder.split(MANAGED_END, 1)
        outside = before + after
    if re.search(rf"(?m)^\[mcp_servers\.{re.escape(capability_id)}\]\s*$", outside):
        raise ValueError(f"Existing unmanaged MCP section conflicts with {capability_id}; refusing to overwrite")
    entries: dict[str, str] = {}
    managed_match = re.search(re.escape(MANAGED_START) + r"\n(.*?)\n" + re.escape(MANAGED_END), current, re.S)
    if managed_match:
        for match in re.finditer(
            r"(?ms)^\[mcp_servers\.([A-Za-z0-9_-]+)\]\n(.*?)(?=^\[mcp_servers\.|\Z)",
            managed_match.group(1),
        ):
            entries[match.group(1)] = f"[mcp_servers.{match.group(1)}]\n{match.group(2).strip()}"
    tools = sorted(set(candidate["allowed_tools"]))
    entries[capability_id] = (
        f"[mcp_servers.{capability_id}]\n"
        f"url = {json.dumps(candidate['source']['url'])}\n"
        f"enabled_tools = {json.dumps(tools)}"
    )
    body = "\n\n".join(entries[name] for name in sorted(entries))
    block = f"{MANAGED_START}\n{body}\n{MANAGED_END}"
    if MANAGED_START in current and MANAGED_END in current:
        current = re.sub(re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), block, current, flags=re.S)
    else:
        current = current.rstrip() + ("\n\n" if current.strip() else "") + block + "\n"
    atomic_write_text(config, current, allowed_root=root)
    return {
        "url": candidate["source"]["url"], "config": str(config),
        "permission": "read", "enabled_tools": tools,
    }


def resolve(root: Path, requested: list[str], apply: bool) -> tuple[dict[str, Any], bool]:
    policy = load_json(control_path(root, "orchestration/capability-policy.json"))
    catalog = load_json(control_path(root, "orchestration/capability-catalog.json")).get("capabilities", {})
    lock_path = control_path(root, "orchestration/capability-lock.json")
    lock = load_json(lock_path)
    runtime_skills, runtime_mcp_servers, runtime_verified = runtime_capabilities(root)
    platform = active_platform(root)
    results: dict[str, Any] = {}
    blocked = False
    for capability_id in requested:
        validate_capability_id(capability_id)
        skill_path = installed_skill(root, capability_id, platform)
        if skill_path:
            if runtime_verified and capability_id in runtime_skills:
                results[capability_id] = {
                    "status": "SATISFIED", "kind": "skill", "path": str(skill_path),
                    "runtime_verified": True,
                }
            else:
                locked = lock.get("resolved", {}).get(capability_id, {})
                provisioned = isinstance(locked, dict) and locked.get("kind") == "skill"
                results[capability_id] = {
                    "status": "PROVISIONED_PENDING_RUNTIME" if provisioned else "DISCOVERED_NOT_RUNTIME_VERIFIED",
                    "kind": "skill", "path": str(skill_path), "runtime_verified": False,
                    "next_action": (
                        "Start a fresh Agent session, verify that the runtime discovers this Skill, "
                        "then record its id in runtime-inventory.json available_skills"
                    ),
                }
                blocked = True
            continue
        config_details = mcp_config_details(root, capability_id) if platform in {"", "codex"} else None
        if config_details is not None:
            locked = lock.get("resolved", {}).get(capability_id, {})
            evidence = locked.get("evidence", {}) if isinstance(locked, dict) else {}
            if (
                locked.get("status") in {"PROVISIONED", "PROVISIONED_PENDING_RUNTIME"}
                and locked.get("kind") == "mcp_http"
                and evidence.get("permission") == "read"
                and evidence.get("enabled_tools")
                and config_details.get("managed") is True
                and config_details.get("section_count") == 1
                and config_details.get("url") == evidence.get("url")
                and config_details.get("enabled_tools") == sorted(evidence.get("enabled_tools", []))
            ):
                if runtime_verified and capability_id in runtime_mcp_servers:
                    results[capability_id] = {
                        "status": "SATISFIED", "kind": "mcp_http",
                        "config": str(root / ".codex/config.toml"),
                        "enabled_tools": evidence["enabled_tools"], "runtime_verified": True,
                    }
                else:
                    results[capability_id] = {
                        "status": "PROVISIONED_PENDING_RUNTIME", "kind": "mcp_http",
                        "config": str(root / ".codex/config.toml"),
                        "enabled_tools": evidence["enabled_tools"], "runtime_verified": False,
                        "next_action": (
                            "Start a fresh Agent session, verify that the runtime connects this MCP server, "
                            "then record its id in runtime-inventory.json available_mcp_servers"
                        ),
                    }
                    blocked = True
            else:
                results[capability_id] = {
                    "status": "BLOCKED_CONFIG_DRIFT",
                    "reason": "Actual MCP config does not exactly match its managed read-only Broker lock",
                }
                blocked = True
            continue
        candidate = catalog.get(capability_id)
        if not isinstance(candidate, dict):
            results[capability_id] = {"status": "BLOCKED_DISCOVERY", "reason": "No trusted catalog candidate; Orchestrator must perform read-only discovery and catalog review."}
            blocked = True
            continue
        reason = validate_candidate(capability_id, candidate, policy)
        if reason:
            results[capability_id] = {"status": reason.split(":", 1)[0], "reason": reason.split(":", 1)[1].strip()}
            blocked = True
            continue
        if candidate.get("kind") == "mcp_http" and platform not in {"", "codex"}:
            results[capability_id] = {
                "status": "BLOCKED_PLATFORM_CONFIGURATION",
                "reason": (
                    f"Automatic MCP rendering is not implemented for {platform}; "
                    "configure it through that host's supported flow and record runtime evidence"
                ),
            }
            blocked = True
            continue
        if not apply:
            results[capability_id] = {"status": "AUTO_PROVISIONABLE", "kind": candidate["kind"], "candidate": candidate}
            continue
        try:
            if candidate["kind"] == "skill":
                evidence = download_skill(root, capability_id, candidate, policy, platform)
            else:
                evidence = configure_mcp(root, capability_id, candidate)
        except ValueError as exc:
            results[capability_id] = {"status": "BLOCKED_PROVISIONING", "reason": str(exc)}
            blocked = True
            continue
        record = {
            "status": "PROVISIONED_PENDING_RUNTIME",
            "kind": candidate["kind"],
            "license": candidate.get("license"),
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
        }
        results[capability_id] = record
        lock.setdefault("resolved", {})[capability_id] = record
        blocked = True
    if apply:
        atomic_write_json(lock_path, lock, allowed_root=root)
    return results, blocked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--required", action="append", default=[], help="Capability id; repeat for multiple requirements")
    parser.add_argument("--apply", action="store_true", help="Provision safe allowlisted candidates; default is plan-only")
    args = parser.parse_args()
    if not args.required:
        print("ERROR: at least one --required capability id is needed", file=sys.stderr)
        return 2
    try:
        results, blocked = resolve(project_root(args.project_dir), sorted(set(args.required)), args.apply)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"mode": "apply" if args.apply else "plan", "capabilities": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 3 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
