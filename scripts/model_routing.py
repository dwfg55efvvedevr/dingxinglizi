#!/usr/bin/env python3
"""Deterministic task-level model routing shared by CLI and task generation."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


POLICY_VERSION = "1.2.0"
MODELS = {
    "Economy": ("gpt-5.6-luna", "low"),
    "Standard": ("gpt-5.6-terra", "medium"),
    "Advanced": ("gpt-5.6-terra", "high"),
    "Expert": ("gpt-5.6-sol", "high"),
    "Exceptional": ("gpt-5.6-sol", "xhigh"),
}
TIER_ORDER = list(MODELS)

LOW_RISK_TASKS = {"scan", "extract", "format", "documentation", "test_run"}
ADVANCED_TASKS = {
    "requirements", "product_audit", "ux", "ui", "implementation", "code_review", "qa",
    "problem_quality", "solution_challenge", "release_quality",
}
EXPERT_TASKS = {"architecture", "security_review", "permission_design", "migration_design", "release_review"}
KNOWN_TASK_TYPES = LOW_RISK_TASKS | ADVANCED_TASKS | EXPERT_TASKS
HIGH_RISK_FLAGS = {
    "security", "privacy", "financial", "payment", "compliance", "production",
    "migration", "concurrency", "consistency", "permissions", "irreversible",
}
REASONING_FAILURES = {"quality", "reasoning", "acceptance", "qa_defect", "evidence_conflict"}
ENVIRONMENT_FAILURES = {"network", "rate_limit", "auth", "permission", "missing_input", "tool_unavailable"}
KNOWN_RISK_FLAGS = HIGH_RISK_FLAGS | {
    "ambiguity", "cross_module", "external_side_effects", "data_integrity", "vendor_lock_in",
    "accessibility", "performance", "cost", "offline", "low_reversibility", "high_impact", "ai_safety",
}
KNOWN_ROLES = {
    "orchestrator", "requirements", "product_auditor", "ux", "ui", "architect",
    "engineering_lead", "qa", "frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker",
    "quality_governor",
}
ROLE_FLOORS = {
    "orchestrator": {"Simple": "Standard", "Standard": "Advanced", "Complex": "Expert"},
    "requirements": {"Simple": "Standard", "Standard": "Standard", "Complex": "Advanced"},
    "product_auditor": {"Simple": "Standard", "Standard": "Standard", "Complex": "Advanced"},
    "ux": {"Simple": "Standard", "Standard": "Standard", "Complex": "Advanced"},
    "ui": {"Simple": "Standard", "Standard": "Standard", "Complex": "Advanced"},
    "architect": {"Simple": "Advanced", "Standard": "Advanced", "Complex": "Expert"},
    "engineering_lead": {"Simple": "Standard", "Standard": "Advanced", "Complex": "Expert"},
    "qa": {"Simple": "Advanced", "Standard": "Advanced", "Complex": "Expert"},
    "quality_governor": {"Simple": "Advanced", "Standard": "Advanced", "Complex": "Expert"},
}


def _raise_tier(tier: str, steps: int = 1) -> str:
    return TIER_ORDER[min(TIER_ORDER.index(tier) + steps, len(TIER_ORDER) - 1)]


def _base_tier(complexity: str, task_type: str) -> str:
    if task_type in LOW_RISK_TASKS:
        return "Economy"
    if task_type in EXPERT_TASKS:
        return "Expert"
    if task_type in ADVANCED_TASKS:
        return "Standard" if complexity == "Simple" else "Advanced"
    return {"Simple": "Economy", "Standard": "Standard", "Complex": "Advanced"}[complexity]


def route_task(
    *,
    complexity: str,
    task_type: str,
    role: str,
    risk_flags: Iterable[str] = (),
    failed_attempts: int = 0,
    failure_type: str = "none",
    available_models: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a stable route. High-risk required models fail closed when unavailable."""
    if complexity not in {"Simple", "Standard", "Complex"}:
        raise ValueError("complexity must be Simple, Standard, or Complex")
    if task_type not in KNOWN_TASK_TYPES:
        raise ValueError(f"unsupported task_type: {task_type}")
    if role not in KNOWN_ROLES:
        raise ValueError(f"unsupported role: {role}")
    if failed_attempts < 0:
        raise ValueError("failed_attempts cannot be negative")
    flags = sorted({flag.strip().lower() for flag in risk_flags if flag.strip()})
    unknown_flags = sorted(set(flags) - KNOWN_RISK_FLAGS)
    if unknown_flags:
        raise ValueError("unsupported risk flag(s): " + ", ".join(unknown_flags))
    unknown_failure = failure_type not in {"none"} | REASONING_FAILURES | ENVIRONMENT_FAILURES
    if unknown_failure:
        raise ValueError(f"unsupported failure_type: {failure_type}")

    tier = _base_tier(complexity, task_type)
    reasons = [f"base:{complexity}/{task_type}/{role}"]
    role_floor = ROLE_FLOORS.get(role, {}).get(complexity)
    if role_floor and TIER_ORDER.index(tier) < TIER_ORDER.index(role_floor):
        tier = role_floor
        reasons.append(f"role-floor:{role}/{complexity}")
    high_risk = sorted(set(flags) & HIGH_RISK_FLAGS)
    if high_risk and TIER_ORDER.index(tier) < TIER_ORDER.index("Expert"):
        tier = "Expert"
        reasons.append("high-risk:" + ",".join(high_risk))
    if complexity == "Complex" and task_type not in LOW_RISK_TASKS and TIER_ORDER.index(tier) < TIER_ORDER.index("Advanced"):
        tier = "Advanced"
        reasons.append("complex-project-floor")

    effort_override: str | None = None
    if failed_attempts >= 3:
        requested_model, effort = MODELS[tier]
        return {
            "policy_version": POLICY_VERSION,
            "routing_mode": "explicit_spawn_override",
            "status": "BLOCKED_ATTEMPTS_EXHAUSTED",
            "capability_tier": tier,
            "preferred_model": requested_model,
            "selected_model": "",
            "model_reasoning_effort": effort,
            "fallback_models": [],
            "routing_reasons": reasons + ["max-attempts-exhausted:orchestrator-review-required"],
            "risk_flags": flags,
            "failed_attempts": failed_attempts,
            "failure_type": failure_type,
            "max_attempts": 3,
            "downgrade_policy": "new_low_risk_task_package_only",
        }
    if failure_type in REASONING_FAILURES and failed_attempts:
        if failed_attempts == 1:
            # The first valid quality failure raises effort before changing model family.
            if tier == "Economy":
                effort_override = "medium"
            elif tier == "Standard":
                effort_override = "high"
            elif tier == "Advanced":
                effort_override = "xhigh"
            elif tier == "Expert":
                effort_override = "xhigh"
            reasons.append("first-quality-failure:raise-effort")
        else:
            if tier == "Economy":
                tier = "Standard"
            elif tier in {"Standard", "Advanced"}:
                tier = "Expert"
            else:
                tier = "Exceptional"
            reasons.append("repeated-quality-failure:raise-capability")
    elif failure_type in ENVIRONMENT_FAILURES and failed_attempts:
        reasons.append("environment-failure:no-model-escalation")

    requested_model, effort = MODELS[tier]
    effort = effort_override or effort
    available = set(MODELS_BY_PREFERENCE if available_models is None else available_models)
    status = "ROUTED"
    selected_model = requested_model
    fallback_chain: list[str] = []
    if requested_model not in available:
        if tier in {"Expert", "Exceptional"} or high_risk:
            status = "BLOCKED_MODEL_UNAVAILABLE"
            selected_model = ""
            reasons.append("required-frontier-model-unavailable")
        else:
            preference = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]
            candidates = [model for model in preference if model in available]
            if not candidates:
                status = "BLOCKED_MODEL_UNAVAILABLE"
                selected_model = ""
            else:
                # Prefer controlled upward fallback. Downward use is allowed only for low-risk work.
                requested_index = preference.index(requested_model)
                upward = [model for model in candidates if preference.index(model) > requested_index]
                if upward:
                    selected_model = upward[0]
                    fallback_chain = [selected_model]
                    reasons.append(f"runtime-upward-fallback:{requested_model}->{selected_model}")
                elif task_type in LOW_RISK_TASKS and not high_risk:
                    selected_model = candidates[-1]
                    fallback_chain = [selected_model]
                    reasons.append(f"controlled-low-risk-downgrade:{requested_model}->{selected_model}")
                else:
                    status = "BLOCKED_MODEL_UNAVAILABLE"
                    selected_model = ""
                    reasons.append("model-floor-unavailable:no-silent-downgrade")

    return {
        "policy_version": POLICY_VERSION,
        "routing_mode": "explicit_spawn_override",
        "status": status,
        "capability_tier": tier,
        "preferred_model": requested_model,
        "selected_model": selected_model,
        "model_reasoning_effort": effort,
        "fallback_models": fallback_chain,
        "routing_reasons": reasons,
        "risk_flags": flags,
        "failed_attempts": failed_attempts,
        "failure_type": failure_type,
        "max_attempts": 3,
        "downgrade_policy": "new_low_risk_task_package_only",
    }


