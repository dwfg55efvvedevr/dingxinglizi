#!/usr/bin/env python3
"""Deterministic task-level governance triage, independent of project size."""

from __future__ import annotations

from typing import Any, Iterable


TASK_MODES = ("QUICK_PATCH", "BOUNDED_CHANGE", "GOVERNED_DELIVERY")
GOVERNED_TRIGGERS = {
    "payment", "financial", "permissions", "security", "privacy", "migration",
    "concurrency", "consistency", "irreversible", "production", "regulated",
    "compliance", "p0_incident", "p1_incident", "multi_writer", "state_machine_rewrite",
    "external_side_effects", "blocking_unknown", "evidence_conflict", "high_impact",
    "repeated_failure",
}
BOUNDED_TRIGGERS = {
    "api_delta", "cross_module", "multi_file", "user_facing", "contract_delta",
    "targeted_qa", "backend_frontend", "reversible_data_write", "map_integration",
    "scope_expansion_confirmed",
}
QUICK_SIGNALS = {
    "single_page", "single_component", "copy_change", "style_change", "isolated_bug",
    "local_config", "targeted_test", "reversible", "no_contract_change",
}
KNOWN_TRIAGE_SIGNALS = GOVERNED_TRIGGERS | BOUNDED_TRIGGERS | QUICK_SIGNALS | {
    "explicit_skill_invocation", "full_process_requested", "scope_expansion_requested",
    "unclear_scope", "repeated_failure", "evidence_conflict",
    "high_impact", "external_side_effects", "blocking_unknown",
}

MODE_BUDGETS: dict[str, dict[str, Any]] = {
    "QUICK_PATCH": {
        "measurement_status": "DECLARED_CALLER_REPORTED_NOT_HOST_OBSERVED",
        "expected_minutes": {"min": 3, "max": 15},
        "max_subagents": 0,
        "max_active_subagents": 0,
        "max_total_role_sessions": 1,
        "max_reference_files": 3,
        "planning_overhead_seconds": 60,
        "progress_blocker_required_cycle": 2,
        "max_wait_cycles_without_progress": 3,
        "independent_qa": "risk_triggered",
        "full_test_suite": False,
    },
    "BOUNDED_CHANGE": {
        "measurement_status": "DECLARED_CALLER_REPORTED_NOT_HOST_OBSERVED",
        "expected_minutes": {"min": 15, "max": 45},
        "max_subagents": 1,
        "max_active_subagents": 1,
        "max_total_role_sessions": 2,
        "max_reference_files": 8,
        "planning_overhead_seconds": 300,
        "progress_blocker_required_cycle": 2,
        "max_wait_cycles_without_progress": 3,
        "independent_qa": "required_after_implementation",
        "full_test_suite": "once_if_relevant",
        "max_targeted_repair_rounds": 1,
    },
    "GOVERNED_DELIVERY": {
        "measurement_status": "DECLARED_CALLER_REPORTED_NOT_HOST_OBSERVED",
        "expected_minutes": "must_be_reported",
        "max_subagents": "quota_and_plan",
        "max_active_subagents": "plan_bound",
        "max_total_role_sessions": "plan_bound",
        "max_reference_files": "plan_bound",
        "planning_overhead_seconds": "plan_bound",
        "progress_blocker_required_cycle": 2,
        "max_wait_cycles_without_progress": 3,
        "independent_qa": "required",
        "full_test_suite": "risk_and_release_plan",
    },
}


def normalize_signals(signals: Iterable[str]) -> set[str]:
    normalized = {value.strip().lower() for value in signals if value and value.strip()}
    unknown = sorted(normalized - KNOWN_TRIAGE_SIGNALS)
    if unknown:
        raise ValueError("unsupported task triage signal(s): " + ", ".join(unknown))
    return normalized


