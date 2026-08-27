#!/usr/bin/env python3
"""Preflight a generated Task Package route and required capability readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import project_root, read_text
from check_project_status import check as check_project_status
from dispatch_receipt import record_dispatch_receipt
from model_routing import route_fingerprint, route_with_inventory, validate_model_policy
from role_routing import POLICY_VERSION as ROLE_POLICY_VERSION, role_plan_fingerprint, validate_role_policy
from route_roles import source_fingerprint
from resolve_capabilities import installed_skill, load_json, mcp_config_details
from task_contract import boolean_scalar, integer_scalar, list_field, quoted_scalar, top_section, validate_task_contract


def check(root: Path, task_path: Path, available_models: list[str] | None = None) -> list[str]:
    text = read_text(task_path)
    risk = top_section(text, "risk_profile")
    role_execution = top_section(text, "role_execution")
    execution = top_section(text, "execution_profile")
    capabilities = top_section(text, "capability_requirements")
    status = load_json(root / "docs/project-status.json")
    validate_model_policy(load_json(root / ".codex/orchestration/model-routing-policy.json"))
    validate_role_policy(load_json(root / ".codex/orchestration/role-routing-policy.json"))
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
    owner = quoted_scalar(text, "owner")
    expected = route_with_inventory(
        complexity=status.get("complexity", ""),
        task_type=quoted_scalar(text, "task_type"),
        role=owner,
        risk_flags=list_field(risk, "flags"),
        failed_attempts=integer_scalar(risk, "failed_attempts"),
        failure_type=quoted_scalar(risk, "failure_type"),
        available_models=runtime_models,
        availability_source=availability_source,
        availability_verified=availability_verified,
    )
    errors: list[str] = []
    errors.extend(validate_task_contract(root, text, owner))
    role_plan = load_json(root / ".codex/orchestration/role-plan.json")
    if role_plan.get("status") != "ROUTED":
        errors.append("BLOCKED_ROLE_PLAN: run route_roles.py --write before dispatch")
    else:
        stored_fingerprint = role_plan.get("plan_fingerprint")
        if stored_fingerprint != role_plan_fingerprint(role_plan):
            errors.append("ROLE_ROUTE_MISMATCH: persisted role plan fingerprint is invalid")
        if quoted_scalar(role_execution, "policy_version") != ROLE_POLICY_VERSION:
            errors.append("ROLE_ROUTE_MISMATCH: Task Package role policy version is stale")
        if quoted_scalar(role_execution, "role_plan_fingerprint") != stored_fingerprint:
            errors.append("ROLE_ROUTE_MISMATCH: Task Package does not reference the current role plan")
        task_stage = quoted_scalar(text, "stage")
        if task_stage != role_plan.get("current_stage"):
            errors.append("ROLE_ROUTE_MISMATCH: Task Package stage differs from the current role plan")
        current_input_fingerprint = source_fingerprint(root, task_stage)
        if role_plan.get("input_fingerprint") != current_input_fingerprint:
            errors.append("STALE_ROLE_PLAN: stage inputs changed; rerun route_roles.py and create a new Task Package")
        quality_gate = role_plan.get("quality_gate")
        if role_plan.get("quality_review_status") == "REUSE_APPROVAL" and quality_gate:
            quality_record = status.get("quality_gates", {}).get(quality_gate, {})
            if (
                quality_record.get("status") != "APPROVED"
                or quality_record.get("input_fingerprint") != current_input_fingerprint
            ):
                errors.append("STALE_QUALITY_APPROVAL: quality gate no longer matches current inputs")
        stage_errors, _ = check_project_status(root, task_stage)
        errors.extend(f"BLOCKED_STAGE: {item}" for item in stage_errors)
        if owner == "orchestrator":
            errors.append("BLOCKED_ROLE_PLAN: Orchestrator must run in the main thread, not as a spawned Agent")
        else:
            workers = {"frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker"}
            worker_allowed = (
                owner in workers
                and owner in role_plan.get("delegable_workers", [])
                and "engineering_lead" in role_plan.get("required_now", [])
                and role_plan.get("max_concurrent_workers", 0) >= 1
            )
            if owner not in role_plan.get("required_now", []) and not worker_allowed:
                errors.append(f"BLOCKED_ROLE_PLAN: owner is not required_now or delegable: {owner}")
            if owner in workers:
                if quoted_scalar(text, "return_to") != "engineering_lead":
                    errors.append("BLOCKED_ROLE_PLAN: Worker must return_to engineering_lead")
                if quoted_scalar(text, "reviewer") != "engineering_lead":
                    errors.append("BLOCKED_ROLE_PLAN: Worker reviewer must be engineering_lead")
                if boolean_scalar(text, "may_spawn_agents") or boolean_scalar(text, "may_spawn_workers"):
                    errors.append("BLOCKED_ROLE_PLAN: Worker may not spawn Agents or Workers")
        waves = role_plan.get("execution_waves", [])
        maximum = role_plan.get("max_active_subagents", 0)
        if not isinstance(waves, list) or any(not isinstance(wave, list) for wave in waves):
            errors.append("ROLE_ROUTE_MISMATCH: execution_waves is invalid")
        elif any(len(wave) > maximum for wave in waves):
            errors.append("BLOCKED_ROLE_BUDGET: execution wave exceeds max_active_subagents")
        wave_index = role_plan.get("current_wave", 0)
        current_wave = waves[wave_index] if isinstance(wave_index, int) and 0 <= wave_index < len(waves) else []
        worker_delegation = owner in role_plan.get("delegable_workers", []) and "engineering_lead" in current_wave
        if owner not in current_wave and not worker_delegation:
            errors.append(f"BLOCKED_ROLE_PLAN: owner is not in the current execution wave: {owner}")
        active_sessions = status.get("execution_control", {}).get("active_sessions", [])
        task_id = quoted_scalar(text, "task_id")
        already_claimed = any(
            item.get("task_id") == task_id and item.get("role") == owner
            for item in active_sessions if isinstance(item, dict)
        )
        duplicate_role = any(
            item.get("role") == owner and item.get("task_id") != task_id
            for item in active_sessions if isinstance(item, dict)
        )
        if duplicate_role:
            errors.append(f"BLOCKED_DUPLICATE_ROLE: {owner} already has a different active task")
        if not already_claimed and len(active_sessions) >= maximum:
            errors.append("BLOCKED_ROLE_BUDGET: no subagent slot is available for this owner")
        allowed_active = set(current_wave) | set(role_plan.get("delegable_workers", []))
        unexpected_active = sorted({
            item.get("role") for item in active_sessions
            if isinstance(item, dict) and item.get("role") not in allowed_active
        })
        if unexpected_active:
            errors.append("BLOCKED_ROLE_PLAN: active role is outside the current wave: " + ", ".join(unexpected_active))
        active_roles = {item.get("role") for item in active_sessions if isinstance(item, dict)} | {owner}
        if owner in {"frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker"}:
            valid_parent = any(
                item.get("role") == "engineering_lead" and item.get("parent_role") == "orchestrator"
                for item in active_sessions if isinstance(item, dict)
            )
            if not valid_parent:
                errors.append("BLOCKED_WORKER_PARENT: an active Engineering Lead owned by Orchestrator is required")
        if {"engineering_lead", "qa"}.issubset(active_roles):
            errors.append("BLOCKED_ROLE_PLAN: Engineering Lead and final QA cannot overlap")
        reviewer = quoted_scalar(text, "reviewer")
        if reviewer != "engineering_lead" and reviewer in active_roles and reviewer != owner:
            errors.append("BLOCKED_ROLE_PLAN: reviewer activated before owner handoff")
        if "qa" in role_plan.get("required_now", []) and "engineering_lead" in role_plan.get("required_now", []):
            errors.append("BLOCKED_ROLE_PLAN: final QA and Engineering Lead cannot be active together")
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
    parser.add_argument(
        "--record-ready", action="store_true",
        help="Persist a READY receipt after every preflight check passes",
    )
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
    if args.record_ready:
        try:
            receipt = record_dispatch_receipt(root, read_text(task_path))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"RECORDED: {receipt.relative_to(root)}")
    print("READY: route matches policy and required capabilities are available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
