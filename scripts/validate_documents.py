#!/usr/bin/env python3
"""Validate project document structure, metadata, status JSON, and core agents."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import (
    CANONICAL_STATES,
    FRONTMATTER_FIELDS,
    INTERRUPT_STATES,
    REQUIRED_AGENTS,
    REQUIRED_DOCS,
    parse_frontmatter,
    print_report,
    project_root,
    read_text,
)
from project_layout import control_path


REQUIRED_HEADINGS = {
    "docs/00-project-context.md": ["# Project context", "## One-sentence goal", "## Fact register and open questions"],
    "docs/01-domain-rules.md": ["# Domain rules", "## Numbered business rules", "## State machines"],
    "docs/03-role-journey-matrix.md": ["## Role-page matrix", "## Page-feature matrix", "## Front-office/back-office matrix"],
    "docs/04-prd.md": ["# Product requirements document", "## Requirements"],
    "docs/05-state-permission-matrix.md": ["## Feature-state matrix", "## Permission matrix"],
    "docs/06-ux-spec.md": ["# UX specification", "## User flows"],
    "docs/07-design-system.md": ["# Design system", "## Components and variants"],
    "docs/08-system-design.md": ["# System design", "## Deployment, migration, compatibility, and rollback"],
    "docs/09-api-data-contract.md": ["# API and data contract", "## APIs and events", "## Data models"],
    "docs/10-test-plan.md": ["# Test and acceptance plan", "## Acceptance matrix", "## Independent QA conclusion"],
    "docs/checklists/problem-quality.md": ["# Problem quality review", "## Claims and evidence", "## Decision"],
    "docs/checklists/solution-challenge.md": ["# Solution challenge", "## Solution logic", "## Decision"],
    "docs/checklists/quality-case.md": ["# Release quality case", "## Claim-evidence map", "## Decision"],
}


def check(root) -> tuple[list[str], list[str]]:
    root = Path(root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if not (root / "AGENTS.md").is_file():
        errors.append("AGENTS.md is missing")
    for relative in (
        "model-routing-policy.json",
        "role-routing-policy.json",
        "role-plan.json",
        "capability-policy.json",
        "capability-catalog.json",
        "capability-lock.json",
        "runtime-inventory.json",
    ):
        path = control_path(root, Path("orchestration") / relative)
        display = str(path.relative_to(root.resolve()))
        if not path.is_file():
            errors.append(f"Required orchestration policy is missing: {display}")
            continue
        try:
            content = json.loads(read_text(path))
            if relative.endswith("model-routing-policy.json"):
                from model_routing import validate_model_policy

                validate_model_policy(content)
            if relative.endswith("role-routing-policy.json"):
                from role_routing import validate_role_policy

                validate_role_policy(content)
            if relative.endswith("role-plan.json") and content.get("status") not in {"NOT_ROUTED", "ROUTED"}:
                errors.append(f"{display}: status must be NOT_ROUTED or ROUTED")
            if relative.endswith("role-plan.json"):
                required_v2_fields = {
                    "max_active_subagents", "required_now", "execution_waves", "deferred_available",
                    "quality_gate", "quality_review_status", "inline_actions", "signals", "input_fingerprint",
                }
                missing_v2 = sorted(required_v2_fields - set(content))
                if missing_v2:
                    errors.append(f"{display}: missing control fields: {', '.join(missing_v2)}")
            if relative.endswith("runtime-inventory.json"):
                provenance_fields = {"runtime_id", "host_id", "runtime_version", "evidence_source"}
                missing_provenance = sorted(provenance_fields - set(content))
                if missing_provenance:
                    errors.append(f"{display}: missing runtime provenance fields: {', '.join(missing_provenance)}")
                if content.get("status") not in {"UNVERIFIED", "VERIFIED"}:
                    errors.append(f"{display}: status must be UNVERIFIED or VERIFIED")
                models = content.get("available_models")
                if not isinstance(models, list):
                    errors.append(f"{display}: available_models must be a list")
                elif content.get("status") == "VERIFIED" and not models:
                    errors.append(f"{display}: VERIFIED inventory requires at least one available model")
                elif isinstance(models, list):
                    supported = {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"}
                    unknown = sorted(set(models) - supported)
                    if unknown:
                        errors.append(
                            f"{display}: unsupported model slug(s) in legacy Codex inventory: "
                            + ", ".join(unknown)
                        )
                for field in ("available_skills", "available_mcp_servers"):
                    values = content.get(field)
                    if not isinstance(values, list) or not all(
                        isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value)
                        for value in values
                    ):
                        errors.append(
                            f"{display}: {field} must be a list of capability IDs"
                        )
                if content.get("status") == "VERIFIED":
                    for field in ("verified_at", "verified_by", "evidence_source"):
                        if not content.get(field):
                            errors.append(f"{display}: VERIFIED inventory requires {field}")
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{display}: invalid JSON: {exc}")
    for relative in REQUIRED_DOCS:
        path = root / relative
        if not path.is_file():
            errors.append(f"Required document is missing: {relative}")
            continue
        text = read_text(path)
        frontmatter = parse_frontmatter(text)
        for field in sorted(FRONTMATTER_FIELDS):
            if not frontmatter.get(field):
                errors.append(f"{relative}: frontmatter field '{field}' is missing or empty")
        if frontmatter.get("status") not in {"DRAFT", "IN_REVIEW", "APPROVED", "SUPERSEDED"}:
            errors.append(f"{relative}: invalid status '{frontmatter.get('status', '')}'")
        if frontmatter.get("version") and not re.fullmatch(r"\d+\.\d+\.\d+", frontmatter["version"]):
            errors.append(f"{relative}: version must use semantic form such as 1.0.0")
        for heading in REQUIRED_HEADINGS.get(relative, []):
            if heading not in text:
                errors.append(f"{relative}: required heading is missing: {heading}")
    status_path = root / "docs" / "project-status.json"
    if not status_path.is_file():
        errors.append("docs/project-status.json is missing")
    else:
        try:
            status = json.loads(read_text(status_path))
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"docs/project-status.json is invalid: {exc}")
        else:
            state = status.get("current_state")
            if state not in set(CANONICAL_STATES) | INTERRUPT_STATES:
                errors.append(f"docs/project-status.json: unsupported current_state '{state}'")
            if status.get("complexity") not in {"Simple", "Standard", "Complex"}:
                errors.append("docs/project-status.json: complexity must be Simple, Standard, or Complex")
            execution = status.get("execution_control", {})
            if execution.get("model_routing_policy") not in {"1.2.0", "2.0.0"}:
                errors.append("docs/project-status.json: model_routing_policy must be 1.2.0 or 2.0.0")
            if execution.get("role_routing_policy") not in {"1.2.0", "1.3.0"}:
                errors.append("docs/project-status.json: role_routing_policy must be 1.2.0 or 1.3.0")
            if execution.get("capability_policy") != "1.1.0":
                errors.append("docs/project-status.json: capability_policy must be 1.1.0")
            if execution.get("quota_mode") not in {"economy", "balanced", "quality_first"}:
                errors.append("docs/project-status.json: quota_mode must be economy, balanced, or quality_first")
            expected_maximum = {"economy": 1, "balanced": 2, "quality_first": 2}.get(execution.get("quota_mode"))
            if expected_maximum is not None and execution.get("max_active_subagents") != expected_maximum:
                errors.append(
                    "docs/project-status.json: max_active_subagents must match quota_mode "
                    f"({execution.get('quota_mode')}={expected_maximum})"
                )
            sessions = execution.get("active_sessions")
            if not isinstance(sessions, list):
                errors.append("docs/project-status.json: active_sessions must be a list")
            else:
                if any(item.get("role") == "orchestrator" for item in sessions if isinstance(item, dict)):
                    errors.append("docs/project-status.json: orchestrator must remain in the main thread")
                maximum = execution.get("max_active_subagents")
                if not isinstance(maximum, int) or maximum not in {1, 2}:
                    errors.append("docs/project-status.json: max_active_subagents must be 1 or 2")
                elif len(sessions) > maximum:
                    errors.append("docs/project-status.json: active_sessions exceeds max_active_subagents")
                workers = {"frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker"}
                for session in sessions:
                    if not isinstance(session, dict):
                        errors.append("docs/project-status.json: every active session must be an object")
                        continue
                    expected_parent = "engineering_lead" if session.get("role") in workers else "orchestrator"
                    if session.get("parent_role") != expected_parent:
                        errors.append(
                            f"docs/project-status.json: active role {session.get('role')} parent_role must be {expected_parent}"
                        )
                active_roles = {item.get("role") for item in sessions if isinstance(item, dict)}
                role_values = [item.get("role") for item in sessions if isinstance(item, dict)]
                duplicate_roles = sorted({role for role in role_values if role and role_values.count(role) > 1})
                if duplicate_roles:
                    errors.append(
                        "docs/project-status.json: duplicate active role sessions are not allowed: "
                        + ", ".join(duplicate_roles)
                    )
                if active_roles & workers and "engineering_lead" not in active_roles:
                    errors.append("docs/project-status.json: active Worker requires an active Engineering Lead")
                if {"engineering_lead", "qa"}.issubset(active_roles):
                    errors.append("docs/project-status.json: Engineering Lead and final QA cannot be active together")
            for gate in ("requirements", "product", "ux", "ui", "architecture", "build", "qa", "release"):
                if gate not in status.get("gates", {}):
                    errors.append(f"docs/project-status.json: missing gate '{gate}'")
            for gate in ("problem", "solution", "release_evidence"):
                if gate not in status.get("quality_gates", {}):
                    errors.append(f"docs/project-status.json: missing quality gate '{gate}'")
    layouts = [
        ("codex", root / ".codex/agents", ".toml", False),
        ("cursor", root / ".cursor/agents", ".md", True),
        ("claude-code", root / ".claude/agents", ".md", True),
        ("opencode", root / ".opencode/agents", ".md", True),
    ]
    active_layouts = [item for item in layouts if item[1].is_dir()]
    if not active_layouts:
        errors.append("No native Agent adapter is installed; render one supported platform before dispatch")
    task_template = root / "tasks/TASK.template.yaml"
    if not task_template.is_file():
        errors.append("tasks/TASK.template.yaml is missing")
    else:
        task_text = read_text(task_template)
        for marker in ('schema_version: 2', 'run_id: "NOT_ATTACHED"', 'source_input_fingerprint: "BLOCKING_UNKNOWN"'):
            if marker not in task_text:
                errors.append(f"tasks/TASK.template.yaml: missing v2 contract marker: {marker}")
    for platform, directory, suffix, hyphenated in active_layouts:
        combined = ""
        for agent in REQUIRED_AGENTS:
            filename = agent.replace("_", "-") if hyphenated else agent
            path = directory / f"{filename}{suffix}"
            display = str(path.relative_to(root.resolve()))
            if not path.is_file():
                errors.append(f"Required {platform} Agent config is missing: {display}")
                continue
            text = read_text(path)
            combined += "\n" + text
            if suffix == ".toml":
                for field in ("name", "description", "developer_instructions"):
                    if not re.search(rf"(?m)^{re.escape(field)}\s*=", text):
                        errors.append(f"{display}: required field '{field}' is missing")
            elif not text.startswith("---\n") or "description:" not in text.split("---", 2)[1]:
                errors.append(f"{display}: invalid Markdown Agent frontmatter")
        shared = directory / "shared-rules.md"
        if shared.is_file():
            combined += "\n" + read_text(shared)
        for marker in ("run_id", "PASS_WITH_ACCEPTED_RISKS", "Quality Governor", "Only Orchestrator"):
            if marker not in combined:
                errors.append(f"{platform} Agent adapter is missing shared contract marker: {marker}")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        errors, warnings = check(root)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return print_report("Document validation", errors, warnings)


if __name__ == "__main__":
    raise SystemExit(main())
