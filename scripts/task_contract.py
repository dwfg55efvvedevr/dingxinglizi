#!/usr/bin/env python3
"""Shared parser and substantive Task Package contract validation."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Iterable


TASK_ID_PATTERN = re.compile(r"TASK-[A-Z0-9][A-Z0-9_-]*")


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


def task_dispatch_fingerprint(text: str) -> str:
    """Fingerprint dispatch-critical content while allowing status/handoff completion updates."""
    normalized = re.sub(
        r'(?m)^status:\s*"(?:READY_FOR_DISPATCH|COMPLETED)"\s*$',
        'status: "DISPATCHED_OR_COMPLETED"',
        text,
        count=1,
    )
    normalized = re.sub(r"(?ms)^handoff:\s*\n.*\Z", "handoff: <normalized>\n", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_task_contract(
    root: Path,
    text: str,
    owner: str,
    *,
    allowed_statuses: Iterable[str] = ("READY_FOR_DISPATCH",),
) -> list[str]:
    errors: list[str] = []
    task_id = quoted_scalar(text, "task_id")
    if not TASK_ID_PATTERN.fullmatch(task_id):
        errors.append("BLOCKED_TASK_CONTRACT: task_id must match TASK-[A-Z0-9][A-Z0-9_-]*")
    allowed = set(allowed_statuses)
    actual_status = quoted_scalar(text, "status")
    if actual_status not in allowed:
        errors.append("BLOCKED_TASK_CONTRACT: status must be " + " or ".join(sorted(allowed)))
    business = top_section(text, "business_context")
    if quoted_scalar(business, "value") in {"", "BLOCKING_UNKNOWN"}:
        errors.append("BLOCKED_TASK_CONTRACT: business_context.value must be concrete")
    for name in ("scope", "deliverables"):
        if not list_field(text, name):
            errors.append(f"BLOCKED_TASK_CONTRACT: {name} must contain at least one item")
    inputs = list_field(text, "input_documents")
    if not inputs:
        errors.append("BLOCKED_TASK_CONTRACT: input_documents must not be empty")
    for relative in inputs:
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            errors.append(f"BLOCKED_TASK_CONTRACT: input document is outside project: {relative}")
            continue
        if not path.is_file():
            errors.append(f"BLOCKED_TASK_CONTRACT: input document does not exist: {relative}")
    acceptance = top_section(text, "acceptance_criteria")
    if not re.search(r'(?m)^  - id: "AC-[A-Z0-9_-]+"$', acceptance):
        errors.append("BLOCKED_TASK_CONTRACT: acceptance_criteria needs at least one AC-* item")
    for field in ("given", "when", "then", "evidence"):
        values = re.findall(rf'(?m)^\s+{field}:\s*"((?:[^"\\]|\\.)*)"\s*$', acceptance)
        if not values or any(json.loads('"' + value + '"') in {"", "BLOCKING_UNKNOWN"} for value in values):
            errors.append(f"BLOCKED_TASK_CONTRACT: every acceptance criterion needs concrete {field}")
    writers = {
        "requirements", "ux", "ui", "architect", "engineering_lead",
        "frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker",
    }
    if owner in writers and not list_field(text, "allowed_files"):
        errors.append("BLOCKED_TASK_CONTRACT: writing tasks need bounded allowed_files")
    validation = top_section(text, "validation")
    if not list_field(validation, "commands") and not list_field(validation, "manual"):
        errors.append("BLOCKED_TASK_CONTRACT: validation needs a command or manual check")
    if owner == "quality_governor":
        quality = top_section(text, "quality_review")
        if quoted_scalar(quality, "review_mode") != "INDEPENDENT":
            errors.append("BLOCKED_TASK_CONTRACT: Quality Governor review_mode must be INDEPENDENT")
        if quoted_scalar(quality, "gate") not in {"problem", "solution", "release_evidence"}:
            errors.append("BLOCKED_TASK_CONTRACT: Quality Governor needs a valid quality gate")
        if quoted_scalar(quality, "decision_question") in {"", "BLOCKING_UNKNOWN"}:
            errors.append("BLOCKED_TASK_CONTRACT: Quality Governor needs a decision_question")
        if not re.fullmatch(r"[a-f0-9]{64}", quoted_scalar(quality, "input_fingerprint")):
            errors.append("BLOCKED_TASK_CONTRACT: Quality Governor needs the routed input_fingerprint")
        if quoted_scalar(quality, "quality_case_ref") in {"", "BLOCKING_UNKNOWN"}:
            errors.append("BLOCKED_TASK_CONTRACT: Quality Governor needs quality_case_ref")
    return errors
