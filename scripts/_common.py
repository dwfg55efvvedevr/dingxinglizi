#!/usr/bin/env python3
"""Shared standard-library helpers for the project orchestration scripts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


SKILL_ROOT = Path(__file__).resolve().parent.parent
PROJECT_TEMPLATE = SKILL_ROOT / "assets" / "templates" / "project"

REQUIRED_DOCS = [
    "docs/00-project-context.md",
    "docs/01-domain-rules.md",
    "docs/02-glossary.md",
    "docs/03-role-journey-matrix.md",
    "docs/04-prd.md",
    "docs/05-state-permission-matrix.md",
    "docs/06-ux-spec.md",
    "docs/07-design-system.md",
    "docs/08-system-design.md",
    "docs/09-api-data-contract.md",
    "docs/10-test-plan.md",
    "docs/checklists/product-completeness.md",
    "docs/checklists/problem-quality.md",
    "docs/checklists/solution-challenge.md",
    "docs/checklists/quality-case.md",
]

AVAILABLE_PROFESSIONAL_ROLES = [
    "orchestrator",
    "requirements",
    "product_auditor",
    "ux",
    "ui",
    "architect",
    "engineering_lead",
    "qa",
    "quality_governor",
]

# Backward-compatible name: these profiles must exist, but are not all active.
REQUIRED_AGENTS = AVAILABLE_PROFESSIONAL_ROLES

CANONICAL_STATES = [
    "BACKLOG",
    "DISCOVERY",
    "REQUIREMENTS_APPROVED",
    "PRODUCT_APPROVED",
    "UX_READY",
    "UI_READY",
    "ARCHITECTURE_READY",
    "READY_FOR_BUILD",
    "IN_DEVELOPMENT",
    "CODE_REVIEW",
    "READY_FOR_QA",
    "QA_PASS",
    "RELEASE_READY",
    "DONE",
]

INTERRUPT_STATES = {
    "BLOCKED",
    "REWORK_REQUIREMENTS",
    "REWORK_PRODUCT",
    "REWORK_UX",
    "REWORK_UI",
    "REWORK_ARCHITECTURE",
    "REWORK_ENGINEERING",
    "REWORK_QA",
}

FRONTMATTER_FIELDS = {"status", "version", "last_updated", "owner", "source_of_truth"}


def project_root(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f"Project path is not a directory: {path}")
    return path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(f"Required file is missing: {path}") from None
    except UnicodeDecodeError as exc:
        raise ValueError(f"File is not valid UTF-8: {path}: {exc}") from exc


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def markdown_tables(text: str) -> list[tuple[list[str], list[dict[str, str]]]]:
    """Return simple pipe tables as (headers, row dictionaries)."""
    lines = text.splitlines()
    tables: list[tuple[list[str], list[dict[str, str]]]] = []
    index = 0
    while index + 1 < len(lines):
        header_line = lines[index].strip()
        separator_line = lines[index + 1].strip()
        if not (header_line.startswith("|") and separator_line.startswith("|")):
            index += 1
            continue
        headers = [cell.strip() for cell in header_line.strip("|").split("|")]
        separators = [cell.strip() for cell in separator_line.strip("|").split("|")]
        if len(headers) != len(separators) or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separators):
            index += 1
            continue
        rows: list[dict[str, str]] = []
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
            index += 1
        tables.append((headers, rows))
    return tables


def find_table(text: str, required_headers: Iterable[str]) -> list[dict[str, str]]:
    wanted = set(required_headers)
    for headers, rows in markdown_tables(text):
        if wanted.issubset(headers):
            return rows
    return []


def id_tokens(value: str, prefix: str) -> set[str]:
    return set(re.findall(rf"\b{re.escape(prefix)}-[A-Z0-9][A-Z0-9_-]*\b", value.upper()))


def print_report(title: str, errors: list[str], warnings: list[str] | None = None) -> int:
    warnings = warnings or []
    print(title)
    for item in warnings:
        print(f"WARNING: {item}")
    for item in errors:
        print(f"ERROR: {item}")
    if errors:
        print(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"PASS: 0 errors, {len(warnings)} warning(s)")
    return 0
