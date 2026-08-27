#!/usr/bin/env python3
"""Fail when the product-completeness catalog is missing or unresolved."""

from __future__ import annotations

import argparse
import sys

from _common import find_table, print_report, project_root, read_text


EXPECTED_IDS = {f"PCM-{number:03d}" for number in range(1, 49)}
APPLICABILITY = {"REQUIRED", "NOT_APPLICABLE", "DEFERRED"}
COVERAGE = {"COVERED", "GAP", "BLOCKED"}


def check(root) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    relative = "docs/checklists/product-completeness.md"
    path = root / relative
    if not path.is_file():
        return [f"Required checklist is missing: {relative}"], warnings
    rows = find_table(
        read_text(path),
        ["Item ID", "Applicability", "Coverage", "Requirement/feature/AC refs", "Reason or evidence", "Owner/target/risk owner"],
    )
    if not rows:
        return [f"{relative}: checklist table is missing or has invalid headers"], warnings
    by_id = {row["Item ID"].upper(): row for row in rows if row.get("Item ID")}
    for missing in sorted(EXPECTED_IDS - set(by_id)):
        errors.append(f"{relative}: required catalog item is missing: {missing}")
    for extra in sorted(set(by_id) - EXPECTED_IDS):
        warnings.append(f"{relative}: custom catalog item detected: {extra}")
    for item_id in sorted(EXPECTED_IDS & set(by_id)):
        row = by_id[item_id]
        applicability = row.get("Applicability", "").upper()
        coverage = row.get("Coverage", "").upper()
        refs = row.get("Requirement/feature/AC refs", "").strip()
        reason = row.get("Reason or evidence", "").strip()
        ownership = row.get("Owner/target/risk owner", "").strip().lower()
        if applicability not in APPLICABILITY:
            errors.append(f"{item_id}: Applicability must be REQUIRED, NOT_APPLICABLE, or DEFERRED")
            continue
        if coverage not in COVERAGE:
            errors.append(f"{item_id}: Coverage must be COVERED, GAP, or BLOCKED")
        if coverage in {"GAP", "BLOCKED"}:
            errors.append(f"{item_id}: unresolved coverage is {coverage}")
        if applicability == "REQUIRED" and not refs:
            errors.append(f"{item_id}: REQUIRED item needs requirement/feature/AC references")
        if applicability == "NOT_APPLICABLE" and not reason:
            errors.append(f"{item_id}: NOT_APPLICABLE item needs a reason")
        if applicability == "DEFERRED":
            if not reason:
                errors.append(f"{item_id}: DEFERRED item needs a reason")
            for key in ("owner=", "target=", "risk_owner="):
                if key not in ownership:
                    errors.append(f"{item_id}: DEFERRED item needs '{key[:-1]}' in Owner/target/risk owner")
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
    return print_report("Product completeness check", errors, warnings)


if __name__ == "__main__":
    raise SystemExit(main())
