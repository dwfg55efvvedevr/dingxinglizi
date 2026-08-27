#!/usr/bin/env python3
"""Check requirement, page, feature, state, backend, and acceptance traceability."""

from __future__ import annotations

import argparse
import sys

from _common import find_table, id_tokens, print_report, project_root, read_text


def tokens_from_rows(rows, column, prefix):
    values = set()
    for row in rows:
        values.update(id_tokens(row.get(column, ""), prefix))
    return values


def require_cells(errors, rows, columns, label_column):
    for row in rows:
        label = row.get(label_column, "<unidentified row>") or "<unidentified row>"
        for column in columns:
            if not row.get(column, "").strip():
                errors.append(f"{label}: required matrix cell is empty: {column}")


def check(root) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    prd = read_text(root / "docs/04-prd.md")
    journeys = read_text(root / "docs/03-role-journey-matrix.md")
    states = read_text(root / "docs/05-state-permission-matrix.md")
    tests = read_text(root / "docs/10-test-plan.md")

    requirement_rows = find_table(prd, ["Requirement ID", "Feature refs", "Acceptance refs"])
    role_page_rows = find_table(journeys, ["Role ID", "Page ID", "Requirement refs"])
    page_feature_rows = find_table(journeys, ["Page ID", "Feature ID", "Requirement refs"])
    backend_rows = find_table(journeys, ["Feature ID", "Front-office action", "Backend/admin module or system handler"])
    state_rows = find_table(states, ["Feature ID", "Acceptance refs"])
    permission_rows = find_table(states, ["Role ID", "Resource", "Acceptance refs"])
    acceptance_rows = find_table(tests, ["Acceptance ID", "Requirement/feature refs", "Evidence type/location", "Result"])

    requirements = tokens_from_rows(requirement_rows, "Requirement ID", "REQ")
    pages_from_roles = tokens_from_rows(role_page_rows, "Page ID", "PAGE")
    pages_from_features = tokens_from_rows(page_feature_rows, "Page ID", "PAGE")
    features = tokens_from_rows(page_feature_rows, "Feature ID", "FEAT")
    backend_features = tokens_from_rows(backend_rows, "Feature ID", "FEAT")
    state_features = tokens_from_rows(state_rows, "Feature ID", "FEAT")
    acceptance = tokens_from_rows(acceptance_rows, "Acceptance ID", "AC")

    if not requirements:
        errors.append("No REQ-* requirement definitions found in docs/04-prd.md")
    if not pages_from_roles:
        errors.append("No PAGE-* rows found in the role-page matrix")
    if not features:
        errors.append("No FEAT-* rows found in the page-feature matrix")
    if not acceptance:
        errors.append("No AC-* rows found in docs/10-test-plan.md")
    if not permission_rows:
        errors.append("Permission matrix has no data rows")

    require_cells(errors, requirement_rows, ["Requirement ID", "Priority", "Role/object", "Requirement", "Business value", "Feature refs", "Acceptance refs", "Fact state"], "Requirement ID")
    require_cells(errors, role_page_rows, ["Role ID", "Surface/client", "Page ID", "Page/name", "Entry point", "Primary task", "Permission ref", "Requirement refs"], "Page ID")
    require_cells(errors, page_feature_rows, ["Page ID", "Feature ID", "Feature/action", "Primary/secondary", "Feedback", "Error/recovery", "Backend dependency", "Requirement refs"], "Feature ID")
    require_cells(errors, backend_rows, ["Feature ID", "Front-office action", "Backend/admin module or system handler", "Business object", "State transition", "Operator/system actor", "User feedback", "Audit/log", "Failure/recovery", "Requirement refs"], "Feature ID")
    require_cells(errors, state_rows, ["Feature ID", "Initial", "Loading", "Empty", "Success", "Failure", "Offline", "Unauthorized", "Expired", "Disabled/validation", "Recovery", "Acceptance refs"], "Feature ID")
    require_cells(errors, permission_rows, ["Role ID", "Resource", "Data scope", "View", "Create", "Modify", "Delete", "Approve/review", "Export", "Sensitive operation log", "Backend enforcement", "Acceptance refs"], "Role ID")
    require_cells(errors, acceptance_rows, ["Acceptance ID", "Requirement/feature refs", "Role/data scope", "Given", "When", "Then", "Evidence type/location", "Owner", "Result"], "Acceptance ID")

    for page in sorted(pages_from_roles - pages_from_features):
        errors.append(f"{page}: role-page matrix entry has no page-feature row")
    for page in sorted(pages_from_features - pages_from_roles):
        errors.append(f"{page}: page-feature row has no role-page coverage")
    for feature in sorted(features - state_features):
        errors.append(f"{feature}: missing feature-state matrix row")
    for feature in sorted(features - backend_features):
        errors.append(f"{feature}: missing front-office/back-office matrix row")

    page_feature_req_refs = tokens_from_rows(page_feature_rows, "Requirement refs", "REQ")
    role_page_req_refs = tokens_from_rows(role_page_rows, "Requirement refs", "REQ")
    backend_req_refs = tokens_from_rows(backend_rows, "Requirement refs", "REQ")
    acceptance_ref_text = " ".join(row.get("Requirement/feature refs", "") for row in acceptance_rows)
    acceptance_req_refs = id_tokens(acceptance_ref_text, "REQ")
    acceptance_feature_refs = id_tokens(acceptance_ref_text, "FEAT")
    for requirement in sorted(requirements - page_feature_req_refs):
        errors.append(f"{requirement}: not referenced by any page-feature row")
    for requirement in sorted(requirements - acceptance_req_refs):
        errors.append(f"{requirement}: not referenced by any acceptance criterion")
    for feature in sorted(features - acceptance_feature_refs):
        errors.append(f"{feature}: not referenced by any acceptance criterion")

    for undefined in sorted((role_page_req_refs | page_feature_req_refs | backend_req_refs) - requirements):
        errors.append(f"Matrix references undefined requirement {undefined}")
    for undefined in sorted((state_features | backend_features) - features):
        errors.append(f"Matrix references undefined feature {undefined}")
    prd_feature_refs = tokens_from_rows(requirement_rows, "Feature refs", "FEAT")
    for undefined in sorted(prd_feature_refs - features):
        errors.append(f"PRD references undefined feature {undefined}")
    matrix_ac_refs = (
        tokens_from_rows(state_rows, "Acceptance refs", "AC")
        | tokens_from_rows(permission_rows, "Acceptance refs", "AC")
        | tokens_from_rows(requirement_rows, "Acceptance refs", "AC")
    )
    for undefined in sorted(matrix_ac_refs - acceptance):
        errors.append(f"Matrix or PRD references undefined acceptance criterion {undefined}")

    defined_refs = requirements | features
    for row in acceptance_rows:
        ac_ids = id_tokens(row.get("Acceptance ID", ""), "AC")
        label = next(iter(ac_ids), row.get("Acceptance ID", "<unknown AC>"))
        refs = id_tokens(row.get("Requirement/feature refs", ""), "REQ") | id_tokens(row.get("Requirement/feature refs", ""), "FEAT")
        if not refs:
            errors.append(f"{label}: acceptance criterion has no REQ-* or FEAT-* reference")
        for undefined in sorted(refs - defined_refs):
            errors.append(f"{label}: references undefined item {undefined}")
        if not row.get("Evidence type/location", "").strip():
            errors.append(f"{label}: evidence type/location is empty")
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
    return print_report("Traceability check", errors, warnings)


if __name__ == "__main__":
    raise SystemExit(main())
