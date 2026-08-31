#!/usr/bin/env python3
"""Run deterministic offline routing and large-review control evaluations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _common import SKILL_ROOT
from model_routing import route_task
from review_findings import merge_findings
from review_planning import build_review_plan
from role_routing import route_roles


DEFAULT_SUITE = SKILL_ROOT / "evals" / "routing-v2.json"
BUNDLED_SUITES = (DEFAULT_SUITE, SKILL_ROOT / "evals" / "large-review-v3.json")


def _assertions(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, value in expected.items():
        if key == "forbidden_roles":
            present = sorted(set(value) & set(actual.get("planned_roles", [])))
            if present:
                errors.append(f"forbidden roles present: {present}")
        elif key == "max_active_subagents_lte":
            if int(actual.get("max_active_subagents", 0)) > int(value):
                errors.append(f"max_active_subagents={actual.get('max_active_subagents')} > {value}")
        elif key == "routing_reasons_contains":
            reasons = actual.get("routing_reasons", [])
            missing = [item for item in value if not any(item in reason for reason in reasons)]
            if missing:
                errors.append(f"routing reason fragments missing: {missing}")
        elif actual.get(key) != value:
            errors.append(f"{key}: expected {value!r}, got {actual.get(key)!r}")
    return errors


def evaluate(path: Path = DEFAULT_SUITE) -> dict[str, Any]:
    try:
        suite = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Evaluation suite is missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid evaluation JSON: {path}: {exc}") from exc
    if not isinstance(suite, dict) or suite.get("schema_version") != 1 or not isinstance(suite.get("cases"), list):
        raise ValueError("Evaluation suite must be a schema_version=1 object with cases[]")
    results: list[dict[str, Any]] = []
    metrics = {
        "role_under_routing": 0,
        "role_over_routing": 0,
        "safety_constraint_violations": 0,
        "model_floor_violations": 0,
    }
    seen: set[str] = set()
    for case in suite["cases"]:
        if not isinstance(case, dict) or not case.get("id") or case["id"] in seen:
            raise ValueError("Every evaluation case needs a unique non-empty id")
        seen.add(case["id"])
        kind = case.get("kind")
        inputs = case.get("input", {})
        expected = case.get("expect", {})
        try:
            if kind == "role_route":
                actual = route_roles(input_fingerprint="eval-fixture", **inputs)
            elif kind == "model_route":
                actual = route_task(**inputs)
            elif kind == "review_plan":
                inventory = {
                    "manifest_fingerprint": inputs.get("manifest_fingerprint", "a" * 64),
                    "entries": inputs.get("entries", []),
                    "modules": inputs.get("modules", []),
                    "disposition_counts": inputs.get("disposition_counts", {}),
                }
                plan = build_review_plan(
                    inventory, budget=inputs.get("budget"), required_risks=inputs.get("required_risks"),
                )
                actual = {
                    "status": plan.get("status"),
                    "primary_shards": len(plan.get("primary_shards", [])),
                    "cross_cut_shards": len(plan.get("cross_cut_shards", [])),
                    "oversized_files": len(plan.get("oversized_files", [])),
                    "declared_files": len(plan.get("file_coverage", {})),
                    "budget_semantics": plan.get("budget_semantics"),
                    "coverage_claim_limit": plan.get("coverage_claim_limit"),
                    "required_risk_lenses": plan.get("required_risk_lenses", []),
                }
            elif kind == "findings_merge":
                merged = merge_findings(inputs.get("findings", []))
                actual = {
                    "input_count": merged["input_count"],
                    "merged_count": merged["merged_count"],
                    "exact_duplicate_groups": len(merged["exact_duplicate_groups"]),
                    "severity_conflicts": len(merged["severity_conflicts"]),
                    "possible_duplicates": len(merged["possible_duplicates"]),
                    "merge_policy": merged["merge_policy"],
                }
            else:
                raise ValueError(f"unsupported evaluation kind: {kind}")
            errors = _assertions(actual, expected)
        except ValueError as exc:
            actual = {"error": str(exc)}
            errors = [] if expected.get("error_contains") and expected["error_contains"] in str(exc) else [str(exc)]
        if kind == "role_route":
            actual_roles = set(actual.get("required_now", []))
            expected_roles = set(expected.get("required_now", []))
            if expected_roles - actual_roles:
                metrics["role_under_routing"] += 1
            if actual_roles - expected_roles and "required_now" in expected:
                metrics["role_over_routing"] += 1
            if {"engineering_lead", "qa"} <= set(actual.get("planned_roles", [])) or actual.get("max_active_subagents", 0) > 2:
                metrics["safety_constraint_violations"] += 1
        if kind == "model_route" and expected.get("status", "").startswith("BLOCKED") and not str(actual.get("status", "")).startswith("BLOCKED"):
            metrics["model_floor_violations"] += 1
        results.append({"id": case["id"], "kind": kind, "passed": not errors, "errors": errors, "actual": actual})
    passed = sum(1 for item in results if item["passed"])
    return {
        "schema_version": 1,
        "suite": suite.get("name", path.name),
        "policy_versions": suite.get("policy_versions", {}),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "metrics": metrics,
        "results": results,
        "scope_note": "This offline suite evaluates deterministic control-plane invariants, not real model intelligence or end-to-end project quality.",
    }


def evaluate_bundled() -> dict[str, Any]:
    reports = [evaluate(path) for path in BUNDLED_SUITES]
    results = [
        {**item, "suite": report["suite"]}
        for report in reports
        for item in report["results"]
    ]
    metrics: dict[str, int] = {}
    for report in reports:
        for key, value in report["metrics"].items():
            metrics[key] = metrics.get(key, 0) + int(value)
    return {
        "schema_version": 1,
        "suite": "bundled-control-plane-evaluations",
        "suites": [report["suite"] for report in reports],
        "total": sum(report["total"] for report in reports),
        "passed": sum(report["passed"] for report in reports),
        "failed": sum(report["failed"] for report in reports),
        "metrics": metrics,
        "results": results,
        "scope_note": (
            "These offline suites evaluate deterministic routing, review planning, and finding-merge "
            "invariants; they do not measure model intelligence or guarantee repository quality."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = evaluate(args.suite) if args.suite else evaluate_bundled()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"Routing eval: {report['passed']}/{report['total']} passed")
            for item in report["results"]:
                if not item["passed"]:
                    print(f"FAIL: {item['id']}: {'; '.join(item['errors'])}")
            print(f"Metrics: {json.dumps(report['metrics'], sort_keys=True)}")
            print(report["scope_note"])
        return 0 if report["failed"] == 0 else 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
