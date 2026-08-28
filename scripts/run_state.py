#!/usr/bin/env python3
"""Project-local run ledger, recovery decision, and evidence report."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import project_root
from role_routing import role_plan_fingerprint
from route_roles import source_fingerprint
from check_project_status import check as check_project_status
from dispatch_receipt import validate_dispatch_receipt
from project_layout import control_path
from state_io import append_jsonl, atomic_write_json, atomic_write_text, load_json_object, safe_project_path, utc_now
from task_contract import list_field, quoted_scalar, top_section, validate_task_contract


RUN_SCHEMA_VERSION = 1
RUN_ID_PATTERN = re.compile(r"^RUN-\d{8}T\d{6}Z-[a-f0-9]{6}$")
RESUME_STATES = {"RESUME_SAFE", "REPLAN_REQUIRED", "RECONCILIATION_REQUIRED", "BLOCKED", "DONE"}
EVENT_TYPES = {
    "TASK_STARTED", "HANDOFF_PERSISTED", "GATE_DECISION", "TASK_BLOCKED",
    "STATE_RECONCILED", "RUN_COMPLETED",
}


def _runs_root(root: Path, create: bool = False) -> Path:
    path = control_path(root, "runs")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _run_dir(root: Path, run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"Invalid run ID: {run_id}")
    path = control_path(root, Path("runs") / run_id)
    try:
        path.relative_to(_runs_root(root))
    except ValueError as exc:
        raise ValueError(f"Run path escapes ledger: {run_id}") from exc
    return path


def _run_file(root: Path, run_id: str, name: str) -> Path:
    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise ValueError(f"Invalid run file name: {name}")
    return control_path(root, Path("runs") / run_id / name)


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"RUN-{stamp}-{secrets.token_hex(3)}"


def _project_snapshot(root: Path) -> dict[str, Any]:
    status = load_json_object(root / "docs/project-status.json")
    stage = str(status.get("current_state", ""))
    plan_path = control_path(root, "orchestration/role-plan.json")
    plan = load_json_object(plan_path) if plan_path.is_file() else {}
    fingerprint = source_fingerprint(root, stage)
    return {
        "captured_at": utc_now(),
        "project": status.get("project"),
        "complexity": status.get("complexity"),
        "current_state": stage,
        "input_fingerprint": fingerprint,
        "role_plan_status": plan.get("status", "NOT_ROUTED"),
        "role_plan_fingerprint": plan.get("plan_fingerprint", ""),
        "routing_cycle_id": plan.get("routing_cycle_id", ""),
        "required_now": plan.get("required_now", []),
        "quota_mode": status.get("execution_control", {}).get("quota_mode", "economy"),
        "active_sessions": status.get("execution_control", {}).get("active_sessions", []),
        "active_tasks": status.get("active_tasks", []),
    }


def next_action(snapshot: dict[str, Any]) -> str:
    if snapshot.get("current_state") == "DONE":
        return "No further project action; verify the final report and release evidence."
    if snapshot.get("active_sessions") or snapshot.get("active_tasks"):
        return "Reconcile active sessions and tasks before resuming; do not clear them automatically."
    required = snapshot.get("required_now") or []
    if required:
        return f"Prepare and preflight one Task Package for required_now role: {required[0]}."
    return "Run the current-stage role plan, then follow only its required_now wave."


def create_run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    snapshot = _project_snapshot(root)
    if snapshot.get("active_sessions"):
        raise ValueError("Cannot create a second run while project active_sessions is non-empty; reconcile first")
    _runs_root(root, create=True)
    existing = list_runs(root)
    if existing:
        latest = load_json_object(_run_dir(root, existing[0]) / "run.json")
        if latest.get("status") in {"OPEN", "BLOCKED"}:
            raise ValueError(
                f"Run {existing[0]} is still {latest.get('status')}; resume and checkpoint it instead of creating a competing run"
            )
    run_id = _new_run_id()
    directory = _run_dir(root, run_id)
    directory.mkdir(parents=False, exist_ok=False)
    now = utc_now()
    run = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "project": snapshot.get("project"),
        "created_at": now,
        "updated_at": now,
        "status": "OPEN",
        "start_state": snapshot.get("current_state"),
        "current_state": snapshot.get("current_state"),
        "input_fingerprint": snapshot.get("input_fingerprint"),
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
        "routing_cycle_id": snapshot.get("routing_cycle_id"),
        "quota_mode": snapshot.get("quota_mode"),
        "active_task_ids": snapshot.get("active_tasks"),
        "active_sessions": snapshot.get("active_sessions"),
        "blocked_reason": None,
        "resume_decision": "RESUME_SAFE",
        "next_action": next_action(snapshot),
    }
    atomic_write_json(directory / "run.json", run)
    atomic_write_json(directory / "project-snapshot.json", snapshot)
    atomic_write_json(directory / "routing-decisions.json", {
        "schema_version": 1,
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
        "routing_cycle_id": snapshot.get("routing_cycle_id"),
        "required_now": snapshot.get("required_now", []),
        "history": [{
            "sequence": 1,
            "captured_at": now,
            "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
            "routing_cycle_id": snapshot.get("routing_cycle_id"),
            "required_now": snapshot.get("required_now", []),
        }],
    })
    atomic_write_json(directory / "evidence-index.json", {"schema_version": 1, "artifacts": [], "evidence": []})
    checkpoint = {
        "schema_version": 1,
        "run_id": run_id,
        "last_event_sequence": 1,
        "current_state": snapshot.get("current_state"),
        "input_fingerprint": snapshot.get("input_fingerprint"),
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
        "active_task_ids": snapshot.get("active_tasks"),
        "active_sessions": snapshot.get("active_sessions"),
        "next_safe_action": run["next_action"],
        "created_at": now,
    }
    atomic_write_json(directory / "checkpoint.json", checkpoint)
    append_jsonl(directory / "events.jsonl", {
        "sequence": 1, "timestamp": now, "run_id": run_id, "event_type": "RUN_CREATED",
        "status": "OPEN", "stage_before": snapshot.get("current_state"),
        "stage_after": snapshot.get("current_state"), "reason_codes": ["local-control-plane"],
        "input_fingerprint": snapshot.get("input_fingerprint"),
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
    })
    return run


def _normalize_refs(root: Path, values: list[str] | None, label: str) -> list[str]:
    normalized: list[str] = []
    for raw in values or []:
        path = safe_project_path(root, raw)
        if not path.is_file():
            raise ValueError(f"{label} reference does not exist as a project file: {raw}")
        relative = path.relative_to(root.resolve()).as_posix()
        if relative not in normalized:
            normalized.append(relative)
    return sorted(normalized)


def _validated_current_plan(root: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    plan = load_json_object(control_path(root, "orchestration/role-plan.json"))
    if plan.get("status") != "ROUTED":
        raise ValueError("A trusted checkpoint requires a persisted current-stage role plan")
    if plan.get("plan_fingerprint") != role_plan_fingerprint(plan):
        raise ValueError("The persisted role plan fingerprint is invalid")
    if plan.get("current_stage") != snapshot.get("current_state"):
        raise ValueError("The role plan stage differs from the current project state; re-plan before checkpointing")
    if plan.get("input_fingerprint") != snapshot.get("input_fingerprint"):
        raise ValueError("The role plan is stale for current stage inputs; re-plan before checkpointing")
    return plan


def _task_path(root: Path, task_id: str) -> Path:
    path = safe_project_path(root, Path("tasks") / f"{task_id}.yaml")
    if not path.is_file():
        raise ValueError(f"Checkpoint Task Package does not exist: tasks/{task_id}.yaml")
    return path


def _validate_task_started(root: Path, selected: str, task_id: str | None) -> None:
    if not task_id:
        raise ValueError("TASK_STARTED requires --task-id")
    text = _task_path(root, task_id).read_text(encoding="utf-8")
    if quoted_scalar(text, "run_id") != selected:
        raise ValueError("TASK_STARTED Task Package belongs to a different run")
    if quoted_scalar(text, "status") != "READY_FOR_DISPATCH":
        raise ValueError("TASK_STARTED requires a READY_FOR_DISPATCH Task Package")
    receipt_errors = validate_dispatch_receipt(root, text)
    if receipt_errors:
        raise ValueError("TASK_STARTED requires a matching dispatch receipt: " + "; ".join(receipt_errors))


def _validate_handoff(
    root: Path,
    selected: str,
    task_id: str | None,
    conclusion: str | None,
    artifacts: list[str],
    evidence: list[str],
) -> None:
    if not task_id:
        raise ValueError("HANDOFF_PERSISTED requires --task-id")
    if conclusion not in {"COMPLETE", "COMPLETED", "PASS", "PASS_WITH_ACCEPTED_RISKS"}:
        raise ValueError("HANDOFF_PERSISTED requires a successful owner/reviewer conclusion")
    if not artifacts and not evidence:
        raise ValueError("HANDOFF_PERSISTED requires at least one artifact or evidence reference")
    text = _task_path(root, task_id).read_text(encoding="utf-8")
    if quoted_scalar(text, "run_id") != selected:
        raise ValueError("HANDOFF_PERSISTED Task Package belongs to a different run")
    owner = quoted_scalar(text, "owner")
    contract_errors = validate_task_contract(root, text, owner, allowed_statuses=("COMPLETED",))
    if contract_errors:
        raise ValueError("HANDOFF_PERSISTED Task Contract is invalid: " + "; ".join(contract_errors))
    receipt_errors = validate_dispatch_receipt(root, text)
    if receipt_errors:
        raise ValueError("HANDOFF_PERSISTED requires a matching dispatch receipt: " + "; ".join(receipt_errors))
    handoff = top_section(text, "handoff")
    if quoted_scalar(handoff, "conclusion") not in {"COMPLETED", "PASS", "PASS_WITH_ACCEPTED_RISKS"}:
        raise ValueError("HANDOFF_PERSISTED Task Package has no successful handoff conclusion")
    declared = set(list_field(handoff, "artifacts") + list_field(handoff, "evidence"))
    missing = sorted((set(artifacts) | set(evidence)) - declared)
    if missing:
        raise ValueError("Checkpoint references are not declared in the Task Package handoff: " + ", ".join(missing))


def _done_gate_errors(root: Path) -> list[str]:
    errors, _ = check_project_status(root, "DONE")
    return errors


def checkpoint(
    root: Path,
    run_id: str | None = None,
    *,
    event_type: str,
    task_id: str | None = None,
    conclusion: str | None = None,
    artifact_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Persist a trusted orchestration checkpoint without claiming Agent liveness."""
    root = root.resolve()
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported checkpoint event type: {event_type}")
    if task_id and not re.fullmatch(r"TASK-[A-Z0-9][A-Z0-9_-]*", task_id):
        raise ValueError("task-id must look like TASK-001 or TASK-AUTH-01")
    if note and len(note) > 1000:
        raise ValueError("checkpoint note must be 1000 characters or fewer")
    artifacts = _normalize_refs(root, artifact_refs, "artifact")
    evidence = _normalize_refs(root, evidence_refs, "evidence")
    selected = run_id or latest_run_id(root)
    directory = _run_dir(root, selected)
    run_files = {
        name: _run_file(root, selected, name)
        for name in (
            "run.json", "checkpoint.json", "project-snapshot.json",
            "routing-decisions.json", "evidence-index.json", "events.jsonl",
        )
    }
    run = load_json_object(run_files["run.json"])
    prior = load_json_object(run_files["checkpoint.json"])
    if run.get("schema_version") != RUN_SCHEMA_VERSION or prior.get("run_id") != selected:
        raise ValueError("Run schema or checkpoint lineage is invalid")
    if run.get("status") == "DONE":
        raise ValueError("A DONE run is immutable; start a new project iteration before creating another run")
    snapshot = _project_snapshot(root)
    if event_type in {"TASK_STARTED", "HANDOFF_PERSISTED", "GATE_DECISION", "STATE_RECONCILED"}:
        _validated_current_plan(root, snapshot)
    if event_type == "TASK_STARTED":
        _validate_task_started(root, selected, task_id)
    elif event_type == "HANDOFF_PERSISTED":
        _validate_handoff(root, selected, task_id, conclusion, artifacts, evidence)
    elif event_type == "GATE_DECISION":
        if conclusion not in {"PASS", "APPROVED", "NEEDS_REVISION", "BLOCKED"}:
            raise ValueError("GATE_DECISION requires PASS, APPROVED, NEEDS_REVISION, or BLOCKED")
        if not evidence:
            raise ValueError("GATE_DECISION requires at least one project-local evidence reference")
        gate_errors, _ = check_project_status(root, str(snapshot.get("current_state")))
        if gate_errors:
            raise ValueError("GATE_DECISION cannot checkpoint a failing lifecycle gate: " + "; ".join(gate_errors))
    elif event_type == "STATE_RECONCILED":
        if snapshot.get("active_sessions") or snapshot.get("active_tasks"):
            raise ValueError("STATE_RECONCILED requires no uncertain active sessions or tasks")
        if not evidence:
            raise ValueError("STATE_RECONCILED requires evidence of the reconciled state or fresh role plan")
    if event_type == "RUN_COMPLETED":
        if snapshot.get("current_state") != "DONE" or snapshot.get("active_sessions") or snapshot.get("active_tasks"):
            raise ValueError("RUN_COMPLETED requires project state DONE with no active sessions or active tasks")
        if conclusion not in {"PASS", "PASS_WITH_ACCEPTED_RISKS"}:
            raise ValueError("RUN_COMPLETED requires an independent QA conclusion of PASS or PASS_WITH_ACCEPTED_RISKS")
        completion_errors = _done_gate_errors(root)
        if completion_errors:
            raise ValueError("RUN_COMPLETED requires the full DONE gate to pass: " + "; ".join(completion_errors))
        if not evidence:
            raise ValueError("RUN_COMPLETED requires indexed independent QA/release evidence")
    if event_type == "TASK_BLOCKED":
        if not task_id:
            raise ValueError("TASK_BLOCKED requires --task-id")
        if not note:
            raise ValueError("TASK_BLOCKED requires a concise blocking note")
    sequence = int(prior.get("last_event_sequence", 0)) + 1
    now = utc_now()
    status = "DONE" if event_type == "RUN_COMPLETED" else ("BLOCKED" if event_type == "TASK_BLOCKED" else "OPEN")
    current_checkpoint = {
        "schema_version": 1,
        "run_id": selected,
        "last_event_sequence": sequence,
        "last_event_type": event_type,
        "last_task_id": task_id,
        "last_conclusion": conclusion,
        "current_state": snapshot.get("current_state"),
        "input_fingerprint": snapshot.get("input_fingerprint"),
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
        "active_task_ids": snapshot.get("active_tasks"),
        "active_sessions": snapshot.get("active_sessions"),
        "next_safe_action": next_action(snapshot),
        "updated_at": now,
    }
    run.update({
        "updated_at": now,
        "status": status,
        "current_state": snapshot.get("current_state"),
        "input_fingerprint": snapshot.get("input_fingerprint"),
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
        "routing_cycle_id": snapshot.get("routing_cycle_id"),
        "active_task_ids": snapshot.get("active_tasks"),
        "active_sessions": snapshot.get("active_sessions"),
        "blocked_reason": note if status == "BLOCKED" else None,
        "resume_decision": "DONE" if status == "DONE" else ("BLOCKED" if status == "BLOCKED" else "RESUME_SAFE"),
        "next_action": current_checkpoint["next_safe_action"],
    })
    index = load_json_object(run_files["evidence-index.json"])
    for key, refs in (("artifacts", artifacts), ("evidence", evidence)):
        entries = index.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"Invalid evidence index list: {key}")
        known = {item.get("ref") for item in entries if isinstance(item, dict)}
        for reference in refs:
            if reference not in known:
                entries.append({"ref": reference, "task_id": task_id, "recorded_at": now, "sequence": sequence})
        index[key] = entries
    routing = load_json_object(run_files["routing-decisions.json"])
    history = routing.get("history", [])
    if not isinstance(history, list):
        raise ValueError("Invalid routing decision history")
    route_record = {
        "sequence": sequence,
        "captured_at": now,
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
        "routing_cycle_id": snapshot.get("routing_cycle_id"),
        "required_now": snapshot.get("required_now", []),
    }
    if not history or any(history[-1].get(key) != route_record.get(key) for key in ("role_plan_fingerprint", "routing_cycle_id", "required_now")):
        history.append(route_record)
    routing.update({
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
        "routing_cycle_id": snapshot.get("routing_cycle_id"),
        "required_now": snapshot.get("required_now", []),
        "history": history,
    })
    atomic_write_json(run_files["project-snapshot.json"], snapshot)
    atomic_write_json(run_files["routing-decisions.json"], routing)
    atomic_write_json(run_files["evidence-index.json"], index)
    atomic_write_json(run_files["checkpoint.json"], current_checkpoint)
    atomic_write_json(run_files["run.json"], run)
    append_jsonl(run_files["events.jsonl"], {
        "sequence": sequence,
        "timestamp": now,
        "run_id": selected,
        "event_type": event_type,
        "status": status,
        "task_id": task_id,
        "conclusion": conclusion,
        "note": note,
        "artifacts": artifacts,
        "evidence": evidence,
        "stage_before": prior.get("current_state"),
        "stage_after": snapshot.get("current_state"),
        "input_fingerprint": snapshot.get("input_fingerprint"),
        "role_plan_fingerprint": snapshot.get("role_plan_fingerprint"),
    })
    return {
        "run_id": selected,
        "sequence": sequence,
        "event_type": event_type,
        "status": status,
        "current_state": snapshot.get("current_state"),
        "next_action": current_checkpoint["next_safe_action"],
        "artifact_count": len(artifacts),
        "evidence_count": len(evidence),
    }


