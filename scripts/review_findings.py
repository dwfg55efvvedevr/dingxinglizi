#!/usr/bin/env python3
"""Strict finding validation and conservative, evidence-preserving merge rules."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


FINDING_ID = re.compile(r"^FIND-[A-Z0-9][A-Z0-9_-]{2,63}$")
SHARD_ID = re.compile(r"^SHARD-\d{4}$")
SEVERITIES = {"P0", "P1", "P2", "P3"}
STATUSES = {"OPEN", "ACCEPTED_RISK", "NOT_REPRODUCIBLE", "RESOLVED"}
REQUIRED_FIELDS = {
    "finding_id", "shard_id", "target_fingerprint", "path", "start_line", "end_line",
    "severity", "category", "title", "description", "evidence", "recommendation", "status",
}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or any(char in value for char in ("\x00", "\r", "\n")):
        raise ValueError("Finding path must be a non-empty project-relative string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("./"):
        raise ValueError(f"Finding path is unsafe: {value}")
    return path.as_posix()


def validate_finding(
    value: dict[str, Any],
    *,
    shard: dict[str, Any],
    target_fingerprint: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Finding must be a JSON object")
    missing = sorted(REQUIRED_FIELDS - set(value))
    unknown = sorted(set(value) - REQUIRED_FIELDS - {"rule_id", "confidence", "references"})
    if missing:
        raise ValueError("Finding is missing required fields: " + ", ".join(missing))
    if unknown:
        raise ValueError("Finding has unknown fields: " + ", ".join(unknown))
    finding_id = str(value["finding_id"])
    if not FINDING_ID.fullmatch(finding_id):
        raise ValueError(f"Invalid finding_id: {finding_id}")
    shard_id = str(value["shard_id"])
    if shard_id != shard.get("shard_id") or not SHARD_ID.fullmatch(shard_id):
        raise ValueError("Finding shard lineage does not match the ingested shard")
    if value["target_fingerprint"] != target_fingerprint:
        raise ValueError("Finding target fingerprint does not match the review target")
    path = _safe_relative_path(value["path"])
    if path not in set(shard.get("files", [])):
        raise ValueError(f"Finding path is outside shard scope: {path}")
    start = value["start_line"]
    end = value["end_line"]
    if isinstance(start, bool) or not isinstance(start, int) or start < 1:
        raise ValueError("Finding start_line must be a positive integer")
    if isinstance(end, bool) or not isinstance(end, int) or end < start:
        raise ValueError("Finding end_line must be an integer not less than start_line")
    if value["severity"] not in SEVERITIES:
        raise ValueError("Finding severity must be one of P0, P1, P2, P3")
    if value["status"] not in STATUSES:
        raise ValueError("Finding status is invalid")
    normalized = dict(value)
    normalized["path"] = path
    for key in ("category", "title", "description", "evidence", "recommendation"):
        if not isinstance(normalized[key], str) or not normalized[key].strip():
            raise ValueError(f"Finding {key} must be a non-empty string")
        normalized[key] = normalized[key].strip()
    if len(normalized["title"]) > 500:
        raise ValueError("Finding title must be 500 characters or fewer")
    for key in ("category", "description", "evidence", "recommendation"):
        if len(normalized[key]) > 20_000:
            raise ValueError(f"Finding {key} exceeds the 20000-character limit")
    if "rule_id" in normalized and (
        not isinstance(normalized["rule_id"], str) or not normalized["rule_id"].strip()
    ):
        raise ValueError("Finding rule_id must be a non-empty string when present")
    if "confidence" in normalized and normalized["confidence"] not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Finding confidence must be LOW, MEDIUM, or HIGH")
    if "references" in normalized:
        if not isinstance(normalized["references"], list) or not all(
            isinstance(item, str) and item.strip() for item in normalized["references"]
        ):
            raise ValueError("Finding references must be a list of non-empty strings")
        if len(normalized["references"]) > 200 or any(len(item) > 2000 for item in normalized["references"]):
            raise ValueError("Finding references exceed count or length limits")
        normalized["references"] = sorted(set(normalized["references"]))
    normalized["exact_identity"] = finding_identity(normalized, include_severity=True)
    normalized["issue_identity"] = finding_identity(normalized, include_severity=False)
    return normalized


def finding_identity(value: dict[str, Any], *, include_severity: bool) -> str:
    identity = {
        "target_fingerprint": value.get("target_fingerprint"),
        "path": value.get("path"),
        "start_line": value.get("start_line"),
        "end_line": value.get("end_line"),
        "category": str(value.get("category", "")).strip().casefold(),
        "rule_id": str(value.get("rule_id", "")).strip().casefold(),
        "title": " ".join(str(value.get("title", "")).strip().casefold().split()),
        "description": " ".join(str(value.get("description", "")).strip().casefold().split()),
        "evidence": " ".join(str(value.get("evidence", "")).strip().casefold().split()),
    }
    if include_severity:
        identity["severity"] = value.get("severity")
    return _canonical_hash(identity)


def merge_findings(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge only exact duplicates; preserve ambiguous and severity-conflicting reports."""
    exact: dict[str, dict[str, Any]] = {}
    duplicate_groups: dict[str, list[str]] = {}
    for finding in sorted(findings, key=lambda item: str(item.get("finding_id", ""))):
        fingerprint = str(finding.get("exact_identity") or finding_identity(finding, include_severity=True))
        if fingerprint not in exact:
            item = dict(finding)
            item["exact_identity"] = fingerprint
            item["issue_identity"] = str(item.get("issue_identity") or finding_identity(item, include_severity=False))
            item["source_finding_ids"] = [str(item["finding_id"])]
            item["source_shard_ids"] = [str(item["shard_id"])]
            exact[fingerprint] = item
        else:
            kept = exact[fingerprint]
            kept["source_finding_ids"] = sorted(set(kept["source_finding_ids"]) | {str(finding["finding_id"])})
            kept["source_shard_ids"] = sorted(set(kept["source_shard_ids"]) | {str(finding["shard_id"])})
            duplicate_groups[fingerprint] = list(kept["source_finding_ids"])

    merged = sorted(exact.values(), key=lambda item: (item["path"], item["start_line"], item["finding_id"]))
    conflicts: list[dict[str, Any]] = []
    by_issue: dict[str, list[dict[str, Any]]] = {}
    for finding in merged:
        by_issue.setdefault(str(finding["issue_identity"]), []).append(finding)
    for identity, group in sorted(by_issue.items()):
        severities = sorted({str(item["severity"]) for item in group})
        if len(severities) > 1:
            conflict_id = "CONFLICT-" + identity[:12].upper()
            for item in group:
                item["severity_conflict_id"] = conflict_id
            conflicts.append({
                "conflict_id": conflict_id,
                "kind": "SEVERITY_CONFLICT_PRESERVED",
                "finding_ids": sorted(str(item["finding_id"]) for item in group),
                "severities": severities,
            })

    # Similar summaries at the same location remain separate and are only cross-referenced.
    by_location: dict[tuple[str, int, int, str], list[dict[str, Any]]] = {}
    for finding in merged:
        key = (
            str(finding["path"]), int(finding["start_line"]), int(finding["end_line"]),
            str(finding["category"]).casefold(),
        )
        by_location.setdefault(key, []).append(finding)
    suspected: list[dict[str, Any]] = []
    for key, group in sorted(by_location.items()):
        if len(group) < 2:
            continue
        identities = {str(item["issue_identity"]) for item in group}
        if len(identities) < 2:
            continue
        ids = sorted(str(item["finding_id"]) for item in group)
        for item in group:
            item["possible_duplicate_refs"] = [value for value in ids if value != item["finding_id"]]
        suspected.append({
            "kind": "POSSIBLE_DUPLICATE_PRESERVED",
            "path": key[0], "start_line": key[1], "end_line": key[2],
            "finding_ids": ids,
        })

    return {
        "schema_version": 1,
        "input_count": len(findings),
        "merged_count": len(merged),
        "exact_duplicate_groups": [
            {"exact_identity": key, "finding_ids": value}
            for key, value in sorted(duplicate_groups.items())
        ],
        "severity_conflicts": conflicts,
        "possible_duplicates": suspected,
        "findings": merged,
        "merge_policy": "EXACT_ONLY; POSSIBLE_DUPLICATES_AND_SEVERITY_CONFLICTS_ARE_PRESERVED",
        "merge_fingerprint": _canonical_hash(merged),
    }
