#!/usr/bin/env python3
"""Preview or persist the smallest current-stage role plan; never starts Agents."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import CANONICAL_STATES, INTERRUPT_STATES, project_root, read_text
from dispatch_receipt import validate_dispatch_receipt
from project_layout import control_path
from role_routing import route_roles, validate_role_policy
from state_io import atomic_write_text, safe_project_path
from task_contract import list_field, quoted_scalar, top_section, validate_task_contract


STAGE_INPUTS = {
    "BACKLOG": ["docs/00-project-context.md"],
    "DISCOVERY": ["docs/00-project-context.md", "docs/01-domain-rules.md", "docs/04-prd.md"],
    "REQUIREMENTS_APPROVED": [
        "docs/00-project-context.md", "docs/01-domain-rules.md", "docs/02-glossary.md", "docs/04-prd.md",
    ],
    "PRODUCT_APPROVED": [
        "docs/03-role-journey-matrix.md", "docs/04-prd.md", "docs/checklists/product-completeness.md",
    ],
    "UX_READY": ["docs/03-role-journey-matrix.md", "docs/04-prd.md", "docs/06-ux-spec.md"],
    "UI_READY": ["docs/04-prd.md", "docs/06-ux-spec.md", "docs/07-design-system.md"],
    "ARCHITECTURE_READY": [
        "docs/04-prd.md", "docs/05-state-permission-matrix.md", "docs/08-system-design.md",
        "docs/09-api-data-contract.md",
    ],
    "READY_FOR_BUILD": [
        "docs/00-project-context.md", "docs/04-prd.md", "docs/03-role-journey-matrix.md",
        "docs/05-state-permission-matrix.md", "docs/06-ux-spec.md", "docs/07-design-system.md",
        "docs/08-system-design.md", "docs/09-api-data-contract.md",
    ],
    "IN_DEVELOPMENT": [
        "docs/04-prd.md", "docs/05-state-permission-matrix.md", "docs/07-design-system.md",
        "docs/08-system-design.md", "docs/09-api-data-contract.md",
    ],
    "CODE_REVIEW": [
        "docs/04-prd.md", "docs/05-state-permission-matrix.md", "docs/08-system-design.md",
        "docs/09-api-data-contract.md", "docs/10-test-plan.md",
    ],
    "READY_FOR_QA": ["docs/04-prd.md", "docs/09-api-data-contract.md", "docs/10-test-plan.md"],
    "QA_PASS": ["docs/10-test-plan.md", "docs/checklists/solution-challenge.md"],
    "RELEASE_READY": ["docs/10-test-plan.md", "docs/checklists/quality-case.md"],
    "DONE": ["docs/10-test-plan.md", "docs/checklists/quality-case.md"],
    "BLOCKED": ["docs/00-project-context.md"],
    "REWORK_REQUIREMENTS": ["docs/00-project-context.md", "docs/01-domain-rules.md", "docs/04-prd.md"],
    "REWORK_PRODUCT": ["docs/03-role-journey-matrix.md", "docs/checklists/product-completeness.md"],
    "REWORK_UX": ["docs/06-ux-spec.md"],
    "REWORK_UI": ["docs/07-design-system.md"],
    "REWORK_ARCHITECTURE": [
        "docs/05-state-permission-matrix.md", "docs/08-system-design.md", "docs/09-api-data-contract.md",
    ],
    "REWORK_ENGINEERING": ["docs/04-prd.md", "docs/08-system-design.md", "docs/09-api-data-contract.md"],
    "REWORK_QA": ["docs/10-test-plan.md"],
}


def source_fingerprint(root: Path, stage: str) -> str:
    digest = hashlib.sha256()
    if stage not in STAGE_INPUTS:
        raise ValueError(f"unsupported fingerprint stage: {stage}")
    for relative in STAGE_INPUTS[stage]:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        payload = path.read_bytes() if path.is_file() else b"MISSING"
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def write_runtime_state(root: Path, status: dict, plan: dict) -> None:
    """Persist quota and role plan together, rolling back status if the second replace fails."""
    status_path = safe_project_path(root, "docs/project-status.json")
    plan_path = control_path(root, "orchestration/role-plan.json")
    status_bytes = status_path.read_bytes()
    execution = status.setdefault("execution_control", {})
    maximum = int(plan["max_active_subagents"])
    sessions = execution.get("active_sessions", [])
    if not isinstance(sessions, list):
        raise ValueError("docs/project-status.json: active_sessions must be a list")
    if len(sessions) > maximum:
        raise ValueError(
            f"cannot switch to {plan['quota_mode']}: {len(sessions)} active sessions exceed limit {maximum}"
        )
    execution["quota_mode"] = plan["quota_mode"]
    execution["max_active_subagents"] = maximum
    status["updated_at"] = datetime.now(timezone.utc).isoformat()
    status["updated_by"] = "orchestrator"
    persisted = dict(plan)
    persisted["generated_at"] = datetime.now(timezone.utc).isoformat()
    status_payload = json.dumps(status, ensure_ascii=False, indent=2) + "\n"
    plan_payload = json.dumps(persisted, ensure_ascii=False, indent=2) + "\n"
    try:
        atomic_write_text(status_path, status_payload, allowed_root=root)
        atomic_write_text(plan_path, plan_payload, allowed_root=root)
    except (OSError, ValueError):
        atomic_write_text(status_path, status_bytes.decode("utf-8"), allowed_root=root)
        raise


def load_current_plan(root: Path) -> dict:
    path = control_path(root, "orchestration/role-plan.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def validate_completed_handoffs(
    root: Path,
    stage: str,
    complexity: str,
    quota_mode: str,
    signals: list[str],
    completed_roles: list[str],
    assignments: list[str],
    current_plan: dict,
) -> None:
    """Require a completed Task Package from the current plan before advancing a wave."""
    mapping: dict[str, str] = {}
    for assignment in assignments:
        role, separator, relative = assignment.partition("=")
        if not separator or not role or not relative or role in mapping:
            raise ValueError("--completed-task must be unique ROLE=PROJECT_RELATIVE_TASK_PATH")
        mapping[role] = relative
    if set(mapping) != set(completed_roles):
        raise ValueError("every --completed-role needs exactly one matching --completed-task ROLE=PATH")
    if not completed_roles:
        return
    if current_plan.get("status") != "ROUTED" or current_plan.get("current_stage") != stage:
        raise ValueError("completed handoff must reference the current routed stage")
    if current_plan.get("complexity") != complexity:
        raise ValueError("completed handoff cannot change the current routing complexity")
    if current_plan.get("quota_mode") != quota_mode:
        raise ValueError("completed handoff cannot change the current routing quota mode")
    if current_plan.get("signals") != signals:
        raise ValueError("completed handoff signals do not match the current routing cycle")
    if not current_plan.get("routing_cycle_id"):
        raise ValueError("completed handoff has no current routing cycle lineage")
    for role in completed_roles:
        if role not in current_plan.get("required_now", []):
            raise ValueError(f"completed role was not required_now in the current persisted plan: {role}")
        path = (root / mapping[role]).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"completed handoff task is outside the project: {mapping[role]}") from exc
        if not path.is_file():
            raise ValueError(f"completed handoff task does not exist: {mapping[role]}")
        text = path.read_text(encoding="utf-8")
        if quoted_scalar(text, "owner") != role or quoted_scalar(text, "stage") != stage:
            raise ValueError(f"completed handoff owner/stage does not match: {mapping[role]}")
        if quoted_scalar(text, "status") != "COMPLETED":
            raise ValueError(f"completed handoff task status must be COMPLETED: {mapping[role]}")
        role_execution = top_section(text, "role_execution")
        if quoted_scalar(role_execution, "role_plan_fingerprint") != current_plan.get("plan_fingerprint"):
            raise ValueError(f"completed handoff task does not reference the current role plan: {mapping[role]}")
        contract_errors = validate_task_contract(root, text, role, allowed_statuses=("COMPLETED",))
        if contract_errors:
            raise ValueError(
                f"completed handoff Task Contract is invalid: {mapping[role]}: "
                + "; ".join(contract_errors)
            )
        receipt_errors = validate_dispatch_receipt(root, text)
        if receipt_errors:
            raise ValueError(
                f"completed handoff has no matching dispatch READY receipt: {mapping[role]}: "
                + "; ".join(receipt_errors)
            )
        handoff = top_section(text, "handoff")
        if quoted_scalar(handoff, "conclusion") not in {"COMPLETED", "PASS", "PASS_WITH_ACCEPTED_RISKS"}:
            raise ValueError(f"completed handoff needs a successful conclusion: {mapping[role]}")
        references = list_field(handoff, "artifacts") + list_field(handoff, "evidence")
        if not references:
            raise ValueError(f"completed handoff needs artifacts or evidence: {mapping[role]}")
        for reference in references:
            evidence_path = (root / reference).resolve()
            try:
                evidence_path.relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(f"completed handoff reference is outside the project: {reference}") from exc
            if not evidence_path.is_file():
                raise ValueError(f"completed handoff reference does not exist: {reference}")


def route_project(
    root: Path,
    *,
    stage: str | None = None,
    quota: str | None = None,
    signals: list[str] | None = None,
    completed_roles: list[str] | None = None,
    completed_tasks: list[str] | None = None,
    write: bool = False,
) -> dict:
    """Route one initialized project without duplicating CLI-only orchestration logic."""
    signals = signals or []
    completed_roles = completed_roles or []
    completed_tasks = completed_tasks or []
    status = json.loads(read_text(root / "docs/project-status.json"))
    policy = json.loads(read_text(control_path(root, "orchestration/role-routing-policy.json")))
    validate_role_policy(policy)
    selected_stage = stage or status.get("current_state")
    selected_quota = quota or status.get("execution_control", {}).get("quota_mode") or policy["default_quota_mode"]
    fingerprint = source_fingerprint(root, selected_stage)
    normalized_signals = sorted({value.strip().lower() for value in signals if value.strip()})
    current_plan = load_current_plan(root)
    validate_completed_handoffs(
        root, selected_stage, status.get("complexity", ""), selected_quota, normalized_signals,
        completed_roles, completed_tasks, current_plan,
    )
    same_cycle = bool(
        current_plan.get("status") == "ROUTED"
        and current_plan.get("current_stage") == selected_stage
        and current_plan.get("complexity") == status.get("complexity")
        and current_plan.get("quota_mode") == selected_quota
        and current_plan.get("signals") == normalized_signals
        and current_plan.get("input_fingerprint") == fingerprint
        and current_plan.get("routing_cycle_id")
    )
    if completed_roles:
        cumulative_completed = sorted(set(current_plan.get("completed_roles", [])) | set(completed_roles))
        cycle_id = str(current_plan["routing_cycle_id"])
    elif same_cycle:
        cumulative_completed = sorted(set(current_plan.get("completed_roles", [])))
        cycle_id = str(current_plan["routing_cycle_id"])
    else:
        cumulative_completed = []
        cycle_id = ""
    gate_name = {"DISCOVERY": "problem", "READY_FOR_BUILD": "solution", "QA_PASS": "release_evidence"}.get(selected_stage)
    gate_record = status.get("quality_gates", {}).get(gate_name, {}) if gate_name else {}
    plan = route_roles(
        complexity=status.get("complexity", ""), stage=selected_stage, quota_mode=selected_quota,
        signals=normalized_signals, completed_roles=cumulative_completed,
        input_fingerprint=fingerprint, quality_gate_record=gate_record,
        routing_cycle_id=cycle_id,
    )
    if write:
        write_runtime_state(root, status, plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--stage", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES))
    parser.add_argument("--quota", choices=["economy", "balanced", "quality_first"])
    parser.add_argument("--signal", action="append", default=[])
    parser.add_argument("--completed-role", action="append", default=[], help="Role with a persisted handoff for these exact inputs")
    parser.add_argument(
        "--completed-task", action="append", default=[], metavar="ROLE=PATH",
        help="Completed Task Package proving the role handoff; repeat with --completed-role",
    )
    parser.add_argument("--write", action="store_true", help="Persist the active control-plane role-plan.json")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        plan = route_project(
            root, stage=args.stage, quota=args.quota, signals=args.signal,
            completed_roles=args.completed_role, completed_tasks=args.completed_task,
            write=args.write,
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
