#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
sys.path.insert(0, str(SCRIPTS))

from route_roles import source_fingerprint  # noqa: E402


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPTS / script), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def add_row(path: Path, header_starts: str, row: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(header_starts):
            lines.insert(index + 2, row)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise AssertionError(f"Table header not found in {path}: {header_starts}")


def make_task_ready(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('status: "DRAFT"', 'status: "READY_FOR_DISPATCH"', 1)
    text = text.replace('  value: "BLOCKING_UNKNOWN"', '  value: "Approved implementation value"', 1)
    text = text.replace('scope: []', 'scope:\n  - "Implement the bounded worker module"', 1)
    text = text.replace('deliverables: []', 'deliverables:\n  - "Tested worker module"', 1)
    text = text.replace('allowed_files: []', 'allowed_files:\n  - "src/worker-module.ts"', 1)
    text = text.replace('    given: "BLOCKING_UNKNOWN"', '    given: "Approved contracts exist"', 1)
    text = text.replace('    when: "BLOCKING_UNKNOWN"', '    when: "The worker implements the module"', 1)
    text = text.replace('    then: "BLOCKING_UNKNOWN"', '    then: "The module passes its contract"', 1)
    text = text.replace('    evidence: "BLOCKING_UNKNOWN"', '    evidence: "evidence/worker-result.txt"', 1)
    text = text.replace('  commands: []', '  commands:\n    - "python3 --version"', 1)
    path.write_text(text, encoding="utf-8")


def approve_for_build(root: Path) -> None:
    for path in (root / "docs").rglob("*.md"):
        text = path.read_text(encoding="utf-8").replace("status: DRAFT", "status: APPROVED")
        text = text.replace("version: 0.1.0", "version: 1.0.0")
        text = text.replace("BLOCKING_UNKNOWN", "CONFIRMED_FOR_TEST")
        path.write_text(text, encoding="utf-8")

    add_row(
        root / "docs/04-prd.md",
        "| Requirement ID |",
        "| REQ-001 | P0 | ROLE-USER / OBJ-CUSTOMER | User can view a customer profile | Complete core task | RULE-001 | FEAT-001 | AC-001 | CONFIRMED |",
    )
    add_row(
        root / "docs/03-role-journey-matrix.md",
        "| Role ID | Surface/client | Page ID |",
        "| ROLE-USER | Web | PAGE-001 | Customer profile | /customers/:id | View profile | PERM-001 | REQ-001 |",
    )
    add_row(
        root / "docs/03-role-journey-matrix.md",
        "| Page ID | Feature ID |",
        "| PAGE-001 | FEAT-001 | View profile | Primary | Profile shown | Retry | API-001 | REQ-001 |",
    )
    add_row(
        root / "docs/03-role-journey-matrix.md",
        "| Feature ID | Front-office action |",
        "| FEAT-001 | Open profile | Customer query handler | OBJ-CUSTOMER | NONE→VIEWED | System | Profile shown | AUDIT-001 | Retry | REQ-001 |",
    )
    add_row(
        root / "docs/05-state-permission-matrix.md",
        "| Feature ID | Initial |",
        "| FEAT-001 | REQUIRED | REQUIRED | REQUIRED | REQUIRED | REQUIRED | NOT_APPLICABLE | REQUIRED | REQUIRED | REQUIRED | Retry | AC-001 |",
    )
    add_row(
        root / "docs/05-state-permission-matrix.md",
        "| Role ID | Resource |",
        "| ROLE-USER | Customer profile | Assigned organization | Yes | No | No | No | No | No | Yes | API-001 | AC-001 |",
    )
    add_row(
        root / "docs/10-test-plan.md",
        "| Acceptance ID | Requirement/feature refs |",
        "| AC-001 | REQ-001 FEAT-001 | ROLE-USER / assigned | Customer exists | User opens PAGE-001 | Profile is shown | evidence/AC-001.txt | qa | PASS |",
    )
    test_plan = root / "docs/10-test-plan.md"
    text = test_plan.read_text(encoding="utf-8")
    text = text.replace("- QA Agent/session: CONFIRMED_FOR_TEST", "- QA Agent/session: qa-session-001")
    text = text.replace("- Engineering owner/session: CONFIRMED_FOR_TEST", "- Engineering owner/session: engineering-session-001")
    text = text.replace("- Conclusion: BLOCKED", "- Conclusion: PASS")
    test_plan.write_text(text, encoding="utf-8")

    for name in ("problem-quality.md", "solution-challenge.md", "quality-case.md"):
        quality_path = root / "docs/checklists" / name
        quality_text = quality_path.read_text(encoding="utf-8").replace("- Conclusion: BLOCKED", "- Conclusion: PASS")
        quality_path.write_text(quality_text, encoding="utf-8")

    checklist = root / "docs/checklists/product-completeness.md"
    lines = checklist.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("| PCM-001 |"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            lines[index] = f"| {cells[0]} | {cells[1]} | {cells[2]} | REQUIRED | COVERED | REQ-001 FEAT-001 AC-001 | Approved baseline | requirements |"
        elif line.startswith("| PCM-"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            lines[index] = f"| {cells[0]} | {cells[1]} | {cells[2]} | NOT_APPLICABLE | COVERED | | Not applicable to approved test scenario | product_auditor |"
    checklist.write_text("\n".join(lines) + "\n", encoding="utf-8")

    status_path = root / "docs/project-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["current_state"] = "ARCHITECTURE_READY"
    status["previous_state"] = "UI_READY"
    status["approval_authority"] = "product-owner"
    status["risk_acceptance_authority"] = "product-owner"
    evidence = {
        "requirements": "docs/04-prd.md",
        "product": "docs/03-role-journey-matrix.md",
        "ux": "docs/06-ux-spec.md",
        "ui": "docs/07-design-system.md",
        "architecture": "docs/08-system-design.md",
    }
    for gate in ("requirements", "product", "ux", "ui", "architecture"):
        status["gates"][gate] = {"status": "APPROVED", "version": "1.0.0", "evidence": [evidence[gate]]}
    quality_evidence = {
        "problem": "docs/checklists/problem-quality.md",
        "solution": "docs/checklists/solution-challenge.md",
        "release_evidence": "docs/checklists/quality-case.md",
    }
    quality_stage = {"problem": "DISCOVERY", "solution": "READY_FOR_BUILD", "release_evidence": "QA_PASS"}
    for gate, path in quality_evidence.items():
        status["quality_gates"][gate] = {
            "status": "APPROVED", "mode": "INLINE", "reviewer": "orchestrator",
            "session": None, "version": "1.0.0", "input_fingerprint": source_fingerprint(root, quality_stage[gate]),
            "evidence": [path],
        }
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        result = run(
            "init_project.py",
            self.root,
            "--project-name",
            "Test Project",
            "--domain",
            "CRM",
            "--complexity",
            "Standard",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        started = run("run_state.py", "start", self.root)
        self.assertEqual(started.returncode, 0, started.stdout)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_initialized_structure_is_valid_but_not_build_ready(self) -> None:
        result = run("validate_documents.py", self.root)
        self.assertEqual(result.returncode, 0, result.stdout)
        missing = run("check_missing_modules.py", self.root)
        trace = run("check_traceability.py", self.root)
        ready = run("check_project_status.py", self.root, "--target", "READY_FOR_BUILD")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(trace.returncode, 1)
        self.assertEqual(ready.returncode, 1)

    def test_initialization_refuses_overwrite_before_writing(self) -> None:
        sentinel = self.root / "AGENTS.md"
        before = sentinel.read_text(encoding="utf-8")
        result = run(
            "init_project.py",
            self.root,
            "--project-name",
            "Changed",
            "--domain",
            "SaaS",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("stopped before writing", result.stdout)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), before)

    def test_task_package_guards(self) -> None:
        created = run(
            "create_task_package.py",
            self.root,
            "--task-id",
            "TASK-001",
            "--owner",
            "engineering_lead",
            "--reviewer",
            "qa",
            "--objective",
            "Build approved flow",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        duplicate = run(
            "create_task_package.py",
            self.root,
            "--task-id",
            "TASK-001",
            "--owner",
            "engineering_lead",
            "--reviewer",
            "qa",
            "--objective",
            "Overwrite",
        )
        self.assertEqual(duplicate.returncode, 2)
        invalid_worker = run(
            "create_task_package.py",
            self.root,
            "--task-id",
            "TASK-002",
            "--owner",
            "frontend_worker",
            "--reviewer",
            "engineering_lead",
            "--objective",
            "Build UI",
        )
        self.assertEqual(invalid_worker.returncode, 2)
        self.assertIn("return_to engineering_lead", invalid_worker.stdout)
        invalid_stage = run(
            "create_task_package.py",
            self.root,
            "--task-id",
            "TASK-003",
            "--owner",
            "qa",
            "--reviewer",
            "orchestrator",
            "--objective",
            "Run acceptance",
            "--stage",
            "TELEPORT",
        )
        self.assertEqual(invalid_stage.returncode, 2)
        invalid_return = run(
            "create_task_package.py",
            self.root,
            "--task-id",
            "TASK-004",
            "--owner",
            "qa",
            "--reviewer",
            "orchestrator",
            "--objective",
            "Run acceptance",
            "--return-to",
            "engineering_lead",
        )
        self.assertEqual(invalid_return.returncode, 2)

    def test_balanced_engineering_can_delegate_one_governed_worker(self) -> None:
        approve_for_build(self.root)
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "READY_FOR_BUILD"
        status["previous_state"] = "ARCHITECTURE_READY"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        routed = run(
            "route_roles.py", self.root, "--stage", "IN_DEVELOPMENT", "--quota", "balanced",
            "--signal", "implementation_workers", "--write",
        )
        self.assertEqual(routed.returncode, 0, routed.stdout)
        plan = json.loads((self.root / ".codex/orchestration/role-plan.json").read_text(encoding="utf-8"))
        self.assertIn("frontend_worker", plan["delegable_workers"])
        self.assertEqual(plan["max_concurrent_workers"], 1)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["execution_control"]["quota_mode"], "balanced")
        self.assertEqual(status["execution_control"]["max_active_subagents"], 2)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-WORKER-1",
            "--owner", "frontend_worker", "--reviewer", "engineering_lead",
            "--return-to", "engineering_lead", "--stage", "IN_DEVELOPMENT",
            "--objective", "Implement the approved frontend module", "--task-type", "implementation",
            "--available-model", "gpt-5.6-luna", "--available-model", "gpt-5.6-terra",
            "--available-model", "gpt-5.6-sol",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        make_task_ready(self.root / "tasks/TASK-WORKER-1.yaml")
        missing_parent = run(
            "check_execution_plan.py", self.root, "tasks/TASK-WORKER-1.yaml",
            "--available-model", "gpt-5.6-luna", "--available-model", "gpt-5.6-terra",
            "--available-model", "gpt-5.6-sol",
        )
        self.assertEqual(missing_parent.returncode, 3, missing_parent.stdout)
        self.assertIn("BLOCKED_WORKER_PARENT", missing_parent.stdout)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["execution_control"]["active_sessions"] = [{
            "session_id": "eng-session-1", "task_id": "TASK-ENGINEERING-1",
            "role": "engineering_lead", "parent_role": "orchestrator", "access_mode": "write",
        }]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        duplicate_engineering = run(
            "create_task_package.py", self.root, "--task-id", "TASK-ENGINEERING-2",
            "--owner", "engineering_lead", "--reviewer", "qa", "--stage", "IN_DEVELOPMENT",
            "--objective", "Attempt a duplicate engineering session", "--task-type", "implementation",
            "--available-model", "gpt-5.6-luna", "--available-model", "gpt-5.6-terra",
            "--available-model", "gpt-5.6-sol",
        )
        self.assertEqual(duplicate_engineering.returncode, 0, duplicate_engineering.stdout)
        make_task_ready(self.root / "tasks/TASK-ENGINEERING-2.yaml")
        duplicate_blocked = run(
            "check_execution_plan.py", self.root, "tasks/TASK-ENGINEERING-2.yaml",
            "--available-model", "gpt-5.6-luna", "--available-model", "gpt-5.6-terra",
            "--available-model", "gpt-5.6-sol",
        )
        self.assertEqual(duplicate_blocked.returncode, 3, duplicate_blocked.stdout)
        self.assertIn("BLOCKED_DUPLICATE_ROLE", duplicate_blocked.stdout)
        ready = run(
            "check_execution_plan.py", self.root, "tasks/TASK-WORKER-1.yaml",
            "--available-model", "gpt-5.6-luna", "--available-model", "gpt-5.6-terra",
            "--available-model", "gpt-5.6-sol",
        )
        self.assertEqual(ready.returncode, 0, ready.stdout)

        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["execution_control"]["active_sessions"].append({
            "session_id": "worker-session-1", "task_id": "TASK-WORKER-OTHER",
            "role": "backend_worker", "parent_role": "engineering_lead", "access_mode": "write",
        })
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        no_third_slot = run(
            "check_execution_plan.py", self.root, "tasks/TASK-WORKER-1.yaml",
            "--available-model", "gpt-5.6-luna", "--available-model", "gpt-5.6-terra",
            "--available-model", "gpt-5.6-sol",
        )
        self.assertEqual(no_third_slot.returncode, 3, no_third_slot.stdout)
        self.assertIn("no subagent slot", no_third_slot.stdout)
        refused_downgrade = run(
            "route_roles.py", self.root, "--stage", "IN_DEVELOPMENT", "--quota", "economy",
            "--signal", "implementation_workers", "--write",
        )
        self.assertEqual(refused_downgrade.returncode, 2, refused_downgrade.stdout)
        status_after_refusal = json.loads(status_path.read_text(encoding="utf-8"))
        plan_after_refusal = json.loads(
            (self.root / ".codex/orchestration/role-plan.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status_after_refusal["execution_control"]["quota_mode"], "balanced")
        self.assertEqual(plan_after_refusal["quota_mode"], "balanced")
        status["execution_control"]["active_sessions"] = status["execution_control"]["active_sessions"][:1]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

        economy = run(
            "route_roles.py", self.root, "--stage", "IN_DEVELOPMENT", "--quota", "economy",
            "--signal", "implementation_workers", "--write",
        )
        self.assertEqual(economy.returncode, 0, economy.stdout)
        rejected = run(
            "create_task_package.py", self.root, "--task-id", "TASK-WORKER-2",
            "--owner", "backend_worker", "--reviewer", "engineering_lead",
            "--return-to", "engineering_lead", "--stage", "IN_DEVELOPMENT",
            "--objective", "Must stay within economy budget", "--task-type", "implementation",
        )
        self.assertEqual(rejected.returncode, 2, rejected.stdout)
        self.assertIn("not required_now or delegable", rejected.stdout)

    def test_active_worker_cannot_be_orphaned(self) -> None:
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["execution_control"]["quota_mode"] = "balanced"
        status["execution_control"]["max_active_subagents"] = 2
        status["execution_control"]["active_sessions"] = [{
            "session_id": "worker-session-orphan", "task_id": "TASK-WORKER-ORPHAN",
            "role": "frontend_worker", "parent_role": "engineering_lead", "access_mode": "write",
        }]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        result = run("validate_documents.py", self.root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("active Worker requires an active Engineering Lead", result.stdout)

    def test_project_name_is_json_safe_and_blank_input_fails(self) -> None:
        second = Path(self.temp.name) / "quoted"
        quoted = run(
            "init_project.py",
            second,
            "--project-name",
            'Customer "North"',
            "--domain",
            "SaaS",
        )
        self.assertEqual(quoted.returncode, 0, quoted.stdout)
        status = json.loads((second / "docs/project-status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["project"], 'Customer "North"')
        context = (second / "docs/00-project-context.md").read_text(encoding="utf-8")
        self.assertIn('title: "Customer \\"North\\" — Project Context"', context)
        blank = run(
            "init_project.py",
            Path(self.temp.name) / "blank",
            "--project-name",
            "   ",
            "--domain",
            "CRM",
        )
        self.assertEqual(blank.returncode, 2)

    def test_ready_for_build_passes_with_complete_evidence(self) -> None:
        approve_for_build(self.root)
        result = run("check_project_status.py", self.root, "--target", "READY_FOR_BUILD")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_quality_subgates_block_their_transitions(self) -> None:
        approve_for_build(self.root)
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "DISCOVERY"
        status["previous_state"] = "BACKLOG"
        status["quality_gates"]["problem"]["status"] = "PENDING"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        problem = run("check_project_status.py", self.root, "--target", "REQUIREMENTS_APPROVED")
        self.assertEqual(problem.returncode, 1, problem.stdout)
        self.assertIn("Quality gate 'problem' must be APPROVED", problem.stdout)

        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "ARCHITECTURE_READY"
        status["previous_state"] = "UI_READY"
        status["quality_gates"]["problem"] = {
            "status": "APPROVED", "mode": "INLINE", "reviewer": "orchestrator", "session": None,
            "version": "1.0.0", "input_fingerprint": "a" * 64,
            "evidence": ["docs/checklists/problem-quality.md"],
        }
        status["quality_gates"]["solution"]["status"] = "PENDING"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        solution = run("check_project_status.py", self.root, "--target", "READY_FOR_BUILD")
        self.assertEqual(solution.returncode, 1, solution.stdout)
        self.assertIn("Quality gate 'solution' must be APPROVED", solution.stdout)

        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "QA_PASS"
        status["previous_state"] = "READY_FOR_QA"
        status["quality_gates"]["release_evidence"]["status"] = "PENDING"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        release = run("check_project_status.py", self.root, "--target", "RELEASE_READY")
        self.assertEqual(release.returncode, 1, release.stdout)
        self.assertIn("Quality gate 'release_evidence' must be APPROVED", release.stdout)

    def test_build_gate_rejects_unknowns_and_fake_evidence(self) -> None:
        approve_for_build(self.root)
        context = self.root / "docs/00-project-context.md"
        context.write_text(context.read_text(encoding="utf-8") + "\n- Decision: BLOCKING_UNKNOWN\n", encoding="utf-8")
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["gates"]["requirements"]["evidence"] = ["evidence/does-not-exist.txt"]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        result = run("check_project_status.py", self.root, "--target", "READY_FOR_BUILD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("BLOCKING_UNKNOWN", result.stdout)
        self.assertIn("evidence does not exist", result.stdout)

    def test_traceability_rejects_undefined_reference_and_empty_matrix_cells(self) -> None:
        approve_for_build(self.root)
        path = self.root / "docs/03-role-journey-matrix.md"
        text = path.read_text(encoding="utf-8").replace("| ROLE-USER | Web | PAGE-001 | Customer profile | /customers/:id | View profile | PERM-001 | REQ-001 |", "| ROLE-USER | Web | PAGE-001 | | | | | REQ-999 |")
        path.write_text(text, encoding="utf-8")
        result = run("check_traceability.py", self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("undefined requirement REQ-999", result.stdout)
        self.assertIn("required matrix cell is empty", result.stdout)

    def test_blocked_state_requires_record(self) -> None:
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "BLOCKED"
        status["blocked"] = None
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        result = run("check_project_status.py", self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires a 'blocked' record", result.stdout)

    def test_transition_cannot_skip_from_backlog(self) -> None:
        result = run("check_project_status.py", self.root, "--target", "READY_FOR_QA")
        self.assertEqual(result.returncode, 1)
        self.assertIn("current_state is not a valid entry state", result.stdout)

    def test_persisted_transition_is_validated_without_target(self) -> None:
        approve_for_build(self.root)
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "READY_FOR_BUILD"
        status["previous_state"] = "BACKLOG"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        result = run("check_project_status.py", self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Persisted transition BACKLOG → READY_FOR_BUILD is invalid", result.stdout)

    def test_early_requirements_gate_rejects_draft_unknowns_and_fake_evidence(self) -> None:
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "DISCOVERY"
        status["previous_state"] = "BACKLOG"
        status["approval_authority"] = "product-owner"
        status["gates"]["requirements"] = {
            "status": "APPROVED",
            "version": "1.0.0",
            "evidence": ["evidence/missing-requirements.txt"],
        }
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        result = run("check_project_status.py", self.root, "--target", "REQUIREMENTS_APPROVED")
        self.assertEqual(result.returncode, 1)
        self.assertIn("evidence does not exist", result.stdout)
        self.assertIn("status must be APPROVED for its gate", result.stdout)
        self.assertIn("BLOCKING_UNKNOWN", result.stdout)

    def test_rework_owner_and_record_are_validated(self) -> None:
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "REWORK_UI"
        status["previous_state"] = "UI_READY"
        status["rework"] = {"defect_id": "BUG-001", "primary_owner": "requirements", "reentry_gate": "UI_READY"}
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        result = run("check_project_status.py", self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("complete 'rework' defect record", result.stdout)
        status["rework"] = {
            "defect_id": "BUG-001",
            "severity": "P1",
            "failed_criterion": "AC-001",
            "evidence": "evidence/BUG-001.txt",
            "primary_owner": "requirements",
            "affected_artifacts": ["docs/07-design-system.md"],
            "required_correction": "Correct visual hierarchy",
            "reentry_gate": "UI_READY",
        }
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        wrong_owner = run("check_project_status.py", self.root)
        self.assertEqual(wrong_owner.returncode, 1)
        self.assertIn("primary_owner must be ui", wrong_owner.stdout)
        self.assertIn("evidence does not exist", wrong_owner.stdout)

        evidence = self.root / "evidence/BUG-001.txt"
        evidence.write_text("sanitized defect evidence\n", encoding="utf-8")
        status["rework"]["primary_owner"] = "ui"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        valid = run("check_project_status.py", self.root)
        self.assertEqual(valid.returncode, 0, valid.stdout)

    def test_qa_and_done_require_real_evidence(self) -> None:
        approve_for_build(self.root)
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "READY_FOR_QA"
        status["previous_state"] = "CODE_REVIEW"
        status["gates"]["build"] = {"status": "APPROVED", "version": "1.0.0", "evidence": ["docs/08-system-design.md"]}
        status["gates"]["qa"] = {"status": "APPROVED", "version": "1.0.0", "evidence": ["docs/10-test-plan.md"]}
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        missing = run("check_project_status.py", self.root, "--target", "QA_PASS")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("AC-001: acceptance evidence does not exist", missing.stdout)
        evidence = self.root / "evidence/AC-001.txt"
        evidence.write_text("sanitized test evidence\n", encoding="utf-8")
        test_plan = self.root / "docs/10-test-plan.md"
        original = test_plan.read_text(encoding="utf-8")
        test_plan.write_text(original.replace("engineering-session-001", "qa-session-001"), encoding="utf-8")
        same_session = run("check_project_status.py", self.root, "--target", "QA_PASS")
        self.assertEqual(same_session.returncode, 1)
        self.assertIn("final QA and engineering sessions must be different", same_session.stdout)
        test_plan.write_text(original, encoding="utf-8")
        qa_pass = run("check_project_status.py", self.root, "--target", "QA_PASS")
        self.assertEqual(qa_pass.returncode, 0, qa_pass.stdout)

        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "QA_PASS"
        status["previous_state"] = "READY_FOR_QA"
        status["gates"]["release"] = {"status": "APPROVED", "version": "1.0.0", "evidence": ["docs/10-test-plan.md"]}
        status["quality_gates"]["release_evidence"]["input_fingerprint"] = source_fingerprint(self.root, "QA_PASS")
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        release = run("check_project_status.py", self.root, "--target", "RELEASE_READY")
        self.assertEqual(release.returncode, 0, release.stdout)
        status["current_state"] = "RELEASE_READY"
        status["previous_state"] = "QA_PASS"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        done = run("check_project_status.py", self.root, "--target", "DONE")
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_pass_with_accepted_risks_needs_a_record(self) -> None:
        approve_for_build(self.root)
        (self.root / "evidence/AC-001.txt").write_text("sanitized evidence\n", encoding="utf-8")
        test_plan = self.root / "docs/10-test-plan.md"
        test_plan.write_text(test_plan.read_text(encoding="utf-8").replace("- Conclusion: PASS\n", "- Conclusion: PASS_WITH_ACCEPTED_RISKS\n"), encoding="utf-8")
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["current_state"] = "READY_FOR_QA"
        status["previous_state"] = "CODE_REVIEW"
        status["gates"]["build"] = {"status": "APPROVED", "version": "1.0.0", "evidence": ["docs/08-system-design.md"]}
        status["gates"]["qa"] = {"status": "APPROVED", "version": "1.0.0", "evidence": ["docs/10-test-plan.md"]}
        status["accepted_risks"] = []
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        result = run("check_project_status.py", self.root, "--target", "QA_PASS")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires at least one recorded accepted risk", result.stdout)
        risk_evidence = self.root / "evidence/RISK-001.txt"
        risk_evidence.write_text("signed risk decision\n", encoding="utf-8")
        status["accepted_risks"] = [{
            "risk_id": "RISK-001",
            "severity": "P2",
            "description": "Known low-impact limitation",
            "accepted_by": "unauthorized-person",
            "evidence": "evidence/RISK-001.txt",
        }]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        unauthorized = run("check_project_status.py", self.root, "--target", "QA_PASS")
        self.assertEqual(unauthorized.returncode, 1)
        self.assertIn("was not accepted by risk_acceptance_authority", unauthorized.stdout)
        status["accepted_risks"][0]["accepted_by"] = status["risk_acceptance_authority"]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        authorized = run("check_project_status.py", self.root, "--target", "QA_PASS")
        self.assertEqual(authorized.returncode, 0, authorized.stdout)


if __name__ == "__main__":
    unittest.main()
