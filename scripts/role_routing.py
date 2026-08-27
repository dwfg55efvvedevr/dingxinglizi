#!/usr/bin/env python3
"""Deterministic current-gate role routing with quota-aware execution waves."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


POLICY_VERSION = "1.2.0"
PROFESSIONAL_ROLES = {
    "requirements", "product_auditor", "ux", "ui", "architect",
    "engineering_lead", "qa", "quality_governor",
}
ALL_AVAILABLE_ROLES = [
    "requirements", "product_auditor", "quality_governor", "ux", "ui",
    "architect", "engineering_lead", "qa",
]
WORKER_ROLES = ["frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker"]
READ_ONLY_ROLES = {"product_auditor", "quality_governor", "qa"}
QUOTA_LIMITS = {"economy": 1, "balanced": 2, "quality_first": 2}
KNOWN_SIGNALS = {
    "unclear_requirements", "novel_problem", "evidence_conflict", "coverage_risk",
    "user_facing", "flow_complexity", "visual_system", "accessibility",
    "new_contracts", "architecture_risk", "cross_module", "contract_delta",
    "implementation_workers", "high_impact", "regulated", "release_risk",
    "repeated_failure", "parallel_safe", "security", "privacy", "financial",
    "payment", "compliance", "production", "migration", "concurrency",
    "consistency", "permissions", "irreversible", "ai_safety",
}
QUALITY_TRIGGERS = {
    "novel_problem", "evidence_conflict", "high_impact", "regulated",
    "release_risk", "repeated_failure", "security", "privacy", "financial",
    "payment", "compliance", "production", "migration", "irreversible", "ai_safety",
}


def validate_role_policy(policy: dict[str, Any]) -> None:
    expected = {
        "policy_version": POLICY_VERSION,
        "routing_unit": "current_gate",
        "orchestrator_runtime": "main_thread",
        "default_quota_mode": "economy",
        "quota_modes": {
            "economy": {"max_active_subagents": 1, "parallel_read_only": False},
            "balanced": {"max_active_subagents": 2, "parallel_read_only": True},
            "quality_first": {"max_active_subagents": 2, "parallel_read_only": True},
        },
        "final_qa_separate_from_engineering": True,
        "professional_agents_may_spawn": False,
        "engineering_lead_may_spawn_workers": True,
        "workers_may_spawn": False,
        "complex_means_lifecycle_available_not_simultaneous": True,
    }
    if policy != expected:
        raise ValueError("role-routing-policy.json does not match executable policy 1.2.0")


def role_plan_fingerprint(plan: dict[str, Any]) -> str:
    value = dict(plan)
    value.pop("plan_fingerprint", None)
    value.pop("generated_at", None)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _quality_gate(stage: str) -> str | None:
    return {"DISCOVERY": "problem", "READY_FOR_BUILD": "solution", "QA_PASS": "release_evidence"}.get(stage)


def _quality_independent(complexity: str, quota_mode: str, signals: set[str]) -> bool:
    return quota_mode == "quality_first" or complexity == "Complex" or bool(signals & QUALITY_TRIGGERS)


def _base_roles(stage: str, complexity: str, signals: set[str]) -> tuple[list[str], dict[str, list[str]]]:
    merged: dict[str, list[str]] = {}
    if stage == "BACKLOG" or stage in {"ARCHITECTURE_READY", "RELEASE_READY", "DONE", "BLOCKED"}:
        return [], merged
    if stage == "DISCOVERY":
        return ["requirements"], merged
    if stage == "REQUIREMENTS_APPROVED":
        if complexity == "Simple" and "coverage_risk" not in signals:
            merged["requirements"] = ["product_auditor"]
            return ["requirements"], merged
        return ["product_auditor"], merged
    if stage == "PRODUCT_APPROVED":
        roles: list[str] = []
        if complexity == "Complex" or signals & {"user_facing", "flow_complexity"}:
            roles.append("ux")
        if signals & {"new_contracts", "architecture_risk", "cross_module"} and not roles:
            roles.append("architect")
        if complexity == "Simple" and roles == ["ux"]:
            merged["ux"] = ["ui"]
        return roles, merged
    if stage == "UX_READY":
        roles = []
        if complexity == "Complex" or signals & {"visual_system", "accessibility"}:
            roles.append("ui")
        if complexity == "Complex" or signals & {"new_contracts", "architecture_risk", "cross_module"}:
            roles.append("architect")
        if complexity == "Standard" and roles == ["ui"] and "visual_system" not in signals:
            merged["ui"] = ["ux"]
        return roles, merged
    if stage == "UI_READY":
        if complexity == "Complex" or signals & {"new_contracts", "architecture_risk", "cross_module"}:
            return ["architect"], merged
        return [], merged
    if stage in {"READY_FOR_BUILD", "IN_DEVELOPMENT"}:
        return ["engineering_lead"], merged
    if stage == "CODE_REVIEW":
        roles = ["engineering_lead"]
        if signals & {"contract_delta", "evidence_conflict", "architecture_risk"}:
            roles.append("architect")
        return roles, merged
    if stage == "READY_FOR_QA":
        return ["qa"], merged
    if stage == "QA_PASS":
        return [], merged
    rework = {
        "REWORK_REQUIREMENTS": "requirements", "REWORK_PRODUCT": "product_auditor",
        "REWORK_UX": "ux", "REWORK_UI": "ui", "REWORK_ARCHITECTURE": "architect",
        "REWORK_ENGINEERING": "engineering_lead", "REWORK_QA": "qa",
    }
    if stage in rework:
        return [rework[stage]], merged
    raise ValueError(f"unsupported role-routing stage: {stage}")


def route_roles(
    *,
    complexity: str,
    stage: str,
    quota_mode: str = "economy",
    signals: Iterable[str] = (),
    completed_roles: Iterable[str] = (),
    input_fingerprint: str = "",
    quality_gate_record: dict[str, Any] | None = None,
    routing_cycle_id: str = "",
) -> dict[str, Any]:
    if complexity not in {"Simple", "Standard", "Complex"}:
        raise ValueError("complexity must be Simple, Standard, or Complex")
    if quota_mode not in QUOTA_LIMITS:
        raise ValueError("quota_mode must be economy, balanced, or quality_first")
    normalized = {value.strip().lower() for value in signals if value.strip()}
    unknown = sorted(normalized - KNOWN_SIGNALS)
    if unknown:
        raise ValueError("unsupported role signal(s): " + ", ".join(unknown))
    completed = {value.strip() for value in completed_roles if value.strip()}
    unknown_completed = sorted(completed - PROFESSIONAL_ROLES)
    if unknown_completed:
        raise ValueError("unsupported completed role(s): " + ", ".join(unknown_completed))

    roles, merged = _base_roles(stage, complexity, normalized)
    reasons: dict[str, list[str]] = {role: [f"stage:{stage}", f"complexity:{complexity}"] for role in roles}
    gate = _quality_gate(stage)
    quality_status = "NOT_AT_QUALITY_GATE"
    inline_actions: list[str] = []
    record = quality_gate_record or {}
    reused = bool(
        gate
        and record.get("status") == "APPROVED"
        and input_fingerprint
        and record.get("input_fingerprint") == input_fingerprint
    )
    if gate and reused:
        quality_status = "REUSE_APPROVAL"
    elif gate and _quality_independent(complexity, quota_mode, normalized):
        quality_status = "INDEPENDENT_REQUIRED"
        if gate == "solution":
            roles = ["quality_governor"]
            merged = {}
            reasons = {"quality_governor": [f"quality-gate:{gate}", "independent-challenge-required"]}
        elif gate == "release_evidence":
            roles = ["quality_governor"]
            reasons = {"quality_governor": [f"quality-gate:{gate}", "independent-challenge-required"]}
        elif "quality_governor" not in roles:
            roles.append("quality_governor")
            reasons["quality_governor"] = [f"quality-gate:{gate}", "independent-challenge-required"]
    elif gate:
        quality_status = "INLINE_REQUIRED"
        inline_actions.append(f"complete-and-approve:{gate}-quality-checklist")
        if gate in {"solution", "release_evidence"}:
            roles = []
            reasons = {}

    # An approved solution challenge allows Engineering Lead to activate at READY_FOR_BUILD.
    if stage == "READY_FOR_BUILD" and reused:
        roles, merged = _base_roles(stage, complexity, normalized)
        reasons = {role: [f"stage:{stage}", "solution-quality-approval-reused"] for role in roles}

    roles = [role for role in dict.fromkeys(roles) if role not in completed]
    if "orchestrator" in roles:
        raise AssertionError("Orchestrator must remain in the main thread")
    if "qa" in roles and "engineering_lead" in roles:
        raise AssertionError("Final QA and Engineering Lead cannot share an activation wave")

    max_active = QUOTA_LIMITS[quota_mode]
    delegable_workers: list[str] = []
    worker_slots = 0
    if stage == "IN_DEVELOPMENT" and "implementation_workers" in normalized and "engineering_lead" in roles:
        if max_active >= 2:
            delegable_workers = list(WORKER_ROLES)
            worker_slots = max_active - 1
        else:
            inline_actions.append("engineering-lead-implements-directly:worker-would-exceed-economy-budget")
    waves: list[list[str]] = []
    if roles:
        can_parallel = (
            max_active > 1 and "parallel_safe" in normalized
            and len(roles) <= max_active and set(roles).issubset(READ_ONLY_ROLES)
        )
        waves = [roles] if can_parallel else [[role] for role in roles]
    max_wave = max((len(wave) for wave in waves), default=0)
    if max_wave > max_active:
        raise AssertionError("Generated role plan exceeds quota concurrency")

    required_now = waves[0] if waves else []
    deferred_sequence = [role for wave in waves[1:] for role in wave]
    if not routing_cycle_id:
        cycle_payload = json.dumps({
            "complexity": complexity,
            "stage": stage,
            "quota_mode": quota_mode,
            "signals": sorted(normalized),
            "starting_input_fingerprint": input_fingerprint,
        }, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        routing_cycle_id = hashlib.sha256(cycle_payload).hexdigest()
    plan: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "status": "ROUTED",
        "routing_unit": "current_gate",
        "complexity": complexity,
        "current_stage": stage,
        "routing_cycle_id": routing_cycle_id,
        "quota_mode": quota_mode,
        "orchestrator": {"runtime": "main_thread", "spawn": False},
        "max_active_subagents": max_active,
        "required_now": required_now,
        "planned_roles": roles,
        "deferred_sequence": deferred_sequence,
        "execution_waves": waves,
        "current_wave": 0,
        "activation_reasons": reasons,
        "merged_responsibilities": merged,
        "deferred_available": [role for role in ALL_AVAILABLE_ROLES if role not in required_now],
        "delegable_workers": delegable_workers,
        "worker_parent": "engineering_lead",
        "max_concurrent_workers": worker_slots,
        "quality_gate": gate,
        "quality_review_status": quality_status,
        "inline_actions": inline_actions,
        "signals": sorted(normalized),
        "completed_roles": sorted(completed),
        "input_fingerprint": input_fingerprint,
        "reviewer_activation": "deferred_until_owner_handoff",
        "exit_rule": "persist_handoff_release_files_then_remove_from_active_set",
    }
    plan["plan_fingerprint"] = role_plan_fingerprint(plan)
    return plan