def classify_task_mode(
    *,
    project_complexity: str,
    signals: Iterable[str] = (),
    requested_mode: str | None = None,
    estimated_business_files: int = 1,
    estimated_minutes: int | None = None,
) -> dict[str, Any]:
    """Classify the current delta while preserving the computed safety floor."""
    if project_complexity not in {"Simple", "Standard", "Complex"}:
        raise ValueError("project_complexity must be Simple, Standard, or Complex")
    if requested_mode and requested_mode not in TASK_MODES:
        raise ValueError("requested_mode must be QUICK_PATCH, BOUNDED_CHANGE, or GOVERNED_DELIVERY")
    if estimated_business_files < 0:
        raise ValueError("estimated_business_files cannot be negative")
    if estimated_minutes is not None and estimated_minutes < 0:
        raise ValueError("estimated_minutes cannot be negative")
    normalized = normalize_signals(signals)
    reasons = [f"project-complexity-context:{project_complexity}"]
    governed = sorted(normalized & GOVERNED_TRIGGERS)
    scope_confirmation_required = bool(
        normalized & {"scope_expansion_requested", "unclear_scope"}
        and "scope_expansion_confirmed" not in normalized
    )
    if governed:
        mode = "GOVERNED_DELIVERY"
        reasons.append("governed-risk:" + ",".join(governed))
    elif scope_confirmation_required:
        mode = "QUICK_PATCH"
        reasons.append("scope-expansion-not-confirmed:keep-narrow")
    elif normalized & BOUNDED_TRIGGERS or estimated_business_files > 3 or (estimated_minutes or 0) > 15:
        mode = "BOUNDED_CHANGE"
        reasons.append("bounded-delta-scope")
    else:
        mode = "QUICK_PATCH"
        reasons.append("local-reversible-default")

    # An explicit mode selection may add governance, but can never lower the computed floor.
    # This is distinct from merely invoking the Skill or asking for a "full process".
    if requested_mode:
        current_rank = TASK_MODES.index(mode)
        requested_rank = TASK_MODES.index(requested_mode)
        if requested_rank < current_rank:
            reasons.append("requested-lighter-mode-rejected-by-computed-floor")
        elif requested_rank > current_rank:
            mode = requested_mode
            reasons.append("user-requested-higher-governance-mode")
    if normalized & {"explicit_skill_invocation", "full_process_requested"}:
        reasons.append("explicit-skill-means-complete-closure-not-all-gates")

    scope = {
        "QUICK_PATCH": "local_delta",
        "BOUNDED_CHANGE": "compact_delta_contract",
        "GOVERNED_DELIVERY": "governed_project_or_module_scope",
    }[mode]
    return {
        "status": "SCOPE_CONFIRMATION_REQUIRED" if scope_confirmation_required and not governed else "ROUTED",
        "project_complexity": project_complexity,
        "task_complexity": mode,
        "task_mode": mode,
        "proposed_mode": mode,
        "scope_class": scope,
        "budget": dict(MODE_BUDGETS[mode]),
        "estimated_business_files": estimated_business_files,
        "estimated_minutes": estimated_minutes,
        "signals": sorted(normalized),
        "routing_reasons": reasons,
        "first_route_summary": {
            "task_mode": mode,
            "scope": scope,
            "max_subagents": MODE_BUDGETS[mode]["max_subagents"],
            "max_active_subagents": MODE_BUDGETS[mode]["max_active_subagents"],
            "max_total_role_sessions": MODE_BUDGETS[mode]["max_total_role_sessions"],
            "time_expectation": MODE_BUDGETS[mode]["expected_minutes"],
        },
    }


def governance_severity(issue: str, *, task_mode: str, risk_flags: Iterable[str] = ()) -> str:
    """Separate execution safety failures from stale, non-safety governance metadata."""
    risks = {value.strip().lower() for value in risk_flags if value and value.strip()}
    if task_mode == "GOVERNED_DELIVERY" or risks & GOVERNED_TRIGGERS:
        return "EXECUTION_SAFETY_BLOCKER"
    degradable = (
        "STALE_ROLE_PLAN", "STALE_TASK_INPUT", "unverified_runtime_inventory",
        "BLOCKED_RUNTIME_INVENTORY", "BLOCKED_RUNTIME_MANIFEST_REQUIRED",
        "non-safety fingerprint", "no active run",
    )
    if any(fragment.lower() in issue.lower() for fragment in degradable):
        return "GOVERNANCE_METADATA_DEGRADED"
    return "EXECUTION_SAFETY_BLOCKER"
