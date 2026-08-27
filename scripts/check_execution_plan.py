#!/usr/bin/env python3
"""Preflight a generated Task Package route and required capability readiness."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import project_root, read_text
from model_routing import route_fingerprint, route_with_inventory, validate_model_policy
from resolve_capabilities import installed_skill, load_json, mcp_config_details


def top_section(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}:\s*\n(.*?)(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)", text)
    return match.group(1) if match else ""


def quoted_scalar(text: str, name: str) -> str:
    match = re.search(rf'(?m)^\s*{re.escape(name)}:\s*"((?:[^"\\]|\\.)*)"\s*$', text)
    if not match:
        raise ValueError(f"Task Package is missing quoted scalar: {name}")
    return json.loads('"' + match.group(1) + '"')


def integer_scalar(text: str, name: str) -> int:
    match = re.search(rf"(?m)^\s*{re.escape(name)}:\s*(\d+)\s*$", text)
    if not match:
        raise ValueError(f"Task Package is missing integer scalar: {name}")
    return int(match.group(1))


def list_field(section: str, name: str) -> list[str]:
    inline = re.search(rf"(?m)^[ \t]*{re.escape(name)}:[ \t]*\[\][ \t]*$", section)
    if inline:
        return []
    match = re.search(
        rf'(?m)^[ \t]*{re.escape(name)}:[ \t]*\n'
        rf'((?:[ \t]+-[ \t]+"(?:[^"\\]|\\.)*"[ \t]*\n?)*)',
        section,
    )
    if not match:
        raise ValueError(f"Task Package is missing list field: {name}")
    return [json.loads(value) for value in re.findall(r'(?m)^\s+-\s+("(?:[^"\\]|\\.)*")\s*$', match.group(1))]


def boolean_scalar(text: str, name: str) -> bool:
    match = re.search(rf"(?m)^\s*{re.escape(name)}:\s*(true|false)\s*$", text)
    if not match:
        raise ValueError(f"Task Package is missing boolean scalar: {name}")
    return match.group(1) == "true"


def check(root: Path, task_path: Path, available_models: list[str] | None = None) -> list[str]:
    text = read_text(task_path)
    risk = top_section(text, "risk_profile")
    execution = top_section(text, "execution_profile")
    capabilities = top_section(text, "capability_requirements")
    status = load_json(root / "docs/project-status.json")
    validate_model_policy(load_json(root / ".codex/orchestration/model-routing-policy.json"))
    inventory = load_json(root / ".codex/orchestration/runtime-inventory.json")
    if available_models is not None:
        runtime_models = sorted(set(available_models))
        availability_source = "verified_runtime_snapshot"
        availability_verified = True
    else:
        values = inventory.get("available_models", [])
        runtime_models = sorted(set(values)) if isinstance(values, list) else []
        availability_verified = inventory.get("status") == "VERIFIED" and bool(runtime_models)
        availability_source = "verified_runtime_snapshot" if availability_verified else "unverified_runtime_inventory"
    expected = route_with_inventory(
        complexity=status.get("complexity", ""),
        task_type=quoted_scalar(text, "task_type"),
        role=quoted_scalar(text, "owner"),
        risk_flags=list_field(risk, "flags"),
        failed_attempts=integer_scalar(risk, "failed_attempts"),
        failure_type=quoted_scalar(risk, "failure_type"),
        available_models=runtime_models,
        availability_source=availability_source,
        availability_verified=availability_verified,
    )
    errors: list[str] = []
    comparisons = {
        "policy_version": expected["policy_version"],
        "route_fingerprint": route_fingerprint(expected),
        "routing_mode": expected["routing_mode"],
        "availability_source": expected["availability_source"],
        "status": expected["status"],
        "capability_tier": expected["capability_tier"],
        "preferred_model": expected["preferred_model"],
        "selected_model": expected["selected_model"],
        "model_reasoning_effort": expected["model_reasoning_effort"],
        "downgrade_policy": expected["downgrade_policy"],
    }
    for field, wanted in comparisons.items():
        actual = quoted_scalar(execution, field)
        if actual != wanted:
            errors.append(f"ROUTE_MISMATCH: {field} is {actual!r}, expected {wanted!r}")
    for field in ("fallback_models", "routing_reasons"):
        actual_list = list_field(execution, field)
        if actual_list != expected[field]:
            errors.append(f"ROUTE_MISMATCH: {field} is {actual_list!r}, expected {expected[field]!r}")
    actual_models = list_field(execution, "available_models")
    if actual_models != expected["available_models"]:
        errors.append(
            f"ROUTE_MISMATCH: available_models is {actual_models!r}, expected {expected['available_models']!r}"
        )
    if boolean_scalar(execution, "availability_verified") != expected["availability_verified"]:
        errors.append("ROUTE_MISMATCH: availability_verified differs from current runtime inventory")
    actual_attempt = integer_scalar(execution, "attempt")
    expected_attempt = expected["failed_attempts"] + 1
    if actual_attempt != expected_attempt:
        errors.append(f"ROUTE_MISMATCH: attempt is {actual_attempt}, expected {expected_attempt}")
    actual_max_attempts = integer_scalar(execution, "max_attempts")
    if actual_max_attempts != expected["max_attempts"]:
        errors.append(
            f"ROUTE_MISMATCH: max_attempts is {actual_max_attempts}, expected {expected['max_attempts']}"
        )
    if expected["status"] != "ROUTED":
        errors.append(f"Execution route is blocked: {expected['status']}")

    if quoted_scalar(capabilities, "permission_ceiling") != "read":
        errors.append("BLOCKED_PERMISSION: automatic capability permission ceiling must remain read")
    lock = load_json(root / ".codex/orchestration/capability-lock.json").get("resolved", {})
    for capability_id in list_field(capabilities, "required"):
        record = lock.get(capability_id, {}) if isinstance(lock, dict) else {}
        evidence = record.get("evidence", {}) if isinstance(record, dict) else {}
        locked_mcp_ready = (
            record.get("status") == "PROVISIONED"
            and record.get("kind") == "mcp_http"
            and evidence.get("permission") == "read"
            and bool(evidence.get("enabled_tools"))
        )
        if locked_mcp_ready:
            details = mcp_config_details(root, capability_id)
            locked_mcp_ready = bool(
                details
                and details.get("managed") is True
                and details.get("section_count") == 1
                and details.get("url") == evidence.get("url")
                and details.get("enabled_tools") == sorted(evidence.get("enabled_tools", []))
            )
        locked_skill_ready = record.get("status") == "PROVISIONED" and record.get("kind") == "skill"
        ready = locked_mcp_ready or locked_skill_ready or installed_skill(root, capability_id) is not None
        if not ready:
            errors.append(f"BLOCKED_CAPABILITY: required capability is not ready: {capability_id}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("task_package", help="Task YAML path, absolute or relative to project")
    parser.add_argument("--available-model", action="append", dest="available_models")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        task_path = Path(args.task_package)
        if not task_path.is_absolute():
            task_path = root / task_path
        errors = check(root, task_path, args.available_models)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"BLOCKED: {len(errors)} execution preflight error(s)")
        return 3
    print("READY: route matches policy and required capabilities are available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
