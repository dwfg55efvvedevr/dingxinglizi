#!/usr/bin/env python3
"""Shared parser and substantive Task Package contract validation."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Iterable

from project_layout import control_path
from review_planning import canonical_hash
from state_io import load_json_object


TASK_ID_PATTERN = re.compile(r"TASK-[A-Z0-9][A-Z0-9_-]*")
RUN_ID_PATTERN = re.compile(r"RUN-\d{8}T\d{6}Z-[a-f0-9]{6}")


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
    if integer_scalar(text, "schema_version") != 2:
        errors.append("BLOCKED_TASK_CONTRACT: schema_version must be 2")
    run_id = quoted_scalar(text, "run_id")
    if not RUN_ID_PATTERN.fullmatch(run_id):
        errors.append("BLOCKED_TASK_CONTRACT: run_id must reference a v2 project run")
    else:
        runs_root = control_path(root, "runs").resolve()
        run_path = (runs_root / run_id / "run.json").resolve()
        try:
            run_path.relative_to(runs_root)
        except ValueError:
            errors.append("BLOCKED_TASK_CONTRACT: run_id resolves outside the project run ledger")
        else:
            try:
                run_record = json.loads(run_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                errors.append("BLOCKED_TASK_CONTRACT: run_id has no valid run record")
            else:
                if run_record.get("run_id") != run_id or run_record.get("status") != "OPEN":
                    errors.append("BLOCKED_TASK_CONTRACT: run_id must reference the current OPEN run")
    source_input = quoted_scalar(text, "source_input_fingerprint")
    if not re.fullmatch(r"[a-f0-9]{64}", source_input):
        errors.append("BLOCKED_TASK_CONTRACT: source_input_fingerprint must be a routed SHA-256 fingerprint")
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
    task_type = quoted_scalar(text, "task_type")
    review = top_section(text, "review_contract")
    review_status = quoted_scalar(review, "status")
    if task_type in {"module_review", "cross_module_review"} or review_status != "NOT_APPLICABLE":
        errors.extend(_validate_review_contract(root, text, review, run_id, task_type))
    repair = top_section(text, "repair_contract")
    repair_status = quoted_scalar(repair, "status") if repair else ""
    if task_type in {"review_repair", "review_verification"} or repair_status not in {"", "NOT_APPLICABLE"}:
        if not repair:
            errors.append("BLOCKED_REPAIR_CONTRACT: repair lifecycle task is missing repair_contract")
        else:
            errors.extend(_validate_repair_contract(root, text, repair, run_id, task_type, owner))
    return errors


def _validate_review_contract(
    root: Path,
    text: str,
    section: str,
    run_id: str,
    task_type: str,
) -> list[str]:
    errors: list[str] = []
    if task_type not in {"module_review", "cross_module_review"}:
        return ["BLOCKED_REVIEW_CONTRACT: routed review_contract requires a review task_type"]
    if quoted_scalar(text, "stage") != "CODE_REVIEW":
        errors.append("BLOCKED_REVIEW_CONTRACT: review shard stage must be CODE_REVIEW")
    if quoted_scalar(section, "status") != "ROUTED":
        errors.append("BLOCKED_REVIEW_CONTRACT: status must be ROUTED")
    review_id = quoted_scalar(section, "review_id")
    if review_id != run_id:
        errors.append("BLOCKED_REVIEW_CONTRACT: review_id must match the Task Package run_id")
        return errors
    shard_id = quoted_scalar(section, "shard_id")
    mode = quoted_scalar(section, "mode")
    if mode not in {"review_only", "review_and_fix"}:
        errors.append("BLOCKED_REVIEW_CONTRACT: invalid review mode")
    if boolean_scalar(section, "source_write_authorized"):
        errors.append("BLOCKED_REVIEW_CONTRACT: review shards may not authorize business-source writes")
    for field in ("fresh_session_required", "compact_handoff_required", "session_attestation_required"):
        if not boolean_scalar(section, field):
            errors.append(f"BLOCKED_REVIEW_CONTRACT: {field} must be true")
    included = list_field(section, "included_files")
    if not included:
        errors.append("BLOCKED_REVIEW_CONTRACT: included_files must not be empty")
    allowed = list_field(text, "allowed_files")
    overlap = sorted(set(included) & set(allowed))
    if overlap:
        errors.append("BLOCKED_REVIEW_CONTRACT: review source appears in allowed_files: " + ", ".join(overlap))
    findings_output = quoted_scalar(section, "findings_output")
    if findings_output not in allowed:
        errors.append("BLOCKED_REVIEW_CONTRACT: findings_output must be the bounded allowed_files output")
    evidence_output = quoted_scalar(section, "evidence_output")
    if evidence_output not in allowed:
        errors.append("BLOCKED_REVIEW_CONTRACT: evidence_output must be a bounded allowed_files output")
    expected_evidence = f"evidence/reviews/{run_id}/{shard_id}.md"
    if evidence_output != expected_evidence:
        errors.append("BLOCKED_REVIEW_CONTRACT: evidence_output differs from the active shard evidence path")
    # The review section is already a bounded top-level slice. Parse the unique
    # nested budget scalars directly so indentation does not erase the block.
    context = section
    for maximum, estimated in (
        ("max_files", "estimated_files"),
        ("max_bytes", "estimated_bytes"),
        ("max_estimated_tokens", "estimated_tokens"),
    ):
        try:
            max_value = integer_scalar(context, maximum)
            estimate_value = integer_scalar(context, estimated)
        except ValueError as exc:
            errors.append(f"BLOCKED_REVIEW_CONTRACT: {exc}")
            continue
        if max_value <= 0 or estimate_value <= 0 or estimate_value > max_value:
            errors.append(f"BLOCKED_REVIEW_CONTRACT: {estimated} must be positive and <= {maximum}")
    try:
        review_state = load_json_object(control_path(root, Path("runs") / review_id / "review" / "review.json"))
        plan = load_json_object(control_path(root, Path("runs") / review_id / "review" / "plan.json"))
        inventory = load_json_object(control_path(root, Path("runs") / review_id / "review" / "inventory.json"))
        trust = load_json_object(control_path(root, Path("runs") / review_id / "review" / "trust.json"))
    except ValueError as exc:
        errors.append(f"BLOCKED_REVIEW_CONTRACT: active review state is invalid: {exc}")
        return errors
    shards = list(plan.get("primary_shards", [])) + list(plan.get("cross_cut_shards", []))
    matches = [item for item in shards if isinstance(item, dict) and item.get("shard_id") == shard_id]
    if len(matches) != 1:
        errors.append("BLOCKED_REVIEW_CONTRACT: shard_id is not uniquely present in the active plan")
        return errors
    shard = matches[0]
    expected_task_type = "cross_module_review" if shard.get("shard_kind") == "CROSS_CUT" else "module_review"
    if task_type != expected_task_type:
        errors.append("BLOCKED_REVIEW_CONTRACT: task_type does not match shard kind")
    expected = {
        "target_fingerprint": review_state.get("target_fingerprint"),
        "repository_manifest_fingerprint": inventory.get("manifest_fingerprint"),
        "review_plan_fingerprint": plan.get("plan_fingerprint"),
        "shard_input_fingerprint": canonical_hash({
            "run_id": review_id,
            "target_fingerprint": review_state.get("target_fingerprint"),
            "plan_fingerprint": plan.get("plan_fingerprint"),
            "shard": shard,
        }),
        "trust_policy_fingerprint": trust.get("policy_fingerprint"),
    }
    for field, value in expected.items():
        if quoted_scalar(section, field) != value:
            errors.append(f"BLOCKED_REVIEW_CONTRACT: {field} is stale or forged")
    if list_field(section, "trusted_instruction_files") != list(trust.get("trusted_instruction_files", [])):
        errors.append("BLOCKED_REVIEW_CONTRACT: trusted instruction files differ from the active trust policy")
    if boolean_scalar(section, "repository_execution_authorized") != bool(trust.get("repository_execution_authorized")):
        errors.append("BLOCKED_REVIEW_CONTRACT: repository execution authorization differs from the active trust policy")
    if quoted_scalar(section, "default_execution_policy") != trust.get("default_execution_policy"):
        errors.append("BLOCKED_REVIEW_CONTRACT: default execution policy differs from the active trust policy")
    if included != list(shard.get("files", [])):
        errors.append("BLOCKED_REVIEW_CONTRACT: included_files differ from the active shard")
    indexed = {
        str(item.get("path")): str(item.get("object_id"))
        for item in inventory.get("entries", []) if isinstance(item, dict)
    }
    expected_objects = {path: indexed[path] for path in included if path in indexed}
    try:
        objects = json.loads(quoted_scalar(section, "pinned_file_objects_json"))
    except json.JSONDecodeError:
        errors.append("BLOCKED_REVIEW_CONTRACT: pinned_file_objects_json is invalid")
    else:
        if objects != expected_objects:
            errors.append("BLOCKED_REVIEW_CONTRACT: pinned file objects differ from the target inventory")
    return errors


def _validate_repair_contract(
    root: Path,
    text: str,
    section: str,
    run_id: str,
    task_type: str,
    owner: str,
) -> list[str]:
    errors: list[str] = []
    if task_type not in {"review_repair", "review_verification"}:
        return ["BLOCKED_REPAIR_CONTRACT: routed repair_contract requires repair lifecycle task_type"]
    if quoted_scalar(text, "stage") != "CODE_REVIEW":
        errors.append("BLOCKED_REPAIR_CONTRACT: repair lifecycle stage must be CODE_REVIEW")
    if quoted_scalar(section, "status") != "ROUTED":
        errors.append("BLOCKED_REPAIR_CONTRACT: status must be ROUTED")
    if quoted_scalar(section, "review_id") != run_id:
        errors.append("BLOCKED_REPAIR_CONTRACT: review_id must match Task Package run_id")
        return errors
    plan_id = quoted_scalar(section, "repair_plan_id")
    try:
        store = load_json_object(control_path(root, Path("runs") / run_id / "review" / "repairs.json"))
    except ValueError as exc:
        return [f"BLOCKED_REPAIR_CONTRACT: active repair state is invalid: {exc}"]
    matches = [item for item in store.get("plans", []) if isinstance(item, dict) and item.get("repair_plan_id") == plan_id]
    if len(matches) != 1:
        return ["BLOCKED_REPAIR_CONTRACT: repair_plan_id is not uniquely active"]
    plan = matches[0]
    phase = quoted_scalar(section, "phase")
    expected_phase = "REPAIR" if task_type == "review_repair" else "REREVIEW"
    if phase != expected_phase:
        errors.append("BLOCKED_REPAIR_CONTRACT: phase does not match task_type")
    expected_owner = plan.get("fixer_id") if phase == "REPAIR" else plan.get("reviewer_id")
    if owner != expected_owner:
        errors.append("BLOCKED_REPAIR_CONTRACT: owner does not match governed repair plan")
    authorization_fingerprint = canonical_hash({
        key: plan[key] for key in (
            "repair_plan_id", "round", "finding_ids", "finding_paths", "fixer_id", "reviewer_id",
            "allowed_files", "source_write_authorized", "target_fingerprint", "authorization",
        )
    })
    if plan.get("authorization_fingerprint") != authorization_fingerprint:
        errors.append("BLOCKED_REPAIR_CONTRACT: stored repair authorization fingerprint is invalid")
    if quoted_scalar(section, "repair_plan_fingerprint") != authorization_fingerprint:
        errors.append("BLOCKED_REPAIR_CONTRACT: repair_plan_fingerprint is stale or forged")
    if quoted_scalar(section, "target_fingerprint") != plan.get("target_fingerprint"):
        errors.append("BLOCKED_REPAIR_CONTRACT: target_fingerprint differs from repair authorization")
    if list_field(section, "finding_ids") != list(plan.get("finding_ids", [])):
        errors.append("BLOCKED_REPAIR_CONTRACT: finding_ids differ from repair authorization")
    if list_field(section, "allowed_source_files") != list(plan.get("allowed_files", [])):
        errors.append("BLOCKED_REPAIR_CONTRACT: allowed_source_files differ from repair authorization")
    source_write = boolean_scalar(section, "source_write_authorized")
    if source_write != (phase == "REPAIR"):
        errors.append("BLOCKED_REPAIR_CONTRACT: source_write_authorized does not match phase")
    evidence_output = quoted_scalar(section, "evidence_output")
    suffix = "repair" if phase == "REPAIR" else "rereview"
    expected_evidence = f"evidence/reviews/{run_id}/{plan_id}.{suffix}.md"
    if evidence_output != expected_evidence:
        errors.append("BLOCKED_REPAIR_CONTRACT: evidence_output differs from governed path")
    expected_allowed = (
        sorted(set(plan.get("allowed_files", [])) | {expected_evidence})
        if phase == "REPAIR" else [expected_evidence]
    )
    if list_field(text, "allowed_files") != expected_allowed:
        errors.append("BLOCKED_REPAIR_CONTRACT: Task Package allowed_files differ from governed contract")
    return errors
