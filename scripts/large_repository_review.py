#!/usr/bin/env python3
"""API facade and standalone CLI for the DingXingLiZi large-repository review engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from review_state import (
    finalize_review,
    ingest_result,
    merge_findings,
    plan_repairs,
    record_repair,
    record_rereview,
    record_qa,
    repair_contract,
    preview_review,
    shard_contract,
    start_review,
    status_review,
)
from state_io import load_json_object


PUBLIC_API = (
    "preview_review", "start_review", "shard_contract", "ingest_result", "merge_findings", "plan_repairs",
    "record_repair", "record_rereview", "record_qa", "repair_contract", "status_review", "finalize_review",
)


def _json_arg(value: str | None, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    path = Path(value).resolve()
    try:
        return load_json_object(path)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: {exc}") from exc


def _list_arg(value: str | None) -> list[str]:
    if value is None or value == "":
        return []
    values = [item.strip() for item in value.split(",")]
    if not all(values):
        raise ValueError("Comma-separated list contains an empty value")
    return values


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for command in ("preview", "start"):
        start = sub.add_parser(command)
        start.add_argument("project_dir")
        start.add_argument("--baseline", default="HEAD")
        start.add_argument("--target", default="HEAD")
        start.add_argument("--mode", choices=("review_only", "review_and_fix"), default="review_only")
        start.add_argument("--authorize-fix", action="store_true")
        start.add_argument("--budget-json")
        start.add_argument("--run-id")
        start.add_argument("--worktree-snapshot", action="store_true")
        start.add_argument(
            "--required-risk", action="append", default=[],
            help="Mandatory cross-cutting risk lens; repeat as needed",
        )
        start.add_argument(
            "--trusted-instruction", action="append", default=[],
            help="Explicitly trusted project-relative instruction file; repeat as needed",
        )
        start.add_argument(
            "--allow-repository-execution", action="store_true",
            help="Explicitly authorize bounded repository commands; default is no repository execution",
        )

    status = sub.add_parser("status")
    status.add_argument("project_dir")
    status.add_argument("--run-id")

    contract = sub.add_parser("contract")
    contract.add_argument("project_dir")
    contract.add_argument("shard_id")
    contract.add_argument("--run-id")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("project_dir")
    ingest.add_argument("shard_id")
    ingest.add_argument("result_json")
    ingest.add_argument("--run-id")

    merge = sub.add_parser("merge")
    merge.add_argument("project_dir")
    merge.add_argument("--run-id")

    repair_plan = sub.add_parser("plan-repairs")
    repair_plan.add_argument("project_dir")
    repair_plan.add_argument("--fixer", required=True)
    repair_plan.add_argument("--reviewer", required=True)
    repair_plan.add_argument("--finding-ids")
    repair_plan.add_argument("--allowed-file", action="append", default=[])
    repair_plan.add_argument("--round", type=int)
    repair_plan.add_argument("--run-id")

    repair_contract_parser = sub.add_parser("repair-contract")
    repair_contract_parser.add_argument("project_dir")
    repair_contract_parser.add_argument("repair_plan_id")
    repair_contract_parser.add_argument("--phase", required=True, choices=("REPAIR", "REREVIEW"))
    repair_contract_parser.add_argument("--run-id")

    repair = sub.add_parser("record-repair")
    repair.add_argument("project_dir")
    repair.add_argument("--repair-plan-id", required=True)
    repair.add_argument("--task-id", required=True)
    repair.add_argument("--fixer", required=True)
    repair.add_argument("--fixer-session", required=True)
    repair.add_argument("--finding-ids", required=True)
    repair.add_argument("--evidence-refs", required=True)
    repair.add_argument(
        "--artifact-fingerprint",
        help="Optional asserted fingerprint; when supplied it must match the engine-computed source snapshot",
    )
    repair.add_argument("--session-attestation-json")
    repair.add_argument("--run-id")

    rereview = sub.add_parser("record-rereview")
    rereview.add_argument("project_dir")
    rereview.add_argument("--repair-plan-id", required=True)
    rereview.add_argument("--task-id", required=True)
    rereview.add_argument("--reviewer", required=True)
    rereview.add_argument("--reviewer-session", required=True)
    rereview.add_argument("--outcomes-json", required=True)
    rereview.add_argument("--verification-notes-json", required=True)
    rereview.add_argument("--evidence-refs", required=True)
    rereview.add_argument("--session-attestation-json")
    rereview.add_argument("--run-id")

    qa = sub.add_parser("record-qa")
    qa.add_argument("project_dir")
    qa.add_argument("--qa", default="qa")
    qa.add_argument("--task-id", required=True)
    qa.add_argument("--qa-session", required=True)
    qa.add_argument("--evidence-refs", required=True)
    qa.add_argument("--finding-verifications-json", required=True)
    qa.add_argument("--session-attestation-json")
    qa.add_argument("--run-id")

    finalize = sub.add_parser("finalize")
    finalize.add_argument("project_dir")
    finalize.add_argument("--run-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = Path(args.project_dir).resolve()
    try:
        if args.command in {"preview", "start"}:
            budget = _json_arg(args.budget_json, "budget JSON") if args.budget_json else None
            operation = preview_review if args.command == "preview" else start_review
            value = operation(
                root, baseline=args.baseline, target=args.target, mode=args.mode,
                fix_authorized=args.authorize_fix, budget=budget, run_id=args.run_id,
                worktree_snapshot=args.worktree_snapshot,
                required_risks=args.required_risk,
                trusted_instructions=args.trusted_instruction,
                allow_repository_execution=args.allow_repository_execution,
            )
        elif args.command == "status":
            value = status_review(root, run_id=args.run_id)
        elif args.command == "contract":
            value = shard_contract(root, args.shard_id, run_id=args.run_id)
        elif args.command == "ingest":
            value = ingest_result(root, args.shard_id, _json_arg(args.result_json, "result JSON"), run_id=args.run_id)
        elif args.command == "merge":
            value = merge_findings(root, run_id=args.run_id)
        elif args.command == "plan-repairs":
            value = plan_repairs(
                root, fixer_id=args.fixer, reviewer_id=args.reviewer,
                finding_ids=_list_arg(args.finding_ids) or None,
                allowed_files=args.allowed_file,
                round_number=args.round, run_id=args.run_id,
            )
        elif args.command == "repair-contract":
            value = repair_contract(
                root, args.repair_plan_id, phase=args.phase, run_id=args.run_id,
            )
        elif args.command == "record-repair":
            value = record_repair(
                root, repair_plan_id=args.repair_plan_id, task_id=args.task_id, fixer_id=args.fixer,
                fixer_session_id=args.fixer_session, finding_ids=_list_arg(args.finding_ids),
                evidence_refs=_list_arg(args.evidence_refs),
                repair_artifact_fingerprint=args.artifact_fingerprint, run_id=args.run_id,
                session_attestation=(
                    _json_arg(args.session_attestation_json, "session attestation JSON")
                    if args.session_attestation_json else None
                ),
            )
        elif args.command == "record-rereview":
            outcomes = _json_arg(args.outcomes_json, "outcomes JSON")
            verification_notes = _json_arg(args.verification_notes_json, "verification notes JSON")
            if not all(isinstance(key, str) and isinstance(value, str) for key, value in outcomes.items()):
                raise ValueError("Outcomes JSON must map finding IDs to string outcomes")
            if not all(isinstance(key, str) and isinstance(value, str) for key, value in verification_notes.items()):
                raise ValueError("Verification notes JSON must map finding IDs to concrete string evidence")
            value = record_rereview(
                root, repair_plan_id=args.repair_plan_id, task_id=args.task_id, reviewer_id=args.reviewer,
                reviewer_session_id=args.reviewer_session, outcomes=outcomes,
                verification_notes=verification_notes,
                evidence_refs=_list_arg(args.evidence_refs), run_id=args.run_id,
                session_attestation=(
                    _json_arg(args.session_attestation_json, "session attestation JSON")
                    if args.session_attestation_json else None
                ),
            )
        elif args.command == "record-qa":
            finding_verifications = _json_arg(args.finding_verifications_json, "finding verifications JSON")
            if not all(isinstance(key, str) and isinstance(value, str) for key, value in finding_verifications.items()):
                raise ValueError("Finding verifications JSON must map P0/P1 finding IDs to concrete strings")
            value = record_qa(
                root, qa_id=args.qa, task_id=args.task_id, qa_session_id=args.qa_session,
                evidence_refs=_list_arg(args.evidence_refs), run_id=args.run_id,
                finding_verifications=finding_verifications,
                session_attestation=(
                    _json_arg(args.session_attestation_json, "session attestation JSON")
                    if args.session_attestation_json else None
                ),
            )
        else:
            value = finalize_review(root, run_id=args.run_id)
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
