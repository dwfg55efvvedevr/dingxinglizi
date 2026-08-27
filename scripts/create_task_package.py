#!/usr/bin/env python3
"""Create a non-overwriting YAML task package with the required delivery contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import CANONICAL_STATES, INTERRUPT_STATES, REQUIRED_AGENTS, project_root
from model_routing import route_fingerprint, route_with_inventory, validate_model_policy
from role_routing import POLICY_VERSION as ROLE_POLICY_VERSION


WORKERS = {"frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker"}
CAPABILITY_ID = re.compile(r"[A-Za-z0-9_-]+")


def quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def yaml_list(values: list[str], indent: int = 2) -> str:
    if not values:
        return " []"
    prefix = " " * indent
    return "\n" + "\n".join(f"{prefix}- {quoted(value)}" for value in values)


def create(
    root: Path,
    task_id: str,
    owner: str,
    reviewer: str,
    objective: str,
    stage: str,
    return_to: str,
    task_type: str = "implementation",
    risk_flags: list[str] | None = None,
    failed_attempts: int = 0,
    failure_type: str = "none",
    required_capabilities: list[str] | None = None,
    optional_capabilities: list[str] | None = None,
    available_models: list[str] | None = None,
) -> Path:
    task_id = task_id.upper()
    if not re.fullmatch(r"TASK-[A-Z0-9][A-Z0-9_-]*", task_id):
        raise ValueError("task-id must look like TASK-001 or TASK-AUTH-01")
    if owner == reviewer:
        raise ValueError("owner and reviewer must be different")
    valid_roles = set(REQUIRED_AGENTS) | WORKERS
    if owner not in valid_roles:
        raise ValueError(f"unsupported owner role: {owner}")
    if reviewer not in set(REQUIRED_AGENTS):
        raise ValueError(f"reviewer must be a professional role, got: {reviewer}")
    if stage not in set(CANONICAL_STATES) | INTERRUPT_STATES:
        raise ValueError(f"unsupported project stage: {stage}")
    if not objective.strip() or objective == "BLOCKING_UNKNOWN":
        raise ValueError("objective must be a concrete, non-empty outcome")
    if owner in WORKERS and return_to != "engineering_lead":
        raise ValueError("temporary Workers must return_to engineering_lead")
    if owner not in WORKERS and return_to != "orchestrator":
        raise ValueError("professional roles must return_to orchestrator")
    status_path = root / "docs/project-status.json"
    if not status_path.is_file():
        raise ValueError("Project is not initialized: docs/project-status.json is missing")
    policy_path = root / ".codex/orchestration/model-routing-policy.json"
    try:
        validate_model_policy(json.loads(policy_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid executable model routing policy: {exc}") from exc
    destination = root / "tasks" / f"{task_id}.yaml"
    if destination.exists():
        raise ValueError(f"Task package already exists and will not be overwritten: {destination}")
    project_name = root.name
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"docs/project-status.json is invalid; routing fails closed: {exc}") from exc
    project_name = status.get("project", project_name)
    complexity = status.get("complexity")
    if complexity not in {"Simple", "Standard", "Complex"}:
        raise ValueError("docs/project-status.json has no valid Simple/Standard/Complex complexity")
    role_plan_path = root / ".codex/orchestration/role-plan.json"
    try:
        role_plan = json.loads(role_plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        role_plan = {"status": "NOT_ROUTED", "plan_fingerprint": "NOT_ROUTED", "quota_mode": "economy"}
    if role_plan.get("status") == "ROUTED" and owner != "orchestrator":
        worker_allowed = (
            owner in WORKERS
            and owner in role_plan.get("delegable_workers", [])
            and "engineering_lead" in role_plan.get("required_now", [])
            and role_plan.get("max_concurrent_workers", 0) >= 1
        )
        if owner not in role_plan.get("required_now", []) and not worker_allowed:
            raise ValueError(f"owner {owner} is not required_now or delegable in the current role plan")
        if stage != role_plan.get("current_stage"):
            raise ValueError("Task Package stage does not match the current role plan stage")
    inventory_path = root / ".codex/orchestration/runtime-inventory.json"
    inventory: dict[str, object] = {}
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    if available_models:
        runtime_models = sorted(set(available_models))
        availability_source = "verified_runtime_snapshot"
        availability_verified = True
    else:
        runtime_models = sorted(set(inventory.get("available_models", []))) if isinstance(inventory.get("available_models"), list) else []
        availability_verified = inventory.get("status") == "VERIFIED" and bool(runtime_models)
        availability_source = "verified_runtime_snapshot" if availability_verified else "unverified_runtime_inventory"
    route = route_with_inventory(
        complexity=complexity,
        task_type=task_type,
        role=owner,
        risk_flags=risk_flags or [],
        failed_attempts=failed_attempts,
        failure_type=failure_type,
        available_models=runtime_models,
        availability_source=availability_source,
        availability_verified=availability_verified,
    )
    required_capabilities = sorted(set(required_capabilities or []))
    optional_capabilities = sorted(set(optional_capabilities or []))
    for capability_id in required_capabilities + optional_capabilities:
        if not CAPABILITY_ID.fullmatch(capability_id):
            raise ValueError(
                f"invalid capability id {capability_id!r}; use only letters, digits, underscore, and hyphen"
            )
    may_spawn_workers = "true" if owner == "engineering_lead" else "false"
    content = f'''task_id: {quoted(task_id)}
project: {quoted(project_name)}
stage: {quoted(stage)}
status: "DRAFT"
owner: {quoted(owner)}
reviewer: {quoted(reviewer)}
return_to: {quoted(return_to)}
may_spawn_agents: false
may_spawn_workers: {may_spawn_workers}
priority: "P2"
objective: {quoted(objective)}
task_type: {quoted(task_type)}
role_execution:
  policy_version: {quoted(ROLE_POLICY_VERSION)}
  role_plan_fingerprint: {quoted(str(role_plan.get('plan_fingerprint') or 'NOT_ROUTED'))}
  status: {quoted(str(role_plan.get('status') or 'NOT_ROUTED'))}
  quota_mode: {quoted(str(role_plan.get('quota_mode') or 'economy'))}
  activation_reasons:{yaml_list(role_plan.get('activation_reasons', {}).get(owner, []) or (["delegated-by:engineering_lead", "signal:implementation_workers"] if owner in WORKERS else []), 4)}
  merged_responsibilities:{yaml_list(role_plan.get('merged_responsibilities', {}).get(owner, []), 4)}
  reviewer_activation: "deferred_until_owner_handoff"
  concurrency_slot: 1
risk_profile:
  flags:{yaml_list(route['risk_flags'], 4)}
  failed_attempts: {failed_attempts}
  failure_type: {quoted(failure_type)}
execution_profile:
  policy_version: {quoted(route['policy_version'])}
  route_fingerprint: {quoted(route_fingerprint(route))}
  routing_mode: {quoted(route['routing_mode'])}
  availability_source: {quoted(route['availability_source'])}
  availability_verified: {str(route['availability_verified']).lower()}
  available_models:{yaml_list(route['available_models'], 4)}
  status: {quoted(route['status'])}
  capability_tier: {quoted(route['capability_tier'])}
  preferred_model: {quoted(route['preferred_model'])}
  selected_model: {quoted(route['selected_model'])}
  model_reasoning_effort: {quoted(route['model_reasoning_effort'])}
  fallback_models:{yaml_list(route['fallback_models'], 4)}
  routing_reasons:{yaml_list(route['routing_reasons'], 4)}
  attempt: {failed_attempts + 1}
  max_attempts: {route['max_attempts']}
  downgrade_policy: {quoted(route['downgrade_policy'])}
  escalation_history: []
quality_review:
  gate: {quoted(str(role_plan.get('quality_gate') or 'NOT_APPLICABLE'))}
  review_mode: {quoted('INDEPENDENT' if owner == 'quality_governor' else 'NOT_APPLICABLE')}
  decision_question: "BLOCKING_UNKNOWN"
  input_fingerprint: {quoted(str(role_plan.get('input_fingerprint') or 'BLOCKING_UNKNOWN'))}
  selected_lenses: []
  adversarial_tests: []
  quality_case_ref: "BLOCKING_UNKNOWN"
capability_requirements:
  required:{yaml_list(required_capabilities, 4)}
  optional:{yaml_list(optional_capabilities, 4)}
  permission_ceiling: "read"
  provisioning_status: "PENDING"
  resolved_skills: []
  resolved_mcp_servers: []
  blocked: []
business_context:
  value: "BLOCKING_UNKNOWN"
  affected_roles: []
  affected_objects: []
  rule_refs: []
input_documents:
  - "docs/00-project-context.md"
  - "docs/01-domain-rules.md"
  - "docs/02-glossary.md"
  - "docs/project-status.json"
dependencies: []
scope: []
out_of_scope: []
deliverables: []
acceptance_criteria:
  - id: "AC-000"
    given: "BLOCKING_UNKNOWN"
    when: "BLOCKING_UNKNOWN"
    then: "BLOCKING_UNKNOWN"
    evidence: "BLOCKING_UNKNOWN"
allowed_files: []
forbidden:
  - "Do not change approved scope, business rules, permissions, contracts, dependencies, or external systems without Orchestrator routing."
  - "Do not perform production deployment, external messaging, purchases, credential use, destructive actions, or irreversible migrations without explicit authorization."
validation:
  commands: []
  manual: []
  evidence_locations: []
assumptions_and_risks: []
handoff:
  conclusion: "BLOCKED"
  inputs_checked: []
  artifacts: []
  evidence: []
  deviations: []
  downstream_decisions: []
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--stage", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES), default="BACKLOG")
    parser.add_argument("--return-to", default="orchestrator")
    parser.add_argument("--task-type", default="implementation")
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--failed-attempts", type=int, default=0)
    parser.add_argument("--failure-type", default="none")
    parser.add_argument("--required-capability", action="append", default=[])
    parser.add_argument("--optional-capability", action="append", default=[])
    parser.add_argument("--available-model", action="append", default=[], help="Runtime-verified model slug; repeat as needed")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        destination = create(
            root, args.task_id, args.owner, args.reviewer, args.objective, args.stage, args.return_to,
            args.task_type, args.risk, args.failed_attempts, args.failure_type,
            args.required_capability, args.optional_capability,
            args.available_model,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Created task package: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
