#!/usr/bin/env python3
"""Diagnose Skill installation and optional initialized-project readiness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from _common import CANONICAL_STATES, INTERRUPT_STATES, REQUIRED_AGENTS, REQUIRED_DOCS, SKILL_ROOT, project_root
from _common import parse_frontmatter
from domain_packs import list_packs
from evolution import status as evolution_status
from evolution_store import EvolutionBlocked
from role_routing import role_plan_fingerprint
from project_layout import control_path, control_relative, layout_report
from state_io import load_json_object, safe_project_path
from validate_documents import check as validate_project_documents


SKILL_FILES = [
    "SKILL.md", "VERSION", "agents/openai.yaml", "scripts/orchestrator.py",
    "scripts/init_project.py", "scripts/route_roles.py", "scripts/check_project_status.py",
    "scripts/lifecycle.py",
    "scripts/evolution.py", "scripts/evolution_store.py",
    "scripts/platform_runtime.py", "scripts/platform_install.py",
    "scripts/project_layout.py", "scripts/migrate_project.py",
    "assets/templates/project/docs/project-status.json", "evals/routing-v2.json",
    "assets/platforms/common/role-catalog.json",
    "assets/platforms/common/common-prompt.md",
    "assets/platforms/common/execution-receipt.template.json",
    "assets/platforms/codex/adapter.json", "assets/platforms/cursor/adapter.json",
    "assets/platforms/claude-code/adapter.json", "assets/platforms/opencode/adapter.json",
    "references/run-ledger.md", "references/recovery.md", "references/evaluation.md",
    "references/domain-packs.md", "references/migration.md", "references/platform-adapters.md",
]


def _check(identifier: str, status: str, evidence: str, remediation: str = "", category: str = "configuration") -> dict[str, str]:
    return {
        "id": identifier,
        "status": status,
        "category": category,
        "evidence": evidence,
        "remediation": remediation,
    }


def _json_check(path: Path, identifier: str, checks: list[dict[str, str]]) -> dict[str, Any] | None:
    try:
        value = load_json_object(path)
    except ValueError as exc:
        checks.append(_check(identifier, "FAIL", str(exc), "Restore the generated file or reinitialize in a clean directory."))
        return None
    checks.append(_check(identifier, "PASS", f"Valid JSON object: {path}"))
    return value


def diagnose(project: Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    version = sys.version_info
    python_ok = version >= (3, 9)
    checks.append(_check(
        "runtime.python", "PASS" if python_ok else "FAIL",
        f"Python {version.major}.{version.minor}.{version.micro}",
        "Install Python 3.9 or newer." if not python_ok else "",
        "runtime",
    ))
    for relative in SKILL_FILES:
        path = SKILL_ROOT / relative
        checks.append(_check(
            f"skill.file.{relative}", "PASS" if path.is_file() else "FAIL",
            f"{'Found' if path.is_file() else 'Missing'}: {path}",
            "Install or copy the complete Skill folder; do not copy SKILL.md alone." if not path.is_file() else "",
        ))
    skill_path = SKILL_ROOT / "SKILL.md"
    if skill_path.is_file():
        metadata = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        valid_metadata = metadata.get("name") == "software-project-orchestrator" and bool(metadata.get("description"))
        checks.append(_check(
            "skill.metadata", "PASS" if valid_metadata else "FAIL",
            f"name={metadata.get('name')}, description={'present' if metadata.get('description') else 'missing'}",
            "Restore the canonical SKILL.md name and non-empty description." if not valid_metadata else "",
        ))
    openai_path = SKILL_ROOT / "agents/openai.yaml"
    if openai_path.is_file():
        openai_text = openai_path.read_text(encoding="utf-8")
        valid_openai = all(marker in openai_text for marker in (
            "interface:", "display_name:", "short_description:", "default_prompt:", "$software-project-orchestrator",
        ))
        checks.append(_check(
            "skill.openai-interface", "PASS" if valid_openai else "FAIL",
            "agents/openai.yaml exposes the stable invocation" if valid_openai else "agents/openai.yaml is missing required interface markers",
            "Restore the current skill-creator interface fields and stable invocation." if not valid_openai else "",
        ))
    try:
        pack_ids = {item["id"] for item in list_packs()}
        expected_packs = {"ecommerce", "crm", "saas", "group-buying", "ai-agent", "home-services"}
        pack_ok = pack_ids == expected_packs
        checks.append(_check(
            "skill.domain-packs", "PASS" if pack_ok else "FAIL", f"bundled={sorted(pack_ids)}",
            "Restore all six validated domain packs." if not pack_ok else "",
        ))
    except (OSError, ValueError) as exc:
        checks.append(_check("skill.domain-packs", "FAIL", str(exc), "Repair invalid bundled domain pack JSON."))
    if project is not None:
        root = project.resolve()
        checks.append(_check("project.root", "PASS" if root.is_dir() else "FAIL", f"Project root: {root}"))
        for relative in REQUIRED_DOCS:
            path = root / relative
            checks.append(_check(
                f"project.file.{relative}", "PASS" if path.is_file() else "FAIL",
                f"{'Found' if path.is_file() else 'Missing'}: {relative}",
                "Run orchestrator.py init for a new project or merge the missing current template manually." if not path.is_file() else "",
            ))
        status = _json_check(root / "docs/project-status.json", "project.status-json", checks)
        layout = layout_report(root)
        checks.append(_check("project.control-layout", "PASS", json.dumps(layout, sort_keys=True)))
        role_policy = _json_check(control_path(root, "orchestration/role-routing-policy.json"), "project.role-policy", checks)
        model_policy = _json_check(control_path(root, "orchestration/model-routing-policy.json"), "project.model-policy", checks)
        inventory = _json_check(control_path(root, "orchestration/runtime-inventory.json"), "runtime.inventory", checks)
        plan = _json_check(control_path(root, "orchestration/role-plan.json"), "project.role-plan", checks)
        if status is not None:
            state = status.get("current_state")
            valid_state = state in set(CANONICAL_STATES) | INTERRUPT_STATES
            checks.append(_check(
                "project.lifecycle-state", "PASS" if valid_state else "FAIL",
                f"Current state: {state}", "Restore a canonical lifecycle state." if not valid_state else "",
            ))
            execution = status.get("execution_control", {})
            sessions = execution.get("active_sessions", []) if isinstance(execution, dict) else []
            limit = execution.get("max_active_subagents", 1) if isinstance(execution, dict) else 1
            valid_sessions = isinstance(sessions, list) and isinstance(limit, int) and len(sessions) <= limit
            roles = [item.get("role") for item in sessions if isinstance(item, dict)] if isinstance(sessions, list) else []
            duplicate_roles = sorted({role for role in roles if role and roles.count(role) > 1})
            separation_ok = not ({"engineering_lead", "qa"} <= set(roles))
            session_ok = valid_sessions and not duplicate_roles and separation_ok
            details = f"active={len(sessions) if isinstance(sessions, list) else 'invalid'}, limit={limit}, roles={roles}"
            checks.append(_check(
                "project.active-sessions", "PASS" if session_ok else "FAIL", details,
                "Reconcile active sessions; never silently clear uncertain sessions." if not session_ok else "",
            ))
        if inventory is not None:
            verified = inventory.get("status") == "VERIFIED" and bool(inventory.get("available_models"))
            checks.append(_check(
                "runtime.model-inventory", "PASS" if verified else "WARN",
                (
                    f"status={inventory.get('status')}, models={inventory.get('available_models', [])}, "
                    f"skills={inventory.get('available_skills', [])}, "
                    f"mcp={inventory.get('available_mcp_servers', [])}"
                ),
                "Have the Orchestrator record the exact runtime model/capability inventory before dispatch." if not verified else "",
                "runtime",
            ))
        if plan is not None and plan.get("status") == "ROUTED":
            expected = role_plan_fingerprint(plan)
            actual = plan.get("plan_fingerprint")
            checks.append(_check(
                "project.role-plan-fingerprint", "PASS" if actual == expected else "FAIL",
                f"stored={actual}, computed={expected}",
                "Re-route the current stage; do not dispatch from a modified plan." if actual != expected else "",
            ))
        for policy_name, policy in (("role", role_policy), ("model", model_policy)):
            if policy is not None:
                checks.append(_check(
                    f"project.{policy_name}-policy-version", "PASS" if bool(policy.get("policy_version")) else "FAIL",
                    f"policy_version={policy.get('policy_version')}", "Restore the generated policy file." if not policy.get("policy_version") else "",
                ))
        document_errors, document_warnings = validate_project_documents(root)
        for index, error in enumerate(document_errors, start=1):
            checks.append(_check(
                f"project.contract.{index}", "FAIL", error,
                "Merge or restore the current project contract before dispatch.",
            ))
        for index, warning in enumerate(document_warnings, start=1):
            checks.append(_check(f"project.contract-warning.{index}", "WARN", warning))
        try:
            runs = safe_project_path(root, control_relative(root, "runs"))
            check_target = runs if runs.exists() else runs.parent
            writable = check_target.is_dir() and os.access(check_target, os.W_OK)
            status = "PASS" if runs.is_dir() and writable else ("WARN" if writable else "FAIL")
            evidence = f"Run ledger: {runs}" if runs.is_dir() else f"Run ledger will be created on first run: {runs}"
            checks.append(_check(
                "project.run-ledger", status, evidence,
                "Make the project-local control-plane runs directory writable without redirecting it outside the project." if not writable else "",
            ))
        except (OSError, ValueError) as exc:
            checks.append(_check("project.run-ledger", "FAIL", str(exc), "Remove path/symlink escape and recreate the project-local control-plane runs directory."))
        try:
            evolution = evolution_status(root)
            evolution_ok = evolution["status"] in {"READY", "NOT_INITIALIZED"}
            exposure_ok = evolution.get("git_reason_code") == "OK"
            check_status = "PASS" if evolution_ok and exposure_ok else "WARN"
            checks.append(_check(
                "project.evolution-core", check_status,
                f"status={evolution['status']}, reason={evolution['reason_code']}, git={evolution.get('git_state')}",
                (
                    "Evolution is optional and never blocks core commands. Explicitly initialize it, repair its local state, "
                    "or ensure the active control-plane evolution directory is ignored and untracked before Evolution writes."
                ) if check_status == "WARN" else "",
            ))
        except (OSError, ValueError, EvolutionBlocked) as exc:
            checks.append(_check(
                "project.evolution-core", "WARN", f"Optional Evolution inspection failed: {exc}",
                "Back up and inspect only the active control-plane evolution directory; core project validation remains independent.",
            ))

    config_fail = any(item["status"] == "FAIL" and item["category"] == "configuration" for item in checks)
    runtime_fail = any(item["status"] == "FAIL" and item["category"] == "runtime" for item in checks)
    warnings = any(item["status"] == "WARN" for item in checks)
    if config_fail:
        overall = "BLOCKED_CONFIGURATION"
    elif runtime_fail:
        overall = "BLOCKED_RUNTIME"
    elif warnings:
        overall = "READY_WITH_LIMITATIONS"
    else:
        overall = "READY"
    return {"schema_version": 1, "status": overall, "skill_version": (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (SKILL_ROOT / "VERSION").is_file() else "UNKNOWN", "checks": checks}


def print_human(report: dict[str, Any]) -> None:
    print(f"Software Project Orchestrator doctor: {report['status']}")
    for item in report["checks"]:
        if item["status"] != "PASS":
            print(f"{item['status']}: {item['id']}: {item['evidence']}")
            if item["remediation"]:
                print(f"  NEXT: {item['remediation']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", help="Optional initialized project directory")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir) if args.project_dir else None
        report = diagnose(root)
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else "", end="" if args.json else "")
        if args.json:
            print()
        else:
            print_human(report)
        return 0 if report["status"] in {"READY", "READY_WITH_LIMITATIONS"} else 3
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
