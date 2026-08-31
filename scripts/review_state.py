#!/usr/bin/env python3
"""Run-bound state machine for deterministic large-repository review."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from project_layout import control_path, layout_report
from dispatch_receipt import validate_dispatch_receipt
from review_findings import merge_findings as merge_finding_values, validate_finding
from review_planning import build_review_plan, canonical_hash, validate_plan_fingerprint
from review_repository import (
    capture_git_snapshot,
    capture_worktree_snapshot,
    effective_source_snapshot,
    selected_source_snapshot,
    inventory_git_target,
    is_git_repository,
    validate_snapshot_unchanged,
)
from run_state import latest_run_id
from state_io import atomic_write_json, load_json_object, safe_project_path, utc_now
from task_contract import (
    TASK_ID_PATTERN,
    list_field,
    quoted_scalar,
    task_dispatch_fingerprint,
    top_section,
    validate_task_contract,
)


REVIEW_MODES = {"review_only", "review_and_fix"}
RESULT_STATUSES = {"COMPLETE", "BLOCKED"}
REVIEWER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$")
MAX_REPAIR_ROUNDS = 2
MAX_FINDINGS_PER_SHARD = 10_000
SESSION_STATUSES = {"ATTESTED_SESSION_ISOLATION", "UNVERIFIED_SESSION_ISOLATION"}


def _write(root: Path, path: Path, value: Any) -> None:
    atomic_write_json(path, value, allowed_root=root.resolve())


def _review_dir(root: Path, run_id: str) -> Path:
    return control_path(root, Path("runs") / run_id / "review")


def _file(root: Path, run_id: str, name: str) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9-]*\.json", name):
        raise ValueError(f"Invalid review state file name: {name}")
    return control_path(root, Path("runs") / run_id / "review" / name)


def _open_run(
    root: Path, run_id: str | None = None, *, starting_review: bool = False,
) -> tuple[str, dict[str, Any]]:
    selected = run_id or latest_run_id(root)
    current = latest_run_id(root)
    if selected != current:
        raise ValueError("Large repository review must bind to the current latest run")
    run_path = control_path(root, Path("runs") / selected / "run.json")
    run = load_json_object(run_path)
    if run.get("run_id") != selected or run.get("status") != "OPEN":
        raise ValueError("Large repository review requires the current OPEN run")
    # Governed v3 runs carry a lifecycle stage. Legacy/minimal ledgers without
    # this field remain readable, but a full project may start this engine only
    # from the CODE_REVIEW gate with the explicit routing signal.
    if "current_state" in run:
        allowed = {"CODE_REVIEW"} if starting_review else {"CODE_REVIEW", "READY_FOR_QA", "QA_PASS"}
        if run.get("current_state") not in allowed:
            raise ValueError(
                "Large repository review requires the governed run to be at " + ", ".join(sorted(allowed))
            )
        if not starting_review:
            return selected, run
        role_plan_path = control_path(root, "orchestration/role-plan.json")
        role_plan = load_json_object(role_plan_path)
        if (
            role_plan.get("status") != "ROUTED"
            or role_plan.get("current_stage") != "CODE_REVIEW"
            or "large_repository_review" not in role_plan.get("signals", [])
        ):
            raise ValueError(
                "Large repository review requires a current CODE_REVIEW role plan with large_repository_review signal"
            )
    return selected, run


def _initial_files(root: Path, run_id: str) -> None:
    for name, value in (
        ("results.json", {
            "schema_version": 1, "results": [],
            "store_fingerprint": canonical_hash([]),
        }),
        ("findings.json", {"schema_version": 1, "input_count": 0, "merged_count": 0, "findings": []}),
        ("repairs.json", {"schema_version": 1, "max_rounds": MAX_REPAIR_ROUNDS, "plans": [], "records": []}),
        ("rereviews.json", {"schema_version": 1, "records": []}),
        ("qa.json", {"schema_version": 1, "status": "PENDING", "record": None}),
        ("coverage.json", {"schema_version": 1, "status": "INCOMPLETE", "reasons": ["no-results"]}),
    ):
        _write(root, _file(root, run_id, name), value)


def start_review(
    root: Path,
    *,
    baseline: str = "HEAD",
    target: str = "HEAD",
    mode: str = "review_only",
    fix_authorized: bool = False,
    budget: dict[str, Any] | None = None,
    run_id: str | None = None,
    worktree_snapshot: bool = False,
    required_risks: list[str] | None = None,
    trusted_instructions: list[str] | None = None,
    allow_repository_execution: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    selected, run, snapshot, inventory, plan, trust = _prepare_review(
        root, baseline=baseline, target=target, mode=mode,
        fix_authorized=fix_authorized, budget=budget, run_id=run_id,
        worktree_snapshot=worktree_snapshot, required_risks=required_risks,
        trusted_instructions=trusted_instructions,
        allow_repository_execution=allow_repository_execution,
    )
    directory = _review_dir(root, selected)
    plan_document_fingerprint = canonical_hash(plan)
    now = utc_now()
    status = "READY" if plan.get("status") == "READY" else str(plan.get("status"))
    review = {
        "schema_version": 1,
        "run_id": selected,
        "project": run.get("project"),
        "created_at": now,
        "updated_at": now,
        "status": status,
        "review_mode": mode,
        "fix_authorized": bool(fix_authorized),
        "snapshot_kind": snapshot.get("snapshot_kind"),
        "target_fingerprint": snapshot.get("target_commit") or inventory.get("manifest_fingerprint"),
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "plan_document_fingerprint": plan_document_fingerprint,
        "trust_policy_fingerprint": trust.get("policy_fingerprint"),
        "max_repair_rounds": MAX_REPAIR_ROUNDS,
        "control_layout": layout_report(root)["layout"],
        "working_tree_drift": snapshot.get("working_tree", {}),
        "completion_claim": None,
        "stale_reasons": [],
    }
    directory.mkdir(parents=True, exist_ok=False)
    _write(root, _file(root, selected, "snapshot.json"), snapshot)
    _write(root, _file(root, selected, "inventory.json"), inventory)
    _write(root, _file(root, selected, "plan.json"), plan)
    _write(root, _file(root, selected, "trust.json"), trust)
    _initial_files(root, selected)
    _write(root, _file(root, selected, "review.json"), review)
    return _review_summary(
        selected, mode, snapshot, inventory, plan,
        review_root=str(directory.relative_to(root)), write_mode="PERSISTED",
        trust=trust,
    )


def preview_review(
    root: Path,
    *,
    baseline: str = "HEAD",
    target: str = "HEAD",
    mode: str = "review_only",
    fix_authorized: bool = False,
    budget: dict[str, Any] | None = None,
    run_id: str | None = None,
    worktree_snapshot: bool = False,
    required_risks: list[str] | None = None,
    trusted_instructions: list[str] | None = None,
    allow_repository_execution: bool = False,
) -> dict[str, Any]:
    """Build the exact inventory/plan summary without creating review state."""
    root = root.resolve()
    selected, _, snapshot, inventory, plan, trust = _prepare_review(
        root, baseline=baseline, target=target, mode=mode,
        fix_authorized=fix_authorized, budget=budget, run_id=run_id,
        worktree_snapshot=worktree_snapshot, required_risks=required_risks,
        trusted_instructions=trusted_instructions,
        allow_repository_execution=allow_repository_execution,
    )
    return _review_summary(
        selected, mode, snapshot, inventory, plan,
        review_root=str(_review_dir(root, selected).relative_to(root)),
        write_mode="PREVIEW_NO_STATE_WRITTEN",
        trust=trust,
    )


def _prepare_review(
    root: Path,
    *,
    baseline: str,
    target: str,
    mode: str,
    fix_authorized: bool,
    budget: dict[str, Any] | None,
    run_id: str | None,
    worktree_snapshot: bool,
    required_risks: list[str] | None,
    trusted_instructions: list[str] | None,
    allow_repository_execution: bool,
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if mode not in REVIEW_MODES:
        raise ValueError("Review mode must be review_only or review_and_fix")
    if mode == "review_and_fix" and not fix_authorized:
        raise ValueError("review_and_fix requires explicit fix authorization")
    if mode == "review_only" and fix_authorized:
        raise ValueError("Fix authorization is incompatible with review_only mode")
    selected, run = _open_run(root, run_id, starting_review=True)
    directory = _review_dir(root, selected)
    if directory.exists():
        raise ValueError(f"Review state already exists for run {selected}; resume it instead of overwriting")
    if is_git_repository(root):
        snapshot = capture_git_snapshot(root, baseline, target)
        inventory = inventory_git_target(root, snapshot)
        snapshot["manifest_fingerprint"] = inventory["manifest_fingerprint"]
    else:
        snapshot, inventory = capture_worktree_snapshot(root, explicit=worktree_snapshot)
    plan = build_review_plan(inventory, budget=budget, required_risks=required_risks)
    trust = _build_trust_manifest(
        root, trusted_instructions or [], allow_repository_execution=allow_repository_execution,
    )
    return selected, run, snapshot, inventory, plan, trust


def _build_trust_manifest(
    root: Path,
    trusted_instructions: list[str],
    *,
    allow_repository_execution: bool,
) -> dict[str, Any]:
    normalized = sorted(set(trusted_instructions))
    snapshot = selected_source_snapshot(root, normalized)
    core = {
        "repository_content_classification": "UNTRUSTED_INPUT_EXCEPT_EXPLICIT_PATHS",
        "trusted_instruction_files": normalized,
        "trusted_instruction_snapshot": snapshot,
        "repository_execution_authorized": bool(allow_repository_execution),
        "default_execution_policy": (
            "BOUNDED_REPOSITORY_EXECUTION_EXPLICITLY_AUTHORIZED"
            if allow_repository_execution else
            "NO_REPOSITORY_COMMANDS_HOOKS_INSTALLS_NETWORK_CREDENTIALS_OR_GENERATED_CODE_EXECUTION"
        ),
    }
    return {"schema_version": 1, **core, "policy_fingerprint": canonical_hash(core)}


def _review_summary(
    selected: str,
    mode: str,
    snapshot: dict[str, Any],
    inventory: dict[str, Any],
    plan: dict[str, Any],
    *,
    review_root: str,
    write_mode: str,
    trust: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": selected,
        "status": "READY" if plan.get("status") == "READY" else str(plan.get("status")),
        "review_mode": mode,
        "snapshot_kind": snapshot.get("snapshot_kind"),
        "target_fingerprint": snapshot.get("target_commit") or inventory.get("manifest_fingerprint"),
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "primary_shards": len(plan.get("primary_shards", [])),
        "cross_cut_shards": len(plan.get("cross_cut_shards", [])),
        "oversized_files": plan.get("oversized_files", []),
        "modules": [
            {
                key: module.get(key)
                for key in ("module_id", "root", "confidence", "discovery_basis", "file_count", "evidence")
            }
            for module in inventory.get("modules", [])
            if isinstance(module, dict)
        ],
        "disposition_counts": inventory.get("disposition_counts", {}),
        "working_tree": snapshot.get("working_tree", {}),
        "exclusions": [
            {"path": entry.get("path"), "disposition": entry.get("disposition")}
            for entry in inventory.get("entries", [])
            if isinstance(entry, dict) and entry.get("disposition") != "INCLUDED"
        ][:1000],
        "exclusions_truncated": sum(
            1 for entry in inventory.get("entries", [])
            if isinstance(entry, dict) and entry.get("disposition") != "INCLUDED"
        ) > 1000,
        "context_budget": plan.get("budget", {}),
        "required_risk_lenses": plan.get("required_risk_lenses", []),
        "trust_policy": {
            "policy_fingerprint": trust.get("policy_fingerprint"),
            "trusted_instruction_files": trust.get("trusted_instruction_files", []),
            "repository_execution_authorized": trust.get("repository_execution_authorized"),
            "default_execution_policy": trust.get("default_execution_policy"),
        },
        "coverage_claim_limit": plan.get("coverage_claim_limit"),
        "review_root": review_root,
        "write_mode": write_mode,
    }


def _load_review_set(root: Path, run_id: str | None = None) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    selected, _ = _open_run(root, run_id)
    review = load_json_object(_file(root, selected, "review.json"))
    snapshot = load_json_object(_file(root, selected, "snapshot.json"))
    inventory = load_json_object(_file(root, selected, "inventory.json"))
    plan = load_json_object(_file(root, selected, "plan.json"))
    if review.get("run_id") != selected:
        raise ValueError("Review state belongs to a different run")
    return selected, review, snapshot, inventory, plan


def _validate_live(
    root: Path,
    run_id: str | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    selected, review, snapshot, inventory, plan = _load_review_set(root, run_id)
    if review.get("status") in {"FINALIZED", "FINALIZED_WITH_FINDINGS"}:
        raise ValueError("Finalized review state is immutable")
    reasons: list[str] = []
    if not validate_plan_fingerprint(plan):
        reasons.append("plan-fingerprint-invalid")
    if canonical_hash(plan) != review.get("plan_document_fingerprint"):
        reasons.append("plan-document-drift")
    if plan.get("plan_fingerprint") != review.get("plan_fingerprint"):
        reasons.append("plan-lineage-drift")
    trust = load_json_object(_file(root, selected, "trust.json"))
    trust_core = {key: value for key, value in trust.items() if key not in {"schema_version", "policy_fingerprint"}}
    if trust.get("policy_fingerprint") != canonical_hash(trust_core):
        reasons.append("trust-policy-fingerprint-invalid")
    if trust.get("policy_fingerprint") != review.get("trust_policy_fingerprint"):
        reasons.append("trust-policy-lineage-drift")
    trusted_paths = trust.get("trusted_instruction_files", [])
    if trust.get("trusted_instruction_snapshot") != selected_source_snapshot(root, trusted_paths):
        reasons.append("trusted-instruction-drift")
    unchanged, snapshot_reasons, _ = validate_snapshot_unchanged(root, snapshot, inventory)
    worktree_warnings = [reason for reason in snapshot_reasons if reason == "working-tree-drift"]
    reasons.extend(reason for reason in snapshot_reasons if reason != "working-tree-drift")
    if not unchanged and not snapshot_reasons:
        reasons.append("unknown-snapshot-drift")
    if reasons:
        review.update({"status": "STALE", "stale_reasons": sorted(set(reasons)), "updated_at": utc_now()})
        _write(root, _file(root, selected, "review.json"), review)
        raise ValueError("Review state is STALE: " + ", ".join(sorted(set(reasons))))
    if review.get("status") == "STALE":
        raise ValueError("Review state is STALE and must be restarted against a new run/target")
    return selected, review, snapshot, inventory, plan, worktree_warnings


def _all_shards(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return list(plan.get("primary_shards", [])) + list(plan.get("cross_cut_shards", []))


def _expected_objects(inventory: dict[str, Any], shard: dict[str, Any]) -> dict[str, str]:
    indexed = {
        str(entry.get("path")): str(entry.get("object_id"))
        for entry in inventory.get("entries", [])
        if isinstance(entry, dict)
    }
    return {path: indexed[path] for path in shard.get("files", []) if path in indexed}


def _record_fingerprint(record: dict[str, Any]) -> str:
    return canonical_hash({key: value for key, value in record.items() if key != "record_fingerprint"})


def _normalized_file_evidence(
    value: Any,
    expected_objects: dict[str, str],
    reviewed_files: list[str],
    *,
    complete: bool,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("Shard result file_evidence must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Every file_evidence entry must be an object")
        if set(item) != {"path", "object_id", "checks_performed", "observation"}:
            raise ValueError("file_evidence entries must contain only path, object_id, checks_performed, observation")
        path = item.get("path")
        object_id = item.get("object_id")
        checks = item.get("checks_performed")
        observation = item.get("observation")
        if not isinstance(path, str) or path in seen or path not in reviewed_files:
            raise ValueError("file_evidence path is duplicate or outside reviewed_files")
        if expected_objects.get(path) != object_id:
            raise ValueError("file_evidence object_id does not match the pinned target")
        if not isinstance(checks, list) or not checks or not all(
            isinstance(check, str) and 1 <= len(check.strip()) <= 200 for check in checks
        ):
            raise ValueError("file_evidence checks_performed must contain concrete bounded checks")
        if not isinstance(observation, str) or not observation.strip() or len(observation) > 4000:
            raise ValueError("file_evidence observation must be concrete and at most 4000 characters")
        seen.add(path)
        normalized.append({
            "path": path,
            "object_id": object_id,
            "checks_performed": sorted(set(check.strip() for check in checks)),
            "observation": observation.strip(),
        })
    if complete and seen != set(reviewed_files):
        raise ValueError("A COMPLETE result needs concrete file_evidence for every reviewed file")
    return sorted(normalized, key=lambda item: str(item["path"]))


def _shard_input_fingerprint(
    run_id: str,
    target_fingerprint: str,
    plan_fingerprint: str,
    shard: dict[str, Any],
) -> str:
    return canonical_hash({
        "run_id": run_id,
        "target_fingerprint": target_fingerprint,
        "plan_fingerprint": plan_fingerprint,
        "shard": shard,
    })


def _load_valid_results(
    root: Path,
    run_id: str,
    review: dict[str, Any],
    inventory: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    store = load_json_object(_file(root, run_id, "results.json"))
    values = store.get("results")
    if store.get("schema_version") != 1 or not isinstance(values, list):
        raise ValueError("Invalid review result store")
    if store.get("store_fingerprint") != canonical_hash(values):
        raise ValueError("Review result store fingerprint is invalid; persisted evidence was modified")
    seen_shards: set[str] = set()
    seen_findings: set[str] = set()
    seen_sessions: set[str] = set()
    for record in values:
        if not isinstance(record, dict) or record.get("record_fingerprint") != _record_fingerprint(record):
            raise ValueError("Review result record fingerprint is invalid; persisted evidence was modified")
        shard_id = str(record.get("shard_id", ""))
        if shard_id in seen_shards:
            raise ValueError(f"Review result store has duplicate shard lineage: {shard_id}")
        seen_shards.add(shard_id)
        shard = _shard(plan, shard_id)
        task_text, dispatch_fingerprint = _validated_review_task(
            root, str(record.get("task_id", "")), shard_id, run_id,
        )
        if record.get("task_dispatch_fingerprint") != dispatch_fingerprint:
            raise ValueError("Stored result Task Package dispatch lineage is stale")
        task_owner = quoted_scalar(task_text, "owner")
        if record.get("task_owner") != task_owner or record.get("reviewer_id") != task_owner:
            raise ValueError("Stored result reviewer identity does not match the dispatched Task Package owner")
        if record.get("target_fingerprint") != review.get("target_fingerprint"):
            raise ValueError("Stored result target fingerprint does not match the review target")
        if record.get("review_id") != run_id:
            raise ValueError("Stored result review/run lineage is invalid")
        if record.get("inventory_fingerprint") != inventory.get("manifest_fingerprint"):
            raise ValueError("Stored result inventory lineage is invalid")
        if record.get("plan_fingerprint") != plan.get("plan_fingerprint"):
            raise ValueError("Stored result plan lineage is invalid")
        if record.get("trust_policy_fingerprint") != review.get("trust_policy_fingerprint"):
            raise ValueError("Stored result trust-policy lineage is invalid")
        if record.get("shard_input_fingerprint") != _shard_input_fingerprint(
            run_id, str(review.get("target_fingerprint")), str(plan.get("plan_fingerprint")), shard,
        ):
            raise ValueError("Stored result shard input lineage is invalid")
        if record.get("status") not in RESULT_STATUSES:
            raise ValueError("Stored result status is invalid")
        if record.get("session_isolation_status") not in SESSION_STATUSES:
            raise ValueError("Stored result session isolation status is missing or invalid")
        _string_identifier(record.get("reviewer_id"), "stored reviewer_id", REVIEWER_PATTERN)
        stored_session = _string_identifier(record.get("review_session_id"), "stored review_session_id", SESSION_PATTERN)
        if stored_session in seen_sessions:
            raise ValueError("Review session identity is reused across multiple shards")
        seen_sessions.add(stored_session)
        reviewed_files = record.get("reviewed_files")
        if not isinstance(reviewed_files, list) or not all(isinstance(item, str) for item in reviewed_files):
            raise ValueError("Stored result reviewed_files is invalid")
        if record.get("status") == "COMPLETE" and sorted(set(reviewed_files)) != sorted(shard.get("files", [])):
            raise ValueError("Stored COMPLETE result no longer covers its declared shard")
        expected_objects = _expected_objects(inventory, shard)
        if record.get("status") == "COMPLETE" and record.get("reviewed_objects") != expected_objects:
            raise ValueError("Stored COMPLETE result object lineage does not match the pinned target")
        file_evidence = _normalized_file_evidence(
            record.get("file_evidence"), expected_objects, reviewed_files,
            complete=record.get("status") == "COMPLETE",
        )
        if record.get("file_evidence") != file_evidence:
            raise ValueError("Stored file-level evidence normalization drift")
        evidence_refs = record.get("evidence_refs")
        _normalize_evidence_refs(root, evidence_refs, "Stored shard result")
        if record.get("evidence_snapshot") != selected_source_snapshot(root, evidence_refs):
            raise ValueError("Stored shard evidence changed after ingestion")
        findings = record.get("findings")
        if not isinstance(findings, list) or record.get("finding_count") != len(findings):
            raise ValueError("Stored result finding count is invalid")
        for finding in findings:
            if not isinstance(finding, dict):
                raise ValueError("Stored finding must be an object")
            finding_id = str(finding.get("finding_id", ""))
            if finding_id in seen_findings:
                raise ValueError(f"Stored finding IDs are not globally unique: {finding_id}")
            seen_findings.add(finding_id)
            raw = {key: value for key, value in finding.items() if key not in {"exact_identity", "issue_identity"}}
            normalized = validate_finding(raw, shard=shard, target_fingerprint=str(review["target_fingerprint"]))
            if normalized != finding:
                raise ValueError(f"Stored finding normalization drift: {finding_id}")
    return store


def _validated_review_task(
    root: Path,
    task_id: str,
    shard_id: str,
    run_id: str,
) -> tuple[str, str]:
    """Validate the immutable review Task Package and its READY dispatch receipt."""
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("Shard result task_id must reference a path-safe review Task Package")
    task_path = safe_project_path(root, Path("tasks") / f"{task_id}.yaml")
    if not task_path.is_file():
        raise ValueError(f"Shard result Task Package does not exist: tasks/{task_id}.yaml")
    text = task_path.read_text(encoding="utf-8")
    owner = quoted_scalar(text, "owner")
    errors = validate_task_contract(
        root, text, owner, allowed_statuses=("READY_FOR_DISPATCH", "COMPLETED"),
    )
    if errors:
        raise ValueError("Shard result Task Package contract is invalid: " + "; ".join(errors))
    if quoted_scalar(text, "run_id") != run_id:
        raise ValueError("Shard result Task Package belongs to a different run")
    review_section = top_section(text, "review_contract")
    if quoted_scalar(review_section, "shard_id") != shard_id:
        raise ValueError("Shard result Task Package belongs to a different review shard")
    receipt_errors = validate_dispatch_receipt(root, text)
    if receipt_errors:
        raise ValueError("Shard result requires a matching dispatch receipt: " + "; ".join(receipt_errors))
    return text, task_dispatch_fingerprint(text)


def _shard(plan: dict[str, Any], shard_id: str) -> dict[str, Any]:
    values = [item for item in _all_shards(plan) if item.get("shard_id") == shard_id]
    if len(values) != 1:
        raise ValueError(f"Unknown or ambiguous shard: {shard_id}")
    return values[0]


def shard_contract(root: Path, shard_id: str, *, run_id: str | None = None) -> dict[str, Any]:
    """Render a compact, no-write review contract for one planned shard."""
    root = root.resolve()
    selected, review, snapshot, inventory, plan, warnings = _validate_live(root, run_id)
    shard = _shard(plan, shard_id)
    reviewed_objects = _expected_objects(inventory, shard)
    kind = str(shard.get("shard_kind"))
    surface = str(shard.get("technology_surface"))
    owner_by_surface = {
        "frontend": "frontend_worker",
        "backend": "backend_worker",
        "ai": "ai_worker",
        "data": "data_worker",
        "test": "test_worker",
        "documentation": "test_worker",
    }
    suggested_owner = "architect" if kind == "CROSS_CUT" else owner_by_surface.get(surface, "engineering_lead")
    task_type = "cross_module_review" if kind == "CROSS_CUT" else "module_review"
    budget = plan.get("budget", {})
    review_relative = _review_dir(root, selected).relative_to(root).as_posix()
    trust = load_json_object(_file(root, selected, "trust.json"))
    return {
        "schema_version": 1,
        "status": "ROUTED",
        "review_id": selected,
        "mode": review.get("review_mode"),
        "phase": task_type,
        "task_type": task_type,
        "suggested_owner": suggested_owner,
        "reviewer": "engineering_lead" if suggested_owner.endswith("_worker") else "orchestrator",
        "shard_id": shard_id,
        "shard_kind": kind,
        "baseline_commit": snapshot.get("baseline_commit"),
        "target_commit": snapshot.get("target_commit"),
        "target_fingerprint": review.get("target_fingerprint"),
        "repository_manifest_fingerprint": inventory.get("manifest_fingerprint"),
        "review_plan_fingerprint": plan.get("plan_fingerprint"),
        "shard_input_fingerprint": _shard_input_fingerprint(
            selected, str(review.get("target_fingerprint")), str(plan.get("plan_fingerprint")), shard,
        ),
        "trust_policy_fingerprint": trust.get("policy_fingerprint"),
        "trusted_instruction_files": list(trust.get("trusted_instruction_files", [])),
        "repository_execution_authorized": bool(trust.get("repository_execution_authorized")),
        "default_execution_policy": trust.get("default_execution_policy"),
        "included_modules": [shard.get("module_id")],
        "included_files": list(shard.get("files", [])),
        "pinned_file_objects": reviewed_objects,
        "content_read_contract": (
            "READ_GIT_OBJECTS_AT_TARGET_COMMIT_NOT_WORKTREE_PATHS"
            if snapshot.get("snapshot_kind") == "GIT_COMMIT"
            else "READ_FILES_ONLY_WHEN_CURRENT_HASH_MATCHES_PINNED_FILE_OBJECTS"
        ),
        "exclusion_index": f"{review_relative}/inventory.json",
        "risk_lenses": list(shard.get("risk_dimensions", [])),
        "findings_output": f"{review_relative}/shard-results/{shard_id}.json",
        "evidence_output": f"evidence/reviews/{selected}/{shard_id}.md",
        "source_write_authorized": False,
        "fresh_session_required": True,
        "compact_handoff_required": True,
        "session_attestation_required": True,
        "session_isolation_status": shard.get("session_isolation_status"),
        "context_budget": {
            "max_files": budget.get("max_files"),
            "max_bytes": budget.get("max_bytes"),
            "max_estimated_tokens": budget.get("max_estimated_tokens"),
            "estimated_files": shard.get("file_count"),
            "estimated_bytes": shard.get("bytes"),
            "estimated_tokens": shard.get("estimated_tokens"),
            "estimate_method": budget.get("token_estimation"),
            "semantics": "STATIC_ESTIMATE_ONLY_NOT_RUNTIME_TOKEN_USAGE",
        },
        "warnings": sorted(set(warnings) | ({"dirty-worktree-at-review-start"} if snapshot.get("working_tree", {}).get("dirty") else set())),
        "completion_claim_limit": "ONE_SHARD_RESULT_ONLY; NO_REPOSITORY_COMPLETION_CLAIM",
    }


def _string_identifier(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value}")
    return value


def _session_status(result: dict[str, Any], shard_id: str) -> str:
    receipt = result.get("session_attestation")
    session_id = result.get("review_session_id")
    if not isinstance(receipt, dict):
        return "UNVERIFIED_SESSION_ISOLATION"
    if (
        receipt.get("session_id") == session_id
        and receipt.get("shard_id") == shard_id
        and receipt.get("fresh_session_attested") is True
        and receipt.get("compact_handoff_attested") is True
        and receipt.get("attested_by") == "orchestrator"
    ):
        return "ATTESTED_SESSION_ISOLATION"
    return "UNVERIFIED_SESSION_ISOLATION"


def _lifecycle_session_status(
    receipt: dict[str, Any] | None,
    *,
    session_id: str,
    repair_plan_id: str,
    independent_from: str | None = None,
) -> str:
    if not isinstance(receipt, dict):
        return "UNVERIFIED_SESSION_ISOLATION"
    matches = (
        receipt.get("session_id") == session_id
        and receipt.get("repair_plan_id") == repair_plan_id
        and receipt.get("fresh_session_attested") is True
        and receipt.get("attested_by") == "orchestrator"
    )
    if independent_from is not None:
        matches = matches and receipt.get("independent_from_session_id") == independent_from
    return "ATTESTED_SESSION_ISOLATION" if matches else "UNVERIFIED_SESSION_ISOLATION"


def ingest_result(
    root: Path,
    shard_id: str,
    result: dict[str, Any],
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    selected, review, _, inventory, plan, warnings = _validate_live(root, run_id)
    if review.get("status") != "READY":
        raise ValueError(f"Review cannot ingest results while status is {review.get('status')}")
    shard = _shard(plan, shard_id)
    if not isinstance(result, dict):
        raise ValueError("Shard result must be a JSON object")
    task_id = _string_identifier(result.get("task_id"), "task_id", TASK_ID_PATTERN)
    task_text, dispatch_fingerprint = _validated_review_task(root, task_id, shard_id, selected)
    reviewer = _string_identifier(result.get("reviewer_id"), "reviewer_id", REVIEWER_PATTERN)
    task_owner = quoted_scalar(task_text, "owner")
    if reviewer != task_owner:
        raise ValueError("Shard result reviewer_id must match the dispatched Task Package owner")
    session = _string_identifier(result.get("review_session_id"), "review_session_id", SESSION_PATTERN)
    status = result.get("status")
    if status not in RESULT_STATUSES:
        raise ValueError("Shard result status must be COMPLETE or BLOCKED")
    if result.get("target_fingerprint") != review.get("target_fingerprint"):
        raise ValueError("Shard result target fingerprint does not match review target")
    if result.get("review_id") != selected:
        raise ValueError("Shard result review_id must match the bound run")
    if result.get("inventory_fingerprint") != inventory.get("manifest_fingerprint"):
        raise ValueError("Shard result inventory fingerprint does not match review inventory")
    if result.get("plan_fingerprint") != plan.get("plan_fingerprint"):
        raise ValueError("Shard result plan fingerprint does not match review plan")
    expected_shard_fingerprint = _shard_input_fingerprint(
        selected, str(review.get("target_fingerprint")), str(plan.get("plan_fingerprint")), shard,
    )
    if result.get("shard_input_fingerprint") != expected_shard_fingerprint:
        raise ValueError("Shard result input fingerprint does not match the planned shard")
    if result.get("trust_policy_fingerprint") != review.get("trust_policy_fingerprint"):
        raise ValueError("Shard result trust policy fingerprint does not match the review contract")
    reviewed_files = result.get("reviewed_files")
    if not isinstance(reviewed_files, list) or not all(isinstance(item, str) for item in reviewed_files):
        raise ValueError("Shard result reviewed_files must be a list of paths")
    if status == "COMPLETE" and sorted(set(reviewed_files)) != sorted(shard.get("files", [])):
        raise ValueError("A COMPLETE shard result must attest every declared shard file exactly")
    if any(path not in set(shard.get("files", [])) for path in reviewed_files):
        raise ValueError("Shard result contains a reviewed file outside shard scope")
    reviewed_objects = result.get("reviewed_objects")
    expected_objects = _expected_objects(inventory, shard)
    if not isinstance(reviewed_objects, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in reviewed_objects.items()
    ):
        raise ValueError("Shard result reviewed_objects must map paths to pinned object IDs")
    if status == "COMPLETE" and reviewed_objects != expected_objects:
        raise ValueError("A COMPLETE shard result must attest every pinned file object exactly")
    if any(path not in expected_objects or expected_objects[path] != object_id for path, object_id in reviewed_objects.items()):
        raise ValueError("Shard result contains object lineage outside the pinned shard target")
    evidence_refs = _normalize_evidence_refs(root, result.get("evidence_refs"), "Shard result")
    required_evidence_output = str(shard_contract(root, shard_id, run_id=selected)["evidence_output"])
    if required_evidence_output not in evidence_refs:
        raise ValueError("Shard result evidence_refs must include the contract-bound evidence_output")
    evidence_snapshot = selected_source_snapshot(root, evidence_refs)
    file_evidence = _normalized_file_evidence(
        result.get("file_evidence"), expected_objects, reviewed_files, complete=status == "COMPLETE",
    )
    raw_findings = result.get("findings", [])
    if not isinstance(raw_findings, list):
        raise ValueError("Shard result findings must be a list")
    if len(raw_findings) > MAX_FINDINGS_PER_SHARD:
        raise ValueError(f"Shard result exceeds finding limit ({MAX_FINDINGS_PER_SHARD})")
    normalized_findings = [
        validate_finding(item, shard=shard, target_fingerprint=str(review["target_fingerprint"]))
        for item in raw_findings
    ]
    store = _load_valid_results(root, selected, review, inventory, plan)
    values = store.get("results", [])
    if not isinstance(values, list):
        raise ValueError("Invalid review result store")
    if any(item.get("shard_id") == shard_id for item in values if isinstance(item, dict)):
        raise ValueError(f"Shard {shard_id} already has an immutable result")
    if any(item.get("review_session_id") == session for item in values if isinstance(item, dict)):
        raise ValueError("One review_session_id cannot be reused across multiple shards")
    existing_finding_ids = {
        str(finding.get("finding_id"))
        for prior in values
        if isinstance(prior, dict)
        for finding in prior.get("findings", [])
        if isinstance(finding, dict)
    }
    repeated_ids = sorted(
        {str(item["finding_id"]) for item in normalized_findings} & existing_finding_ids
    )
    local_ids = [str(item["finding_id"]) for item in normalized_findings]
    if repeated_ids or len(local_ids) != len(set(local_ids)):
        raise ValueError("Finding IDs must be globally unique within a review: " + ", ".join(repeated_ids or local_ids))
    session_status = _session_status(result, shard_id)
    handoff_summary = str(result.get("handoff_summary", "")).strip()
    if len(handoff_summary) > 20_000:
        raise ValueError("Shard handoff_summary exceeds the 20000-character limit")
    record = {
        "review_id": selected,
        "task_id": task_id,
        "task_dispatch_fingerprint": dispatch_fingerprint,
        "task_owner": task_owner,
        "shard_id": shard_id,
        "shard_kind": shard.get("shard_kind"),
        "target_fingerprint": review.get("target_fingerprint"),
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "shard_input_fingerprint": expected_shard_fingerprint,
        "trust_policy_fingerprint": review.get("trust_policy_fingerprint"),
        "reviewer_id": reviewer,
        "review_session_id": session,
        "session_isolation_status": session_status,
        "status": status,
        "reviewed_files": sorted(set(reviewed_files)),
        "reviewed_objects": dict(sorted(reviewed_objects.items())),
        "file_evidence": file_evidence,
        "evidence_refs": evidence_refs,
        "evidence_snapshot": evidence_snapshot,
        "finding_count": len(normalized_findings),
        "findings": normalized_findings,
        "handoff_summary": handoff_summary,
        "recorded_at": utc_now(),
    }
    record["record_fingerprint"] = _record_fingerprint(record)
    values.append(record)
    store["results"] = values
    store["store_fingerprint"] = canonical_hash(values)
    _write(root, _file(root, selected, "results.json"), store)
    coverage = _coverage(plan, values)
    if warnings:
        coverage["warnings"] = sorted(set(warnings))
    _write(root, _file(root, selected, "coverage.json"), coverage)
    return {
        "run_id": selected,
        "shard_id": shard_id,
        "status": status,
        "session_isolation_status": session_status,
        "finding_count": len(normalized_findings),
        "coverage_status": coverage["status"],
    }


def _coverage(plan: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    if plan.get("status") != "READY":
        return {
            "schema_version": 1,
            "status": "INCOMPLETE",
            "expected_shards": 0,
            "completed_shards": 0,
            "missing_shards": [],
            "declared_primary_files": 0,
            "covered_primary_files": 0,
            "missing_primary_files": [],
            "session_isolation_evidence": [],
            "reasons": [f"plan-status:{plan.get('status')}"] ,
            "limitations": ["No coverage claim is allowed while the review plan is blocked"],
        }
    expected = {str(item["shard_id"]): item for item in _all_shards(plan)}
    complete = {
        str(item.get("shard_id")): item
        for item in results
        if isinstance(item, dict) and item.get("status") == "COMPLETE"
    }
    missing = sorted(set(expected) - set(complete))
    primary_files = {
        path
        for shard in plan.get("primary_shards", [])
        for path in shard.get("files", [])
    }
    reviewed_primary = {
        path
        for shard_id, result in complete.items()
        if expected[shard_id].get("shard_kind") == "PRIMARY"
        for path in result.get("reviewed_files", [])
    }
    missing_files = sorted(primary_files - reviewed_primary)
    status = "COMPLETE_FOR_DECLARED_SCOPE" if not missing and not missing_files else "INCOMPLETE"
    isolation = sorted({
        str(item.get("session_isolation_status", "UNVERIFIED_SESSION_ISOLATION"))
        for item in complete.values()
    })
    return {
        "schema_version": 1,
        "status": status,
        "expected_shards": len(expected),
        "completed_shards": len(complete),
        "missing_shards": missing,
        "declared_primary_files": len(primary_files),
        "covered_primary_files": len(reviewed_primary),
        "missing_primary_files": missing_files,
        "session_isolation_evidence": isolation,
        "limitations": [
            "Coverage applies only to the declared deterministic inventory and heuristic module plan",
            "It does not prove complete semantic understanding",
        ] + (["One or more fresh-session claims remain UNVERIFIED_SESSION_ISOLATION"] if "UNVERIFIED_SESSION_ISOLATION" in isolation else []),
    }


def merge_findings(root: Path, *, run_id: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    selected, review, _, inventory, plan, _ = _validate_live(root, run_id)
    store = _load_valid_results(root, selected, review, inventory, plan)
    findings = [
        finding
        for result in store.get("results", [])
        if isinstance(result, dict)
        for finding in result.get("findings", [])
        if isinstance(finding, dict)
    ]
    merged = merge_finding_values(findings)
    merged["generated_at"] = utc_now()
    _write(root, _file(root, selected, "findings.json"), merged)
    return merged


def plan_repairs(
    root: Path,
    *,
    fixer_id: str,
    reviewer_id: str,
    finding_ids: list[str] | None = None,
    allowed_files: list[str] | None = None,
    round_number: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    selected, review, _, inventory, plan_state, _ = _validate_live(root, run_id)
    if review.get("review_mode") != "review_and_fix" or review.get("fix_authorized") is not True:
        raise ValueError("Repair planning is forbidden in review_only or without explicit fix authorization")
    fixer = _string_identifier(fixer_id, "fixer_id", REVIEWER_PATTERN)
    reviewer = _string_identifier(reviewer_id, "reviewer_id", REVIEWER_PATTERN)
    if fixer == reviewer:
        raise ValueError("Fixer and independent rereviewer must be different identities")
    if reviewer not in {"engineering_lead", "architect"}:
        raise ValueError(
            "Independent repair rereviewer must be engineering_lead or architect; "
            "final release QA remains a separate qa task at READY_FOR_QA"
        )
    result_store = _load_valid_results(root, selected, review, inventory, plan_state)
    coverage = _coverage(plan_state, result_store.get("results", []))
    if coverage.get("status") != "COMPLETE_FOR_DECLARED_SCOPE":
        raise ValueError("Repair planning requires complete declared review coverage")
    merged = merge_findings(root, run_id=selected)
    available = {
        str(item["finding_id"]): item
        for item in merged.get("findings", [])
        if item.get("status") == "OPEN"
    }
    passed_findings = _passed_rereview_findings(root, selected)
    available = {key: value for key, value in available.items() if key not in passed_findings}
    selected_ids = sorted(set(finding_ids or available.keys()))
    if not selected_ids:
        raise ValueError("No open findings are available for repair planning")
    unknown = sorted(set(selected_ids) - set(available))
    if unknown:
        raise ValueError("Repair plan references unknown or non-open findings: " + ", ".join(unknown))
    repair_store = load_json_object(_file(root, selected, "repairs.json"))
    plans = repair_store.get("plans", [])
    if not isinstance(plans, list):
        raise ValueError("Invalid repair plan store")
    next_rounds = {
        finding_id: 1 + max(
            (
                int(item.get("round", 0))
                for item in plans
                if isinstance(item, dict) and finding_id in item.get("finding_ids", [])
            ),
            default=0,
        )
        for finding_id in selected_ids
    }
    if len(set(next_rounds.values())) != 1:
        raise ValueError("Findings with different retry rounds require separate repair plans")
    expected_round = next(iter(next_rounds.values()))
    chosen_round = expected_round if round_number is None else round_number
    if chosen_round != expected_round or chosen_round < 1 or chosen_round > MAX_REPAIR_ROUNDS:
        raise ValueError(f"Repair round must be the next per-finding round and no greater than {MAX_REPAIR_ROUNDS}")
    overlapping = [
        item for item in plans
        if isinstance(item, dict) and set(item.get("finding_ids", [])) & set(selected_ids)
    ]
    if any(item.get("status") != "REREVIEW_FAILED" for item in overlapping):
        raise ValueError("A finding already belongs to an active or passed repair plan")
    derived_files = {str(available[finding_id]["path"]) for finding_id in selected_ids}
    finding_paths = {finding_id: str(available[finding_id]["path"]) for finding_id in selected_ids}
    normalized_allowed = sorted(derived_files | set(allowed_files or []))
    for relative in normalized_allowed:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not relative:
            raise ValueError(f"Repair allowed file is unsafe: {relative}")
    allowed_before = selected_source_snapshot(root, normalized_allowed)
    outside_before = effective_source_snapshot(root, excluded_paths=normalized_allowed)
    repair_plan_id = "REPAIR-%02d-%s" % (
        chosen_round,
        canonical_hash({"findings": selected_ids, "round": chosen_round, "fixer": fixer})[:10].upper(),
    )
    plan = {
        "repair_plan_id": repair_plan_id,
        "round": chosen_round,
        "finding_ids": selected_ids,
        "finding_paths": finding_paths,
        "fixer_id": fixer,
        "reviewer_id": reviewer,
        "allowed_files": normalized_allowed,
        "source_write_authorized": True,
        "allowed_source_before": allowed_before,
        "outside_allowed_before_fingerprint": outside_before.get("fingerprint"),
        "target_fingerprint": review.get("target_fingerprint"),
        "authorization": "EXPLICIT_REVIEW_AND_FIX",
        "status": "PLANNED",
        "created_at": utc_now(),
    }
    plan["authorization_fingerprint"] = canonical_hash({
        key: plan[key] for key in (
            "repair_plan_id", "round", "finding_ids", "finding_paths", "fixer_id", "reviewer_id",
            "allowed_files", "source_write_authorized", "target_fingerprint", "authorization",
        )
    })
    plan["plan_fingerprint"] = _record_fingerprint(plan)
    plans.append(plan)
    repair_store["plans"] = plans
    _write(root, _file(root, selected, "repairs.json"), repair_store)
    return plan


def repair_contract(
    root: Path,
    repair_plan_id: str,
    *,
    phase: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Render a no-write Task Package contract for repair or independent rereview."""
    root = root.resolve()
    selected, review, _, _, _, _ = _validate_live(root, run_id)
    if phase not in {"REPAIR", "REREVIEW"}:
        raise ValueError("Repair Task Package phase must be REPAIR or REREVIEW")
    store = load_json_object(_file(root, selected, "repairs.json"))
    matches = [item for item in store.get("plans", []) if item.get("repair_plan_id") == repair_plan_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown repair plan: {repair_plan_id}")
    plan = matches[0]
    if plan.get("plan_fingerprint") != canonical_hash({
        key: value for key, value in plan.items() if key != "plan_fingerprint"
    }):
        raise ValueError("Repair plan fingerprint is invalid")
    authorization_fingerprint = canonical_hash({
        key: plan[key] for key in (
            "repair_plan_id", "round", "finding_ids", "finding_paths", "fixer_id", "reviewer_id",
            "allowed_files", "source_write_authorized", "target_fingerprint", "authorization",
        )
    })
    if plan.get("authorization_fingerprint") != authorization_fingerprint:
        raise ValueError("Repair authorization fingerprint is invalid")
    repair_evidence = f"evidence/reviews/{selected}/{repair_plan_id}.repair.md"
    rereview_evidence = f"evidence/reviews/{selected}/{repair_plan_id}.rereview.md"
    is_repair = phase == "REPAIR"
    return {
        "schema_version": 1,
        "status": "ROUTED",
        "review_id": selected,
        "review_mode": review.get("review_mode"),
        "repair_plan_id": repair_plan_id,
        "repair_plan_fingerprint": authorization_fingerprint,
        "phase": phase,
        "task_type": "review_repair" if is_repair else "review_verification",
        "owner": plan.get("fixer_id") if is_repair else plan.get("reviewer_id"),
        "finding_ids": list(plan.get("finding_ids", [])),
        "allowed_source_files": list(plan.get("allowed_files", [])),
        "target_fingerprint": review.get("target_fingerprint"),
        "source_write_authorized": is_repair,
        "evidence_output": repair_evidence if is_repair else rereview_evidence,
        "allowed_files": (
            sorted(set(plan.get("allowed_files", [])) | {repair_evidence})
            if is_repair else [rereview_evidence]
        ),
    }


def _validated_repair_task(
    root: Path,
    task_id: str,
    contract: dict[str, Any],
    evidence_refs: list[str],
) -> tuple[str, str]:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("Repair lifecycle task_id must reference a path-safe Task Package")
    task_path = safe_project_path(root, Path("tasks") / f"{task_id}.yaml")
    if not task_path.is_file():
        raise ValueError(f"Repair lifecycle Task Package does not exist: tasks/{task_id}.yaml")
    text = task_path.read_text(encoding="utf-8")
    owner = str(contract["owner"])
    errors = validate_task_contract(root, text, owner, allowed_statuses=("COMPLETED",))
    if errors:
        raise ValueError("Repair lifecycle Task Package contract is invalid: " + "; ".join(errors))
    expected = {
        "run_id": contract["review_id"],
        "owner": owner,
        "stage": "CODE_REVIEW",
        "task_type": contract["task_type"],
    }
    for field, wanted in expected.items():
        if quoted_scalar(text, field) != wanted:
            raise ValueError(f"Repair lifecycle Task Package {field} must be {wanted}")
    receipt_errors = validate_dispatch_receipt(root, text)
    if receipt_errors:
        raise ValueError("Repair lifecycle requires a matching READY dispatch receipt: " + "; ".join(receipt_errors))
    handoff = top_section(text, "handoff")
    if quoted_scalar(handoff, "conclusion") != "COMPLETED":
        raise ValueError("Repair lifecycle Task Package handoff must conclude COMPLETED")
    if not set(evidence_refs) <= set(list_field(handoff, "evidence")):
        raise ValueError("Repair lifecycle evidence_refs must appear in the completed Task Package handoff")
    return text, task_dispatch_fingerprint(text)


def record_repair(
    root: Path,
    *,
    repair_plan_id: str,
    task_id: str,
    fixer_id: str,
    fixer_session_id: str,
    finding_ids: list[str],
    evidence_refs: list[str],
    repair_artifact_fingerprint: str | None = None,
    session_attestation: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    selected, review, _, _, _, _ = _validate_live(root, run_id)
    if review.get("review_mode") != "review_and_fix" or review.get("fix_authorized") is not True:
        raise ValueError("Recording repairs is forbidden without explicit review_and_fix authorization")
    fixer = _string_identifier(fixer_id, "fixer_id", REVIEWER_PATTERN)
    session = _string_identifier(fixer_session_id, "fixer_session_id", SESSION_PATTERN)
    normalized_refs = _normalize_evidence_refs(root, evidence_refs, "Repair")
    source_snapshot = effective_source_snapshot(root)
    computed_fingerprint = str(source_snapshot["fingerprint"])
    if repair_artifact_fingerprint is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", repair_artifact_fingerprint):
            raise ValueError("repair_artifact_fingerprint must be a 64-hex content fingerprint")
        if repair_artifact_fingerprint != computed_fingerprint:
            raise ValueError("repair_artifact_fingerprint does not match the current effective source snapshot")
    store = load_json_object(_file(root, selected, "repairs.json"))
    matches = [item for item in store.get("plans", []) if item.get("repair_plan_id") == repair_plan_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown repair plan: {repair_plan_id}")
    plan = matches[0]
    if plan.get("plan_fingerprint") != canonical_hash({
        key: value for key, value in plan.items() if key != "plan_fingerprint"
    }):
        raise ValueError("Repair plan fingerprint is invalid")
    if plan.get("status") != "PLANNED" or plan.get("fixer_id") != fixer:
        raise ValueError("Repair record does not match the planned fixer or plan status")
    if sorted(set(finding_ids)) != sorted(set(plan.get("finding_ids", []))):
        raise ValueError("Repair record finding lineage must exactly match the repair plan")
    records = store.get("records", [])
    if any(item.get("repair_plan_id") == repair_plan_id for item in records if isinstance(item, dict)):
        raise ValueError("Repair plan already has a recorded repair")
    contract = repair_contract(root, repair_plan_id, phase="REPAIR", run_id=selected)
    if contract.get("evidence_output") not in normalized_refs:
        raise ValueError("Repair evidence_refs must include the contract-bound repair evidence output")
    _, task_fingerprint = _validated_repair_task(root, task_id, contract, normalized_refs)
    allowed_files = list(plan.get("allowed_files", []))
    allowed_after = selected_source_snapshot(root, allowed_files)
    if allowed_after.get("fingerprint") == plan.get("allowed_source_before", {}).get("fingerprint"):
        raise ValueError("Repair is a no-op: no authorized source file changed")
    outside_after = effective_source_snapshot(root, excluded_paths=allowed_files)
    if outside_after.get("fingerprint") != plan.get("outside_allowed_before_fingerprint"):
        raise ValueError("Repair changed source outside the authorized allowed_files boundary")
    before_entries = {
        str(item.get("path")): item for item in plan.get("allowed_source_before", {}).get("entries", [])
        if isinstance(item, dict)
    }
    after_entries = {
        str(item.get("path")): item for item in allowed_after.get("entries", [])
        if isinstance(item, dict)
    }
    changed_paths = sorted(
        path for path in set(before_entries) | set(after_entries)
        if before_entries.get(path) != after_entries.get(path)
    )
    if not changed_paths:
        raise ValueError("Repair has no content-level changed paths")
    unchanged_finding_paths = sorted(set(plan.get("finding_paths", {}).values()) - set(changed_paths))
    if unchanged_finding_paths:
        raise ValueError(
            "Repair did not change every finding-bound source path: " + ", ".join(unchanged_finding_paths)
        )
    record = {
        "repair_plan_id": repair_plan_id,
        "task_id": task_id,
        "task_dispatch_fingerprint": task_fingerprint,
        "round": plan["round"],
        "finding_ids": sorted(set(finding_ids)),
        "finding_paths": dict(sorted(plan.get("finding_paths", {}).items())),
        "allowed_files": allowed_files,
        "changed_paths": changed_paths,
        "allowed_source_after": allowed_after,
        "outside_allowed_after_fingerprint": outside_after.get("fingerprint"),
        "fixer_id": fixer,
        "fixer_session_id": session,
        "session_isolation_status": _lifecycle_session_status(
            session_attestation, session_id=session, repair_plan_id=repair_plan_id,
        ),
        "repair_artifact_fingerprint": computed_fingerprint,
        "repair_target_snapshot": source_snapshot,
        "evidence_refs": normalized_refs,
        "evidence_snapshot": selected_source_snapshot(root, normalized_refs),
        "recorded_at": utc_now(),
        "status": "REPAIRED_AWAITING_REREVIEW",
    }
    record["record_fingerprint"] = _record_fingerprint(record)
    records.append(record)
    store["records"] = records
    for item in store["plans"]:
        if item.get("repair_plan_id") == repair_plan_id:
            item["status"] = "REPAIRED_AWAITING_REREVIEW"
            item["plan_fingerprint"] = canonical_hash({
                key: value for key, value in item.items() if key != "plan_fingerprint"
            })
    _write(root, _file(root, selected, "repairs.json"), store)
    return record


def record_rereview(
    root: Path,
    *,
    repair_plan_id: str,
    task_id: str,
    reviewer_id: str,
    reviewer_session_id: str,
    outcomes: dict[str, str],
    verification_notes: dict[str, str],
    evidence_refs: list[str],
    session_attestation: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    selected, _, _, _, _, _ = _validate_live(root, run_id)
    reviewer = _string_identifier(reviewer_id, "reviewer_id", REVIEWER_PATTERN)
    reviewer_session = _string_identifier(reviewer_session_id, "reviewer_session_id", SESSION_PATTERN)
    normalized_refs = _normalize_evidence_refs(root, evidence_refs, "Rereview")
    repairs = load_json_object(_file(root, selected, "repairs.json"))
    plans = [item for item in repairs.get("plans", []) if item.get("repair_plan_id") == repair_plan_id]
    records = [item for item in repairs.get("records", []) if item.get("repair_plan_id") == repair_plan_id]
    if len(plans) != 1 or len(records) != 1:
        raise ValueError("Rereview requires one matching plan and recorded repair")
    plan, repair = plans[0], records[0]
    if plan.get("plan_fingerprint") != canonical_hash({
        key: value for key, value in plan.items() if key != "plan_fingerprint"
    }):
        raise ValueError("Rereview repair plan fingerprint is invalid")
    if repair.get("record_fingerprint") != _record_fingerprint(repair):
        raise ValueError("Rereview repair record fingerprint is invalid")
    if reviewer != plan.get("reviewer_id") or reviewer == repair.get("fixer_id"):
        raise ValueError("Rereviewer must match the independent planned reviewer and be different from fixer")
    if reviewer_session == repair.get("fixer_session_id"):
        raise ValueError("Rereview must use a session different from the fixer session")
    current_source = effective_source_snapshot(root)
    if current_source.get("fingerprint") != repair.get("repair_artifact_fingerprint"):
        raise ValueError("Effective source changed after repair; re-review lineage is stale")
    expected = sorted(set(plan.get("finding_ids", [])))
    if sorted(outcomes) != expected or any(value not in {"PASS", "FAIL", "BLOCKED"} for value in outcomes.values()):
        raise ValueError("Rereview outcomes must cover every planned finding with PASS, FAIL, or BLOCKED")
    if sorted(verification_notes) != expected or any(
        not isinstance(value, str) or not value.strip() or len(value) > 4000
        for value in verification_notes.values()
    ):
        raise ValueError("Rereview verification_notes must give concrete bounded evidence for every finding")
    store = load_json_object(_file(root, selected, "rereviews.json"))
    if any(item.get("repair_plan_id") == repair_plan_id for item in store.get("records", [])):
        raise ValueError("Repair plan already has an immutable rereview")
    contract = repair_contract(root, repair_plan_id, phase="REREVIEW", run_id=selected)
    if contract.get("evidence_output") not in normalized_refs:
        raise ValueError("Rereview evidence_refs must include the contract-bound rereview evidence output")
    _, task_fingerprint = _validated_repair_task(root, task_id, contract, normalized_refs)
    record = {
        "repair_plan_id": repair_plan_id,
        "task_id": task_id,
        "task_dispatch_fingerprint": task_fingerprint,
        "round": plan["round"],
        "reviewer_id": reviewer,
        "reviewer_session_id": reviewer_session,
        "fixer_separation": "RECORDED_ID_AND_SESSION_DIFFERENCE",
        "reviewed_target_fingerprint": current_source.get("fingerprint"),
        "session_isolation_status": _lifecycle_session_status(
            session_attestation,
            session_id=reviewer_session,
            repair_plan_id=repair_plan_id,
            independent_from=str(repair.get("fixer_session_id")),
        ),
        "outcomes": dict(sorted(outcomes.items())),
        "verification_notes": {key: verification_notes[key].strip() for key in sorted(verification_notes)},
        "evidence_refs": normalized_refs,
        "evidence_snapshot": selected_source_snapshot(root, normalized_refs),
        "recorded_at": utc_now(),
        "status": "PASS" if all(value == "PASS" for value in outcomes.values()) else "NEEDS_REVISION",
    }
    record["record_fingerprint"] = _record_fingerprint(record)
    store.setdefault("records", []).append(record)
    _write(root, _file(root, selected, "rereviews.json"), store)
    for item in repairs["plans"]:
        if item.get("repair_plan_id") == repair_plan_id:
            item["status"] = "REREVIEW_PASS" if record["status"] == "PASS" else "REREVIEW_FAILED"
            item["plan_fingerprint"] = canonical_hash({
                key: value for key, value in item.items() if key != "plan_fingerprint"
            })
    _write(root, _file(root, selected, "repairs.json"), repairs)
    return record


def _passed_rereview_findings(root: Path, run_id: str) -> set[str]:
    repairs = load_json_object(_file(root, run_id, "repairs.json"))
    plans = {
        str(item.get("repair_plan_id")): item
        for item in repairs.get("plans", []) if isinstance(item, dict)
    }
    for record in repairs.get("records", []):
        if not isinstance(record, dict) or record.get("record_fingerprint") != _record_fingerprint(record):
            raise ValueError("Repair record fingerprint is invalid")
        plan_id = str(record.get("repair_plan_id", ""))
        if plan_id not in plans:
            raise ValueError("Repair record has no matching plan")
        contract = repair_contract(root, plan_id, phase="REPAIR", run_id=run_id)
        _, task_fingerprint = _validated_repair_task(
            root, str(record.get("task_id", "")), contract, list(record.get("evidence_refs", [])),
        )
        if record.get("task_dispatch_fingerprint") != task_fingerprint:
            raise ValueError("Repair Task Package dispatch lineage is stale")
        if record.get("evidence_snapshot") != selected_source_snapshot(root, record.get("evidence_refs", [])):
            raise ValueError("Repair evidence changed after recording")
    store = load_json_object(_file(root, run_id, "rereviews.json"))
    for record in store.get("records", []):
        if not isinstance(record, dict) or record.get("record_fingerprint") != _record_fingerprint(record):
            raise ValueError("Rereview record fingerprint is invalid")
        if record.get("evidence_snapshot") != selected_source_snapshot(root, record.get("evidence_refs", [])):
            raise ValueError("Rereview evidence changed after recording")
        plan_id = str(record.get("repair_plan_id", ""))
        contract = repair_contract(root, plan_id, phase="REREVIEW", run_id=run_id)
        _, task_fingerprint = _validated_repair_task(
            root, str(record.get("task_id", "")), contract, list(record.get("evidence_refs", [])),
        )
        if record.get("task_dispatch_fingerprint") != task_fingerprint:
            raise ValueError("Rereview Task Package dispatch lineage is stale")
    return {
        finding_id
        for record in store.get("records", [])
        if isinstance(record, dict)
        for finding_id, outcome in record.get("outcomes", {}).items()
        if outcome == "PASS"
    }


def _normalize_evidence_refs(root: Path, values: list[str], label: str) -> list[str]:
    if not values or not all(isinstance(item, str) and item.strip() for item in values):
        raise ValueError(f"{label} evidence_refs must contain at least one non-empty reference")
    normalized: list[str] = []
    for value in values:
        if any(char in value for char in ("\x00", "\r", "\n")):
            raise ValueError(f"{label} evidence reference contains unsafe control characters")
        path = safe_project_path(root, value)
        if not path.is_file():
            raise ValueError(f"{label} evidence reference does not exist as a project file: {value}")
        metadata = os.lstat(path)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"{label} evidence reference must be an ordinary single-link file: {value}")
        if metadata.st_size <= 0:
            raise ValueError(f"{label} evidence reference must not be empty: {value}")
        relative = path.relative_to(root.resolve()).as_posix()
        if relative not in normalized:
            normalized.append(relative)
    return sorted(normalized)


def _validated_qa_task(
    root: Path,
    task_id: str,
    run_id: str,
    evidence_refs: list[str],
) -> tuple[str, str]:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("Final QA task_id must reference a path-safe Task Package")
    task_path = safe_project_path(root, Path("tasks") / f"{task_id}.yaml")
    if not task_path.is_file():
        raise ValueError(f"Final QA Task Package does not exist: tasks/{task_id}.yaml")
    text = task_path.read_text(encoding="utf-8")
    errors = validate_task_contract(root, text, "qa", allowed_statuses=("COMPLETED",))
    if errors:
        raise ValueError("Final QA Task Package contract is invalid: " + "; ".join(errors))
    expected = {
        "run_id": run_id,
        "owner": "qa",
        "stage": "READY_FOR_QA",
        "task_type": "qa",
    }
    for field, wanted in expected.items():
        if quoted_scalar(text, field) != wanted:
            raise ValueError(f"Final QA Task Package {field} must be {wanted}")
    receipt_errors = validate_dispatch_receipt(root, text)
    if receipt_errors:
        raise ValueError("Final QA requires a matching READY dispatch receipt: " + "; ".join(receipt_errors))
    handoff = top_section(text, "handoff")
    if quoted_scalar(handoff, "conclusion") != "PASS":
        raise ValueError(
            "Review finalization requires a pure PASS QA handoff; accepted risks must be resolved or governed outside this claim"
        )
    task_evidence = set(list_field(handoff, "evidence"))
    if not set(evidence_refs) <= task_evidence:
        raise ValueError("Final QA evidence_refs must be recorded in the completed QA Task Package handoff")
    return text, task_dispatch_fingerprint(text)


def record_qa(
    root: Path,
    *,
    qa_id: str,
    task_id: str,
    qa_session_id: str,
    evidence_refs: list[str],
    finding_verifications: dict[str, str],
    run_id: str | None = None,
    session_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record independent final QA bound to current coverage/findings/target evidence."""
    root = root.resolve()
    selected, review, _, inventory, plan, _ = _validate_live(root, run_id)
    _, run = _open_run(root, selected)
    if "current_state" in run:
        if run.get("current_state") != "READY_FOR_QA":
            raise ValueError("Final QA recording requires the governed run to be at READY_FOR_QA")
        role_plan = load_json_object(control_path(root, "orchestration/role-plan.json"))
        if (
            role_plan.get("status") != "ROUTED"
            or role_plan.get("current_stage") != "READY_FOR_QA"
            or "qa" not in role_plan.get("required_now", [])
        ):
            raise ValueError("Final QA recording requires the current READY_FOR_QA role plan to route qa")
    if qa_id != "qa":
        raise ValueError("Final review acceptance must be recorded by the canonical qa role")
    session = _string_identifier(qa_session_id, "qa_session_id", SESSION_PATTERN)
    results = _load_valid_results(root, selected, review, inventory, plan)
    coverage = _coverage(plan, results.get("results", []))
    if coverage.get("status") != "COMPLETE_FOR_DECLARED_SCOPE":
        raise ValueError("Final QA requires complete declared review coverage")
    merged = merge_findings(root, run_id=selected)
    high = [item for item in merged.get("findings", []) if item.get("severity") in {"P0", "P1"}]
    passed = _passed_rereview_findings(root, selected)
    unresolved = sorted(str(item["finding_id"]) for item in high if item["finding_id"] not in passed)
    if unresolved:
        raise ValueError("Final QA cannot pass unresolved P0/P1 findings: " + ", ".join(unresolved))
    high_ids = sorted(str(item["finding_id"]) for item in high)
    repair_progress = _repair_progress(root, selected, passed)
    required_verification_ids = sorted(set(high_ids) | set(repair_progress["authorized_finding_ids"]))
    if sorted(finding_verifications) != required_verification_ids or any(
        not isinstance(value, str) or not value.strip() or len(value) > 4000
        for value in finding_verifications.values()
    ):
        raise ValueError(
            "Final QA finding_verifications must give concrete current-target verification for every P0/P1 "
            "and every authorized repair finding"
        )
    prior_sessions = {
        str(item.get("review_session_id")) for item in results.get("results", []) if isinstance(item, dict)
    }
    if review.get("review_mode") == "review_and_fix":
        repairs = load_json_object(_file(root, selected, "repairs.json"))
        rereviews = load_json_object(_file(root, selected, "rereviews.json"))
        prior_sessions.update(
            str(item.get(key))
            for item in list(repairs.get("records", [])) + list(rereviews.get("records", []))
            if isinstance(item, dict)
            for key in ("fixer_session_id", "reviewer_session_id")
            if item.get(key)
        )
        effective_target = effective_source_snapshot(root).get("fingerprint")
    else:
        effective_target = review.get("target_fingerprint")
    if session in prior_sessions:
        raise ValueError("Final QA must use a session independent from review, repair, and rereview sessions")
    normalized_refs = _normalize_evidence_refs(root, evidence_refs, "Final QA")
    _, qa_task_fingerprint = _validated_qa_task(root, task_id, selected, normalized_refs)
    evidence_snapshot = selected_source_snapshot(root, normalized_refs)
    qa_store = load_json_object(_file(root, selected, "qa.json"))
    if qa_store.get("record") is not None:
        raise ValueError("Final QA record is immutable and already exists")
    attestation_status = "UNVERIFIED_SESSION_ISOLATION"
    if isinstance(session_attestation, dict) and (
        session_attestation.get("session_id") == session
        and session_attestation.get("run_id") == selected
        and session_attestation.get("fresh_session_attested") is True
        and session_attestation.get("independent_qa_attested") is True
        and session_attestation.get("attested_by") == "orchestrator"
    ):
        attestation_status = "ATTESTED_SESSION_ISOLATION"
    record = {
        "qa_id": qa_id,
        "task_id": task_id,
        "task_dispatch_fingerprint": qa_task_fingerprint,
        "qa_session_id": session,
        "status": "PASS",
        "target_fingerprint": effective_target,
        "coverage_fingerprint": canonical_hash(coverage),
        "findings_merge_fingerprint": merged.get("merge_fingerprint"),
        "finding_verifications": {
            key: finding_verifications[key].strip() for key in sorted(finding_verifications)
        },
        "evidence_refs": normalized_refs,
        "evidence_snapshot": evidence_snapshot,
        "session_isolation_status": attestation_status,
        "recorded_at": utc_now(),
    }
    record["record_fingerprint"] = _record_fingerprint(record)
    qa_store.update({"status": "PASS", "record": record})
    _write(root, _file(root, selected, "qa.json"), qa_store)
    return record


def _validated_qa(
    root: Path,
    run_id: str,
    review: dict[str, Any],
    coverage: dict[str, Any],
    merged: dict[str, Any],
) -> dict[str, Any]:
    store = load_json_object(_file(root, run_id, "qa.json"))
    record = store.get("record")
    if store.get("status") != "PASS" or not isinstance(record, dict):
        raise ValueError("Finalization requires an independent QA PASS record")
    if record.get("record_fingerprint") != _record_fingerprint(record):
        raise ValueError("Final QA record fingerprint is invalid")
    _, qa_task_fingerprint = _validated_qa_task(
        root, str(record.get("task_id", "")), run_id, list(record.get("evidence_refs", [])),
    )
    if record.get("task_dispatch_fingerprint") != qa_task_fingerprint:
        raise ValueError("Final QA Task Package dispatch lineage is stale")
    if record.get("coverage_fingerprint") != canonical_hash(coverage):
        raise ValueError("Final QA coverage lineage is stale")
    if record.get("findings_merge_fingerprint") != merged.get("merge_fingerprint"):
        raise ValueError("Final QA findings lineage is stale")
    high_ids = {
        str(item["finding_id"]) for item in merged.get("findings", [])
        if item.get("severity") in {"P0", "P1"}
    }
    repair_progress = _repair_progress(root, run_id)
    required_verification_ids = sorted(high_ids | set(repair_progress["authorized_finding_ids"]))
    verifications = record.get("finding_verifications")
    if not isinstance(verifications, dict) or sorted(verifications) != required_verification_ids or any(
        not isinstance(value, str) or not value.strip() for value in verifications.values()
    ):
        raise ValueError("Final QA current-target finding verification lineage is invalid")
    if record.get("evidence_snapshot") != selected_source_snapshot(root, record.get("evidence_refs", [])):
        raise ValueError("Final QA evidence changed after acceptance")
    expected_target = (
        effective_source_snapshot(root).get("fingerprint")
        if review.get("review_mode") == "review_and_fix"
        else review.get("target_fingerprint")
    )
    if record.get("target_fingerprint") != expected_target:
        raise ValueError("Final QA target lineage is stale")
    return record


def _repair_progress(
    root: Path,
    run_id: str,
    passed: set[str] | None = None,
    final_qa_verifications: set[str] | None = None,
) -> dict[str, Any]:
    """Summarize every authorized repair without hiding failed historical attempts."""
    store = load_json_object(_file(root, run_id, "repairs.json"))
    plans = [item for item in store.get("plans", []) if isinstance(item, dict)]
    status_counts: dict[str, int] = {}
    authorized: set[str] = set()
    for plan in plans:
        status = str(plan.get("status", "UNKNOWN"))
        status_counts[status] = status_counts.get(status, 0) + 1
        authorized.update(str(value) for value in plan.get("finding_ids", []) if isinstance(value, str))
    verified = set(passed) if passed is not None else _passed_rereview_findings(root, run_id)
    final_verified = set(final_qa_verifications or set())
    missing_rereview = authorized - verified
    missing_final_qa = authorized - final_verified
    if not authorized:
        status = "NOT_APPLICABLE"
    elif missing_rereview:
        status = "INCOMPLETE_REREVIEW"
    elif missing_final_qa:
        status = "AWAITING_FINAL_QA"
    else:
        status = "PASS"
    return {
        "plan_count": len(plans),
        "plan_status_counts": dict(sorted(status_counts.items())),
        "authorized_finding_ids": sorted(authorized),
        "verified_finding_ids": sorted(authorized & verified),
        "unverified_finding_ids": sorted(missing_rereview),
        "final_target_qa_verified_finding_ids": sorted(authorized & final_verified),
        "final_target_qa_unverified_finding_ids": sorted(missing_final_qa),
        "status": status,
    }


def status_review(root: Path, *, run_id: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    selected, review, _, _, plan = _load_review_set(root, run_id)
    if review.get("status") in {"FINALIZED", "FINALIZED_WITH_FINDINGS"}:
        report = load_json_object(_file(root, selected, "final-report.json"))
        return {
            "run_id": selected,
            "status": review.get("status"),
            "review_mode": review.get("review_mode"),
            "target_fingerprint": review.get("target_fingerprint"),
            "inventory_fingerprint": report.get("inventory_fingerprint"),
            "plan_fingerprint": report.get("plan_fingerprint"),
            "disposition_counts": report.get("disposition_counts", {}),
            "exclusions": report.get("exclusions", []),
            "drift_status": "FINALIZED_IMMUTABLE",
            "warnings": report.get("working_tree_warnings", []),
            "coverage": load_json_object(_file(root, selected, "coverage.json")),
            "finding_counts": report.get("severity_counts", {}),
            "repair_progress": report.get("repair_progress", {
                "plan_count": 0, "plan_status_counts": {}, "authorized_finding_ids": [],
                "verified_finding_ids": [], "unverified_finding_ids": [],
                "final_target_qa_verified_finding_ids": [], "final_target_qa_unverified_finding_ids": [],
                "status": "NOT_APPLICABLE",
            }),
            "next_action": "Preserve the immutable final report; start a new OPEN run for another target.",
        }
    try:
        selected, review, _, _, plan, warnings = _validate_live(root, run_id)
        drift = "CURRENT"
    except ValueError as exc:
        selected, review, _, _, plan = _load_review_set(root, run_id)
        if review.get("status") != "STALE":
            raise
        warnings = []
        drift = str(exc)
    inventory = load_json_object(_file(root, selected, "inventory.json"))
    results = _load_valid_results(root, selected, review, inventory, plan)
    coverage = _coverage(plan, results.get("results", []))
    merged = merge_finding_values([
        finding
        for result in results.get("results", [])
        if isinstance(result, dict)
        for finding in result.get("findings", [])
        if isinstance(finding, dict)
    ])
    qa_store = load_json_object(_file(root, selected, "qa.json"))
    qa_verifications = (
        set(qa_store.get("record", {}).get("finding_verifications", {}))
        if isinstance(qa_store.get("record"), dict) else set()
    )
    repair_progress = (
        _repair_progress(root, selected, final_qa_verifications=qa_verifications)
        if review.get("review_mode") == "review_and_fix" else {
            "plan_count": 0, "plan_status_counts": {}, "authorized_finding_ids": [],
            "verified_finding_ids": [], "unverified_finding_ids": [],
            "final_target_qa_verified_finding_ids": [], "final_target_qa_unverified_finding_ids": [],
            "status": "NOT_APPLICABLE",
        }
    )
    return {
        "run_id": selected,
        "status": review.get("status"),
        "review_mode": review.get("review_mode"),
        "target_fingerprint": review.get("target_fingerprint"),
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "primary_shards": len(plan.get("primary_shards", [])),
        "cross_cut_shards": len(plan.get("cross_cut_shards", [])),
        "disposition_counts": inventory.get("disposition_counts", {}),
        "oversized_files": plan.get("oversized_files", []),
        "exclusions": [
            {"path": item.get("path"), "disposition": item.get("disposition")}
            for item in inventory.get("entries", [])
            if isinstance(item, dict) and item.get("disposition") != "INCLUDED"
        ][:1000],
        "drift_status": drift,
        "warnings": warnings,
        "coverage": coverage,
        "finding_counts": {
            severity: sum(1 for item in merged.get("findings", []) if item.get("severity") == severity)
            for severity in ("P0", "P1", "P2", "P3")
        },
        "qa_status": qa_store.get("status"),
        "repair_progress": repair_progress,
        "next_action": _next_action(review, coverage, merged, qa_store.get("status"), repair_progress),
    }


def _next_action(
    review: dict[str, Any], coverage: dict[str, Any], merged: dict[str, Any], qa_status: Any,
    repair_progress: dict[str, Any] | None = None,
) -> str:
    if review.get("status") == "STALE":
        return "Start a new run/review against a fresh immutable target; do not reuse stale conclusions."
    if str(review.get("status", "")).startswith("BLOCKED_"):
        return "Resolve the recorded inventory or context-budget blocker, then start a fresh governed review."
    if coverage.get("status") != "COMPLETE_FOR_DECLARED_SCOPE":
        return "Dispatch the missing primary/cross-cut shards using fresh bounded Task Packages."
    high = [item for item in merged.get("findings", []) if item.get("severity") in {"P0", "P1"}]
    if high and review.get("review_mode") == "review_only":
        return "Report P0/P1 blockers; explicit review_and_fix authority and a new governed run are required to repair."
    if high:
        return "Plan or complete authorized repair and independent rereview for every P0/P1 finding."
    if repair_progress and repair_progress.get("unverified_finding_ids"):
        return "Complete or re-plan every authorized repair finding until independent rereview passes."
    if qa_status != "PASS":
        return "Run independent final QA in a fresh session and record its evidence before finalization."
    return "Finalize the review with its declared-scope and session-isolation limitations."


def finalize_review(root: Path, *, run_id: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    selected, review, snapshot, inventory, plan, warnings = _validate_live(root, run_id)
    _, run = _open_run(root, selected)
    if "current_state" in run and run.get("current_state") != "QA_PASS":
        raise ValueError("Governed review finalization requires the canonical lifecycle to reach QA_PASS")
    if plan.get("status") != "READY":
        raise ValueError(f"Review plan is not executable: {plan.get('status')}")
    results = _load_valid_results(root, selected, review, inventory, plan)
    coverage = _coverage(plan, results.get("results", []))
    if coverage.get("status") != "COMPLETE_FOR_DECLARED_SCOPE":
        raise ValueError("Cannot finalize before every declared primary and cross-cut shard is complete")
    merged = merge_findings(root, run_id=selected)
    high = [
        item for item in merged.get("findings", [])
        if item.get("severity") in {"P0", "P1"}
    ]
    passed = _passed_rereview_findings(root, selected)
    unresolved = sorted(str(item["finding_id"]) for item in high if item["finding_id"] not in passed)
    if unresolved:
        raise ValueError("P0/P1 findings require independent rereview PASS before finalize: " + ", ".join(unresolved))
    repair_progress = (
        _repair_progress(root, selected, passed)
        if review.get("review_mode") == "review_and_fix"
        else {
            "plan_count": 0, "plan_status_counts": {}, "authorized_finding_ids": [],
            "verified_finding_ids": [], "unverified_finding_ids": [],
            "final_target_qa_verified_finding_ids": [], "final_target_qa_unverified_finding_ids": [],
            "status": "NOT_APPLICABLE",
        }
    )
    if repair_progress["unverified_finding_ids"]:
        raise ValueError(
            "Every authorized repair finding requires independent rereview PASS before finalize: "
            + ", ".join(repair_progress["unverified_finding_ids"])
        )
    qa_record = _validated_qa(root, selected, review, coverage, merged)
    if review.get("review_mode") == "review_and_fix":
        repair_progress = _repair_progress(
            root, selected, passed, set(qa_record.get("finding_verifications", {})),
        )
    findings = merged.get("findings", [])
    status = "FINALIZED_WITH_FINDINGS" if findings else "FINALIZED"
    session_unverified = any(
        item.get("session_isolation_status") != "ATTESTED_SESSION_ISOLATION"
        for item in results.get("results", [])
        if isinstance(item, dict)
    )
    session_unverified = session_unverified or qa_record.get("session_isolation_status") != "ATTESTED_SESSION_ISOLATION"
    if review.get("review_mode") == "review_and_fix":
        repairs = load_json_object(_file(root, selected, "repairs.json"))
        rereviews = load_json_object(_file(root, selected, "rereviews.json"))
        lifecycle_records = list(repairs.get("records", [])) + list(rereviews.get("records", []))
        session_unverified = session_unverified or any(
            item.get("session_isolation_status") != "ATTESTED_SESSION_ISOLATION"
            for item in lifecycle_records if isinstance(item, dict)
        )
        repair_records = [item for item in repairs.get("records", []) if isinstance(item, dict)]
        effective_target = effective_source_snapshot(root)
        if repair_records:
            # Rounds are per finding, so multiple independent plans may all be
            # round 1. The immutable append order is the repair target chain.
            latest_repair = repair_records[-1]
            if effective_target.get("fingerprint") != latest_repair.get("repair_artifact_fingerprint"):
                raise ValueError("Effective source changed after the latest repair/re-review; finalization is stale")
    else:
        effective_target = None
    completion_claim = (
        "INITIAL_DECLARED_SCOPE_REVIEW_COMPLETE_AND_AUTHORIZED_REPAIRS_QA_VERIFIED"
        if review.get("review_mode") == "review_and_fix"
        else "COMPLETE_FOR_DECLARED_SCOPE"
    )
    report = {
        "schema_version": 1,
        "run_id": selected,
        "status": status,
        "finalized_at": utc_now(),
        "review_mode": review.get("review_mode"),
        "snapshot_kind": snapshot.get("snapshot_kind"),
        "target_fingerprint": review.get("target_fingerprint"),
        "effective_repaired_target_fingerprint": (
            effective_target.get("fingerprint") if effective_target is not None else None
        ),
        "effective_repaired_target_strength": (
            effective_target.get("conclusion_strength") if effective_target is not None else None
        ),
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "disposition_counts": inventory.get("disposition_counts", {}),
        "exclusions": [
            {"path": item.get("path"), "disposition": item.get("disposition")}
            for item in inventory.get("entries", [])
            if isinstance(item, dict) and item.get("disposition") != "INCLUDED"
        ][:1000],
        "exclusions_truncated": sum(
            1 for item in inventory.get("entries", [])
            if isinstance(item, dict) and item.get("disposition") != "INCLUDED"
        ) > 1000,
        "coverage_status": "COMPLETE_FOR_DECLARED_SCOPE",
        "finding_count": len(findings),
        "severity_counts": {
            severity: sum(1 for item in findings if item.get("severity") == severity)
            for severity in ("P0", "P1", "P2", "P3")
        },
        "p0_p1_rereview_passed": sorted(passed),
        "p0_p1_final_qa_verified": sorted(
            set(qa_record.get("finding_verifications", {}))
            & {str(item["finding_id"]) for item in high}
        ),
        "final_qa_verified_finding_ids": sorted(qa_record.get("finding_verifications", {})),
        "repair_progress": repair_progress,
        "qa_status": qa_record.get("status"),
        "qa_evidence_refs": qa_record.get("evidence_refs"),
        "qa_record_fingerprint": qa_record.get("record_fingerprint"),
        "session_isolation": "UNVERIFIED_SESSION_ISOLATION" if session_unverified else "ATTESTED_SESSION_ISOLATION",
        "working_tree_warnings": warnings,
        "limitations": coverage.get("limitations", []) + [
            "Static byte/token estimates are not measurements of host runtime context usage",
            "Module discovery is manifest/directory heuristic evidence, not complete semantic understanding",
        ],
        "completion_claim": completion_claim,
    }
    _write(root, _file(root, selected, "final-report.json"), report)
    review.update({
        "status": status,
        "updated_at": utc_now(),
        "completion_claim": completion_claim,
    })
    _write(root, _file(root, selected, "review.json"), review)
    _write(root, _file(root, selected, "coverage.json"), coverage)
    return report
