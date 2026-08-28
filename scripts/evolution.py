#!/usr/bin/env python3
"""Deterministic, project-local Evolution Core operations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from evolution_store import (
    EVOLUTION_REL, GENERATOR_VERSION, POLICY_VERSION, PROTECTED_INVARIANTS,
    EvolutionBlocked, atomic_append_jsonl, atomic_json, canonical_json,
    deterministic_id, evolution_rel, evolution_root, exclusive_lock, fingerprint, git_exposure,
    initialize_workspace, load_json_file, load_manifest, load_strict_jsonl,
    parse_json, require_exact_keys, require_git_safe, require_utc_timestamp,
    stable_hash_file, strict_file,
    validate_project_root,
)
from state_io import utc_now
from task_contract import quoted_scalar
from project_layout import control_path, control_relative


RUN_ID = re.compile(r"^RUN-\d{8}T\d{6}Z-[a-f0-9]{6}$")
TASK_ID = re.compile(r"^TASK-[A-Z0-9][A-Z0-9_-]*$")
HEX = re.compile(r"^[a-f0-9]{64}$")
OUT_ID = re.compile(r"^OUT-[A-F0-9]{20}$")
FDB_ID = re.compile(r"^FDB-[A-F0-9]{20}$")
RETRO_ID = re.compile(r"^RET-[A-F0-9]{20}$")
PROPOSAL_ID = re.compile(r"^PRP-[A-F0-9]{20}$")
EVAL_ID = re.compile(r"^EVC-[A-F0-9]{20}$")
CATEGORIES = [
    "business_rule", "product_completeness", "ux", "ui", "architecture",
    "implementation", "test_coverage", "model_routing", "role_routing",
    "capability", "recovery", "process", "security_privacy", "cost_latency",
]
KINDS = ["user_correction", "repeated_defect", "routing_waste", "model_mismatch", "process_gap", "security_or_privacy"]
RESULTS = ["CORRECTED", "FAIL", "BLOCKED", "ACCEPTED_RISK", "OBSERVED"]
SEVERITIES = ["P0", "P1", "P2", "P3", "INFO"]
UNKNOWN_VALUES = ["actual_model", "reasoning", "tokens", "cost", "quota", "agent_runtime", "product_quality", "agent_necessity"]
ROLES = [
    "orchestrator", "requirements", "product_auditor", "ux", "ui", "architect",
    "engineering_lead", "qa", "quality_governor", "frontend_worker",
    "backend_worker", "ai_worker", "data_worker", "test_worker",
]
FORBIDDEN_CHANGES = sorted([
    "acceptance_criteria", "authorization_rules", "development_qa_separation",
    "evolution_evidence_policy", "formal_eval_expectations",
    "protected_invariant_registry", "release_gate", "stage_gates",
])
TARGETS = {
    "business_rule": "template", "product_completeness": "checklist", "ux": "checklist",
    "ui": "checklist", "architecture": "template", "implementation": "checklist",
    "test_coverage": "checklist", "model_routing": "model_routing",
    "role_routing": "role_routing", "capability": "capability_policy",
    "recovery": "recovery", "process": "prompt", "security_privacy": "capability_policy",
    "cost_latency": "model_routing",
}
PROPOSAL_TEXT = {
    "rationale_template": "Evidence lineages meet the controlled threshold for this category.",
    "falsifier": "Reject if an independent evaluation does not reproduce the recorded failure class.",
    "expected_benefit": "Reduce recurrence of the bounded category-level failure.",
    "possible_harm": "A narrow rule may overfit and create unnecessary process cost.",
    "rollback_strategy": "Remove only the separately approved change and rerun the prior formal suite.",
    "required_evaluation": "Create a reviewed regression case that preserves every protected invariant.",
}
SENSITIVE = [
    re.compile(r"BEGIN[^\n]{0,40}PRIVATE KEY", re.I),
    re.compile(r"\b(?:sk-|gh[opusr]_)[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"https?://[^/\s:@]+:[^/\s@]+@", re.I),
    re.compile(r"[?&](?:token|key|secret|password|auth)=[^&\s]+", re.I),
    re.compile(r"\b(?:password|passwd|token|secret|api_key|apikey|authorization)\s*[:=]\s*(?!<[^>]+>|REDACTED|PLACEHOLDER)[^\s,;]+", re.I),
]
FORBIDDEN_PATH_PARTS = {".git", ".codex", ".dingxinglizi", ".aws", ".ssh", "credentials", "credential", "secrets", "private-keys"}
FORBIDDEN_FILE = re.compile(r"^(?:\.env(?:\..*)?|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|.*\.(?:pem|p12|pfx|key|keystore))$", re.I)


def _blocked(reason: str, message: str, **details: Any) -> EvolutionBlocked:
    return EvolutionBlocked(reason, message, **details)


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _blocked("CORRUPT_ARTIFACT", f"{label} must be an object")
    require_exact_keys(value, keys, label)
    return value


def _string_list(value: Any, label: str, *, non_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value) or (non_empty and not value):
        raise _blocked("CORRUPT_ARTIFACT", f"{label} must be a string array")
    return value


def _check_text(text: str, label: str, limit: int) -> None:
    if not isinstance(text, str) or not (1 <= len(text.encode("utf-8")) <= limit):
        raise ValueError(f"{label} must be 1-{limit} UTF-8 bytes")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text) or "\n" in text or "\r" in text:
        raise ValueError(f"{label} must be one line without control characters")
    if any(pattern.search(text) for pattern in SENSITIVE):
        raise ValueError(f"{label} contains sensitive-looking data and was not persisted")


def _check_hex(value: Any, label: str) -> None:
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise _blocked("CORRUPT_ARTIFACT", f"Invalid {label}")


def _check_project_relative_evidence(root: Path, raw: str, *, max_bytes: int) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > 512:
        raise ValueError("Evidence path must be 1-512 UTF-8 bytes")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Evidence path must be project-relative without traversal: {raw}")
    lowered = [part.lower() for part in path.parts]
    if any(part in FORBIDDEN_PATH_PARTS for part in lowered) or (len(lowered) >= 2 and lowered[:2] == [".codex", "evolution"]):
        raise ValueError(f"Evidence path is in a forbidden location: {raw}")
    if FORBIDDEN_FILE.fullmatch(path.name) or any(any(pattern.search(part) for pattern in SENSITIVE) for part in path.parts):
        raise ValueError(f"Evidence path name is sensitive-looking: {raw}")
    digest, size = stable_hash_file(root, path, max_bytes=max_bytes)
    return {"path": path.as_posix(), "content_hash": digest, "size_bytes": size}


def _json_obj(root: Path, relative: Path) -> dict[str, Any]:
    try:
        return load_json_file(root, relative)
    except ValueError as exc:
        raise _blocked("PATH_POLICY_VIOLATION", str(exc)) from exc


def _events(root: Path, relative: Path) -> list[dict[str, Any]]:
    _, raw = strict_file(root, relative, max_bytes=32 * 1024 * 1024)
    if not raw or not raw.endswith(b"\n"):
        raise _blocked("CORRUPT_ARTIFACT", "Run events must be non-empty strict JSONL with a final newline")
    lines = raw.splitlines()
    if len(lines) > 100_000:
        raise _blocked("RESOURCE_LIMIT_EXCEEDED", "Run has more than 100,000 events")
    result: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line or len(line) > 64 * 1024:
            raise _blocked("CORRUPT_ARTIFACT", f"Invalid event line size at {number}")
        try:
            value = parse_json(line.decode("utf-8"), f"events.jsonl:{number}")
        except (UnicodeDecodeError, EvolutionBlocked) as exc:
            raise _blocked("CORRUPT_ARTIFACT", f"Invalid event JSON at line {number}") from exc
        if not isinstance(value, dict):
            raise _blocked("CORRUPT_ARTIFACT", f"Event line {number} is not an object")
        result.append(value)
    return result


def _validate_run(root: Path, run_id: str) -> dict[str, Any]:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"Invalid run ID: {run_id}")
    base = control_relative(root, Path("runs") / run_id)
    directory = root / base
    try:
        info = os.lstat(directory)
    except FileNotFoundError:
        raise _blocked("INSUFFICIENT_EVIDENCE", f"Run does not exist: {run_id}") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise _blocked("PATH_POLICY_VIOLATION", f"Run path is not an ordinary directory: {run_id}")
    names = ["run.json", "checkpoint.json", "evidence-index.json", "routing-decisions.json", "project-snapshot.json"]
    values = {name: _json_obj(root, base / name) for name in names}
    events = _events(root, base / "events.jsonl")
    run, checkpoint = values["run.json"], values["checkpoint.json"]
    index, routing, snapshot = values["evidence-index.json"], values["routing-decisions.json"], values["project-snapshot.json"]
    if run.get("schema_version") != 1 or checkpoint.get("schema_version") != 1 or index.get("schema_version") != 1 or routing.get("schema_version") != 1:
        raise _blocked("UNSUPPORTED_SCHEMA", f"Run {run_id} uses an unsupported schema")
    required_run = {"run_id", "status", "start_state", "current_state", "input_fingerprint", "role_plan_fingerprint", "created_at", "updated_at"}
    if not required_run <= set(run) or not all(isinstance(run.get(key), str) for key in required_run):
        raise _blocked("CORRUPT_ARTIFACT", f"Run record lacks required v2 fields: {run_id}")
    require_utc_timestamp(run["created_at"], "Run created_at")
    require_utc_timestamp(run["updated_at"], "Run updated_at")
    if run.get("run_id") != run_id or checkpoint.get("run_id") != run_id:
        raise _blocked("CORRUPT_ARTIFACT", f"Run lineage mismatch: {run_id}")
    if run.get("status") != "DONE" or run.get("current_state") != "DONE" or checkpoint.get("current_state") != "DONE":
        raise _blocked("INSUFFICIENT_EVIDENCE", f"Run is not a completed DONE run: {run_id}")
    if not events or [event.get("sequence") for event in events] != list(range(1, len(events) + 1)):
        raise _blocked("CORRUPT_ARTIFACT", f"Run event sequence is invalid: {run_id}")
    if events[0].get("event_type") != "RUN_CREATED" or events[-1].get("event_type") != "RUN_COMPLETED":
        raise _blocked("CORRUPT_ARTIFACT", f"Run event boundary is invalid: {run_id}")
    required_event = {"sequence", "timestamp", "run_id", "event_type", "status", "stage_before", "stage_after", "input_fingerprint", "role_plan_fingerprint"}
    if any(not required_event <= set(event) or event.get("run_id") != run_id for event in events):
        raise _blocked("CORRUPT_ARTIFACT", f"Run event structure or lineage is invalid: {run_id}")
    for event in events:
        require_utc_timestamp(event["timestamp"], "Run event timestamp")
    final = events[-1]
    conclusion = final.get("conclusion")
    if final.get("status") != "DONE" or conclusion not in {"PASS", "PASS_WITH_ACCEPTED_RISKS"}:
        raise _blocked("INSUFFICIENT_EVIDENCE", f"Run lacks accepted independent-QA completion: {run_id}")
    if checkpoint.get("last_event_sequence") != len(events) or checkpoint.get("last_event_type") != "RUN_COMPLETED" or checkpoint.get("last_conclusion") != conclusion:
        raise _blocked("CORRUPT_ARTIFACT", f"Run checkpoint does not point to completion: {run_id}")
    input_fp = run.get("input_fingerprint")
    role_fp = run.get("role_plan_fingerprint")
    if not isinstance(input_fp, str) or not isinstance(role_fp, str) or any(item != input_fp for item in (checkpoint.get("input_fingerprint"), final.get("input_fingerprint"), snapshot.get("input_fingerprint"))):
        raise _blocked("CORRUPT_ARTIFACT", f"Run input fingerprint lineage is inconsistent: {run_id}")
    if any(item != role_fp for item in (checkpoint.get("role_plan_fingerprint"), final.get("role_plan_fingerprint"), snapshot.get("role_plan_fingerprint"), routing.get("role_plan_fingerprint"))):
        raise _blocked("CORRUPT_ARTIFACT", f"Run role-plan fingerprint lineage is inconsistent: {run_id}")
    for key in ("artifacts", "evidence"):
        if not isinstance(index.get(key), list):
            raise _blocked("CORRUPT_ARTIFACT", f"Run evidence index {key} is invalid")
    indexed: dict[str, dict[str, Any]] = {}
    hashes: list[dict[str, Any]] = []
    total_bytes = 0
    all_entries = index["artifacts"] + index["evidence"]
    if len(all_entries) > 1000:
        raise _blocked("RESOURCE_LIMIT_EXCEEDED", "Run indexes more than 1,000 evidence refs")
    for entry in all_entries:
        if not isinstance(entry, dict) or set(entry) != {"ref", "task_id", "recorded_at", "sequence"} or not isinstance(entry.get("ref"), str) or not isinstance(entry.get("recorded_at"), str) or not isinstance(entry.get("sequence"), int) or isinstance(entry.get("sequence"), bool) or not (1 <= entry["sequence"] <= len(events)) or (entry.get("task_id") is not None and not TASK_ID.fullmatch(str(entry.get("task_id")))):
            raise _blocked("CORRUPT_ARTIFACT", f"Invalid evidence-index entry in run {run_id}")
        require_utc_timestamp(entry["recorded_at"], "Evidence index recorded_at")
        try:
            metadata = _check_project_relative_evidence(root, entry["ref"], max_bytes=64 * 1024 * 1024)
        except ValueError as exc:
            raise _blocked("PATH_POLICY_VIOLATION", str(exc)) from exc
        total_bytes += metadata["size_bytes"]
        if total_bytes > 512 * 1024 * 1024:
            raise _blocked("RESOURCE_LIMIT_EXCEEDED", "Indexed run evidence exceeds 512 MiB")
        prior = indexed.get(entry["ref"])
        if prior and prior != entry:
            raise _blocked("CORRUPT_ARTIFACT", f"Conflicting duplicate evidence ref: {entry['ref']}")
        indexed[entry["ref"]] = entry
        hashes.append(metadata)
    history = routing.get("history")
    if not isinstance(history, list) or not isinstance(routing.get("required_now"), list) or not isinstance(routing.get("role_plan_fingerprint"), str) or not isinstance(routing.get("routing_cycle_id"), str):
        raise _blocked("CORRUPT_ARTIFACT", f"Invalid routing history in run {run_id}")
    for item in history:
        if not isinstance(item, dict) or not isinstance(item.get("sequence"), int) or isinstance(item.get("sequence"), bool) or not (1 <= item["sequence"] <= len(events)) or not isinstance(item.get("required_now"), list) or not isinstance(item.get("captured_at"), str) or not isinstance(item.get("role_plan_fingerprint"), str) or not isinstance(item.get("routing_cycle_id"), str):
            raise _blocked("CORRUPT_ARTIFACT", f"Invalid routing history entry in run {run_id}")
        require_utc_timestamp(item["captured_at"], "Routing history captured_at")
    required_snapshot = {"captured_at", "current_state", "input_fingerprint", "role_plan_fingerprint", "routing_cycle_id", "required_now"}
    if not required_snapshot <= set(snapshot) or not all(isinstance(snapshot.get(key), str) for key in required_snapshot - {"required_now"}) or not isinstance(snapshot.get("required_now"), list):
        raise _blocked("CORRUPT_ARTIFACT", f"Invalid project snapshot in run {run_id}")
    require_utc_timestamp(snapshot["captured_at"], "Project snapshot captured_at")
    canonical_sources = {**values, "events.jsonl": events, "indexed_files": sorted(hashes, key=lambda item: item["path"])}
    run_fp = fingerprint(canonical_sources)
    return {"run": run, "checkpoint": checkpoint, "events": events, "index": index, "routing": routing, "snapshot": snapshot, "indexed": indexed, "indexed_hashes": hashes, "run_fingerprint": run_fp, "qa_conclusion": conclusion}


def _valid_completed_runs(root: Path) -> list[str]:
    runs = control_path(root, "runs")
    if not runs.is_dir():
        return []
    candidates = sorted(item.name for item in runs.iterdir() if item.is_dir() and RUN_ID.fullmatch(item.name))
    valid: list[str] = []
    for run_id in candidates:
        try:
            _validate_run(root, run_id)
        except EvolutionBlocked as exc:
            if exc.reason_code == "INSUFFICIENT_EVIDENCE":
                continue
            raise
        valid.append(run_id)
    return valid


def _actual_execution(root: Path, run_id: str, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    facts = ("model", "reasoning", "tokens", "cost", "quota", "agent_runtime")
    actual: dict[str, Any] = {key: "UNAVAILABLE" for key in facts}
    refs: dict[str, Any] = {key: None for key in facts}
    evidence_hashes = {item["path"]: item["content_hash"] for item in data["indexed_hashes"]}
    for entry in data["index"]["evidence"]:
        path = entry["ref"]
        if not path.lower().endswith(".json"):
            continue
        try:
            candidate = load_json_file(root, Path(path))
        except EvolutionBlocked:
            continue
        if candidate.get("type") != "execution_attestation":
            continue
        if set(candidate) != {"schema_version", "type", "run_id", "recorded_by", "recorded_at", "actual_execution"} or candidate.get("schema_version") != 1 or candidate.get("run_id") != run_id or candidate.get("recorded_by") not in ROLES or not isinstance(candidate.get("recorded_at"), str) or not isinstance(candidate.get("actual_execution"), dict):
            raise _blocked("CORRUPT_ARTIFACT", f"Invalid execution attestation: {path}")
        require_utc_timestamp(candidate["recorded_at"], "Execution attestation recorded_at")
        values = candidate["actual_execution"]
        if not values or not set(values) <= set(facts):
            raise _blocked("CORRUPT_ARTIFACT", f"Execution attestation has invalid facts: {path}")
        for key, value in values.items():
            valid = False
            if key == "model":
                valid = isinstance(value, str) and len(value) <= 80 and bool(re.fullmatch(r"[A-Za-z0-9._:-]+", value)) and not any(pattern.search(value) for pattern in SENSITIVE)
            elif key == "reasoning":
                valid = value in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
            elif key == "quota":
                valid = value in {"economy", "balanced", "quality_first"}
            elif key == "agent_runtime":
                valid = value in {"STARTED", "COMPLETED", "FAILED", "INTERRUPTED"}
            elif key == "tokens":
                valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
            elif key == "cost":
                valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
            if not valid or (actual[key] != "UNAVAILABLE" and actual[key] != value):
                raise _blocked("CORRUPT_ARTIFACT", f"Invalid or conflicting execution attestation fact {key}: {path}")
            actual[key] = value
            refs[key] = {"path": path, "json_pointer": f"/actual_execution/{key}", "content_hash": evidence_hashes[path]}
    actual["attestation_refs"] = refs
    unknown_map = {"model": "actual_model", "reasoning": "reasoning", "tokens": "tokens", "cost": "cost", "quota": "quota", "agent_runtime": "agent_runtime"}
    unknowns = sorted([unknown_map[key] for key in facts if actual[key] == "UNAVAILABLE"] + ["product_quality", "agent_necessity"])
    return actual, unknowns


def validate_outcome(value: dict[str, Any]) -> None:
    keys = {"schema_version", "generator_version", "outcome_id", "fingerprint", "independence_key", "recorded_at", "project_fingerprint", "run_id", "source", "lifecycle", "completion", "counts", "planned_routing", "actual_execution", "categories", "unknowns"}
    require_exact_keys(value, keys, "Outcome")
    if value["schema_version"] != 1:
        raise _blocked("UNSUPPORTED_SCHEMA", "Unsupported Outcome schema")
    if not OUT_ID.fullmatch(str(value["outcome_id"])):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Outcome ID")
    for key in ("fingerprint", "independence_key", "project_fingerprint"):
        _check_hex(value[key], f"Outcome {key}")
    if value["outcome_id"] != deterministic_id("OUT", value["fingerprint"]):
        raise _blocked("CORRUPT_ARTIFACT", "Outcome ID does not match its fingerprint")
    require_utc_timestamp(value["recorded_at"], "Outcome recorded_at")
    source = _exact_object(value["source"], {"type", "run_fingerprint", "last_event_sequence"}, "Outcome source")
    _check_hex(source["run_fingerprint"], "Outcome source run_fingerprint")
    if not RUN_ID.fullmatch(str(value["run_id"])) or source["type"] != "structurally_validated_completed_run" or not isinstance(source["last_event_sequence"], int) or isinstance(source["last_event_sequence"], bool):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Outcome source")
    lifecycle = _exact_object(value["lifecycle"], {"start_state", "final_state"}, "Outcome lifecycle")
    completion = _exact_object(value["completion"], {"status", "qa_conclusion"}, "Outcome completion")
    if not all(isinstance(item, str) for item in lifecycle.values()) or completion["status"] != "DONE" or completion["qa_conclusion"] not in {"PASS", "PASS_WITH_ACCEPTED_RISKS"}:
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Outcome completion")
    count_keys = {"events", "tasks_started", "handoffs", "blocks", "rework", "artifacts", "evidence"}
    counts = _exact_object(value["counts"], count_keys, "Outcome counts")
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in counts.values()):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Outcome counts")
    planned = _exact_object(value["planned_routing"], {"roles", "models"}, "Outcome planned_routing")
    _string_list(planned["roles"], "Outcome planned roles")
    _string_list(planned["models"], "Outcome planned models")
    execution = _exact_object(value["actual_execution"], {"model", "reasoning", "tokens", "cost", "quota", "agent_runtime", "attestation_refs"}, "Outcome actual_execution")
    refs = _exact_object(execution["attestation_refs"], {"model", "reasoning", "tokens", "cost", "quota", "agent_runtime"}, "Outcome attestation_refs")
    if not isinstance(refs, dict):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Outcome execution attestations")
    for fact in ("model", "reasoning", "tokens", "cost", "quota", "agent_runtime"):
        reference = refs[fact]
        if execution[fact] == "UNAVAILABLE":
            if reference is not None:
                raise _blocked("CORRUPT_ARTIFACT", f"Unavailable Outcome fact has an attestation: {fact}")
        else:
            reference = _exact_object(reference, {"path", "json_pointer", "content_hash"}, f"Outcome {fact} attestation")
            if any(not isinstance(item, str) for item in reference.values()):
                raise _blocked("CORRUPT_ARTIFACT", f"Available Outcome fact has an invalid attestation: {fact}")
    _string_list(value["categories"], "Outcome categories")
    _string_list(value["unknowns"], "Outcome unknowns")
    if any(item not in CATEGORIES for item in value["categories"]):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Outcome categories")
    if sorted(set(value["categories"])) != value["categories"] or sorted(set(value["unknowns"])) != value["unknowns"] or any(item not in UNKNOWN_VALUES for item in value["unknowns"]):
        raise _blocked("CORRUPT_ARTIFACT", "Outcome categories or unknowns are not canonical")
    if value["independence_key"] != fingerprint({"project_fingerprint": value["project_fingerprint"], "run_id": value["run_id"]}):
        raise _blocked("CORRUPT_ARTIFACT", "Outcome independence key mismatch")


def _build_outcome(root: Path, manifest: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    run_id = data["run"]["run_id"]
    events, index = data["events"], data["index"]
    roles = sorted({role for item in data["routing"]["history"] for role in item.get("required_now", []) if isinstance(role, str)})
    counts = {
        "events": len(events),
        "tasks_started": sum(item.get("event_type") == "TASK_STARTED" for item in events),
        "handoffs": sum(item.get("event_type") == "HANDOFF_PERSISTED" for item in events),
        "blocks": sum(item.get("event_type") == "TASK_BLOCKED" or (item.get("event_type") == "GATE_DECISION" and item.get("conclusion") == "BLOCKED") for item in events),
        "rework": sum(item.get("conclusion") == "NEEDS_REVISION" or (item.get("stage_before") != item.get("stage_after") and (str(item.get("stage_before", "")).startswith("REWORK_") or str(item.get("stage_after", "")).startswith("REWORK_"))) for item in events),
        "artifacts": len({item["ref"] for item in index["artifacts"]}),
        "evidence": len({item["ref"] for item in index["evidence"]}),
    }
    actual, unknowns = _actual_execution(root, run_id, data)
    value = {
        "schema_version": 1, "generator_version": GENERATOR_VERSION,
        "outcome_id": deterministic_id("OUT", data["run_fingerprint"]),
        "fingerprint": data["run_fingerprint"],
        "independence_key": fingerprint({"project_fingerprint": manifest["project_fingerprint"], "run_id": run_id}),
        "recorded_at": data["run"]["updated_at"], "project_fingerprint": manifest["project_fingerprint"],
        "run_id": run_id,
        "source": {"type": "structurally_validated_completed_run", "run_fingerprint": data["run_fingerprint"], "last_event_sequence": len(events)},
        "lifecycle": {"start_state": data["run"]["start_state"], "final_state": "DONE"},
        "completion": {"status": "DONE", "qa_conclusion": data["qa_conclusion"]},
        "counts": counts, "planned_routing": {"roles": roles, "models": []},
        "actual_execution": actual, "categories": [], "unknowns": unknowns,
    }
    validate_outcome(value)
    return value


def validate_feedback(value: dict[str, Any]) -> None:
    keys = {"schema_version", "generator_version", "feedback_id", "fingerprint", "independence_key", "recorded_at", "project_fingerprint", "kind", "result", "severity", "category", "summary", "run_id", "task_id", "role", "evidence"}
    require_exact_keys(value, keys, "Feedback")
    if value["schema_version"] != 1:
        raise _blocked("UNSUPPORTED_SCHEMA", "Unsupported Feedback schema")
    if not FDB_ID.fullmatch(str(value["feedback_id"])):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Feedback ID")
    for key in ("fingerprint", "independence_key", "project_fingerprint"):
        _check_hex(value[key], f"Feedback {key}")
    if value["feedback_id"] != deterministic_id("FDB", value["fingerprint"]):
        raise _blocked("CORRUPT_ARTIFACT", "Feedback ID does not match its fingerprint")
    require_utc_timestamp(value["recorded_at"], "Feedback recorded_at")
    if value["kind"] not in KINDS or value["result"] not in RESULTS or value["severity"] not in SEVERITIES or value["category"] not in CATEGORIES:
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Feedback enum")
    try:
        _check_text(value["summary"], "Feedback summary", 500)
    except ValueError as exc:
        raise _blocked("CORRUPT_ARTIFACT", str(exc)) from exc
    if value["run_id"] is not None and not RUN_ID.fullmatch(str(value["run_id"])):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Feedback run ID")
    if value["task_id"] is not None and not TASK_ID.fullmatch(str(value["task_id"])):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Feedback task ID")
    if value["role"] is not None and value["role"] not in ROLES:
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Feedback role")
    if not isinstance(value["evidence"], list) or not value["evidence"]:
        raise _blocked("CORRUPT_ARTIFACT", "Feedback requires evidence")
    for item in value["evidence"]:
        if not isinstance(item, dict) or set(item) != {"path", "content_hash", "size_bytes"}:
            raise _blocked("CORRUPT_ARTIFACT", "Invalid Feedback evidence metadata")
        _check_hex(item.get("content_hash"), "Feedback evidence content_hash")
        if not isinstance(item.get("path"), str) or not isinstance(item.get("size_bytes"), int) or isinstance(item.get("size_bytes"), bool) or item["size_bytes"] < 0:
            raise _blocked("CORRUPT_ARTIFACT", "Invalid Feedback evidence values")
    if value["evidence"] != sorted(value["evidence"], key=lambda item: item["path"]) or len({item["path"] for item in value["evidence"]}) != len(value["evidence"]):
        raise _blocked("CORRUPT_ARTIFACT", "Feedback evidence is not sorted and unique")
    identity = {key: value[key] for key in keys - {"feedback_id", "fingerprint", "independence_key", "recorded_at"}}
    if value["fingerprint"] != fingerprint(identity):
        raise _blocked("CORRUPT_ARTIFACT", "Feedback fingerprint mismatch")
    expected_independence = fingerprint({"project_fingerprint": value["project_fingerprint"], "run_id": value["run_id"]}) if value["run_id"] else fingerprint(sorted(item["content_hash"] for item in value["evidence"]))
    if value["independence_key"] != expected_independence:
        raise _blocked("CORRUPT_ARTIFACT", "Feedback independence key mismatch")


def _load_ledgers(root: Path, manifest: dict[str, Any], *, validate_sources: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    workspace = evolution_root(root)
    outcomes = load_strict_jsonl(workspace / "outcomes.jsonl", validate_outcome, "Outcome")
    feedback = load_strict_jsonl(workspace / "feedback.jsonl", validate_feedback, "Feedback")
    expected = manifest["project_fingerprint"]
    if any(item["project_fingerprint"] != expected for item in outcomes + feedback):
        raise _blocked("CORRUPT_LEDGER", "Evolution ledger contains another project lineage")
    if validate_sources:
        for item in outcomes:
            try:
                current = _validate_run(root, item["run_id"])
            except EvolutionBlocked as exc:
                raise _blocked("CORRUPT_LEDGER", f"Outcome source run is no longer structurally valid: {item['outcome_id']}") from exc
            expected_outcome = _build_outcome(root, manifest, current)
            if expected_outcome != item:
                raise _blocked("CORRUPT_LEDGER", f"Outcome no longer exactly matches its six-file and attestation sources: {item['outcome_id']}")
    for item in feedback:
        total = 0
        for evidence in item["evidence"]:
            try:
                digest, size = stable_hash_file(root, evidence["path"], max_bytes=10 * 1024 * 1024)
            except (ValueError, EvolutionBlocked) as exc:
                raise _blocked("CORRUPT_LEDGER", f"Feedback evidence is no longer valid: {item['feedback_id']}") from exc
            total += size
            if digest != evidence["content_hash"] or size != evidence["size_bytes"] or total > 10 * 1024 * 1024:
                raise _blocked("CORRUPT_LEDGER", f"Feedback evidence fingerprint changed: {item['feedback_id']}")
        if item["run_id"]:
            try:
                run_data = _validate_run(root, item["run_id"])
            except EvolutionBlocked as exc:
                raise _blocked("CORRUPT_LEDGER", f"Feedback run lineage is no longer valid: {item['feedback_id']}") from exc
            if any(evidence["path"] not in run_data["indexed"] for evidence in item["evidence"]):
                raise _blocked("CORRUPT_LEDGER", f"Feedback evidence is outside its run index: {item['feedback_id']}")
            if item["role"] and not item["task_id"]:
                planned = {role for decision in run_data["routing"]["history"] for role in decision.get("required_now", []) if isinstance(role, str)}
                if item["role"] not in planned:
                    raise _blocked("CORRUPT_LEDGER", f"Feedback role is outside its run's planned-routing lineage: {item['feedback_id']}")
    return outcomes, feedback


def evolution_init(root: Path) -> dict[str, Any]:
    return initialize_workspace(root)


def collect(root: Path, run_id: str | None = None) -> dict[str, Any]:
    root = validate_project_root(root)
    manifest = load_manifest(root)
    require_git_safe(root)
    lock = evolution_root(root) / ".write-lock"
    with exclusive_lock(lock, "collect"):
        outcomes, _ = _load_ledgers(root, manifest, validate_sources=False)
        if run_id is None:
            valid = _valid_completed_runs(root)
            if not valid:
                raise _blocked("INSUFFICIENT_EVIDENCE", "No structurally validated completed run exists")
            if len(valid) > 1:
                raise _blocked("AMBIGUOUS_INPUT", "More than one completed run exists; supply --run-id", candidates=valid)
            run_id = valid[0]
        data = _validate_run(root, run_id)
        existing = [item for item in outcomes if item["run_id"] == run_id]
        if existing:
            expected = _build_outcome(root, manifest, data)
            if existing[0] == expected:
                return {"status": "EXISTING", "reason_code": "OK", "outcome_id": existing[0]["outcome_id"], "run_id": run_id}
            if existing[0]["fingerprint"] == data["run_fingerprint"]:
                raise _blocked("CORRUPT_LEDGER", "Stored Outcome differs from its authoritative sources", run_id=run_id)
            raise _blocked("BLOCKED_RUN_LINEAGE_DRIFT", "A collected run changed after its Outcome was recorded", run_id=run_id)
        value = _build_outcome(root, manifest, data)
        atomic_append_jsonl(evolution_root(root) / "outcomes.jsonl", [value])
        return {"status": "COLLECTED", "reason_code": "OK", "outcome_id": value["outcome_id"], "run_id": run_id, "fingerprint": value["fingerprint"]}


def feedback(root: Path, *, kind: str, result: str, severity: str, category: str, summary: str, evidence_paths: list[str], run_id: str | None = None, task_id: str | None = None, role: str | None = None) -> dict[str, Any]:
    root = validate_project_root(root)
    manifest = load_manifest(root)
    require_git_safe(root)
    if kind not in KINDS or result not in RESULTS or severity not in SEVERITIES or category not in CATEGORIES:
        raise ValueError("Feedback kind, result, severity, or category is invalid")
    _check_text(summary, "Feedback summary", 500)
    if not evidence_paths or len(evidence_paths) > 20:
        raise ValueError("Feedback requires 1-20 evidence paths")
    if task_id and not run_id:
        raise ValueError("--task-id requires --run-id")
    if role and role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    lock = evolution_root(root) / ".write-lock"
    with exclusive_lock(lock, "feedback"):
        _, records = _load_ledgers(root, manifest)
        run_data = _validate_run(root, run_id) if run_id else None
        evidence = sorted((_check_project_relative_evidence(root, path, max_bytes=10 * 1024 * 1024) for path in sorted(set(evidence_paths))), key=lambda item: item["path"])
        if sum(item["size_bytes"] for item in evidence) > 10 * 1024 * 1024:
            raise _blocked("RESOURCE_LIMIT_EXCEEDED", "Feedback evidence exceeds 10 MiB total")
        if run_data and any(item["path"] not in run_data["indexed"] for item in evidence):
            raise ValueError("Run-linked feedback evidence must already be in that run's evidence index")
        if task_id:
            if not TASK_ID.fullmatch(task_id):
                raise ValueError(f"Invalid task ID: {task_id}")
            if not any(entry.get("task_id") == task_id and entry.get("ref") in {item["path"] for item in evidence} for entry in run_data["indexed"].values()):
                raise ValueError("Task-linked feedback evidence does not match the run evidence index")
            task_path = root / "tasks" / f"{task_id}.yaml"
            if not task_path.is_file() or quoted_scalar(task_path.read_text(encoding="utf-8"), "run_id") != run_id or quoted_scalar(task_path.read_text(encoding="utf-8"), "task_id") != task_id:
                raise ValueError("Task Package lineage does not match feedback")
            owner = quoted_scalar(task_path.read_text(encoding="utf-8"), "owner")
            if role and role != owner:
                raise ValueError("Feedback role does not match Task Package owner")
        elif run_data and role:
            planned_roles = {planned for decision in run_data["routing"]["history"] for planned in decision.get("required_now", []) if isinstance(planned, str)}
            if role not in planned_roles:
                raise ValueError("Run-linked feedback role is not present in the run's validated planned-routing lineage")
        independence = fingerprint({"project_fingerprint": manifest["project_fingerprint"], "run_id": run_id}) if run_id else fingerprint(sorted(item["content_hash"] for item in evidence))
        identity = {
            "schema_version": 1, "generator_version": GENERATOR_VERSION,
            "project_fingerprint": manifest["project_fingerprint"], "kind": kind, "result": result,
            "severity": severity, "category": category, "summary": summary, "run_id": run_id,
            "task_id": task_id, "role": role, "evidence": evidence,
        }
        digest = fingerprint(identity)
        existing = next((item for item in records if item["fingerprint"] == digest), None)
        if existing:
            return {"status": "EXISTING", "reason_code": "OK", "feedback_id": existing["feedback_id"], "fingerprint": digest}
        value = {**identity, "feedback_id": deterministic_id("FDB", digest), "fingerprint": digest, "independence_key": independence, "recorded_at": utc_now()}
        validate_feedback(value)
        atomic_append_jsonl(evolution_root(root) / "feedback.jsonl", [value])
        return {"status": "RECORDED", "reason_code": "OK", "feedback_id": value["feedback_id"], "fingerprint": digest}


def _cluster_unlinked(records: list[dict[str, Any]]) -> dict[str, str]:
    parent: dict[str, str] = {}
    def find(item: str) -> str:
        parent.setdefault(item, item)
        if parent[item] != item:
            parent[item] = find(parent[item])
        return parent[item]
    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)
    hashes_by_id: dict[str, list[str]] = {}
    for record in records:
        hashes = sorted({item["content_hash"] for item in record["evidence"]})
        hashes_by_id[record["feedback_id"]] = hashes
        for item in hashes[1:]:
            union(hashes[0], item)
        if hashes:
            find(hashes[0])
    clusters: dict[str, list[str]] = defaultdict(list)
    for record_id, hashes in hashes_by_id.items():
        clusters[find(hashes[0])].append(record_id)
    result: dict[str, str] = {}
    for member_ids in clusters.values():
        key = fingerprint(sorted(member_ids))
        for record_id in member_ids:
            result[record_id] = key
    return result


def validate_retrospective(value: dict[str, Any]) -> None:
    keys = {"schema_version", "generator_version", "retrospective_id", "fingerprint", "input_fingerprint", "generated_at", "project_fingerprint", "run_scope", "source_records", "counts", "patterns", "unknowns", "candidate_eligibility"}
    require_exact_keys(value, keys, "Retrospective")
    if value["schema_version"] != 1:
        raise _blocked("UNSUPPORTED_SCHEMA", "Unsupported Retrospective schema")
    if not RETRO_ID.fullmatch(str(value["retrospective_id"])):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Retrospective ID")
    for key in ("fingerprint", "input_fingerprint", "project_fingerprint"):
        _check_hex(value[key], f"Retrospective {key}")
    if value["fingerprint"] != fingerprint({"input_fingerprint": value["input_fingerprint"], "run_scope": value["run_scope"], "policy_version": POLICY_VERSION}):
        raise _blocked("CORRUPT_ARTIFACT", "Retrospective fingerprint mismatch")
    if value["retrospective_id"] != deterministic_id("RET", value["fingerprint"]):
        raise _blocked("CORRUPT_ARTIFACT", "Retrospective ID mismatch")
    require_utc_timestamp(value["generated_at"], "Retrospective generated_at")
    if value["run_scope"] is not None and not RUN_ID.fullmatch(str(value["run_scope"])):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid retrospective run scope")
    if not isinstance(value["source_records"], list) or not value["source_records"]:
        raise _blocked("CORRUPT_ARTIFACT", "Retrospective requires source records")
    for item in value["source_records"]:
        if not isinstance(item, dict) or set(item) != {"type", "id", "fingerprint", "independence_key"} or item["type"] not in {"outcome", "feedback"}:
            raise _blocked("CORRUPT_ARTIFACT", "Invalid retrospective source record")
        expected_id = OUT_ID if item["type"] == "outcome" else FDB_ID
        if not isinstance(item["id"], str) or not expected_id.fullmatch(item["id"]):
            raise _blocked("CORRUPT_ARTIFACT", "Invalid retrospective source record ID")
        _check_hex(item["fingerprint"], "Retrospective source fingerprint")
        _check_hex(item["independence_key"], "Retrospective source independence key")
    expected_input = fingerprint(sorted({f"{item['id']}:{item['fingerprint']}" for item in value["source_records"]}))
    if value["input_fingerprint"] != expected_input:
        raise _blocked("CORRUPT_ARTIFACT", "Retrospective input fingerprint mismatch")
    expected_count_keys = {"total_records", "independent_records", "by_category", "by_result", "by_severity", "by_role", "by_run"}
    counts = _exact_object(value["counts"], expected_count_keys, "Retrospective counts")
    by_category = _exact_object(counts["by_category"], set(CATEGORIES), "Retrospective by_category")
    by_result = _exact_object(counts["by_result"], set(RESULTS), "Retrospective by_result")
    by_severity = _exact_object(counts["by_severity"], set(SEVERITIES), "Retrospective by_severity")
    by_role = _exact_object(counts["by_role"], set(ROLES + ["UNSPECIFIED"]), "Retrospective by_role")
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in [counts["total_records"], counts["independent_records"], *by_category.values(), *by_result.values(), *by_severity.values(), *by_role.values()]):
        raise _blocked("CORRUPT_ARTIFACT", "Retrospective count enums are incomplete")
    if not isinstance(counts["by_run"], list):
        raise _blocked("CORRUPT_ARTIFACT", "Retrospective by_run must be an array")
    for item in counts["by_run"]:
        run_count = _exact_object(item, {"run_id", "records", "independent_records"}, "Retrospective by_run entry")
        if not RUN_ID.fullmatch(str(run_count["run_id"])) or any(not isinstance(run_count[key], int) or isinstance(run_count[key], bool) or run_count[key] < 0 for key in ("records", "independent_records")):
            raise _blocked("CORRUPT_ARTIFACT", "Invalid Retrospective by_run entry")
    if not isinstance(value["patterns"], list):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid retrospective patterns")
    pattern_keys = {"category", "severity_max", "independence_keys", "record_ids", "evidence_count", "eligible", "threshold_reason"}
    for item in value["patterns"]:
        pattern = _exact_object(item, pattern_keys, "Retrospective pattern")
        _string_list(pattern["independence_keys"], "Retrospective pattern independence_keys")
        _string_list(pattern["record_ids"], "Retrospective pattern record_ids")
        if pattern["category"] not in CATEGORIES or pattern["severity_max"] not in SEVERITIES or pattern["threshold_reason"] not in {"P0_SINGLE", "SECURITY_PRIVACY_SINGLE", "THREE_INDEPENDENT", "INSUFFICIENT"} or not isinstance(pattern["eligible"], bool) or not isinstance(pattern["evidence_count"], int) or isinstance(pattern["evidence_count"], bool):
            raise _blocked("CORRUPT_ARTIFACT", "Invalid retrospective pattern")
    eligibility = _exact_object(value["candidate_eligibility"], {"eligible_categories", "insufficient_categories", "threshold_policy"}, "Retrospective candidate_eligibility")
    _string_list(eligibility["eligible_categories"], "Retrospective eligible_categories")
    _string_list(eligibility["insufficient_categories"], "Retrospective insufficient_categories")
    if eligibility["threshold_policy"] != POLICY_VERSION:
        raise _blocked("CORRUPT_ARTIFACT", "Invalid retrospective candidate eligibility")


def _build_retrospective(manifest: dict[str, Any], outcomes: list[dict[str, Any]], feedback_records: list[dict[str, Any]], run_id: str | None) -> dict[str, Any]:
    records = [("outcome", item) for item in outcomes] + [("feedback", item) for item in feedback_records]
    if not records:
        raise _blocked("INSUFFICIENT_EVIDENCE", "No validated Evolution records match the retrospective scope")
    cluster_keys = _cluster_unlinked([item for item in feedback_records if item["run_id"] is None])
    source_records, normalized_keys = [], {}
    for record_type, record in records:
        record_id = record.get("outcome_id") or record.get("feedback_id")
        independence = cluster_keys.get(record_id, record["independence_key"])
        normalized_keys[record_id] = independence
        source_records.append({"type": record_type, "id": record_id, "fingerprint": record["fingerprint"], "independence_key": independence})
    source_records.sort(key=lambda item: (item["type"], item["id"]))
    input_fp = fingerprint(sorted({f"{item['id']}:{item['fingerprint']}" for item in source_records}))
    retro_fp = fingerprint({"input_fingerprint": input_fp, "run_scope": run_id, "policy_version": POLICY_VERSION})
    counts_by_category = Counter(item["category"] for item in feedback_records)
    counts_by_result = Counter(item["result"] for item in feedback_records)
    counts_by_severity = Counter(item["severity"] for item in feedback_records)
    counts_by_role = Counter(item["role"] or "UNSPECIFIED" for item in feedback_records)
    by_run = []
    for selected in sorted({item["run_id"] for item in outcomes + feedback_records if item["run_id"]}):
        matching = [item for item in outcomes + feedback_records if item["run_id"] == selected]
        by_run.append({"run_id": selected, "records": len(matching), "independent_records": len({item["independence_key"] for item in matching})})
    patterns = []
    for category in CATEGORIES:
        matching = [item for item in feedback_records if item["category"] == category]
        if not matching:
            continue
        independence = sorted({normalized_keys[item["feedback_id"]] for item in matching})
        severity_max = min((item["severity"] for item in matching), key=SEVERITIES.index)
        if any(item["severity"] == "P0" for item in matching):
            reason = "P0_SINGLE"
        elif any(item["kind"] == "security_or_privacy" for item in matching):
            reason = "SECURITY_PRIVACY_SINGLE"
        elif len(independence) >= 3:
            reason = "THREE_INDEPENDENT"
        else:
            reason = "INSUFFICIENT"
        patterns.append({"category": category, "severity_max": severity_max, "independence_keys": independence, "record_ids": sorted(item["feedback_id"] for item in matching), "evidence_count": len(independence), "eligible": reason != "INSUFFICIENT", "threshold_reason": reason})
    eligible = sorted(item["category"] for item in patterns if item["eligible"])
    insufficient = sorted(item["category"] for item in patterns if not item["eligible"])
    value = {
        "schema_version": 1, "generator_version": GENERATOR_VERSION,
        "retrospective_id": deterministic_id("RET", retro_fp), "fingerprint": retro_fp,
        "input_fingerprint": input_fp, "generated_at": max(str(item["recorded_at"]) for _, item in records),
        "project_fingerprint": manifest["project_fingerprint"], "run_scope": run_id,
        "source_records": source_records,
        "counts": {
            "total_records": len(records), "independent_records": len({item["independence_key"] for item in source_records}),
            "by_category": {key: counts_by_category[key] for key in CATEGORIES},
            "by_result": {key: counts_by_result[key] for key in RESULTS},
            "by_severity": {key: counts_by_severity[key] for key in SEVERITIES},
            "by_role": {key: counts_by_role[key] for key in ROLES + ["UNSPECIFIED"]}, "by_run": by_run,
        },
        "patterns": patterns, "unknowns": sorted({unknown for item in outcomes for unknown in item["unknowns"]}),
        "candidate_eligibility": {"eligible_categories": eligible, "insufficient_categories": insufficient, "threshold_policy": POLICY_VERSION},
    }
    validate_retrospective(value)
    return value


def retrospect(root: Path, run_id: str | None = None) -> dict[str, Any]:
    root = validate_project_root(root)
    manifest = load_manifest(root)
    require_git_safe(root)
    lock = evolution_root(root) / ".write-lock"
    with exclusive_lock(lock, "retrospect"):
        outcomes, feedback_records = _load_ledgers(root, manifest)
        if run_id:
            if not RUN_ID.fullmatch(run_id):
                raise ValueError(f"Invalid run ID: {run_id}")
            outcomes = [item for item in outcomes if item["run_id"] == run_id]
            feedback_records = [item for item in feedback_records if item["run_id"] == run_id]
        value = _build_retrospective(manifest, outcomes, feedback_records, run_id)
        retro_id = value["retrospective_id"]
        destination = evolution_root(root) / "retrospectives" / f"{retro_id}.json"
        if destination.exists():
            existing = _load_direct_artifact(root, "retrospectives", destination.name, validate_retrospective, "retrospective_id")
            return {"status": "EXISTING", "reason_code": "OK", "retrospective_id": existing["retrospective_id"], "fingerprint": existing["fingerprint"]}
        atomic_json(destination, value)
        return {"status": "GENERATED", "reason_code": "OK", "retrospective_id": retro_id, "fingerprint": value["fingerprint"], "eligible_categories": value["candidate_eligibility"]["eligible_categories"]}


def _load_direct_artifact(root: Path, directory: str, supplied: str, validator: Any, id_key: str) -> dict[str, Any]:
    raw = Path(supplied)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("Artifact selector must be a direct project-relative workspace file")
    if len(raw.parts) == 1:
        relative = evolution_rel(root) / directory / raw
    elif raw.parent in {evolution_rel(root) / directory, EVOLUTION_REL / directory, Path(".codex/evolution") / directory}:
        relative = evolution_rel(root) / directory / raw.name
    else:
        raise ValueError("Artifact selector must be directly inside its Evolution directory")
    if relative.suffix != ".json":
        raise ValueError("Artifact selector must name a JSON file")
    value = load_json_file(root, relative)
    validator(value)
    if relative.stem != value[id_key]:
        raise _blocked("CORRUPT_ARTIFACT", "Artifact filename and internal ID differ")
    manifest = load_manifest(root)
    if value["project_fingerprint"] != manifest["project_fingerprint"]:
        raise _blocked("CORRUPT_ARTIFACT", "Artifact project lineage mismatch")
    if directory == "retrospectives":
        outcomes, feedback_records = _load_ledgers(root, manifest)
        records = {item.get("outcome_id") or item.get("feedback_id"): item for item in outcomes + feedback_records}
        selected_outcomes, selected_feedback = [], []
        for source in value["source_records"]:
            actual = records.get(source["id"])
            if actual is None or actual["fingerprint"] != source["fingerprint"]:
                raise _blocked("CORRUPT_ARTIFACT", "Retrospective source lineage is missing or changed")
            (selected_outcomes if source["type"] == "outcome" else selected_feedback).append(actual)
        if value["run_scope"] is not None and any(item["run_id"] != value["run_scope"] for item in selected_outcomes + selected_feedback):
            raise _blocked("CORRUPT_ARTIFACT", "Retrospective source is outside its run scope")
        expected = _build_retrospective(manifest, selected_outcomes, selected_feedback, value["run_scope"])
        if expected != value:
            raise _blocked("CORRUPT_ARTIFACT", "Retrospective derived content differs from its authoritative ledger sources")
    elif directory == "candidates":
        source = value["source_retrospective"]
        retrospective = _load_direct_artifact(root, "retrospectives", f"{source['id']}.json", validate_retrospective, "retrospective_id")
        if retrospective["fingerprint"] != source["fingerprint"]:
            raise _blocked("CORRUPT_ARTIFACT", "Proposal source lineage is missing or changed")
        outcomes, feedback_records = _load_ledgers(root, manifest)
        all_records = {item.get("outcome_id") or item.get("feedback_id"): item for item in outcomes + feedback_records}
        pattern = next((item for item in retrospective["patterns"] if item["category"] == value["category"] and item["eligible"]), None)
        if pattern is None or _build_proposal(manifest, retrospective, pattern, all_records) != value:
            raise _blocked("CORRUPT_ARTIFACT", "Proposal differs from its authoritative retrospective and ledger sources")
    elif directory == "eval-candidates":
        source = value["source_proposal"]
        proposal = _load_direct_artifact(root, "candidates", f"{source['id']}.json", validate_proposal, "proposal_id")
        if proposal["fingerprint"] != source["fingerprint"]:
            raise _blocked("CORRUPT_ARTIFACT", "Eval candidate source lineage is missing or changed")
        if _build_eval_candidate(manifest, proposal) != value:
            raise _blocked("CORRUPT_ARTIFACT", "Eval candidate differs from its authoritative Proposal source")
    return value


def _select_artifact(root: Path, directory: str, supplied: str | None, validator: Any, id_key: str) -> dict[str, Any]:
    if supplied:
        return _load_direct_artifact(root, directory, supplied, validator, id_key)
    path = evolution_root(root) / directory
    candidates: list[str] = []
    for item in path.iterdir():
        if item.suffix != ".json":
            continue
        info = os.lstat(item)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _blocked("CORRUPT_ARTIFACT", f"Persisted {directory} JSON artifact is not an ordinary singly-linked file: {item.name}")
        candidates.append(item.name)
    candidates.sort()
    valid = [_load_direct_artifact(root, directory, name, validator, id_key) for name in candidates]
    if not valid:
        raise _blocked("INSUFFICIENT_EVIDENCE", f"No valid {directory} artifact exists")
    if len(valid) > 1:
        raise _blocked("AMBIGUOUS_INPUT", f"Multiple {directory} artifacts exist; supply an explicit selector", candidates=candidates)
    return valid[0]


def validate_proposal(value: dict[str, Any]) -> None:
    keys = {"schema_version", "generator_version", "proposal_id", "fingerprint", "policy_version", "generated_at", "project_fingerprint", "source_retrospective", "artifact_status", "review_status", "category", "priority", "title", "rationale_template", "falsifier", "independence_keys", "record_ids", "evidence_refs", "target", "expected_benefit", "possible_harm", "rollback_strategy", "required_evaluation", "protected_invariants", "forbidden_changes", "authority"}
    require_exact_keys(value, keys, "Proposal")
    if value["schema_version"] != 1 or value["policy_version"] != POLICY_VERSION:
        raise _blocked("UNSUPPORTED_SCHEMA", "Unsupported Proposal schema or policy")
    if not PROPOSAL_ID.fullmatch(str(value["proposal_id"])) or value["artifact_status"] != "DRAFT" or value["review_status"] != "REVIEW_REQUIRED":
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Proposal status or ID")
    require_utc_timestamp(value["generated_at"], "Proposal generated_at")
    _check_hex(value["fingerprint"], "Proposal fingerprint")
    _check_hex(value["project_fingerprint"], "Proposal project fingerprint")
    _string_list(value["protected_invariants"], "Proposal protected_invariants")
    _string_list(value["forbidden_changes"], "Proposal forbidden_changes")
    authority = _exact_object(value["authority"], {"auto_apply", "commit", "push", "merge", "release"}, "Proposal authority")
    if value["protected_invariants"] != PROTECTED_INVARIANTS or value["forbidden_changes"] != FORBIDDEN_CHANGES or authority != {"auto_apply": False, "commit": False, "push": False, "merge": False, "release": False}:
        raise _blocked("CORRUPT_ARTIFACT", "Proposal weakens protected authority or invariants")
    source = _exact_object(value["source_retrospective"], {"id", "fingerprint"}, "Proposal source_retrospective")
    _check_hex(source["fingerprint"], "Proposal source retrospective fingerprint")
    if not isinstance(value["category"], str) or value["category"] not in CATEGORIES or not isinstance(value["target"], str):
        raise _blocked("CORRUPT_ARTIFACT", "Proposal category and target must be strings")
    expected = fingerprint({"retrospective_fingerprint": source["fingerprint"], "category": value["category"], "target": value["target"], "policy_version": POLICY_VERSION})
    if value["fingerprint"] != expected or value["proposal_id"] != deterministic_id("PRP", expected):
        raise _blocked("CORRUPT_ARTIFACT", "Proposal fingerprint mismatch")
    if not RETRO_ID.fullmatch(str(source["id"])):
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Proposal source")
    if value["category"] not in CATEGORIES or value["target"] != TARGETS[value["category"]] or value["priority"] not in {"HIGH", "NORMAL"}:
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Proposal routing")
    if value["title"] != f"Review a bounded improvement for {value['category']}" or any(value[key] != expected_text for key, expected_text in PROPOSAL_TEXT.items()):
        raise _blocked("CORRUPT_ARTIFACT", "Proposal controlled text was modified")
    for key in ("title", "rationale_template", "falsifier", "expected_benefit", "possible_harm", "rollback_strategy", "required_evaluation"):
        try:
            _check_text(value[key], f"Proposal {key}", 500)
        except ValueError as exc:
            raise _blocked("CORRUPT_ARTIFACT", str(exc)) from exc
    for key in ("independence_keys", "record_ids", "evidence_refs"):
        _string_list(value[key], f"Proposal {key}", non_empty=True)
        if value[key] != sorted(set(value[key])):
            raise _blocked("CORRUPT_ARTIFACT", f"Proposal {key} must be sorted, unique and non-empty")


def _build_proposal(manifest: dict[str, Any], retro: dict[str, Any], pattern: dict[str, Any], all_records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    category, target = pattern["category"], TARGETS[pattern["category"]]
    digest = fingerprint({"retrospective_fingerprint": retro["fingerprint"], "category": category, "target": target, "policy_version": POLICY_VERSION})
    try:
        evidence_refs = sorted({evidence["path"] for record_id in pattern["record_ids"] for evidence in all_records[record_id].get("evidence", [])})
    except KeyError as exc:
        raise _blocked("CORRUPT_ARTIFACT", "Proposal pattern references a missing ledger record") from exc
    value = {
        "schema_version": 1, "generator_version": GENERATOR_VERSION,
        "proposal_id": deterministic_id("PRP", digest), "fingerprint": digest,
        "policy_version": POLICY_VERSION, "generated_at": retro["generated_at"],
        "project_fingerprint": manifest["project_fingerprint"],
        "source_retrospective": {"id": retro["retrospective_id"], "fingerprint": retro["fingerprint"]},
        "artifact_status": "DRAFT", "review_status": "REVIEW_REQUIRED", "category": category,
        "priority": "HIGH" if pattern["threshold_reason"] in {"P0_SINGLE", "SECURITY_PRIVACY_SINGLE"} else "NORMAL",
        "title": f"Review a bounded improvement for {category}", "rationale_template": PROPOSAL_TEXT["rationale_template"],
        "falsifier": PROPOSAL_TEXT["falsifier"], "independence_keys": pattern["independence_keys"],
        "record_ids": pattern["record_ids"], "evidence_refs": evidence_refs, "target": target,
        "expected_benefit": PROPOSAL_TEXT["expected_benefit"], "possible_harm": PROPOSAL_TEXT["possible_harm"],
        "rollback_strategy": PROPOSAL_TEXT["rollback_strategy"], "required_evaluation": PROPOSAL_TEXT["required_evaluation"],
        "protected_invariants": PROTECTED_INVARIANTS, "forbidden_changes": FORBIDDEN_CHANGES,
        "authority": {"auto_apply": False, "commit": False, "push": False, "merge": False, "release": False},
    }
    validate_proposal(value)
    return value


def propose(root: Path, retrospective: str | None = None) -> dict[str, Any]:
    root = validate_project_root(root)
    manifest = load_manifest(root)
    require_git_safe(root)
    lock = evolution_root(root) / ".write-lock"
    with exclusive_lock(lock, "propose"):
        retro = _select_artifact(root, "retrospectives", retrospective, validate_retrospective, "retrospective_id")
        outcomes, feedback_records = _load_ledgers(root, manifest)
        all_records = {item.get("outcome_id") or item.get("feedback_id"): item for item in outcomes + feedback_records}
        eligible = [item for item in retro["patterns"] if item["eligible"]]
        if not eligible:
            raise _blocked("INSUFFICIENT_EVIDENCE", "Retrospective has no evidence-eligible category")
        created, existing = [], []
        for pattern in eligible:
            value = _build_proposal(manifest, retro, pattern, all_records)
            proposal_id = value["proposal_id"]
            destination = evolution_root(root) / "candidates" / f"{proposal_id}.json"
            if destination.exists():
                found = _load_direct_artifact(root, "candidates", destination.name, validate_proposal, "proposal_id")
                if found != value:
                    raise _blocked("CORRUPT_ARTIFACT", f"Existing Proposal differs from deterministic content: {proposal_id}")
                existing.append(proposal_id)
            else:
                atomic_json(destination, value)
                created.append(proposal_id)
        return {"status": "GENERATED" if created else "EXISTING", "reason_code": "OK", "retrospective_id": retro["retrospective_id"], "created": sorted(created), "existing": sorted(existing)}


PROMOTION = "Independent reviewer must manually validate and copy this case into a formal suite; this artifact performs no promotion."


def validate_eval_candidate(value: dict[str, Any]) -> None:
    keys = {"schema_version", "generator_version", "eval_candidate_id", "fingerprint", "policy_version", "generated_at", "project_fingerprint", "source_proposal", "artifact_status", "review_status", "scenario", "prevented_failure", "acceptance_intent", "suggested_eval_kind", "fixture_requirements", "expected_invariant", "falsifier", "reviewer_checklist", "promotion_instructions"}
    require_exact_keys(value, keys, "Eval candidate")
    if value["schema_version"] != 1 or value["policy_version"] != POLICY_VERSION:
        raise _blocked("UNSUPPORTED_SCHEMA", "Unsupported Eval candidate schema or policy")
    if not EVAL_ID.fullmatch(str(value["eval_candidate_id"])) or value["artifact_status"] != "DRAFT" or value["review_status"] != "REVIEW_REQUIRED" or value["promotion_instructions"] != PROMOTION:
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Eval candidate status or ID")
    require_utc_timestamp(value["generated_at"], "Eval candidate generated_at")
    source = _exact_object(value["source_proposal"], {"id", "fingerprint"}, "Eval candidate source_proposal")
    _check_hex(source["fingerprint"], "Eval candidate source proposal fingerprint")
    if not isinstance(value["suggested_eval_kind"], str):
        raise _blocked("CORRUPT_ARTIFACT", "Eval candidate kind must be a string")
    expected = fingerprint({"proposal_fingerprint": source["fingerprint"], "policy_version": POLICY_VERSION})
    if value["fingerprint"] != expected or value["eval_candidate_id"] != deterministic_id("EVC", expected):
        raise _blocked("CORRUPT_ARTIFACT", "Eval candidate fingerprint mismatch")
    if not PROPOSAL_ID.fullmatch(str(source["id"])) or value["suggested_eval_kind"] not in {"deterministic", "semantic_review"}:
        raise _blocked("CORRUPT_ARTIFACT", "Invalid Eval candidate source or kind")
    for key in ("scenario", "prevented_failure", "acceptance_intent", "expected_invariant", "falsifier"):
        try:
            _check_text(value[key], f"Eval candidate {key}", 500)
        except ValueError as exc:
            raise _blocked("CORRUPT_ARTIFACT", str(exc)) from exc
    for key in ("fixture_requirements", "reviewer_checklist"):
        _string_list(value[key], f"Eval candidate {key}", non_empty=True)
        if value[key] != sorted(set(value[key])):
            raise _blocked("CORRUPT_ARTIFACT", f"Eval candidate {key} must be sorted, unique and non-empty")


def _build_eval_candidate(manifest: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    digest = fingerprint({"proposal_fingerprint": selected["fingerprint"], "policy_version": POLICY_VERSION})
    value = {
        "schema_version": 1, "generator_version": GENERATOR_VERSION,
        "eval_candidate_id": deterministic_id("EVC", digest), "fingerprint": digest,
        "policy_version": POLICY_VERSION, "generated_at": selected["generated_at"],
        "project_fingerprint": manifest["project_fingerprint"],
        "source_proposal": {"id": selected["proposal_id"], "fingerprint": selected["fingerprint"]},
        "artifact_status": "DRAFT", "review_status": "REVIEW_REQUIRED",
        "scenario": "Exercise the bounded category-level failure represented by the reviewed proposal.",
        "prevented_failure": "The same evidence-backed failure class recurs without detection.",
        "acceptance_intent": "Detect the failure while preserving every protected invariant and existing formal expectation.",
        "suggested_eval_kind": "deterministic" if selected["target"] in {"role_routing", "model_routing", "checklist", "recovery", "capability_policy"} else "semantic_review",
        "fixture_requirements": ["A negative case that reproduces the bounded failure", "A sanitized fixture with no customer data or credentials"],
        "expected_invariant": "No candidate may weaken authorization, QA separation, stage gates, acceptance, release gates, or formal evals.",
        "falsifier": "Reject if the case cannot distinguish the target failure from compliant behavior.",
        "reviewer_checklist": ["Confirm fixture provenance and sanitization", "Confirm no formal suite was changed", "Confirm protected invariants remain stronger or equal"],
        "promotion_instructions": PROMOTION,
    }
    validate_eval_candidate(value)
    return value


def eval_candidates(root: Path, proposal: str | None = None) -> dict[str, Any]:
    root = validate_project_root(root)
    manifest = load_manifest(root)
    require_git_safe(root)
    lock = evolution_root(root) / ".write-lock"
    with exclusive_lock(lock, "eval-candidates"):
        selected = _select_artifact(root, "candidates", proposal, validate_proposal, "proposal_id")
        value = _build_eval_candidate(manifest, selected)
        candidate_id = value["eval_candidate_id"]
        destination = evolution_root(root) / "eval-candidates" / f"{candidate_id}.json"
        if destination.exists():
            found = _load_direct_artifact(root, "eval-candidates", destination.name, validate_eval_candidate, "eval_candidate_id")
            if found != value:
                raise _blocked("CORRUPT_ARTIFACT", "Existing Eval candidate differs from deterministic content")
            status = "EXISTING"
        else:
            atomic_json(destination, value)
            status = "GENERATED"
        return {"status": status, "reason_code": "OK", "eval_candidate_id": candidate_id, "proposal_id": selected["proposal_id"], "artifact_status": "DRAFT", "review_status": "REVIEW_REQUIRED"}


def status(root: Path) -> dict[str, Any]:
    root = validate_project_root(root)
    exposure = git_exposure(root)
    workspace = evolution_root(root)
    if (workspace.parent / ".evolution-init-lock").exists():
        return {"status": "BLOCKED", "reason_code": "BLOCKED_LOCKED", "message": "Evolution initialization lock exists", "schema_version": "UNAVAILABLE", "policy_version": "UNAVAILABLE", "counts": "UNAVAILABLE", "latest_ids": "UNAVAILABLE", **exposure, "next_safe_action": "Verify the recorded process is inactive before explicitly removing only the stale initialization lock."}
    if not workspace.exists():
        return {"status": "NOT_INITIALIZED", "reason_code": "NOT_INITIALIZED", "schema_version": "UNAVAILABLE", "policy_version": "UNAVAILABLE", "counts": "UNAVAILABLE", "latest_ids": "UNAVAILABLE", **exposure, "next_safe_action": "Run evolution init explicitly."}
    try:
        manifest = load_manifest(root)
        if (workspace / ".write-lock").exists():
            raise _blocked("BLOCKED_LOCKED", "Evolution write lock exists")
        outcomes, feedback_records = _load_ledgers(root, manifest)
        artifact_specs = [
            ("retrospectives", validate_retrospective, "retrospective_id"),
            ("candidates", validate_proposal, "proposal_id"),
            ("eval-candidates", validate_eval_candidate, "eval_candidate_id"),
        ]
        artifacts: dict[str, list[dict[str, Any]]] = {}
        for directory, validator, id_key in artifact_specs:
            names: list[str] = []
            for item in (workspace / directory).iterdir():
                if item.suffix != ".json":
                    continue
                info = os.lstat(item)
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise _blocked("CORRUPT_ARTIFACT", f"Persisted {directory} JSON artifact is not an ordinary singly-linked file: {item.name}")
                names.append(item.name)
            names.sort()
            artifacts[directory] = [_load_direct_artifact(root, directory, name, validator, id_key) for name in names]
        counts = {"outcomes": len(outcomes), "feedback": len(feedback_records), "retrospectives": len(artifacts["retrospectives"]), "proposals": len(artifacts["candidates"]), "eval_candidates": len(artifacts["eval-candidates"])}
        latest = {
            "outcome": max((item["outcome_id"] for item in outcomes), default=None),
            "feedback": max((item["feedback_id"] for item in feedback_records), default=None),
            "retrospective": max((item["retrospective_id"] for item in artifacts["retrospectives"]), default=None),
            "proposal": max((item["proposal_id"] for item in artifacts["candidates"]), default=None),
            "eval_candidate": max((item["eval_candidate_id"] for item in artifacts["eval-candidates"]), default=None),
        }
        next_action = "Resolve Git exposure before any Evolution write." if exposure["git_reason_code"] != "OK" else "Collect a completed run or record sanitized feedback."
        return {"status": "READY", "reason_code": "OK", "schema_version": manifest["schema_version"], "policy_version": manifest["policy_version"], "project_fingerprint": manifest["project_fingerprint"], "counts": counts, "latest_ids": latest, **exposure, "next_safe_action": next_action}
    except EvolutionBlocked as exc:
        return {"status": "BLOCKED", "reason_code": exc.reason_code, "message": exc.message, "schema_version": "UNAVAILABLE", "policy_version": "UNAVAILABLE", "counts": "UNAVAILABLE", "latest_ids": "UNAVAILABLE", **exposure, "next_safe_action": "Back up the workspace and repair or explicitly recover the reported local state."}
    except (TypeError, KeyError, ValueError, OSError) as exc:
        return {"status": "BLOCKED", "reason_code": "CORRUPT_ARTIFACT", "message": f"Persisted Evolution artifact is invalid: {exc}", "schema_version": "UNAVAILABLE", "policy_version": "UNAVAILABLE", "counts": "UNAVAILABLE", "latest_ids": "UNAVAILABLE", **exposure, "next_safe_action": "Back up the workspace and repair or explicitly recover the reported local state."}
