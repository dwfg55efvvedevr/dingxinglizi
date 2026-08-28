#!/usr/bin/env python3
"""Unified local control plane for Software Project Orchestrator v2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import CANONICAL_STATES, INTERRUPT_STATES, SKILL_ROOT, print_report, project_root, read_text
from check_execution_plan import check as check_execution_plan
from check_missing_modules import check as check_missing_modules
from check_project_status import check as check_project_status
from check_traceability import check as check_traceability
from create_task_package import create as create_task
from dispatch_receipt import record_dispatch_receipt
from doctor import diagnose, print_human
from domain_packs import apply_pack, list_packs, load_pack
from evaluate_routing import evaluate
from init_project import initialize
from lifecycle import transition as transition_lifecycle
from model_routing import KNOWN_TASK_TYPES
from resolve_capabilities import resolve as resolve_capabilities
from route_roles import route_project
from run_state import checkpoint as record_checkpoint
from run_state import create_run, report as create_report, resume as resume_run
from validate_documents import check as validate_documents


def version() -> str:
    return (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="Print the Skill product version")

    doctor_parser = sub.add_parser("doctor", help="Diagnose the Skill and an optional initialized project")
    doctor_parser.add_argument("project_dir", nargs="?")
    doctor_parser.add_argument("--json", action="store_true")

    init_parser = sub.add_parser("init", help="Initialize a new or empty project without overwriting files")
    init_parser.add_argument("project_dir")
    init_parser.add_argument("--project-name", required=True)
    init_parser.add_argument("--domain", required=True)
    init_parser.add_argument("--complexity", choices=["Simple", "Standard", "Complex"], default="Standard")
    init_parser.add_argument("--domain-pack", choices=[item["id"] for item in list_packs()])
    init_parser.add_argument("--dry-run", action="store_true")

    plan_parser = sub.add_parser("plan", help="Preview or persist the current-stage minimum role plan")
    plan_parser.add_argument("project_dir")
    plan_parser.add_argument("--stage", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES))
    plan_parser.add_argument("--quota", choices=["economy", "balanced", "quality_first"])
    plan_parser.add_argument("--signal", action="append", default=[])
    plan_parser.add_argument("--completed-role", action="append", default=[])
    plan_parser.add_argument("--completed-task", action="append", default=[])
    plan_parser.add_argument("--write", action="store_true")

    run_parser = sub.add_parser("run", help="Create a local run ledger and produce the next safe action")
    run_parser.add_argument("project_dir")
    checkpoint_parser = sub.add_parser("checkpoint", help="Persist a sanitized handoff, gate, block, reconciliation, or completion checkpoint")
    checkpoint_parser.add_argument("project_dir")
    checkpoint_parser.add_argument("--run-id")
    checkpoint_parser.add_argument("--event", required=True, choices=[
        "TASK_STARTED", "HANDOFF_PERSISTED", "GATE_DECISION", "TASK_BLOCKED", "STATE_RECONCILED", "RUN_COMPLETED",
    ])
    checkpoint_parser.add_argument("--task-id")
    checkpoint_parser.add_argument("--conclusion")
    checkpoint_parser.add_argument("--artifact", action="append", default=[])
    checkpoint_parser.add_argument("--evidence", action="append", default=[])
    checkpoint_parser.add_argument("--note")
    resume_parser = sub.add_parser("resume", help="Reconstruct a safe recovery decision without restarting Agents")
    resume_parser.add_argument("project_dir")
    resume_parser.add_argument("--run-id")
    report_parser = sub.add_parser("report", help="Generate an evidence-oriented run report")
    report_parser.add_argument("project_dir")
    report_parser.add_argument("--run-id")

    validate_parser = sub.add_parser("validate", help="Run document, completeness, traceability, and optional gate checks")
    validate_parser.add_argument("project_dir")
    validate_parser.add_argument("--target", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES))

    status_parser = sub.add_parser("status", help="Validate and summarize the current or target lifecycle state")
    status_parser.add_argument("project_dir")
    status_parser.add_argument("--target", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES))

    transition_parser = sub.add_parser("transition", help="Validate and persist a canonical lifecycle transition")
    transition_parser.add_argument("project_dir")
    transition_parser.add_argument("--target", required=True, choices=CANONICAL_STATES)

    task_parser = sub.add_parser("task", help="Create a governed DRAFT Task Package")
    task_parser.add_argument("project_dir")
    task_parser.add_argument("--task-id", required=True)
    task_parser.add_argument("--owner", required=True)
    task_parser.add_argument("--reviewer", required=True)
    task_parser.add_argument("--objective", required=True)
    task_parser.add_argument("--stage", required=True, choices=CANONICAL_STATES + sorted(INTERRUPT_STATES))
    task_parser.add_argument("--return-to", default="orchestrator")
    task_parser.add_argument("--task-type", choices=sorted(KNOWN_TASK_TYPES), default="implementation")
    task_parser.add_argument("--risk", action="append", default=[])
    task_parser.add_argument("--failed-attempts", type=int, default=0)
    task_parser.add_argument("--failure-type", default="none")
    task_parser.add_argument("--required-capability", action="append", default=[])
    task_parser.add_argument("--optional-capability", action="append", default=[])
    task_parser.add_argument("--available-model", action="append")

    preflight_parser = sub.add_parser("preflight", help="Validate a Task Package and optionally record its READY receipt")
    preflight_parser.add_argument("project_dir")
    preflight_parser.add_argument("task_package")
    preflight_parser.add_argument("--available-model", action="append")
    preflight_parser.add_argument("--record-ready", action="store_true")

    capability_parser = sub.add_parser("capabilities", help="Resolve required Skills/MCP through the safe Capability Broker")
    capability_parser.add_argument("project_dir")
    capability_parser.add_argument("--required", action="append", required=True)
    capability_parser.add_argument("--apply", action="store_true")

    eval_parser = sub.add_parser("eval", help="Run deterministic offline routing evaluations")
    eval_parser.add_argument("--suite", type=Path)
    eval_parser.add_argument("--json", action="store_true")

    domain_parser = sub.add_parser("domains", help="List, inspect, or safely apply a versioned domain pack")
    domain_sub = domain_parser.add_subparsers(dest="domain_command", required=True)
    domain_sub.add_parser("list")
    inspect_parser = domain_sub.add_parser("inspect")
    inspect_parser.add_argument("pack_id")
    apply_parser = domain_sub.add_parser("apply")
    apply_parser.add_argument("project_dir")
    apply_parser.add_argument("pack_id")
    apply_parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "version":
            print(version())
            return 0
        if args.command == "doctor":
            root = project_root(args.project_dir) if args.project_dir else None
            result = diagnose(root)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print_human(result)
            return 0 if result["status"] in {"READY", "READY_WITH_LIMITATIONS"} else 3
        if args.command == "init":
            root = project_root(args.project_dir)
            initialize(root, args.project_name.strip(), args.domain.strip(), args.complexity, args.dry_run)
            if args.domain_pack and not args.dry_run:
                print(json.dumps(apply_pack(root, args.domain_pack), ensure_ascii=False, indent=2))
            elif args.domain_pack and args.dry_run:
                print(json.dumps({"domain_pack": args.domain_pack, "status": "DRY_RUN_AFTER_INITIALIZATION"}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "plan":
            result = route_project(
                project_root(args.project_dir), stage=args.stage, quota=args.quota, signals=args.signal,
                completed_roles=args.completed_role, completed_tasks=args.completed_task, write=args.write,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "run":
            print(json.dumps(create_run(project_root(args.project_dir)), ensure_ascii=False, indent=2))
            return 0
        if args.command == "checkpoint":
            result = record_checkpoint(
                project_root(args.project_dir), args.run_id, event_type=args.event,
                task_id=args.task_id, conclusion=args.conclusion,
                artifact_refs=args.artifact, evidence_refs=args.evidence, note=args.note,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 3 if result["status"] == "BLOCKED" else 0
        if args.command == "resume":
            result = resume_run(project_root(args.project_dir), args.run_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 3 if result["decision"] in {"BLOCKED", "RECONCILIATION_REQUIRED"} else 0
        if args.command == "report":
            content, path = create_report(project_root(args.project_dir), args.run_id)
            print(json.dumps({"report": str(path), "content": content}, ensure_ascii=False, indent=2))
            return 0
        if args.command in {"validate", "status"}:
            root = project_root(args.project_dir)
            if args.command == "status":
                errors, warnings = check_project_status(root, args.target)
            else:
                errors, warnings = validate_documents(root)
                module_errors, module_warnings = check_missing_modules(root)
                trace_errors, trace_warnings = check_traceability(root)
                errors.extend(module_errors)
                warnings.extend(module_warnings)
                errors.extend(trace_errors)
                warnings.extend(trace_warnings)
                if args.target:
                    gate_errors, gate_warnings = check_project_status(root, args.target)
                    errors.extend(gate_errors)
                    warnings.extend(gate_warnings)
            return print_report(f"Software Project Orchestrator {args.command}", errors, warnings)
        if args.command == "transition":
            print(json.dumps(
                transition_lifecycle(project_root(args.project_dir), args.target),
                ensure_ascii=False, indent=2,
            ))
            return 0
        if args.command == "task":
            path = create_task(
                project_root(args.project_dir), args.task_id, args.owner, args.reviewer,
                args.objective, args.stage, args.return_to, args.task_type, args.risk,
                args.failed_attempts, args.failure_type, args.required_capability,
                args.optional_capability, args.available_model,
            )
            print(f"CREATED_DRAFT: {path}")
            return 0
        if args.command == "preflight":
            root = project_root(args.project_dir)
            task = Path(args.task_package)
            task = task if task.is_absolute() else root / task
            errors = check_execution_plan(root, task, args.available_model)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}")
                print(f"BLOCKED: {len(errors)} execution preflight error(s)")
                return 3
            if args.record_ready:
                receipt = record_dispatch_receipt(root, read_text(task))
                print(f"RECORDED: {receipt.relative_to(root)}")
            print("READY: route matches policy and required capabilities are available")
            return 0
        if args.command == "capabilities":
            result, blocked = resolve_capabilities(project_root(args.project_dir), sorted(set(args.required)), args.apply)
            print(json.dumps({"mode": "apply" if args.apply else "plan", "capabilities": result}, ensure_ascii=False, indent=2, sort_keys=True))
            return 3 if blocked else 0
        if args.command == "eval":
            result = evaluate(args.suite) if args.suite else evaluate()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"Routing eval: {result['passed']}/{result['total']} passed")
                for item in result["results"]:
                    if not item["passed"]:
                        print(f"FAIL: {item['id']}: {'; '.join(item['errors'])}")
                print(result["scope_note"])
            return 0 if result["failed"] == 0 else 1
        if args.command == "domains":
            if args.domain_command == "list":
                result = list_packs()
            elif args.domain_command == "inspect":
                result = load_pack(args.pack_id)
            else:
                result = apply_pack(project_root(args.project_dir), args.pack_id, args.dry_run)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        raise AssertionError(f"Unhandled command: {args.command}")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
