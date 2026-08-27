#!/usr/bin/env python3
"""Compute a deterministic Luna/Terra/Sol route for one work package."""

from __future__ import annotations

import argparse
import json
import sys

from model_routing import MODELS_BY_PREFERENCE, route_task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complexity", choices=["Simple", "Standard", "Complex"], required=True)
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--failed-attempts", type=int, default=0)
    parser.add_argument("--failure-type", default="none")
    parser.add_argument("--available-model", action="append", dest="available_models")
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
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(route, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if route["status"] == "ROUTED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
