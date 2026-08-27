#!/usr/bin/env python3
"""Validate lifecycle state and the evidence required for a target gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import CANONICAL_STATES, INTERRUPT_STATES, REQUIRED_DOCS, find_table, parse_frontmatter, print_report, project_root, read_text
from check_missing_modules import check as check_modules
from check_traceability import check as check_traceability
from validate_documents import check as validate_documents


BUILD_GATES = ("requirements", "product", "ux", "ui", "architecture")

GATE_DOCS = {
    "requirements": ("docs/00-project-context.md", "docs/01-domain-rules.md", "docs/02-glossary.md", "docs/04-prd.md"),
    "product": ("docs/03-role-journey-matrix.md", "docs/checklists/product-completeness.md"),
    "ux": ("docs/06-ux-spec.md",),
    "ui": ("docs/07-design-system.md",),
    "architecture": ("docs/05-state-permission-matrix.md", "docs/08-system-design.md", "docs/09-api-data-contract.md"),
}

REWORK_OWNERS = {
    "REWORK_REQUIREMENTS": "requirements",
    "REWORK_PRODUCT": "product_auditor",
    "REWORK_UX": "ux",
    "REWORK_UI": "ui",
    "REWORK_ARCHITECTURE": "architect",
    "REWORK_ENGINEERING": "engineering_lead",
    "REWORK_QA": "qa",
}

REWORK_REENTRY = {
    "REWORK_REQUIREMENTS": "REQUIREMENTS_APPROVED",
    "REWORK_PRODUCT": "PRODUCT_APPROVED",
    "REWORK_UX": "UX_READY",
    "REWORK_UI": "UI_READY",
    "REWORK_ARCHITECTURE": "ARCHITECTURE_READY",
    "REWORK_ENGINEERING": "CODE_REVIEW",
    "REWORK_QA": "READY_FOR_QA",
}

ALLOWED_ENTRY_STATES = {
    "DISCOVERY": {"BACKLOG", "DISCOVERY"},
    "REQUIREMENTS_APPROVED": {"DISCOVERY", "REQUIREMENTS_APPROVED"},
    "PRODUCT_APPROVED": {"REQUIREMENTS_APPROVED", "PRODUCT_APPROVED"},
    "UX_READY": {"PRODUCT_APPROVED", "UI_READY", "ARCHITECTURE_READY", "UX_READY"},
    "UI_READY": {"UX_READY", "ARCHITECTURE_READY", "UI_READY"},
    "ARCHITECTURE_READY": {"PRODUCT_APPROVED", "UX_READY", "UI_READY", "ARCHITECTURE_READY"},
    "READY_FOR_BUILD": {"UX_READY", "UI_READY", "ARCHITECTURE_READY", "READY_FOR_BUILD"},
    "IN_DEVELOPMENT": {"READY_FOR_BUILD", "IN_DEVELOPMENT"},
    "CODE_REVIEW": {"IN_DEVELOPMENT", "CODE_REVIEW"},
    "READY_FOR_QA": {"CODE_REVIEW", "READY_FOR_QA"},
    "QA_PASS": {"READY_FOR_QA", "QA_PASS"},
    "RELEASE_READY": {"QA_PASS", "RELEASE_READY"},
    "DONE": {"RELEASE_READY", "DONE"},
}


def approved_gate(status, gate):
    data = status.get("gates", {}).get(gate, {})
    return data.get("status") == "APPROVED" and bool(data.get("version")) and bool(data.get("evidence"))


def evidence_exists(root, reference):
    if not isinstance(reference, str) or not reference.strip():
        return False
    value = reference.strip()
    if value.startswith(("https://", "http://")):
        return True
    path = (root / value).resolve() if not value.startswith("/") else Path(value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    return path.is_file()


def unresolved_business_fields(root, relatives=None):
    unresolved = []
    for relative in (relatives or REQUIRED_DOCS):
        path = root / relative
        if not path.is_file():
            continue
        for number, line in enumerate(read_text(path).splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(">") or stripped.startswith("#"):
                continue
            if (
                stripped in {"BLOCKING_UNKNOWN", "- BLOCKING_UNKNOWN"}
                or ": BLOCKING_UNKNOWN" in stripped
                or (stripped.startswith("|") and "| BLOCKING_UNKNOWN |" in stripped)
            ):
                unresolved.append(f"{relative}:{number}")
    return unresolved


def list_field(text, label):
    prefix = f"- {label}:"
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def validate_gate_evidence(root, status, gates):
    errors = []
    for gate in gates:
        data = status.get("gates", {}).get(gate, {})
        if data.get("status") != "APPROVED":
            continue
        for reference in data.get("evidence", []):
            if not evidence_exists(root, reference):
                errors.append(f"Gate '{gate}' evidence does not exist or is outside the project: {reference}")
    return errors


def validate_approval_bundle(root, status, gates):
    errors = []
    relatives = []
    for gate in gates:
        if not approved_gate(status, gate):
            errors.append(f"Gate '{gate}' must be APPROVED with version and evidence")
        relatives.extend(GATE_DOCS.get(gate, ()))
    errors.extend(validate_gate_evidence(root, status, gates))
    for relative in relatives:
        path = root / relative
        if not path.is_file():
            continue
        if parse_frontmatter(read_text(path)).get("status") != "APPROVED":
            errors.append(f"{relative}: status must be APPROVED for its gate")
    unresolved = unresolved_business_fields(root, relatives)
    if unresolved:
        preview = ", ".join(unresolved[:8])
        suffix = ", ..." if len(unresolved) > 8 else ""
        errors.append(f"Gate baseline still contains BLOCKING_UNKNOWN fields: {preview}{suffix}")
    if "product" in gates:
        module_errors, _ = check_modules(root)
        errors.extend(module_errors)
    if "requirements" in gates:
        prd_path = root / "docs/04-prd.md"
        rows = find_table(read_text(prd_path), ["Requirement ID", "Requirement", "Fact state"]) if prd_path.is_file() else []
        if not rows:
            errors.append("Requirements gate needs at least one PRD requirement row")
        for row in rows:
            if not row.get("Requirement ID") or not row.get("Requirement") or not row.get("Fact state"):
                errors.append("Requirements gate has an incomplete PRD requirement row")
    if "product" in gates:
        matrix_path = root / "docs/03-role-journey-matrix.md"
        matrix_text = read_text(matrix_path) if matrix_path.is_file() else ""
        table_specs = (
            (["Role ID", "Page ID", "Primary task", "Requirement refs"], "role-page"),
            (["Page ID", "Feature ID", "Feature/action", "Requirement refs"], "page-feature"),
            (["Feature ID", "Front-office action", "Backend/admin module or system handler", "Requirement refs"], "front-office/back-office"),
        )
        for headers, label in table_specs:
            rows = find_table(matrix_text, headers)
            if not rows:
                errors.append(f"Product gate needs at least one {label} matrix row")
                continue
            for row in rows:
                for header in headers:
                    if not row.get(header, "").strip():
                        errors.append(f"Product gate {label} matrix has an empty '{header}' cell")
    return errors


def check(root, target: str | None) -> tuple[list[str], list[str]]:
    errors, warnings = validate_documents(root)
    status_path = root / "docs/project-status.json"
    if not status_path.is_file():
        return errors, warnings
    try:
        status = json.loads(read_text(status_path))
    except (ValueError, json.JSONDecodeError):
        return errors, warnings
    current = status.get("current_state")
    all_states = set(CANONICAL_STATES) | INTERRUPT_STATES
    if current not in all_states:
        errors.append(f"Unsupported current_state: {current}")
        return errors, warnings
    if current == "BLOCKED":
        blocked = status.get("blocked")
        if not isinstance(blocked, dict) or not all(blocked.get(key) for key in ("reason", "owner", "unblock_evidence", "blocked_from", "resume_state")):
            errors.append("BLOCKED state requires a 'blocked' record with reason, owner, unblock_evidence, blocked_from, and resume_state")
        elif blocked.get("blocked_from") not in CANONICAL_STATES or blocked.get("resume_state") not in CANONICAL_STATES:
            errors.append("BLOCKED blocked_from and resume_state must be canonical states")
    if current.startswith("REWORK_"):
        rework = status.get("rework")
        required = ("defect_id", "severity", "failed_criterion", "evidence", "primary_owner", "affected_artifacts", "required_correction", "reentry_gate")
        if not isinstance(rework, dict) or not all(rework.get(key) for key in required):
            errors.append(f"{current} requires a complete 'rework' defect record")
        else:
            if rework.get("primary_owner") != REWORK_OWNERS[current]:
                errors.append(f"{current} primary_owner must be {REWORK_OWNERS[current]}")
            if rework.get("reentry_gate") != REWORK_REENTRY[current]:
                errors.append(f"{current} reentry_gate must be {REWORK_REENTRY[current]}")
            if rework.get("severity") not in {"P0", "P1", "P2", "P3"}:
                errors.append(f"{current} severity must be P0, P1, P2, or P3")
            if not evidence_exists(root, rework.get("evidence")):
                errors.append(f"{current} evidence does not exist or is outside the project: {rework.get('evidence')}")
    previous = status.get("previous_state")
    if current == "BACKLOG":
        if previous not in {None, "BACKLOG"}:
            errors.append("BACKLOG previous_state must be null or BACKLOG")
    elif current in CANONICAL_STATES:
        if previous not in ALLOWED_ENTRY_STATES.get(current, set()):
            errors.append(f"Persisted transition {previous} → {current} is invalid")
    elif current == "BLOCKED" and isinstance(status.get("blocked"), dict):
        if previous != status["blocked"].get("blocked_from"):
            errors.append("BLOCKED previous_state must equal blocked.blocked_from")
    elif current.startswith("REWORK_") and previous not in CANONICAL_STATES:
        errors.append(f"{current} previous_state must be a canonical state")
    requested = target or current
    if requested not in all_states:
        errors.append(f"Unsupported target state: {requested}")
        return errors, warnings
    if requested in INTERRUPT_STATES:
        return errors, warnings
    if target and requested in ALLOWED_ENTRY_STATES:
        valid_entry = current in ALLOWED_ENTRY_STATES[requested]
        if current == "BLOCKED" and isinstance(status.get("blocked"), dict):
            valid_entry = status["blocked"].get("resume_state") == requested
        if current.startswith("REWORK_") and isinstance(status.get("rework"), dict):
            valid_entry = status["rework"].get("reentry_gate") == requested
        if not valid_entry:
            errors.append(f"Cannot check transition {current} → {requested}; current_state is not a valid entry state")
    if requested not in {"BACKLOG", "DISCOVERY"} and status.get("open_p0_p1"):
        errors.append("Open P0/P1 items prevent downstream approval")

    gate_requirements = {
        "REQUIREMENTS_APPROVED": ("requirements",),
        "PRODUCT_APPROVED": ("requirements", "product"),
        "UX_READY": ("requirements", "product", "ux"),
        "UI_READY": ("requirements", "product", "ux", "ui"),
        "ARCHITECTURE_READY": ("requirements", "product", "ux", "architecture"),
    }

    build_or_later = {
        "READY_FOR_BUILD", "IN_DEVELOPMENT", "CODE_REVIEW", "READY_FOR_QA",
        "QA_PASS", "RELEASE_READY", "DONE",
    }
    qa_or_later = {"QA_PASS", "RELEASE_READY", "DONE"}
    ready_for_qa_or_later = {"READY_FOR_QA", "QA_PASS", "RELEASE_READY", "DONE"}
    release_or_later = {"RELEASE_READY", "DONE"}

    required_approval_gates = BUILD_GATES if requested in build_or_later else gate_requirements.get(requested, ())
    if required_approval_gates:
        errors.extend(validate_approval_bundle(root, status, required_approval_gates))
        if status.get("approval_authority") in {None, "", "BLOCKING_UNKNOWN"}:
            errors.append(f"approval_authority must be confirmed for {requested}")

    if requested in build_or_later:
        module_errors, module_warnings = check_modules(root)
        trace_errors, trace_warnings = check_traceability(root)
        errors.extend(module_errors)
        errors.extend(trace_errors)
        warnings.extend(module_warnings)
        warnings.extend(trace_warnings)
        if status.get("risk_acceptance_authority") in {None, "", "BLOCKING_UNKNOWN"}:
            errors.append("risk_acceptance_authority must be confirmed for READY_FOR_BUILD")
        for relative in REQUIRED_DOCS:
            frontmatter = parse_frontmatter(read_text(root / relative)) if (root / relative).is_file() else {}
            if frontmatter.get("status") != "APPROVED":
                errors.append(f"{relative}: status must be APPROVED for READY_FOR_BUILD or later")

    if requested in ready_for_qa_or_later:
        if not approved_gate(status, "build"):
            errors.append(f"Gate 'build' must be APPROVED with version and evidence for {requested}")
        errors.extend(validate_gate_evidence(root, status, ("build",)))

    if requested in qa_or_later:
        if not approved_gate(status, "qa"):
            errors.append("Gate 'qa' must be APPROVED with version and evidence for QA_PASS")
        errors.extend(validate_gate_evidence(root, status, ("qa",)))
        test_plan = read_text(root / "docs/10-test-plan.md") if (root / "docs/10-test-plan.md").is_file() else ""
        accepted_risk_conclusion = "- Conclusion: PASS_WITH_ACCEPTED_RISKS\n" in test_plan
        if "- Conclusion: PASS\n" not in test_plan and not accepted_risk_conclusion:
            errors.append("docs/10-test-plan.md: independent QA conclusion must be PASS or PASS_WITH_ACCEPTED_RISKS")
        qa_session = list_field(test_plan, "QA Agent/session")
        engineering_session = list_field(test_plan, "Engineering owner/session")
        if qa_session in {"", "BLOCKING_UNKNOWN"} or engineering_session in {"", "BLOCKING_UNKNOWN"}:
            errors.append("docs/10-test-plan.md: independent QA and engineering sessions must be identified")
        elif qa_session == engineering_session:
            errors.append("docs/10-test-plan.md: final QA and engineering sessions must be different")
        acceptance_rows = find_table(test_plan, ["Acceptance ID", "Evidence type/location", "Result"])
        for row in acceptance_rows:
            ac_id = row.get("Acceptance ID", "<unknown AC>")
            if row.get("Result") != "PASS":
                errors.append(f"{ac_id}: result must be PASS for QA_PASS")
            evidence = row.get("Evidence type/location", "")
            if not evidence_exists(root, evidence):
                errors.append(f"{ac_id}: acceptance evidence does not exist or is outside the project: {evidence}")
        if accepted_risk_conclusion and not status.get("accepted_risks"):
            errors.append("PASS_WITH_ACCEPTED_RISKS requires at least one recorded accepted risk")
        for risk in status.get("accepted_risks", []):
            required = ("risk_id", "severity", "description", "accepted_by", "evidence")
            if not all(risk.get(field) for field in required):
                errors.append("Every accepted risk needs risk_id, severity, description, accepted_by, and evidence")
                continue
            if risk.get("severity") not in {"P0", "P1", "P2", "P3"}:
                errors.append(f"Accepted risk {risk.get('risk_id')} has invalid severity")
            if risk.get("accepted_by") != status.get("risk_acceptance_authority"):
                errors.append(f"Accepted risk {risk.get('risk_id')} was not accepted by risk_acceptance_authority")
            if not evidence_exists(root, risk.get("evidence")):
                errors.append(f"Accepted-risk evidence does not exist or is outside the project: {risk.get('evidence')}")

    if requested in release_or_later:
        release = status.get("gates", {}).get("release", {})
        if release.get("status") not in {"APPROVED", "NOT_APPLICABLE"}:
            errors.append("Gate 'release' must be APPROVED or NOT_APPLICABLE for DONE")
        if release.get("status") == "APPROVED" and (not release.get("version") or not release.get("evidence")):
            errors.append("Approved release gate needs version and evidence")
        if release.get("status") == "APPROVED":
            errors.extend(validate_gate_evidence(root, status, ("release",)))
        if release.get("status") == "NOT_APPLICABLE" and not release.get("reason"):
            errors.append("NOT_APPLICABLE release gate needs a reason")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--target", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES), help="Check readiness for this state")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        errors, warnings = check(root, args.target)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return print_report(f"Project status check ({args.target or 'current state'})", errors, warnings)


if __name__ == "__main__":
    raise SystemExit(main())
