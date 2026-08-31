#!/usr/bin/env python3
"""Create a non-overwriting YAML task package with the required delivery contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import CANONICAL_STATES, INTERRUPT_STATES, REQUIRED_AGENTS, project_root
from model_routing import (
    KNOWN_TASK_TYPES, PLATFORM_POLICY_VERSION, route_fingerprint, route_with_inventory,
    route_with_platform_manifest, route_without_platform_manifest, validate_model_policy,
)
from platform_runtime import load_runtime_manifest
from project_layout import control_path
from role_routing import POLICY_VERSION as ROLE_POLICY_VERSION
from large_repository_review import repair_contract, shard_contract
from run_state import latest_run_id
from state_io import atomic_write_text, load_json_object, safe_project_path


WORKERS = {"frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker"}
CAPABILITY_ID = re.compile(r"[A-Za-z0-9_-]+")


def quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def yaml_list(values: list[str], indent: int = 2) -> str:
    if not values:
        return " []"
    prefix = " " * indent
    return "\n" + "\n".join(f"{prefix}- {quoted(value)}" for value in values)


def review_yaml(contract: dict[str, object] | None) -> str:
    if contract is None:
        return '''review_contract:
  status: "NOT_APPLICABLE"
  review_id: "NOT_APPLICABLE"
  mode: "NOT_APPLICABLE"
  phase: "NOT_APPLICABLE"
  shard_id: "NOT_APPLICABLE"
  baseline_commit: "NOT_APPLICABLE"
  target_commit: "NOT_APPLICABLE"
  target_fingerprint: "NOT_APPLICABLE"
  repository_manifest_fingerprint: "NOT_APPLICABLE"
  review_plan_fingerprint: "NOT_APPLICABLE"
  shard_input_fingerprint: "NOT_APPLICABLE"
  trust_policy_fingerprint: "NOT_APPLICABLE"
  trusted_instruction_files: []
  repository_execution_authorized: false
  default_execution_policy: "NOT_APPLICABLE"
  included_modules: []
  included_files: []
  pinned_file_objects_json: "NOT_APPLICABLE"
  exclusion_index: "NOT_APPLICABLE"
  risk_lenses: []
  findings_output: "NOT_APPLICABLE"
  evidence_output: "NOT_APPLICABLE"
  source_write_authorized: false
  fresh_session_required: false
  compact_handoff_required: false
  session_attestation_required: false
  context_budget:
    max_files: 0
    max_bytes: 0
    max_estimated_tokens: 0
    estimated_files: 0
    estimated_bytes: 0
    estimated_tokens: 0
    estimate_method: "NOT_APPLICABLE"
'''
    budget = contract.get("context_budget", {})
    if not isinstance(budget, dict):
        raise ValueError("Review contract context budget is invalid")
    objects = json.dumps(contract.get("pinned_file_objects", {}), ensure_ascii=False, sort_keys=True)
    return f'''review_contract:
  status: "ROUTED"
  review_id: {quoted(str(contract['review_id']))}
  mode: {quoted(str(contract['mode']))}
  phase: {quoted(str(contract['phase']))}
  shard_id: {quoted(str(contract['shard_id']))}
  baseline_commit: {quoted(str(contract.get('baseline_commit') or 'NOT_APPLICABLE'))}
  target_commit: {quoted(str(contract.get('target_commit') or 'NOT_APPLICABLE'))}
  target_fingerprint: {quoted(str(contract['target_fingerprint']))}
  repository_manifest_fingerprint: {quoted(str(contract['repository_manifest_fingerprint']))}
  review_plan_fingerprint: {quoted(str(contract['review_plan_fingerprint']))}
  shard_input_fingerprint: {quoted(str(contract['shard_input_fingerprint']))}
  trust_policy_fingerprint: {quoted(str(contract['trust_policy_fingerprint']))}
  trusted_instruction_files:{yaml_list([str(value) for value in contract.get('trusted_instruction_files', [])], 4)}
  repository_execution_authorized: {str(bool(contract.get('repository_execution_authorized'))).lower()}
  default_execution_policy: {quoted(str(contract['default_execution_policy']))}
  included_modules:{yaml_list([str(value) for value in contract.get('included_modules', [])], 4)}
  included_files:{yaml_list([str(value) for value in contract.get('included_files', [])], 4)}
  pinned_file_objects_json: {quoted(objects)}
  exclusion_index: {quoted(str(contract['exclusion_index']))}
  risk_lenses:{yaml_list([str(value) for value in contract.get('risk_lenses', [])], 4)}
  findings_output: {quoted(str(contract['findings_output']))}
  evidence_output: {quoted(str(contract['evidence_output']))}
  source_write_authorized: false
  fresh_session_required: true
  compact_handoff_required: true
  session_attestation_required: true
  context_budget:
    max_files: {int(budget['max_files'])}
    max_bytes: {int(budget['max_bytes'])}
    max_estimated_tokens: {int(budget['max_estimated_tokens'])}
    estimated_files: {int(budget['estimated_files'])}
    estimated_bytes: {int(budget['estimated_bytes'])}
    estimated_tokens: {int(budget['estimated_tokens'])}
    estimate_method: {quoted(str(budget['estimate_method']))}
'''


def repair_yaml(contract: dict[str, object] | None) -> str:
    if contract is None:
        return '''repair_contract:
  status: "NOT_APPLICABLE"
  review_id: "NOT_APPLICABLE"
  repair_plan_id: "NOT_APPLICABLE"
  repair_plan_fingerprint: "NOT_APPLICABLE"
  phase: "NOT_APPLICABLE"
  finding_ids: []
  allowed_source_files: []
  target_fingerprint: "NOT_APPLICABLE"
  source_write_authorized: false
  evidence_output: "NOT_APPLICABLE"
'''
    return f'''repair_contract:
  status: "ROUTED"
  review_id: {quoted(str(contract['review_id']))}
  repair_plan_id: {quoted(str(contract['repair_plan_id']))}
  repair_plan_fingerprint: {quoted(str(contract['repair_plan_fingerprint']))}
  phase: {quoted(str(contract['phase']))}
  finding_ids:{yaml_list([str(value) for value in contract.get('finding_ids', [])], 4)}
  allowed_source_files:{yaml_list([str(value) for value in contract.get('allowed_source_files', [])], 4)}
  target_fingerprint: {quoted(str(contract['target_fingerprint']))}
  source_write_authorized: {str(bool(contract.get('source_write_authorized'))).lower()}
  evidence_output: {quoted(str(contract['evidence_output']))}
'''


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
    review_shard_id: str | None = None,
    repair_plan_id: str | None = None,
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
    policy_path = control_path(root, "orchestration/model-routing-policy.json")
    try:
        model_policy = json.loads(policy_path.read_text(encoding="utf-8"))
        validate_model_policy(model_policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid executable model routing policy: {exc}") from exc
    destination = safe_project_path(root, Path("tasks") / f"{task_id}.yaml")
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
    role_plan_path = control_path(root, "orchestration/role-plan.json")
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
    if review_shard_id and repair_plan_id:
        raise ValueError("A Task Package cannot bind both a review shard and a repair plan")
    review_contract: dict[str, object] | None = None
    routed_repair_contract: dict[str, object] | None = None
    if review_shard_id:
        if stage != "CODE_REVIEW":
            raise ValueError("Review shard Task Packages must use CODE_REVIEW stage")
        review_contract = shard_contract(root, review_shard_id)
        if task_type != review_contract.get("task_type"):
            raise ValueError(f"Review shard requires task_type={review_contract.get('task_type')}")
        suggested = str(review_contract.get("suggested_owner"))
        if owner not in {suggested, "engineering_lead"}:
            raise ValueError(f"Review shard owner must be {suggested} or engineering_lead")
    if repair_plan_id:
        if stage != "CODE_REVIEW":
            raise ValueError("Repair lifecycle Task Packages must use CODE_REVIEW stage")
        phase = "REPAIR" if task_type == "review_repair" else "REREVIEW" if task_type == "review_verification" else ""
        if not phase:
            raise ValueError("Repair plan Task Packages require review_repair or review_verification task_type")
        routed_repair_contract = repair_contract(root, repair_plan_id, phase=phase)
        if owner != routed_repair_contract.get("owner"):
            raise ValueError(f"Repair {phase} owner must be {routed_repair_contract.get('owner')}")
    attached_run_id = "NOT_ATTACHED"
    try:
        candidate_run_id = latest_run_id(root)
        candidate_run = load_json_object(control_path(root, Path("runs") / candidate_run_id / "run.json"))
        if candidate_run.get("status") == "OPEN":
            attached_run_id = candidate_run_id
    except ValueError:
        pass
    inventory_path = control_path(root, "orchestration/runtime-inventory.json")
    inventory: dict[str, object] = {}
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    manifest_path = control_path(root, "orchestration/runtime-manifest.json")
    platform_neutral = model_policy.get("policy_version") == PLATFORM_POLICY_VERSION
    if platform_neutral and available_models is not None:
        raise ValueError(
            "--available-model is legacy-v2 only; v3 requires a verified platform runtime manifest"
        )
    if platform_neutral and manifest_path.is_file():
        manifest = load_runtime_manifest(manifest_path)
        route = route_with_platform_manifest(
            manifest=manifest,
            availability_source=str(manifest_path.relative_to(root.resolve())),
            complexity=complexity,
            task_type=task_type,
            role=owner,
            risk_flags=risk_flags or [],
            failed_attempts=failed_attempts,
            failure_type=failure_type,
        )
    elif platform_neutral:
        route = route_without_platform_manifest(
            complexity=complexity,
            task_type=task_type,
            role=owner,
            risk_flags=risk_flags or [],
            failed_attempts=failed_attempts,
            failure_type=failure_type,
        )
    if not platform_neutral:
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
    review_contract_text = review_yaml(review_contract)
    repair_contract_text = repair_yaml(routed_repair_contract)
    review_allowed_files = (
        [str(review_contract["findings_output"]), str(review_contract["evidence_output"])]
        if review_contract is not None else []
    )
    if routed_repair_contract is not None:
        review_allowed_files = [str(value) for value in routed_repair_contract.get("allowed_files", [])]
    content = f'''schema_version: 2
run_id: {quoted(attached_run_id)}
task_id: {quoted(task_id)}
project: {quoted(project_name)}
stage: {quoted(stage)}
status: "DRAFT"
source_input_fingerprint: {quoted(str(role_plan.get('input_fingerprint') or 'BLOCKING_UNKNOWN'))}
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
  platform: {quoted(str(route['platform'] if 'platform' in route else 'legacy-codex'))}
  preferred_model: {quoted(route['preferred_model'])}
  selected_model: {quoted(route['selected_model'])}
  selected_provider: {quoted(str(route['selected_provider'] if 'selected_provider' in route else 'openai'))}
  model_reasoning_effort: {quoted(route['model_reasoning_effort'])}
  actual_model_attested: {str(bool(route.get('actual_model_attested', False))).lower()}
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
{review_contract_text.rstrip()}
{repair_contract_text.rstrip()}
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
allowed_files:{yaml_list(review_allowed_files, 2)}
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
    atomic_write_text(destination, content, allowed_root=root)
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
    parser.add_argument("--task-type", choices=sorted(KNOWN_TASK_TYPES), default="implementation")
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--failed-attempts", type=int, default=0)
    parser.add_argument("--failure-type", default="none")
    parser.add_argument("--required-capability", action="append", default=[])
    parser.add_argument("--optional-capability", action="append", default=[])
    parser.add_argument("--available-model", action="append", default=[], help="Runtime-verified model slug; repeat as needed")
    parser.add_argument("--review-shard", help="Bind this Task Package to one active large-review shard")
    parser.add_argument("--repair-plan", help="Bind this Task Package to one active repair plan")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        destination = create(
            root, args.task_id, args.owner, args.reviewer, args.objective, args.stage, args.return_to,
            args.task_type, args.risk, args.failed_attempts, args.failure_type,
            args.required_capability, args.optional_capability,
            args.available_model,
            args.review_shard,
            args.repair_plan,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Created task package: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