def list_runs(root: Path) -> list[str]:
    runs_root = _runs_root(root)
    if not runs_root.is_dir():
        return []
    return sorted(
        (path.name for path in runs_root.iterdir() if path.is_dir() and RUN_ID_PATTERN.fullmatch(path.name)),
        reverse=True,
    )


def latest_run_id(root: Path) -> str:
    values = list_runs(root)
    if not values:
        raise ValueError("No run ledger exists. Start one with orchestrator.py run PROJECT_DIR")
    return values[0]


def resume(root: Path, run_id: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    selected = run_id or latest_run_id(root)
    directory = _run_dir(root, selected)
    try:
        run = load_json_object(directory / "run.json")
        checkpoint = load_json_object(directory / "checkpoint.json")
        current = _project_snapshot(root)
    except ValueError as exc:
        return {"run_id": selected, "decision": "BLOCKED", "reason": str(exc), "next_action": "Repair or archive the corrupt run evidence; do not infer completion."}
    if run.get("schema_version") != RUN_SCHEMA_VERSION or checkpoint.get("run_id") != selected:
        return {"run_id": selected, "decision": "BLOCKED", "reason": "Run schema or checkpoint lineage is invalid", "next_action": "Inspect the run ledger before continuing."}
    if run.get("status") == "BLOCKED":
        decision, reason = "BLOCKED", str(run.get("blocked_reason") or "The latest trusted checkpoint is blocked")
    elif current.get("current_state") == "DONE" and not current.get("active_sessions") and not current.get("active_tasks"):
        completion_errors = _done_gate_errors(root)
        if completion_errors:
            decision, reason = "BLOCKED", "Project claims DONE but the full completion gate fails: " + "; ".join(completion_errors)
        elif run.get("status") == "DONE":
            decision, reason = "DONE", "Project and run completion evidence both satisfy DONE"
        else:
            decision, reason = "RECONCILIATION_REQUIRED", "Project satisfies DONE but the run has no trusted completion checkpoint"
    elif current.get("active_sessions") or current.get("active_tasks"):
        decision, reason = "RECONCILIATION_REQUIRED", "Project records active sessions or tasks whose liveness cannot be inferred"
    elif current.get("current_state") != checkpoint.get("current_state"):
        decision, reason = "RECONCILIATION_REQUIRED", "Project state changed after the last trusted checkpoint"
    elif current.get("input_fingerprint") != checkpoint.get("input_fingerprint"):
        decision, reason = "REPLAN_REQUIRED", "Current-stage source documents changed after the checkpoint"
    else:
        plan_path = control_path(root, "orchestration/role-plan.json")
        plan = load_json_object(plan_path) if plan_path.is_file() else {}
        stored = plan.get("plan_fingerprint", "")
        if plan.get("status") == "ROUTED" and stored != role_plan_fingerprint(plan):
            decision, reason = "BLOCKED", "Persisted role plan fingerprint is invalid"
        elif stored != checkpoint.get("role_plan_fingerprint"):
            decision, reason = "REPLAN_REQUIRED", "Role plan changed after the checkpoint"
        else:
            decision, reason = "RESUME_SAFE", "Project sources and role plan still match the trusted checkpoint"
    if decision not in RESUME_STATES:
        raise AssertionError(f"Unknown resume decision: {decision}")
    action_snapshot = dict(current)
    if decision == "REPLAN_REQUIRED":
        action = "Re-run the current-stage role plan before dispatching any task."
    elif decision == "RECONCILIATION_REQUIRED":
        action = "Reconcile recorded sessions/tasks against the Codex host; do not auto-clear or auto-restart."
    elif decision == "BLOCKED":
        action = "Repair the invalid project/run evidence before continuing."
    elif decision == "DONE":
        action = "Generate and review the final report; no Agent should be restarted."
    else:
        action = next_action(action_snapshot)
    return {"run_id": selected, "decision": decision, "reason": reason, "next_action": action, "current": current}


def report(root: Path, run_id: str | None = None, write: bool = True) -> tuple[str, Path]:
    root = root.resolve()
    selected = run_id or latest_run_id(root)
    directory = _run_dir(root, selected)
    run = load_json_object(directory / "run.json")
    checkpoint_value = load_json_object(directory / "checkpoint.json")
    evidence_index = load_json_object(directory / "evidence-index.json")
    decision = resume(root, selected)
    lines = [
        f"# Run report — {selected}", "",
        f"- Project: {run.get('project')}",
        f"- Started: {run.get('created_at')}",
        f"- Updated: {run.get('updated_at')}",
        f"- Run status: {run.get('status')}",
        f"- Start state: {run.get('start_state')}",
        f"- Current state: {run.get('current_state')}",
        f"- Last event sequence: {checkpoint_value.get('last_event_sequence')}",
        f"- Resume decision: {decision.get('decision')}",
        f"- Reason: {decision.get('reason')}",
        f"- Next safe action: {decision.get('next_action')}", "",
        "## Evidence", "",
        f"- Indexed artifacts: {len(evidence_index.get('artifacts', []))}",
        f"- Indexed acceptance evidence: {len(evidence_index.get('evidence', []))}",
        "- `run.json`: run identity and bounded control state",
        "- `events.jsonl`: append-only sanitized execution events",
        "- `checkpoint.json`: last trusted local checkpoint",
        "- `project-snapshot.json`: project state captured at run creation",
        "- `evidence-index.json`: artifact and acceptance-evidence references",
        "- `routing-decisions.json`: role-plan lineage used by this run", "",
        "This report does not claim that the Python control plane started or restored a native host Agent session.", "",
    ]
    content = "\n".join(lines)
    path = directory / "final-report.md"
    if write:
        atomic_write_text(path, content)
    return content, path


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("project_dir")
    resume_parser = sub.add_parser("resume")
    resume_parser.add_argument("project_dir")
    resume_parser.add_argument("--run-id")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("project_dir")
    report_parser.add_argument("--run-id")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        if args.command == "start":
            value = create_run(root)
        elif args.command == "resume":
            value = resume(root, args.run_id)
        else:
            content, path = report(root, args.run_id)
            value = {"report": str(path), "content": content}
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value.get("decision") not in {"BLOCKED", "RECONCILIATION_REQUIRED"} else 3
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
