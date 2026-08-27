#!/usr/bin/env python3
"""Create a non-overwriting YAML task package with the required delivery contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import CANONICAL_STATES, INTERRUPT_STATES, REQUIRED_AGENTS, project_root


WORKERS = {"frontend_worker", "backend_worker", "ai_worker", "data_worker", "test_worker"}


def quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def create(root: Path, task_id: str, owner: str, reviewer: str, objective: str, stage: str, return_to: str) -> Path:
    task_id = task_id.upper()
    if not re.fullmatch(r"TASK-[A-Z0-9][A-Z0-9_-]*", task_id):
        raise ValueError("task-id must look like TASK-001 or TASK-AUTH-01")
    if owner == reviewer:
        raise ValueError("owner and reviewer must be different")
    valid_roles = set(REQUIRED_AGENTS) | WORKERS
    if owner not in valid_roles:
        raise ValueError(f"unsupported owner role: {owner}")
    if reviewer not in set(REQUIRED_AGENTS):
        raise ValueError(f"reviewer must be a professional role, got: {reviewer}")
    if stage not in set(CANONICAL_STATES) | INTERRUPT_STATES:
        raise ValueError(f"unsupported project stage: {stage}")
    if not objective.strip() or objective == "BLOCKING_UNKNOWN":
        raise ValueError("objective must be a concrete, non-empty outcome")
    if owner in WORKERS and return_to != "engineering_lead":
        raise ValueError("temporary Workers must return_to engineering_lead")
    if owner not in WORKERS and return_to != "orchestrator":
        raise ValueError("professional roles must return_to orchestrator")
    status_path = root / "docs/project-status.json"
    if not status_path.is_file():
        raise ValueError("Project is not initialized: docs/project-status.json is missing")
    destination = root / "tasks" / f"{task_id}.yaml"
    if destination.exists():
        raise ValueError(f"Task package already exists and will not be overwritten: {destination}")
    project_name = root.name
    try:
        import json

        project_name = json.loads(status_path.read_text(encoding="utf-8")).get("project", project_name)
    except (ValueError, OSError):
        pass
    may_spawn_workers = "true" if owner == "engineering_lead" else "false"
    content = f'''task_id: {quoted(task_id)}
project: {quoted(project_name)}
stage: {quoted(stage)}
status: "DRAFT"
owner: {quoted(owner)}
reviewer: {quoted(reviewer)}
return_to: {quoted(return_to)}
may_spawn_agents: false
may_spawn_workers: {may_spawn_workers}
priority: "P2"
objective: {quoted(objective)}
business_context:
  value: "BLOCKING_UNKNOWN"
  affected_roles: []
  affected_objects: []
  rule_refs: []
input_documents:
  - "docs/00-project-context.md"
  - "docs/01-domain-rules.md"
  - "docs/02-glossary.md"
  - "docs/project-status.json"
dependencies: []
scope: []
out_of_scope: []
deliverables: []
acceptance_criteria:
  - id: "AC-000"
    given: "BLOCKING_UNKNOWN"
    when: "BLOCKING_UNKNOWN"
    then: "BLOCKING_UNKNOWN"
    evidence: "BLOCKING_UNKNOWN"
allowed_files: []
forbidden:
  - "Do not change approved scope, business rules, permissions, contracts, dependencies, or external systems without Orchestrator routing."
  - "Do not perform production deployment, external messaging, purchases, credential use, destructive actions, or irreversible migrations without explicit authorization."
validation:
  commands: []
  manual: []
  evidence_locations: []
assumptions_and_risks: []
handoff:
  conclusion: "BLOCKED"
  inputs_checked: []
  artifacts: []
  evidence: []
  deviations: []
  downstream_decisions: []
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--stage", choices=CANONICAL_STATES + sorted(INTERRUPT_STATES), default="BACKLOG")
    parser.add_argument("--return-to", default="orchestrator")
    args = parser.parse_args()
    try:
        root = project_root(args.project_dir)
        destination = create(root, args.task_id, args.owner, args.reviewer, args.objective, args.stage, args.return_to)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Created task package: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
