#!/usr/bin/env python3
"""DingXingLiZi v3 control plane with explicit v2 compatibility."""

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
from dependency_check import dependency_report, print_human as print_dependencies_human
from doctor import diagnose, print_human
from domain_packs import apply_pack, list_packs, load_pack
from evaluate_routing import evaluate, evaluate_bundled
from evolution import collect as evolution_collect
from evolution import eval_candidates as evolution_eval_candidates
from evolution import evolution_init, feedback as evolution_feedback
from evolution import propose as evolution_propose
from evolution import retrospect as evolution_retrospect
from evolution import status as evolution_status
from evolution import CATEGORIES as EVOLUTION_CATEGORIES
from evolution import KINDS as EVOLUTION_KINDS
from evolution import RESULTS as EVOLUTION_RESULTS
from evolution import ROLES as EVOLUTION_ROLES
from evolution import SEVERITIES as EVOLUTION_SEVERITIES
from evolution_store import EvolutionBlocked
from init_project import initialize
from lifecycle import transition as transition_lifecycle
from large_repository_review import main as large_review_main
from migrate_project import apply as apply_migration
from migrate_project import plan as plan_migration
from model_routing import KNOWN_TASK_TYPES
from platform_install import install_platform
from project_layout import control_path
from platform_runtime import (
    CAPABILITY_TIERS, OPENCODE_SCHEMAS, PLATFORM_CHOICES, REASONING_LEVELS,
    build_runtime_manifest, detect_platforms, doctor_platform,
    load_runtime_manifest, render_adapter_files, render_project_adapter,
    resolve_model, resolve_opencode_schema,
    write_json_non_overwriting,
)
from resolve_capabilities import resolve as resolve_capabilities
from route_roles import route_project
from task_mode import TASK_MODES, classify_task_mode
from iteration_state import STATES as ITERATION_STATES, transition_iteration
from wait_budget import wait_decision
from run_state import checkpoint as record_checkpoint
from run_state import create_run, report as create_report, resume as resume_run
from validate_documents import check as validate_documents


