#!/usr/bin/env python3
"""Persist and verify fail-closed READY receipts for Task Package dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from task_contract import TASK_ID_PATTERN, list_field, quoted_scalar, task_dispatch_fingerprint, top_section


SCHEMA_VERSION = 1


def _receipt_fingerprint(receipt: dict[str, Any]) -> str:
    value = dict(receipt)
    value.pop("receipt_fingerprint", None)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def receipt_path(root: Path, task_id: str) -> Path:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("dispatch receipt task_id is not path-safe")
    root_resolved = root.resolve()
    dispatch_dir = (root / "evidence" / "dispatch").resolve()
    try:
        dispatch_dir.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("dispatch receipt directory resolves outside the project") from exc
    destination = (dispatch_dir / f"{task_id}.ready.json").resolve()
    if destination.parent != dispatch_dir:
        raise ValueError("dispatch receipt path resolves outside the dispatch directory")
    return destination


def _expected_fields(text: str) -> dict[str, Any]:
    role_execution = top_section(text, "role_execution")
    execution = top_section(text, "execution_profile")
    capabilities = top_section(text, "capability_requirements")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "READY",
        "task_id": quoted_scalar(text, "task_id"),
        "owner": quoted_scalar(text, "owner"),
        "stage": quoted_scalar(text, "stage"),
        "role_plan_fingerprint": quoted_scalar(role_execution, "role_plan_fingerprint"),
        "execution_route_fingerprint": quoted_scalar(execution, "route_fingerprint"),
        "task_dispatch_fingerprint": task_dispatch_fingerprint(text),
        "required_capabilities": sorted(list_field(capabilities, "required")),
    }


def record_dispatch_receipt(root: Path, text: str) -> Path:
    expected = _expected_fields(text)
    destination = receipt_path(root, expected["task_id"])
    if destination.is_file():
        errors = validate_dispatch_receipt(root, text)
        if errors:
            raise ValueError("existing dispatch receipt is stale or invalid: " + "; ".join(errors))
        return destination
    receipt = dict(expected)
    receipt["recorded_at"] = datetime.now(timezone.utc).isoformat()
    receipt["recorded_by"] = "check_execution_plan.py"
    receipt["receipt_fingerprint"] = _receipt_fingerprint(receipt)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def validate_dispatch_receipt(root: Path, text: str) -> list[str]:
    expected = _expected_fields(text)
    path = receipt_path(root, expected["task_id"])
    if not path.is_file():
        return [f"dispatch READY receipt is missing: {path.relative_to(root)}"]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"dispatch READY receipt is invalid: {exc}"]
    errors: list[str] = []
    if receipt.get("receipt_fingerprint") != _receipt_fingerprint(receipt):
        errors.append("dispatch READY receipt fingerprint is invalid")
    for field, wanted in expected.items():
        if receipt.get(field) != wanted:
            errors.append(f"dispatch READY receipt {field} does not match the completed task")
    if not receipt.get("recorded_at") or receipt.get("recorded_by") != "check_execution_plan.py":
        errors.append("dispatch READY receipt has no valid recorder metadata")
    return errors
