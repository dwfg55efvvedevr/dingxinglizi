#!/usr/bin/env python3
"""Compute a deterministic Luna/Terra/Sol route for one work package."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Iterable

from model_routing import HIGH_RISK_FLAGS, MODELS_BY_PREFERENCE, route_task


REASONING_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")


def apply_user_model_override(
    route: dict[str, Any],
    *,
    requested_model: str | None,
    requested_reasoning: str | None = None,
    approved: bool = False,
    available_models: Iterable[str] = (),
    actual_launch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep recommendation, user decision, and launch attestation as distinct facts."""
    result = dict(route)
    result["policy_recommendation"] = {
        "capability_tier": route.get("capability_tier", ""),
        "model": route.get("selected_model", "") or route.get("preferred_model", ""),
        "reasoning_effort": route.get("model_reasoning_effort", ""),
        "status": route.get("status", ""),
    }
    result["user_approved_override"] = {
        "approved": bool(approved and requested_model),
        "model": requested_model or "",
        "reasoning_effort": requested_reasoning or "",
        "status": "NOT_REQUESTED" if not requested_model else "PENDING_VALIDATION",
    }
    launch = actual_launch or {}
    result["actual_launch_attestation"] = {
        "attested": bool(launch.get("attested", False)),
        "model": str(launch.get("model", "")),
        "reasoning_effort": str(launch.get("reasoning_effort", "")),
        "evidence": str(launch.get("evidence", "")),
    }
    if not requested_model:
        return result
    if not approved:
        result["user_approved_override"]["status"] = "BLOCKED_NOT_APPROVED"
        return result
    if requested_model not in set(available_models):
        result["user_approved_override"]["status"] = "BLOCKED_UNAVAILABLE"
        result["status"] = "BLOCKED_MODEL_UNAVAILABLE"
        result["selected_model"] = ""
        return result
    high_risk = bool(set(route.get("risk_flags", [])) & HIGH_RISK_FLAGS)
    recommended = result["policy_recommendation"]["model"]
    if high_risk and requested_model != recommended:
        result["user_approved_override"]["status"] = "BLOCKED_HIGH_RISK_FLOOR"
        result["status"] = "BLOCKED_MODEL_OVERRIDE_BELOW_FLOOR"
        result["selected_model"] = ""
        return result
    recommended_reasoning = str(result["policy_recommendation"]["reasoning_effort"])
    if requested_reasoning:
        if requested_reasoning not in REASONING_ORDER:
            result["user_approved_override"]["status"] = "BLOCKED_UNSUPPORTED_REASONING"
            result["status"] = "BLOCKED_REASONING_EFFORT_UNAVAILABLE"
            result["selected_model"] = ""
            return result
        if (
            high_risk
            and recommended_reasoning in REASONING_ORDER
            and REASONING_ORDER.index(requested_reasoning) < REASONING_ORDER.index(recommended_reasoning)
        ):
            result["user_approved_override"]["status"] = "BLOCKED_REASONING_BELOW_FLOOR"
            result["status"] = "BLOCKED_REASONING_OVERRIDE_BELOW_FLOOR"
            result["selected_model"] = ""
            return result
    result["user_approved_override"]["status"] = "ACCEPTED"
    result["selected_model"] = requested_model
    if requested_reasoning:
        result["model_reasoning_effort"] = requested_reasoning
    result["routing_mode"] = "user_approved_task_override"
    result.setdefault("routing_reasons", []).append(
        f"user-approved-override:{recommended}->{requested_model}"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complexity", choices=["Simple", "Standard", "Complex"], required=True)
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--failed-attempts", type=int, default=0)
    parser.add_argument("--failure-type", default="none")
    parser.add_argument("--available-model", action="append", dest="available_models")
    parser.add_argument("--user-model-override")
    parser.add_argument("--user-reasoning-override")
    parser.add_argument("--override-approved", action="store_true")
    args = parser.parse_args()
    try:
        route = route_task(
            complexity=args.complexity,
            task_type=args.task_type,
            role=args.role,
            risk_flags=args.risk,
            failed_attempts=args.failed_attempts,
            failure_type=args.failure_type,
            available_models=args.available_models or MODELS_BY_PREFERENCE,
        )
        route = apply_user_model_override(
            route,
            requested_model=args.user_model_override,
            requested_reasoning=args.user_reasoning_override,
            approved=args.override_approved,
            available_models=args.available_models or MODELS_BY_PREFERENCE,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(route, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if route["status"] == "ROUTED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