def version() -> str:
    return (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="Print the Skill product version")

    dependencies_parser = sub.add_parser("dependencies", help="Report required, optional-feature, and development-only dependencies")
    dependencies_parser.add_argument("--json", action="store_true")

    doctor_parser = sub.add_parser("doctor", help="Diagnose the Skill and an optional initialized project")
    doctor_parser.add_argument("project_dir", nargs="?")
    doctor_parser.add_argument("--json", action="store_true")

    init_parser = sub.add_parser("init", help="Initialize a new or empty project without overwriting files")
    init_parser.add_argument("project_dir")
    init_parser.add_argument("--project-name", required=True)
    init_parser.add_argument("--domain", required=True)
    init_parser.add_argument("--complexity", choices=["Simple", "Standard", "Complex"], default="Standard")
    init_parser.add_argument("--platform", choices=("auto",) + PLATFORM_CHOICES, default="auto")
    init_parser.add_argument("--opencode-schema", choices=OPENCODE_SCHEMAS, default="auto")
    init_parser.add_argument("--domain-pack", choices=[item["id"] for item in list_packs()])
    init_parser.add_argument("--dry-run", action="store_true")

    migrate_parser = sub.add_parser("migrate", help="Preview or apply a non-destructive v2 control-state migration")
    migrate_parser.add_argument("project_dir")
    migrate_parser.add_argument("--apply", action="store_true")
    migrate_parser.add_argument("--include-evolution", action="store_true")

    plan_parser = sub.add_parser("plan", help="Preview or persist the current-stage minimum role plan")
    plan_parser.add_argument("project_dir")
    plan_parser.add_argument("--stage", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES))
    plan_parser.add_argument("--quota", choices=["economy", "balanced", "quality_first"])
    plan_parser.add_argument("--signal", action="append", default=[])
    plan_parser.add_argument("--completed-role", action="append", default=[])
    plan_parser.add_argument("--completed-task", action="append", default=[])
    plan_parser.add_argument("--write", action="store_true")
    plan_parser.add_argument("--task-mode", choices=TASK_MODES)

    triage_parser = sub.add_parser("triage", help="Choose task governance before loading the project lifecycle")
    triage_parser.add_argument("--project-complexity", choices=["Simple", "Standard", "Complex"], required=True)
    triage_parser.add_argument("--signal", action="append", default=[])
    triage_parser.add_argument("--requested-mode", choices=TASK_MODES)
    triage_parser.add_argument("--estimated-business-files", type=int, default=1)
    triage_parser.add_argument("--estimated-minutes", type=int)
    triage_parser.add_argument("--explicit-skill", action="store_true")
    triage_parser.add_argument("--full-process", action="store_true")

    wait_parser = sub.add_parser("wait-budget", help="Decide whether another wait is allowed or takeover is required")
    wait_parser.add_argument("--task-mode", choices=TASK_MODES, required=True)
    wait_parser.add_argument("--no-progress-cycles", type=int, required=True)
    wait_parser.add_argument("--elapsed-minutes", type=int, default=0)

    iteration_parser = sub.add_parser("iteration-transition", help="Advance a bounded delta without changing project state")
    iteration_parser.add_argument("--current", choices=ITERATION_STATES, required=True)
    iteration_parser.add_argument("--target", choices=ITERATION_STATES, required=True)
    iteration_parser.add_argument("--repair-rounds", type=int, default=0)
    iteration_parser.add_argument("--engineering-session", default="")
    iteration_parser.add_argument("--qa-session", default="")
    iteration_parser.add_argument("--qa-conclusion", default="")
    iteration_parser.add_argument("--qa-evidence", action="append", default=[])
    iteration_parser.add_argument("--unaccepted-p0-p1", type=int, default=0)

    quick_parser = sub.add_parser("quick", help="Preview a no-subagent local patch receipt without initializing governance")
    quick_parser.add_argument("project_dir")
    quick_parser.add_argument("--goal", required=True)
    quick_parser.add_argument("--target", action="append", required=True)
    quick_parser.add_argument("--verify", action="append", required=True)

    change_parser = sub.add_parser("change", help="Preview a Compact Delta Contract for a bounded change")
    change_parser.add_argument("project_dir")
    change_parser.add_argument("--goal", required=True)
    change_parser.add_argument("--surface", action="append", required=True)
    change_parser.add_argument("--verify", action="append", default=[])

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

    review_parser = sub.add_parser(
        "review",
        add_help=False,
        help="Run the bounded large-repository review engine (use `review --help`)",
    )
    review_parser.add_argument("-h", "--help", action="store_true", dest="review_help")
    review_parser.add_argument("review_args", nargs=argparse.REMAINDER)

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
    task_parser.add_argument("--review-shard", help="Bind the Task Package to one active review shard")
    task_parser.add_argument("--repair-plan", help="Bind the Task Package to one active repair/rereview plan")

    preflight_parser = sub.add_parser("preflight", help="Validate a Task Package and optionally record its READY receipt")
    preflight_parser.add_argument("project_dir")
    preflight_parser.add_argument("task_package")
    preflight_parser.add_argument("--available-model", action="append")
    preflight_parser.add_argument("--record-ready", action="store_true")

    capability_parser = sub.add_parser("capabilities", help="Resolve required Skills/MCP through the safe Capability Broker")
    capability_parser.add_argument("project_dir")
    capability_parser.add_argument("--required", action="append", required=True)
    capability_parser.add_argument("--apply", action="store_true")

    platform_parser = sub.add_parser("platform", help="Detect, install, render, and verify native host adapters")
    platform_sub = platform_parser.add_subparsers(dest="platform_command", required=True)
    platform_detect = platform_sub.add_parser("detect", help="Probe supported runtime executables without changing them")
    platform_detect.add_argument("--platform", choices=PLATFORM_CHOICES)
    platform_render = platform_sub.add_parser("render", help="Render only one platform's project Agent profiles")
    platform_render.add_argument("project_dir")
    platform_render.add_argument("--platform", required=True, choices=PLATFORM_CHOICES)
    platform_render.add_argument("--update", action="store_true", help="Update differing generated profiles")
    platform_render.add_argument("--opencode-schema", choices=OPENCODE_SCHEMAS, default="auto")
    platform_install_parser = platform_sub.add_parser("install", help="Plan or explicitly apply a user/project install")
    platform_install_parser.add_argument("target_dir", nargs="?")
    platform_install_parser.add_argument("--platform", required=True, choices=PLATFORM_CHOICES)
    platform_install_parser.add_argument("--scope", required=True, choices=["user", "project"])
    platform_install_parser.add_argument("--apply", action="store_true", help="Write the planned files; default is preview")
    platform_install_parser.add_argument("--update", action="store_true", help="Update differing installed files")
    platform_install_parser.add_argument("--opencode-schema", choices=OPENCODE_SCHEMAS, default="auto")
    platform_doctor = platform_sub.add_parser("doctor", help="Report honest L1-L4 compatibility for one target")
    platform_doctor.add_argument("target_dir", nargs="?")
    platform_doctor.add_argument("--platform", required=True, choices=PLATFORM_CHOICES)
    platform_doctor.add_argument("--scope", default="project", choices=["user", "project"])
    platform_doctor.add_argument("--manifest", type=Path)
    platform_doctor.add_argument("--opencode-schema", choices=OPENCODE_SCHEMAS, default="auto")
    platform_doctor.add_argument("--require-level", choices=["L1", "L2", "L3", "L4"])
    platform_manifest = platform_sub.add_parser("runtime-manifest", help="Capture executable and sourced model-inventory evidence")
    platform_manifest.add_argument("--platform", required=True, choices=PLATFORM_CHOICES)
    platform_manifest.add_argument("--project-dir")
    platform_manifest.add_argument("--models-file", type=Path)
    platform_manifest.add_argument("--evidence-source", default="")
    platform_manifest.add_argument("--models-verified", action="store_true")
    platform_manifest.add_argument("--dispatch-receipt", type=Path)
    platform_manifest.add_argument("--output", type=Path)
    platform_manifest.add_argument("--update", action="store_true")
    platform_resolve = platform_sub.add_parser("model-resolve", help="Resolve a logical capability tier from a runtime manifest")
    platform_resolve.add_argument("manifest", type=Path)
    platform_resolve.add_argument("--tier", required=True, choices=CAPABILITY_TIERS)
    platform_resolve.add_argument("--reasoning", default="medium", choices=REASONING_LEVELS)
    platform_resolve.add_argument("--risk", action="append", default=[])
    platform_resolve.add_argument("--risk-level", default="normal", choices=["low", "normal", "high"])

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

    evolution_parser = sub.add_parser("evolution", help="Manage the project-local, review-gated Evolution Core")
    evolution_sub = evolution_parser.add_subparsers(dest="evolution_command", required=True)
    evolution_init_parser = evolution_sub.add_parser("init", help="Explicitly initialize an isolated Evolution workspace")
    evolution_init_parser.add_argument("project_dir")
    collect_parser = evolution_sub.add_parser("collect", help="Collect one structurally validated completed run")
    collect_parser.add_argument("project_dir")
    collect_parser.add_argument("--run-id")
    feedback_parser = evolution_sub.add_parser("feedback", help="Record sanitized, evidence-linked feedback")
    feedback_parser.add_argument("project_dir")
    feedback_parser.add_argument("--kind", required=True, choices=EVOLUTION_KINDS)
    feedback_parser.add_argument("--result", required=True, choices=EVOLUTION_RESULTS)
    feedback_parser.add_argument("--severity", required=True, choices=EVOLUTION_SEVERITIES)
    feedback_parser.add_argument("--category", required=True, choices=EVOLUTION_CATEGORIES)
    feedback_parser.add_argument("--summary", required=True)
    feedback_parser.add_argument("--evidence", action="append", required=True)
    feedback_parser.add_argument("--run-id")
    feedback_parser.add_argument("--task-id")
    feedback_parser.add_argument("--role", choices=EVOLUTION_ROLES)
    retrospect_parser = evolution_sub.add_parser("retrospect", help="Generate a deterministic evidence retrospective")
    retrospect_parser.add_argument("project_dir")
    retrospect_parser.add_argument("--run-id")
    propose_parser = evolution_sub.add_parser("propose", help="Generate review-required improvement proposal drafts")
    propose_parser.add_argument("project_dir")
    propose_parser.add_argument("--retrospective")
    candidate_parser = evolution_sub.add_parser("eval-candidates", help="Generate an isolated regression-eval candidate draft")
    candidate_parser.add_argument("project_dir")
    candidate_parser.add_argument("--proposal")
    evolution_status_parser = evolution_sub.add_parser("status", help="Inspect Evolution without mutating it")
    evolution_status_parser.add_argument("project_dir")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "version":
            print(version())
            return 0
        if args.command == "dependencies":
            result = dependency_report()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print_dependencies_human(result)
            return 0 if result["runtime_ready"] else 3
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
            selected_platform = args.platform
            if selected_platform == "auto":
                detection = detect_platforms()
                selected_platform = detection["selected_platform"]
                if not selected_platform:
                    found = [
                        name for name, probe in detection["platforms"].items()
                        if probe["status"] != "NOT_FOUND"
                    ]
                    if found:
                        raise ValueError(
                            "auto platform detection is ambiguous (%s); pass --platform explicitly"
                            % ", ".join(found)
                        )
                    # Backward-compatible format choice only. This does not claim a
                    # Codex runtime exists; platform doctor will report it unverified.
                    selected_platform = "codex"
                    print("WARNING: no runtime executable detected; rendering the backward-compatible Codex adapter")
            # Resolve and render the host schema before project initialization.
            # The initializer validates template + adapter paths together and
            # renders every payload before its first write, preventing a failed
            # adapter from leaving an unrecoverable half-initialized project.
            selected_opencode_schema = (
                resolve_opencode_schema(args.opencode_schema)
                if selected_platform == "opencode" else ""
            )
            adapter_files = render_adapter_files(
                selected_platform,
                opencode_schema=selected_opencode_schema or args.opencode_schema,
            )
            initialize(
                root, args.project_name.strip(), args.domain.strip(), args.complexity,
                args.dry_run, platform_neutral=True,
                generated_files=adapter_files,
            )
            if args.dry_run:
                print(f"Platform adapter to render: {selected_platform}")
            else:
                adapter_result = {
                    "status": "RENDERED",
                    "platform": selected_platform,
                    "scope": "project",
                    "root": str(root),
                    "created": [str(root / relative) for relative in sorted(adapter_files)],
                    "updated": [],
                    "unchanged": [],
                    "conflicts": [],
                }
                if selected_platform == "opencode":
                    adapter_result["adapter_schema"] = selected_opencode_schema
                print(json.dumps({"platform_adapter": adapter_result}, ensure_ascii=False, indent=2))
            if args.domain_pack and not args.dry_run:
                print(json.dumps(apply_pack(root, args.domain_pack), ensure_ascii=False, indent=2))
            elif args.domain_pack and args.dry_run:
                print(json.dumps({"domain_pack": args.domain_pack, "status": "DRY_RUN_AFTER_INITIALIZATION"}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "migrate":
            root = project_root(args.project_dir)
            result = apply_migration(root, args.include_evolution) if args.apply else plan_migration(root, args.include_evolution)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "plan":
            plan_signals = list(args.signal)
            if args.task_mode:
                plan_signals.append(args.task_mode.lower())
            result = route_project(
                project_root(args.project_dir), stage=args.stage, quota=args.quota, signals=plan_signals,
                completed_roles=args.completed_role, completed_tasks=args.completed_task, write=args.write,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "triage":
            triage_signals = list(args.signal)
            if args.explicit_skill:
                triage_signals.append("explicit_skill_invocation")
            if args.full_process:
                triage_signals.append("full_process_requested")
            print(json.dumps(classify_task_mode(
                project_complexity=args.project_complexity,
                signals=triage_signals,
                requested_mode=args.requested_mode,
                estimated_business_files=args.estimated_business_files,
                estimated_minutes=args.estimated_minutes,
            ), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "wait-budget":
            print(json.dumps(wait_decision(
                task_mode=args.task_mode,
                consecutive_no_progress=args.no_progress_cycles,
                elapsed_minutes=args.elapsed_minutes,
            ), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "iteration-transition":
            print(json.dumps(transition_iteration(
                args.current, args.target, repair_rounds=args.repair_rounds,
                engineering_session=args.engineering_session, qa_session=args.qa_session,
                qa_conclusion=args.qa_conclusion, qa_evidence=args.qa_evidence,
                unaccepted_p0_p1=args.unaccepted_p0_p1,
            ), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command in {"quick", "change"}:
            local_root = Path(args.project_dir).expanduser().resolve()
            if not local_root.is_dir():
                raise ValueError(f"project directory does not exist: {local_root}")
            if args.command == "quick":
                payload = {
                    "status": "PREVIEW", "writes_performed": False,
                    "task_mode": "QUICK_PATCH", "project_root": str(local_root),
                    "goal": args.goal, "target_scope": args.target,
                    "verification": args.verify, "owner": "main_session",
                    "subagents": 0, "max_active_subagents": 0,
                    "max_total_role_sessions": 1,
                    "time_expectation": {"min": 3, "max": 15},
                    "next_action": "implement-narrowly-then-run-targeted-verification",
                }
            else:
                payload = {
                    "status": "PREVIEW", "writes_performed": False,
                    "task_mode": "BOUNDED_CHANGE", "project_root": str(local_root),
                    "compact_delta_contract": {
                        "current_problem": args.goal,
                        "allowed_scope": args.surface,
                        "preserved_business_rules": ["record-before-implementation"],
                        "acceptance_criteria": args.verify or ["BLOCKING_UNKNOWN: add 3-8 observable criteria"],
                        "targeted_tests": args.verify or ["BLOCKING_UNKNOWN: add targeted validation"],
                        "risks_and_rollback": ["record-before-implementation"],
                    },
                    "workflow": [
                        "single_engineering_lead", "targeted_validation", "independent_qa",
                        "at_most_one_targeted_repair",
                    ],
                    "max_active_subagents": 1, "max_total_role_sessions": 2,
                    "time_expectation": {"min": 15, "max": 45},
                    "next_action": "complete-contract-then-dispatch-one-engineering-owner",
                }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
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
        if args.command == "review":
            return large_review_main(["--help"] if args.review_help else args.review_args)
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
                args.review_shard,
                args.repair_plan,
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
        if args.command == "platform":
            if args.platform_command == "detect":
                result = detect_platforms(args.platform)
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            if args.platform_command == "render":
                result = render_project_adapter(
                    project_root(args.project_dir), args.platform, update=args.update,
                    opencode_schema=args.opencode_schema,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 3 if result["status"] == "BLOCKED_CONFLICT" else 0
            if args.platform_command == "install":
                if args.target_dir:
                    target = Path(args.target_dir).expanduser().resolve()
                elif args.scope == "user":
                    target = Path.home().resolve()
                else:
                    raise ValueError("project scope requires target_dir")
                result = install_platform(
                    target, args.platform, scope=args.scope,
                    apply=args.apply, update=args.update,
                    opencode_schema=args.opencode_schema,
                )
                dependencies = dependency_report()
                result["dependency_status"] = dependencies["status"]
                result["dependency_notices"] = dependencies["notices"]
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 3 if result["status"] == "BLOCKED_CONFLICT" else 0
            if args.platform_command == "doctor":
                if args.target_dir:
                    target = Path(args.target_dir).expanduser().resolve()
                elif args.scope == "user":
                    target = Path.home().resolve()
                else:
                    target = Path.cwd().resolve()
                manifest = load_runtime_manifest(args.manifest) if args.manifest else None
                result = doctor_platform(
                    args.platform, target, scope=args.scope, manifest=manifest,
                    opencode_schema=args.opencode_schema,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                if args.require_level:
                    actual = int(result["compatibility_level"][1:])
                    required = int(args.require_level[1:])
                    return 3 if actual < required else 0
                return 3 if result["compatibility_level"] == "L0" else 0
            if args.platform_command == "runtime-manifest":
                result = build_runtime_manifest(
                    args.platform, models_file=args.models_file,
                    evidence_source=args.evidence_source,
                    models_verified=args.models_verified,
                    dispatch_receipt=args.dispatch_receipt,
                )
                output_path = args.output
                allowed_root = None
                if output_path is None and args.project_dir:
                    allowed_root = project_root(args.project_dir)
                    output_path = control_path(
                        allowed_root,
                        "orchestration/runtime-manifest.json",
                    )
                if output_path:
                    write_result = write_json_non_overwriting(
                        output_path, result, update=args.update, allowed_root=allowed_root,
                    )
                    print(json.dumps({"manifest": result, "write": write_result}, ensure_ascii=False, indent=2, sort_keys=True))
                    return 3 if write_result["status"] == "BLOCKED_CONFLICT" else 0
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            if args.platform_command == "model-resolve":
                result = resolve_model(
                    load_runtime_manifest(args.manifest), args.tier,
                    reasoning_effort=args.reasoning,
                    risk_flags=args.risk, risk_level=args.risk_level,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 3 if result["status"].startswith("BLOCKED") else 0
            raise AssertionError(f"Unhandled platform command: {args.platform_command}")
        if args.command == "eval":
            result = evaluate(args.suite) if args.suite else evaluate_bundled()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"Control-plane eval: {result['passed']}/{result['total']} passed")
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
        if args.command == "evolution":
            root = project_root(args.project_dir)
            if args.evolution_command == "init":
                result = evolution_init(root)
            elif args.evolution_command == "collect":
                result = evolution_collect(root, args.run_id)
            elif args.evolution_command == "feedback":
                result = evolution_feedback(
                    root, kind=args.kind, result=args.result, severity=args.severity,
                    category=args.category, summary=args.summary,
                    evidence_paths=args.evidence, run_id=args.run_id,
                    task_id=args.task_id, role=args.role,
                )
            elif args.evolution_command == "retrospect":
                result = evolution_retrospect(root, args.run_id)
            elif args.evolution_command == "propose":
                result = evolution_propose(root, args.retrospective)
            elif args.evolution_command == "eval-candidates":
                result = evolution_eval_candidates(root, args.proposal)
            else:
                result = evolution_status(root)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 3 if result.get("status") == "BLOCKED" else 0
        raise AssertionError(f"Unhandled command: {args.command}")
    except EvolutionBlocked as exc:
        print(json.dumps(exc.payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 3
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
