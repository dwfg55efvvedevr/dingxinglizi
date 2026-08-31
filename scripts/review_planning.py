#!/usr/bin/env python3
"""Deterministic risk/technology review shard planning with context budgets."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from state_io import utc_now


DEFAULT_BUDGET = {
    "max_files": 120,
    "max_bytes": 1_500_000,
    "max_estimated_tokens": 468_750,
    "token_estimation": "ceil(bytes/4*1.25-static-safety-margin)",
}
MAX_SHARDS = 10_000

SURFACES = {
    "frontend": {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".css", ".scss", ".html"},
    "backend": {".py", ".rb", ".php", ".java", ".kt", ".go", ".rs", ".cs", ".scala"},
    "data": {".sql", ".prisma", ".graphql", ".proto", ".avsc"},
    "infrastructure": {".tf", ".hcl", ".yaml", ".yml", ".toml", ".dockerfile"},
    "native": {".swift", ".m", ".mm", ".c", ".cc", ".cpp", ".h", ".hpp"},
    "documentation": {".md", ".rst", ".txt"},
}

RISK_PATTERNS = {
    "security": re.compile(r"(^|/)(auth|oauth|security|crypto|permission|permissions|rbac|acl)(/|[._-])", re.I),
    "money": re.compile(r"(^|/)(payment|payments|billing|invoice|refund|settlement|checkout)(/|[._-])", re.I),
    "migration": re.compile(r"(^|/)(migration|migrations|schema|schemas|database|db)(/|[._-])", re.I),
    "api-contract": re.compile(r"(^|/)(api|apis|graphql|proto|openapi|swagger)(/|[._-])", re.I),
    "deployment": re.compile(r"(^|/)(deploy|deployment|infra|infrastructure|terraform|k8s|kubernetes)(/|[._-])", re.I),
    "concurrency": re.compile(r"(^|/)(queue|worker|concurrent|async|lock|transaction)(/|[._-])", re.I),
}
SUPPORTED_RISK_LENSES = frozenset({
    *RISK_PATTERNS,
    "supply-chain", "permissions", "privacy", "data-integrity", "state-machine",
    "external-side-effects", "release", "ai-safety",
})


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def estimate_tokens(size_bytes: int) -> int:
    """A static upper estimate, never a claim about real runtime token use."""
    if size_bytes < 0:
        raise ValueError("File size must not be negative")
    return int(math.ceil((size_bytes / 4.0) * 1.25))


def validate_budget(value: dict[str, Any] | None) -> dict[str, Any]:
    budget = dict(DEFAULT_BUDGET)
    if value:
        unknown = sorted(set(value) - {"max_files", "max_bytes", "max_estimated_tokens"})
        if unknown:
            raise ValueError("Unknown context budget fields: " + ", ".join(unknown))
        budget.update(value)
    for key in ("max_files", "max_bytes", "max_estimated_tokens"):
        current = budget.get(key)
        if isinstance(current, bool) or not isinstance(current, int) or current <= 0:
            raise ValueError(f"Context budget {key} must be a positive integer")
    budget["token_estimation"] = DEFAULT_BUDGET["token_estimation"]
    return budget


def technology_surface(path: str) -> str:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    lowered = path.lower()
    if re.search(r"(^|/)(ai|agents?|llm|evals?|guardrails?)(/|[._-])", lowered):
        return "ai"
    if re.search(r"(^|/)(tests?|specs?|fixtures?)(/|[._-])", lowered) or re.search(
        r"(^|[._-])(test|spec)([._-]|$)", name,
    ):
        return "test"
    if name in {"dockerfile", "makefile"}:
        return "infrastructure"
    for surface, suffixes in SURFACES.items():
        if suffix in suffixes:
            return surface
    return "other"


def file_risks(path: str) -> list[str]:
    values = [name for name, pattern in RISK_PATTERNS.items() if pattern.search(path)]
    if Path(path).name.lower() in {"package-lock.json", "poetry.lock", "cargo.lock", "go.sum"}:
        values.append("supply-chain")
    return sorted(set(values))


def _module_for_path(path: str, modules: list[dict[str, Any]]) -> str:
    matches: list[tuple[int, str]] = []
    for module in modules:
        root = str(module.get("root", "."))
        if root == "." or path == root or path.startswith(root + "/"):
            matches.append((len(Path(root).parts), str(module["module_id"])))
    return max(matches)[1] if matches else "module-unassigned"


def _new_shard(sequence: int, module_id: str, surface: str) -> dict[str, Any]:
    return {
        "shard_id": f"SHARD-{sequence:04d}",
        "shard_kind": "PRIMARY",
        "module_id": module_id,
        "technology_surface": surface,
        "risk_dimensions": [],
        "files": [],
        "file_count": 0,
        "bytes": 0,
        "estimated_tokens": 0,
        "fresh_session_required": True,
        "compact_handoff_required": True,
        "session_isolation_status": "UNVERIFIED_SESSION_ISOLATION",
    }


def _fits(shard: dict[str, Any], entry: dict[str, Any], budget: dict[str, Any]) -> bool:
    size = int(entry["size_bytes"])
    return (
        shard["file_count"] + 1 <= budget["max_files"]
        and shard["bytes"] + size <= budget["max_bytes"]
        and shard["estimated_tokens"] + estimate_tokens(size) <= budget["max_estimated_tokens"]
    )


def build_review_plan(
    inventory: dict[str, Any],
    *,
    budget: dict[str, Any] | None = None,
    required_risks: list[str] | None = None,
) -> dict[str, Any]:
    selected_budget = validate_budget(budget)
    selected_risks = sorted(set(required_risks or []))
    unknown_risks = sorted(set(selected_risks) - SUPPORTED_RISK_LENSES)
    if unknown_risks:
        raise ValueError("Unknown required risk lenses: " + ", ".join(unknown_risks))
    blocked_dispositions = [
        {"path": entry.get("path"), "disposition": entry.get("disposition")}
        for entry in inventory.get("entries", [])
        if str(entry.get("disposition", "")).startswith("BLOCKED_")
    ]
    if blocked_dispositions:
        return _blocked_inventory_plan(inventory, selected_budget, blocked_dispositions)
    entries = [entry for entry in inventory.get("entries", []) if entry.get("disposition") == "INCLUDED"]
    if not entries:
        return _blocked_empty_plan(inventory, selected_budget)
    modules = list(inventory.get("modules", []))
    oversized: list[dict[str, Any]] = []
    for entry in entries:
        size = int(entry.get("size_bytes", 0))
        estimated = estimate_tokens(size)
        if (
            size > selected_budget["max_bytes"]
            or estimated > selected_budget["max_estimated_tokens"]
        ):
            oversized.append({
                "path": entry["path"],
                "size_bytes": size,
                "estimated_tokens": estimated,
                "reason": "single-file-exceeds-context-budget",
            })
    if oversized:
        return _blocked_plan(inventory, selected_budget, oversized)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    file_metadata: dict[str, dict[str, Any]] = {}
    for entry in sorted(entries, key=lambda item: str(item["path"])):
        path = str(entry["path"])
        module_id = _module_for_path(path, modules)
        surface = technology_surface(path)
        # Explicit project risks are mandatory lenses across the declared target,
        # even when filenames do not reveal the relevant behavior.
        risks = sorted(set(file_risks(path)) | set(selected_risks))
        enriched = dict(entry)
        enriched["module_id"] = module_id
        enriched["technology_surface"] = surface
        enriched["risk_dimensions"] = risks
        grouped.setdefault((module_id, surface), []).append(enriched)
        file_metadata[path] = {
            "module_id": module_id,
            "technology_surface": surface,
            "risk_dimensions": risks,
            "primary_shard_id": None,
        }

    primary: list[dict[str, Any]] = []
    sequence = 1
    for (module_id, surface), values in sorted(grouped.items()):
        shard = _new_shard(sequence, module_id, surface)
        for entry in values:
            if shard["file_count"] and not _fits(shard, entry, selected_budget):
                primary.append(shard)
                sequence += 1
                if sequence > MAX_SHARDS:
                    raise ValueError(f"Review plan exceeds shard limit ({MAX_SHARDS})")
                shard = _new_shard(sequence, module_id, surface)
            if not _fits(shard, entry, selected_budget):
                raise AssertionError("Oversized file escaped preflight")
            path = str(entry["path"])
            shard["files"].append(path)
            shard["file_count"] += 1
            shard["bytes"] += int(entry["size_bytes"])
            shard["estimated_tokens"] += estimate_tokens(int(entry["size_bytes"]))
            shard["risk_dimensions"] = sorted(set(shard["risk_dimensions"]) | set(entry["risk_dimensions"]))
            file_metadata[path]["primary_shard_id"] = shard["shard_id"]
        if shard["file_count"]:
            primary.append(shard)
            sequence += 1

    cross_cut: list[dict[str, Any]] = []
    risks = sorted({risk for value in file_metadata.values() for risk in value["risk_dimensions"]})
    for risk in risks:
        values = [path for path in sorted(file_metadata) if risk in file_metadata[path]["risk_dimensions"]]
        current: list[str] = []
        current_bytes = 0
        current_tokens = 0
        part = 1
        for path in values:
            entry = next(item for item in entries if item["path"] == path)
            size = int(entry["size_bytes"])
            tokens = estimate_tokens(size)
            if current and (
                len(current) + 1 > selected_budget["max_files"]
                or current_bytes + size > selected_budget["max_bytes"]
                or current_tokens + tokens > selected_budget["max_estimated_tokens"]
            ):
                cross_cut.append(_cross_cut_shard(sequence, risk, part, current, current_bytes, current_tokens))
                sequence += 1
                if sequence > MAX_SHARDS:
                    raise ValueError(f"Review plan exceeds shard limit ({MAX_SHARDS})")
                part += 1
                current, current_bytes, current_tokens = [], 0, 0
            current.append(path)
            current_bytes += size
            current_tokens += tokens
        if current:
            cross_cut.append(_cross_cut_shard(sequence, risk, part, current, current_bytes, current_tokens))
            sequence += 1
            if sequence > MAX_SHARDS + 1:
                raise ValueError(f"Review plan exceeds shard limit ({MAX_SHARDS})")

    plan_core = {
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": selected_budget,
        "required_risk_lenses": selected_risks,
        "primary_shards": primary,
        "cross_cut_shards": cross_cut,
        "file_coverage": file_metadata,
    }
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "status": "READY",
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": selected_budget,
        "required_risk_lenses": selected_risks,
        "budget_semantics": "STATIC_ESTIMATE_ONLY_NOT_RUNTIME_TOKEN_USAGE",
        "primary_shards": primary,
        "cross_cut_shards": cross_cut,
        "file_coverage": file_metadata,
        "excluded_dispositions": inventory.get("disposition_counts", {}),
        "oversized_files": [],
        "plan_fingerprint": canonical_hash(plan_core),
        "coverage_claim_limit": "PLAN_COVERS_DECLARED_INCLUDED_FILES; HEURISTICS_DO_NOT_PROVE_SEMANTIC_COMPLETENESS",
    }


def _cross_cut_shard(
    sequence: int,
    risk: str,
    part: int,
    files: list[str],
    size: int,
    tokens: int,
) -> dict[str, Any]:
    return {
        "shard_id": f"SHARD-{sequence:04d}",
        "shard_kind": "CROSS_CUT",
        "module_id": "cross-module",
        "technology_surface": "cross-cutting",
        "risk_dimensions": [risk],
        "cross_cut_part": part,
        "files": list(files),
        "file_count": len(files),
        "bytes": size,
        "estimated_tokens": tokens,
        "fresh_session_required": True,
        "compact_handoff_required": True,
        "session_isolation_status": "UNVERIFIED_SESSION_ISOLATION",
    }


def _blocked_plan(
    inventory: dict[str, Any],
    budget: dict[str, Any],
    oversized: list[dict[str, Any]],
) -> dict[str, Any]:
    core = {
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": budget,
        "oversized_files": oversized,
    }
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "status": "BLOCKED_OVERSIZED_FILE",
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": budget,
        "budget_semantics": "STATIC_ESTIMATE_ONLY_NOT_RUNTIME_TOKEN_USAGE",
        "primary_shards": [],
        "cross_cut_shards": [],
        "file_coverage": {},
        "excluded_dispositions": inventory.get("disposition_counts", {}),
        "oversized_files": oversized,
        "plan_fingerprint": canonical_hash(core),
        "coverage_claim_limit": "NO_COVERAGE_CLAIM_WHILE_OVERSIZED_FILE_IS_BLOCKED",
    }


def _blocked_inventory_plan(
    inventory: dict[str, Any],
    budget: dict[str, Any],
    blocked: list[dict[str, Any]],
) -> dict[str, Any]:
    core = {
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": budget,
        "blocked_dispositions": blocked,
    }
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "status": "BLOCKED_INVENTORY_DISPOSITION",
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": budget,
        "budget_semantics": "STATIC_ESTIMATE_ONLY_NOT_RUNTIME_TOKEN_USAGE",
        "primary_shards": [],
        "cross_cut_shards": [],
        "file_coverage": {},
        "excluded_dispositions": inventory.get("disposition_counts", {}),
        "blocked_dispositions": blocked,
        "oversized_files": [],
        "plan_fingerprint": canonical_hash(core),
        "coverage_claim_limit": "NO_COVERAGE_CLAIM_WHILE_INVENTORY_HAS_BLOCKED_DISPOSITIONS",
    }


def _blocked_empty_plan(inventory: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    core = {
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": budget,
        "reason": "no-included-reviewable-files",
    }
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "status": "BLOCKED_NO_INCLUDED_FILES",
        "inventory_fingerprint": inventory.get("manifest_fingerprint"),
        "budget": budget,
        "budget_semantics": "STATIC_ESTIMATE_ONLY_NOT_RUNTIME_TOKEN_USAGE",
        "primary_shards": [], "cross_cut_shards": [], "file_coverage": {},
        "excluded_dispositions": inventory.get("disposition_counts", {}),
        "oversized_files": [],
        "block_reason": "no-included-reviewable-files",
        "plan_fingerprint": canonical_hash(core),
        "coverage_claim_limit": "NO_COVERAGE_CLAIM_WITHOUT_REVIEWABLE_FILES",
    }


def validate_plan_fingerprint(plan: dict[str, Any]) -> bool:
    if plan.get("status") == "BLOCKED_NO_INCLUDED_FILES":
        core = {
            "inventory_fingerprint": plan.get("inventory_fingerprint"),
            "budget": plan.get("budget"),
            "reason": plan.get("block_reason"),
        }
    elif plan.get("status") == "BLOCKED_INVENTORY_DISPOSITION":
        core = {
            "inventory_fingerprint": plan.get("inventory_fingerprint"),
            "budget": plan.get("budget"),
            "blocked_dispositions": plan.get("blocked_dispositions"),
        }
    elif plan.get("status") == "BLOCKED_OVERSIZED_FILE":
        core = {
            "inventory_fingerprint": plan.get("inventory_fingerprint"),
            "budget": plan.get("budget"),
            "oversized_files": plan.get("oversized_files"),
        }
    else:
        core = {
            "inventory_fingerprint": plan.get("inventory_fingerprint"),
            "budget": plan.get("budget"),
            "required_risk_lenses": plan.get("required_risk_lenses", []),
            "primary_shards": plan.get("primary_shards"),
            "cross_cut_shards": plan.get("cross_cut_shards"),
            "file_coverage": plan.get("file_coverage"),
        }
    return plan.get("plan_fingerprint") == canonical_hash(core)