def route_with_inventory(
    *,
    available_models: Iterable[str],
    availability_source: str,
    availability_verified: bool,
    **route_inputs: Any,
) -> dict[str, Any]:
    """Route against a runtime snapshot and fail closed when the snapshot is unverified."""
    models = sorted(set(available_models))
    route = route_task(available_models=models, **route_inputs)
    route["available_models"] = models
    route["availability_source"] = availability_source
    route["availability_verified"] = availability_verified
    if not availability_verified:
        route["status"] = "BLOCKED_RUNTIME_INVENTORY"
        route["selected_model"] = ""
        route["routing_reasons"].append("runtime-model-inventory-unverified")
    return route


MODELS_BY_PREFERENCE = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]


def route_fingerprint(route: dict[str, Any]) -> str:
    """Hash the complete deterministic route so launch preflight can detect drift."""
    encoded = json.dumps(route, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_model_policy(policy: dict[str, Any]) -> None:
    expected = {
        "policy_version": POLICY_VERSION,
        "routing_unit": "task_package",
        "runtime_precedence": [
            "task_package_execution_profile", "explicit_spawn_override",
            "runtime_agent_default", "parent_inheritance",
        ],
        "model_families": {
            "economy": "gpt-5.6-luna", "balanced": "gpt-5.6-terra", "frontier": "gpt-5.6-sol",
        },
        "max_attempts": 3,
        "max_escalations": 2,
        "silent_high_risk_downgrade": False,
        "agent_toml_model_binding": False,
    }
    if policy != expected:
        raise ValueError(
            "model-routing-policy.json does not match the executable router policy version 1.2.0"
        )
