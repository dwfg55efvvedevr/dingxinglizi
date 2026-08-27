#!/usr/bin/env python3
"""Validate project document structure, metadata, status JSON, and core agents."""

from __future__ import annotations

import argparse
import json
import re
import sys

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
}


def check(root) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not (root / "AGENTS.md").is_file():
        errors.append("AGENTS.md is missing")
    for relative in (
        ".codex/orchestration/model-routing-policy.json",
        ".codex/orchestration/capability-policy.json",
        ".codex/orchestration/capability-catalog.json",
        ".codex/orchestration/capability-lock.json",
        ".codex/orchestration/runtime-inventory.json",
    ):
        path = root / relative
        if not path.is_file():
            errors.append(f"Required orchestration policy is missing: {relative}")
            continue
        try:
            content = json.loads(read_text(path))
            if relative.endswith("model-routing-policy.json"):
                from model_routing import validate_model_policy

                validate_model_policy(content)
            if relative.endswith("runtime-inventory.json"):
                if content.get("status") not in {"UNVERIFIED", "VERIFIED"}:
                    errors.append(f"{relative}: status must be UNVERIFIED or VERIFIED")
                models = content.get("available_models")
                if not isinstance(models, list):
                    errors.append(f"{relative}: available_models must be a list")
                elif content.get("status") == "VERIFIED" and not models:
                    errors.append(f"{relative}: VERIFIED inventory requires at least one available model")
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: invalid JSON: {exc}")
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
            if execution.get("model_routing_policy") != "1.1.0":
                errors.append("docs/project-status.json: model_routing_policy must be 1.1.0")
            if execution.get("capability_policy") != "1.1.0":
                errors.append("docs/project-status.json: capability_policy must be 1.1.0")
            for gate in ("requirements", "product", "ux", "ui", "architecture", "build", "qa", "release"):
                if gate not in status.get("gates", {}):
                    errors.append(f"docs/project-status.json: missing gate '{gate}'")
    shared = root / ".codex" / "agents" / "shared-rules.md"
    if not shared.is_file():
        errors.append(".codex/agents/shared-rules.md is missing")
    for agent in REQUIRED_AGENTS:
        path = root / ".codex" / "agents" / f"{agent}.toml"
        if not path.is_file():
            errors.append(f"Required custom Agent config is missing: .codex/agents/{agent}.toml")
            continue
        text = read_text(path)
        for field in ("name", "description", "developer_instructions"):
            if not re.search(rf"(?m)^{re.escape(field)}\s*=", text):
                errors.append(f".codex/agents/{agent}.toml: required field '{field}' is missing")
        if "shared-rules.md" not in text:
            errors.append(f".codex/agents/{agent}.toml: does not load shared-rules.md")
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
