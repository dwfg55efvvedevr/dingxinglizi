#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
sys.path.insert(0, str(SCRIPTS))

from model_routing import route_task  # noqa: E402
from role_routing import route_roles  # noqa: E402
from resolve_capabilities import configure_mcp, download_skill  # noqa: E402
from dispatch_receipt import receipt_path  # noqa: E402


def run(script: str, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPTS / script), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def make_task_ready(path: Path, *, quality: bool = False) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('status: "DRAFT"', 'status: "READY_FOR_DISPATCH"', 1)
    text = text.replace('  value: "BLOCKING_UNKNOWN"', '  value: "Approved test value"', 1)
    text = text.replace('scope: []', 'scope:\n  - "Complete the bounded test objective"', 1)
    text = text.replace('deliverables: []', 'deliverables:\n  - "Verified test deliverable"', 1)
    text = text.replace('allowed_files: []', 'allowed_files:\n  - "docs/00-project-context.md"', 1)
    text = text.replace('    given: "BLOCKING_UNKNOWN"', '    given: "Approved inputs exist"', 1)
    text = text.replace('    when: "BLOCKING_UNKNOWN"', '    when: "The owner performs the task"', 1)
    text = text.replace('    then: "BLOCKING_UNKNOWN"', '    then: "The expected result is observable"', 1)
    text = text.replace('    evidence: "BLOCKING_UNKNOWN"', '    evidence: "evidence/TASK-result.txt"', 1)
    text = text.replace('  commands: []', '  commands:\n    - "python3 --version"', 1)
    if quality:
        text = text.replace('  decision_question: "BLOCKING_UNKNOWN"', '  decision_question: "Is the current claim supported?"', 1)
        text = text.replace('  quality_case_ref: "BLOCKING_UNKNOWN"', '  quality_case_ref: "docs/checklists/problem-quality.md"', 1)
    path.write_text(text, encoding="utf-8")


def mark_task_completed(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('status: "READY_FOR_DISPATCH"', 'status: "COMPLETED"', 1)
    text = text.replace('  conclusion: "BLOCKED"', '  conclusion: "COMPLETED"', 1)
    text = text.replace('  artifacts: []', '  artifacts:\n    - "docs/04-prd.md"', 1)
    path.write_text(text, encoding="utf-8")


class ModelRoutingTests(unittest.TestCase):
    def test_identical_input_is_deterministic(self) -> None:
        kwargs = dict(complexity="Complex", task_type="architecture", role="architect", risk_flags=["security"])
        self.assertEqual(route_task(**kwargs), route_task(**kwargs))

    def test_role_task_and_risk_floors(self) -> None:
        scan = route_task(complexity="Simple", task_type="scan", role="frontend_worker")
        self.assertEqual(scan["selected_model"], "gpt-5.6-luna")
        implementation = route_task(complexity="Standard", task_type="implementation", role="engineering_lead")
        self.assertEqual(implementation["selected_model"], "gpt-5.6-terra")
        self.assertEqual(implementation["model_reasoning_effort"], "high")
        security = route_task(
            complexity="Standard", task_type="implementation", role="engineering_lead", risk_flags=["security"]
        )
        self.assertEqual(security["selected_model"], "gpt-5.6-sol")

    def test_failure_escalation_is_bounded_and_classified(self) -> None:
        first = route_task(
            complexity="Simple", task_type="scan", role="frontend_worker",
            failed_attempts=1, failure_type="quality",
        )
        self.assertEqual(first["selected_model"], "gpt-5.6-luna")
        self.assertEqual(first["model_reasoning_effort"], "medium")
        environment = route_task(
            complexity="Simple", task_type="scan", role="frontend_worker",
            failed_attempts=1, failure_type="network",
        )
        self.assertEqual(environment["model_reasoning_effort"], "low")
        second = route_task(
            complexity="Simple", task_type="requirements", role="requirements",
            failed_attempts=2, failure_type="quality",
        )
        self.assertEqual(second["selected_model"], "gpt-5.6-sol")
        exhausted = route_task(
            complexity="Simple", task_type="scan", role="frontend_worker",
            failed_attempts=3, failure_type="quality",
        )
        self.assertEqual(exhausted["status"], "BLOCKED_ATTEMPTS_EXHAUSTED")

    def test_high_risk_route_does_not_silently_downgrade(self) -> None:
        result = route_task(
            complexity="Complex", task_type="security_review", role="architect",
            risk_flags=["security"], available_models=["gpt-5.6-terra"],
        )
        self.assertEqual(result["status"], "BLOCKED_MODEL_UNAVAILABLE")
        self.assertEqual(result["selected_model"], "")

    def test_unknown_task_risk_and_empty_availability_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            route_task(complexity="Standard", task_type="securty_review", role="architect")
        with self.assertRaises(ValueError):
            route_task(
                complexity="Standard", task_type="security_review", role="architect", risk_flags=["securty"]
            )
        empty = route_task(
            complexity="Simple", task_type="scan", role="frontend_worker", available_models=[]
        )
        self.assertEqual(empty["status"], "BLOCKED_MODEL_UNAVAILABLE")


class RoleRoutingTests(unittest.TestCase):
    def test_identical_role_input_is_deterministic(self) -> None:
        kwargs = dict(complexity="Complex", stage="DISCOVERY", quota_mode="economy", signals=["novel_problem"])
        self.assertEqual(route_roles(**kwargs), route_roles(**kwargs))

    def test_simple_discovery_starts_only_requirements(self) -> None:
        plan = route_roles(complexity="Simple", stage="DISCOVERY")
        self.assertEqual(plan["required_now"], ["requirements"])
        self.assertFalse(plan["orchestrator"]["spawn"])
        self.assertNotIn("qa", plan["required_now"])

    def test_complex_does_not_start_all_roles(self) -> None:
        plan = route_roles(complexity="Complex", stage="DISCOVERY")
        self.assertEqual(plan["required_now"], ["requirements"])
        self.assertEqual(plan["deferred_sequence"], ["quality_governor"])
        self.assertEqual(plan["execution_waves"], [["requirements"], ["quality_governor"]])
        self.assertLess(len(plan["required_now"]), len(plan["deferred_available"]))

    def test_standard_product_gate_only_uses_product_auditor(self) -> None:
        plan = route_roles(complexity="Standard", stage="REQUIREMENTS_APPROVED")
        self.assertEqual(plan["required_now"], ["product_auditor"])

    def test_ready_for_qa_activates_qa_not_engineering(self) -> None:
        plan = route_roles(complexity="Complex", stage="READY_FOR_QA")
        self.assertEqual(plan["required_now"], ["qa"])
        self.assertNotIn("engineering_lead", plan["required_now"])

    def test_solution_quality_blocks_owner_until_approved_then_reuses(self) -> None:
        pending = route_roles(
            complexity="Standard", stage="READY_FOR_BUILD", input_fingerprint="b" * 64,
        )
        self.assertEqual(pending["required_now"], [])
        self.assertEqual(pending["quality_review_status"], "INLINE_REQUIRED")
        approved = route_roles(
            complexity="Standard", stage="READY_FOR_BUILD", input_fingerprint="b" * 64,
            quality_gate_record={"status": "APPROVED", "input_fingerprint": "b" * 64},
        )
        self.assertEqual(approved["quality_review_status"], "REUSE_APPROVAL")
        self.assertEqual(approved["required_now"], ["engineering_lead"])

    def test_high_impact_adds_sequential_quality_governor(self) -> None:
        plan = route_roles(
            complexity="Standard", stage="DISCOVERY", quota_mode="balanced",
            signals=["high_impact", "parallel_safe"],
        )
        self.assertEqual(plan["required_now"], ["requirements"])
        self.assertEqual(plan["deferred_sequence"], ["quality_governor"])
        self.assertEqual(plan["execution_waves"], [["requirements"], ["quality_governor"]])

    def test_completed_role_advances_to_next_wave(self) -> None:
        first = route_roles(
            complexity="Complex", stage="CODE_REVIEW", quota_mode="economy",
            signals=["contract_delta"],
        )
        self.assertEqual(first["required_now"], ["engineering_lead"])
        self.assertEqual(first["deferred_sequence"], ["architect"])
        second = route_roles(
            complexity="Complex", stage="CODE_REVIEW", quota_mode="economy",
            signals=["contract_delta"], completed_roles=["engineering_lead"],
        )
        self.assertEqual(second["required_now"], ["architect"])
        self.assertEqual(second["completed_roles"], ["engineering_lead"])

    def test_parallel_budget_never_exceeds_two(self) -> None:
        plan = route_roles(
            complexity="Complex", stage="DISCOVERY", quota_mode="quality_first",
            signals=["parallel_safe"],
        )
        self.assertLessEqual(max(map(len, plan["execution_waves"])), 2)

    def test_quality_governor_model_floor_is_task_routed(self) -> None:
        standard = route_task(complexity="Standard", task_type="solution_challenge", role="quality_governor")
        complex_route = route_task(complexity="Complex", task_type="solution_challenge", role="quality_governor")
        self.assertEqual((standard["selected_model"], standard["model_reasoning_effort"]), ("gpt-5.6-terra", "high"))
        self.assertEqual((complex_route["selected_model"], complex_route["model_reasoning_effort"]), ("gpt-5.6-sol", "high"))

    def test_unknown_role_signal_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            route_roles(complexity="Standard", stage="DISCOVERY", signals=["start_everyone"])


class CapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        result = run(
            "init_project.py", self.root,
            "--project-name", "Automation Test", "--domain", "SaaS", "--complexity", "Standard",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        started = run("run_state.py", "start", self.root)
        self.assertEqual(started.returncode, 0, started.stdout)
        inventory = self.root / ".codex/orchestration/runtime-inventory.json"
        inventory.write_text(json.dumps({
            "schema_version": 1,
            "status": "VERIFIED",
            "runtime_id": "test-runtime",
            "host_id": "test-host",
            "runtime_version": "test-version",
            "evidence_source": "test-fixture",
            "available_models": ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"],
            "available_skills": [],
            "available_mcp_servers": [],
            "verified_at": "2026-08-27T00:00:00Z",
            "verified_by": "test-runtime",
        }, indent=2) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @property
    def catalog_path(self) -> Path:
        return self.root / ".codex/orchestration/capability-catalog.json"

    def write_catalog(self, capabilities: dict[str, object]) -> None:
        self.catalog_path.write_text(
            json.dumps({"catalog_version": "1.0.0", "capabilities": capabilities}, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_task_package_contains_route_and_capability_contract(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        result = run(
            "create_task_package.py", self.root, "--task-id", "TASK-AUTO-1",
            "--owner", "requirements", "--reviewer", "qa",
            "--objective", "Establish approved permission intent", "--task-type", "requirements", "--stage", "DISCOVERY",
            "--risk", "permissions", "--required-capability", "github-read",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        task_path = self.root / "tasks/TASK-AUTO-1.yaml"
        make_task_ready(task_path)
        text = task_path.read_text(encoding="utf-8")
        self.assertRegex(text, r'(?m)^run_id: "RUN-\d{8}T\d{6}Z-[a-f0-9]{6}"$')
        self.assertRegex(text, r'(?m)^source_input_fingerprint: "[a-f0-9]{64}"$')
        self.assertIn('preferred_model: "gpt-5.6-sol"', text)
        self.assertIn('model_reasoning_effort: "high"', text)
        self.assertIn('required:\n    - "github-read"', text)
        blocked = run("check_execution_plan.py", self.root, "tasks/TASK-AUTO-1.yaml")
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn("BLOCKED_CAPABILITY", blocked.stdout)
        skill = self.root / ".agents/skills/github-read"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: github-read\ndescription: test\n---\n", encoding="utf-8")
        still_blocked = run("check_execution_plan.py", self.root, "tasks/TASK-AUTO-1.yaml")
        self.assertEqual(still_blocked.returncode, 3, still_blocked.stdout)
        self.assertIn("BLOCKED_CAPABILITY", still_blocked.stdout)
        inventory_path = self.root / ".codex/orchestration/runtime-inventory.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        inventory["available_skills"] = ["github-read"]
        inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        ready = run("check_execution_plan.py", self.root, "tasks/TASK-AUTO-1.yaml", "--record-ready")
        self.assertEqual(ready.returncode, 0, ready.stdout)
        receipt = json.loads(receipt_path(self.root, "TASK-AUTO-1").read_text(encoding="utf-8"))
        self.assertEqual(receipt["schema_version"], 2)
        self.assertRegex(receipt["run_id"], r"^RUN-\d{8}T\d{6}Z-[a-f0-9]{6}$")
        self.assertEqual(receipt["source_input_fingerprint"], json.loads(
            (self.root / ".codex/orchestration/role-plan.json").read_text(encoding="utf-8")
        )["input_fingerprint"])

    def test_preflight_rejects_detached_and_stale_task_lineage(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-LINEAGE-1",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Verify task lineage", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        task = self.root / "tasks/TASK-LINEAGE-1.yaml"
        make_task_ready(task)
        text = task.read_text(encoding="utf-8")
        text = re.sub(r'(?m)^run_id: ".*"$', 'run_id: "NOT_ATTACHED"', text, count=1)
        text = re.sub(
            r'(?m)^source_input_fingerprint: ".*"$',
            'source_input_fingerprint: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"',
            text, count=1,
        )
        task.write_text(text, encoding="utf-8")
        blocked = run("check_execution_plan.py", self.root, "tasks/TASK-LINEAGE-1.yaml")
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn("run_id must reference", blocked.stdout)
        self.assertIn("STALE_TASK_INPUT", blocked.stdout)

    def test_dispatch_receipt_rejects_unsafe_task_id_and_symlink_escape(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-SAFE-ID",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Verify receipt path safety", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        task_path = self.root / "tasks/TASK-SAFE-ID.yaml"
        make_task_ready(task_path)
        safe_text = task_path.read_text(encoding="utf-8")
        outside = Path(self.temp.name) / "outside"
        for unsafe in ("../../../outside/QA-ESCAPE", "/tmp/QA-ESCAPE"):
            task_path.write_text(
                safe_text.replace('task_id: "TASK-SAFE-ID"', f'task_id: "{unsafe}"', 1),
                encoding="utf-8",
            )
            blocked = run("check_execution_plan.py", self.root, "tasks/TASK-SAFE-ID.yaml", "--record-ready")
            self.assertEqual(blocked.returncode, 3, blocked.stdout)
            self.assertIn("task_id must match", blocked.stdout)
            with self.assertRaises(ValueError):
                receipt_path(self.root, unsafe)
        task_path.write_text(safe_text, encoding="utf-8")
        dispatch_dir = self.root / "evidence/dispatch"
        dispatch_dir.parent.mkdir(parents=True, exist_ok=True)
        outside.mkdir(parents=True, exist_ok=True)
        dispatch_dir.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            receipt_path(self.root, "TASK-SAFE-ID")

    def test_draft_task_contract_never_reports_ready(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-DRAFT-1",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Establish project facts", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        blocked = run("check_execution_plan.py", self.root, "tasks/TASK-DRAFT-1.yaml")
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn("status must be READY_FOR_DISPATCH", blocked.stdout)
        self.assertIn("scope must contain", blocked.stdout)
        self.assertIn("writing tasks need bounded allowed_files", blocked.stdout)

    def test_execution_preflight_detects_route_tampering(self) -> None:
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-ROUTE-1",
            "--owner", "engineering_lead", "--reviewer", "qa",
            "--objective", "Implement approved module", "--task-type", "implementation",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        task = self.root / "tasks/TASK-ROUTE-1.yaml"
        text = task.read_text(encoding="utf-8").replace(
            'selected_model: "gpt-5.6-terra"', 'selected_model: "gpt-5.6-luna"'
        )
        text = text.replace('routing_mode: "explicit_spawn_override"', 'routing_mode: "parent_inheritance"')
        text = text.replace("attempt: 1", "attempt: 99").replace("max_attempts: 3", "max_attempts: 999")
        task.write_text(text, encoding="utf-8")
        result = run("check_execution_plan.py", self.root, "tasks/TASK-ROUTE-1.yaml")
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("ROUTE_MISMATCH", result.stdout)

    def test_execution_preflight_detects_role_plan_tampering(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-ROLE-1",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Establish project facts", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        plan_path = self.root / ".codex/orchestration/role-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["max_active_subagents"] = 99
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        result = run("check_execution_plan.py", self.root, "tasks/TASK-ROLE-1.yaml")
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("ROLE_ROUTE_MISMATCH", result.stdout)

    def test_execution_preflight_blocks_stale_role_inputs(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-STALE-1",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Establish current project facts", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        make_task_ready(self.root / "tasks/TASK-STALE-1.yaml")
        ready = run("check_execution_plan.py", self.root, "tasks/TASK-STALE-1.yaml")
        self.assertEqual(ready.returncode, 0, ready.stdout)
        context = self.root / "docs/00-project-context.md"
        context.write_text(context.read_text(encoding="utf-8") + "\nMaterial input change.\n", encoding="utf-8")
        stale = run("check_execution_plan.py", self.root, "tasks/TASK-STALE-1.yaml")
        self.assertEqual(stale.returncode, 3, stale.stdout)
        self.assertIn("STALE_ROLE_PLAN", stale.stdout)

    def test_execution_preflight_reserves_quota_for_prospective_owner(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-SLOT-1",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Establish project facts", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        make_task_ready(self.root / "tasks/TASK-SLOT-1.yaml")
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["execution_control"]["active_sessions"] = [{
            "session_id": "active-1", "task_id": "TASK-OTHER", "role": "product_auditor",
            "parent_role": "orchestrator", "access_mode": "read-only",
        }]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        blocked = run("check_execution_plan.py", self.root, "tasks/TASK-SLOT-1.yaml")
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn("no subagent slot", blocked.stdout)
        self.assertIn("outside the current wave", blocked.stdout)

    def test_balanced_cannot_start_duplicate_professional_role(self) -> None:
        routed = run("route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced", "--write")
        self.assertEqual(routed.returncode, 0, routed.stdout)
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-REQ-2",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Establish the second set of facts", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        make_task_ready(self.root / "tasks/TASK-REQ-2.yaml")
        status_path = self.root / "docs/project-status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["execution_control"]["active_sessions"] = [{
            "session_id": "requirements-active-1", "task_id": "TASK-REQ-1",
            "role": "requirements", "parent_role": "orchestrator", "access_mode": "write",
        }]
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        blocked = run("check_execution_plan.py", self.root, "tasks/TASK-REQ-2.yaml")
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn("BLOCKED_DUPLICATE_ROLE", blocked.stdout)

    def test_completed_wave_requires_matching_task_handoff(self) -> None:
        routed = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--write",
        )
        self.assertEqual(routed.returncode, 0, routed.stdout)
        inventory_path = self.root / ".codex/orchestration/runtime-inventory.json"
        verified_inventory = inventory_path.read_text(encoding="utf-8")
        inventory_path.write_text(json.dumps({
            "schema_version": 1, "status": "UNVERIFIED",
            "runtime_id": None, "host_id": None, "runtime_version": None,
            "evidence_source": None, "available_models": [],
            "available_skills": [], "available_mcp_servers": [],
            "verified_at": None, "verified_by": None,
        }, indent=2) + "\n", encoding="utf-8")
        no_model_created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-REQ-NOMODEL",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Attempt completion without a routed model", "--task-type", "requirements",
        )
        self.assertEqual(no_model_created.returncode, 0, no_model_created.stdout)
        no_model_path = self.root / "tasks/TASK-REQ-NOMODEL.yaml"
        make_task_ready(no_model_path)
        no_model_preflight = run(
            "check_execution_plan.py", self.root, "tasks/TASK-REQ-NOMODEL.yaml", "--record-ready"
        )
        self.assertEqual(no_model_preflight.returncode, 3, no_model_preflight.stdout)
        self.assertFalse((self.root / "evidence/dispatch/TASK-REQ-NOMODEL.ready.json").exists())
        mark_task_completed(no_model_path)
        no_model_completion = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "requirements",
            "--completed-task", "requirements=tasks/TASK-REQ-NOMODEL.yaml", "--write",
        )
        self.assertEqual(no_model_completion.returncode, 2, no_model_completion.stdout)
        self.assertIn("dispatch READY receipt is missing", no_model_completion.stdout)
        inventory_path.write_text(verified_inventory, encoding="utf-8")

        no_cap_created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-REQ-NOCAP",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Attempt completion without a required capability", "--task-type", "requirements",
            "--required-capability", "missing-required-skill",
        )
        self.assertEqual(no_cap_created.returncode, 0, no_cap_created.stdout)
        no_cap_path = self.root / "tasks/TASK-REQ-NOCAP.yaml"
        make_task_ready(no_cap_path)
        no_cap_preflight = run(
            "check_execution_plan.py", self.root, "tasks/TASK-REQ-NOCAP.yaml", "--record-ready"
        )
        self.assertEqual(no_cap_preflight.returncode, 3, no_cap_preflight.stdout)
        self.assertIn("BLOCKED_CAPABILITY", no_cap_preflight.stdout)
        self.assertFalse((self.root / "evidence/dispatch/TASK-REQ-NOCAP.ready.json").exists())
        mark_task_completed(no_cap_path)
        no_cap_completion = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "requirements",
            "--completed-task", "requirements=tasks/TASK-REQ-NOCAP.yaml", "--write",
        )
        self.assertEqual(no_cap_completion.returncode, 2, no_cap_completion.stdout)
        self.assertIn("dispatch READY receipt is missing", no_cap_completion.stdout)

        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-REQ-HANDOFF",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Persist the requirements handoff", "--task-type", "requirements",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        task_path = self.root / "tasks/TASK-REQ-HANDOFF.yaml"
        make_task_ready(task_path)
        dispatch_ready = run(
            "check_execution_plan.py", self.root, "tasks/TASK-REQ-HANDOFF.yaml", "--record-ready"
        )
        self.assertEqual(dispatch_ready.returncode, 0, dispatch_ready.stdout)
        self.assertIn("RECORDED: evidence/dispatch/TASK-REQ-HANDOFF.ready.json", dispatch_ready.stdout)
        mark_task_completed(task_path)
        missing_proof = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "requirements", "--write",
        )
        self.assertEqual(missing_proof.returncode, 2, missing_proof.stdout)
        self.assertIn("matching --completed-task", missing_proof.stdout)
        fake_created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-REQ-FAKE",
            "--owner", "requirements", "--reviewer", "qa", "--stage", "DISCOVERY",
            "--objective", "Attempt a fake completion", "--task-type", "requirements",
        )
        self.assertEqual(fake_created.returncode, 0, fake_created.stdout)
        fake_path = self.root / "tasks/TASK-REQ-FAKE.yaml"
        fake_text = fake_path.read_text(encoding="utf-8")
        fake_text = fake_text.replace('status: "DRAFT"', 'status: "COMPLETED"', 1)
        fake_text = fake_text.replace('  conclusion: "BLOCKED"', '  conclusion: "COMPLETED"', 1)
        fake_text = fake_text.replace('  artifacts: []', '  artifacts:\n    - "docs/04-prd.md"', 1)
        fake_path.write_text(fake_text, encoding="utf-8")
        incomplete_contract = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "requirements",
            "--completed-task", "requirements=tasks/TASK-REQ-FAKE.yaml", "--write",
        )
        self.assertEqual(incomplete_contract.returncode, 2, incomplete_contract.stdout)
        self.assertIn("Task Contract is invalid", incomplete_contract.stdout)
        self.assertIn("business_context.value must be concrete", incomplete_contract.stdout)
        valid_text = task_path.read_text(encoding="utf-8")
        task_path.write_text(
            valid_text.replace('    - "docs/04-prd.md"', '    - "evidence/THIS-FILE-DOES-NOT-EXIST.txt"', 1),
            encoding="utf-8",
        )
        missing_reference = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "requirements",
            "--completed-task", "requirements=tasks/TASK-REQ-HANDOFF.yaml", "--write",
        )
        self.assertEqual(missing_reference.returncode, 2, missing_reference.stdout)
        self.assertIn("reference does not exist", missing_reference.stdout)
        task_path.write_text(
            valid_text.replace('    - "docs/04-prd.md"', '    - "../outside-project.txt"', 1),
            encoding="utf-8",
        )
        outside_reference = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "requirements",
            "--completed-task", "requirements=tasks/TASK-REQ-HANDOFF.yaml", "--write",
        )
        self.assertEqual(outside_reference.returncode, 2, outside_reference.stdout)
        self.assertIn("outside the project", outside_reference.stdout)
        task_path.write_text(valid_text, encoding="utf-8")
        advanced = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "requirements",
            "--completed-task", "requirements=tasks/TASK-REQ-HANDOFF.yaml", "--write",
        )
        self.assertEqual(advanced.returncode, 0, advanced.stdout)
        plan = json.loads((self.root / ".codex/orchestration/role-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["required_now"], ["quality_governor"])
        self.assertEqual(plan["completed_roles"], ["requirements"])
        cycle_id = plan["routing_cycle_id"]

        quality_created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-PROBLEM-QUALITY",
            "--owner", "quality_governor", "--reviewer", "orchestrator", "--stage", "DISCOVERY",
            "--objective", "Challenge the persisted problem framing", "--task-type", "problem_quality",
        )
        self.assertEqual(quality_created.returncode, 0, quality_created.stdout)
        quality_path = self.root / "tasks/TASK-PROBLEM-QUALITY.yaml"
        make_task_ready(quality_path, quality=True)
        quality_dispatch = run(
            "check_execution_plan.py", self.root, "tasks/TASK-PROBLEM-QUALITY.yaml", "--record-ready"
        )
        self.assertEqual(quality_dispatch.returncode, 0, quality_dispatch.stdout)
        mark_task_completed(quality_path)
        changed_signal = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "release_risk", "--completed-role", "quality_governor",
            "--completed-task", "quality_governor=tasks/TASK-PROBLEM-QUALITY.yaml", "--write",
        )
        self.assertEqual(changed_signal.returncode, 2, changed_signal.stdout)
        self.assertIn("signals do not match", changed_signal.stdout)
        quality_advanced = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--completed-role", "quality_governor",
            "--completed-task", "quality_governor=tasks/TASK-PROBLEM-QUALITY.yaml", "--write",
        )
        self.assertEqual(quality_advanced.returncode, 0, quality_advanced.stdout)
        final_plan = json.loads((self.root / ".codex/orchestration/role-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(final_plan["required_now"], [])
        self.assertEqual(final_plan["completed_roles"], ["quality_governor", "requirements"])
        self.assertEqual(final_plan["routing_cycle_id"], cycle_id)
        stable = run(
            "route_roles.py", self.root, "--stage", "DISCOVERY", "--quota", "balanced",
            "--signal", "high_impact", "--write",
        )
        self.assertEqual(stable.returncode, 0, stable.stdout)
        stable_plan = json.loads((self.root / ".codex/orchestration/role-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(stable_plan["required_now"], [])
        self.assertEqual(stable_plan["completed_roles"], ["quality_governor", "requirements"])

    def test_runtime_availability_is_persisted_and_high_risk_blocks(self) -> None:
        created = run(
            "create_task_package.py", self.root, "--task-id", "TASK-NO-SOL",
            "--owner", "architect", "--reviewer", "qa", "--objective", "Security design",
            "--task-type", "security_review", "--risk", "security",
            "--available-model", "gpt-5.6-terra",
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        task = (self.root / "tasks/TASK-NO-SOL.yaml").read_text(encoding="utf-8")
        self.assertIn('status: "BLOCKED_MODEL_UNAVAILABLE"', task)
        preflight = run(
            "check_execution_plan.py", self.root, "tasks/TASK-NO-SOL.yaml",
            "--available-model", "gpt-5.6-terra",
        )
        self.assertEqual(preflight.returncode, 3, preflight.stdout)
        self.assertIn("Execution route is blocked", preflight.stdout)
        self.assertNotIn("ROUTE_MISMATCH", preflight.stdout)

    def test_policy_tampering_and_unknown_route_input_are_rejected(self) -> None:
        policy = self.root / ".codex/orchestration/model-routing-policy.json"
        data = json.loads(policy.read_text(encoding="utf-8"))
        data["max_attempts"] = 999
        policy.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        rejected = run(
            "create_task_package.py", self.root, "--task-id", "TASK-POLICY",
            "--owner", "engineering_lead", "--reviewer", "qa", "--objective", "Test policy",
        )
        self.assertEqual(rejected.returncode, 2, rejected.stdout)
        self.assertIn("does not match the executable router policy", rejected.stdout)

        data["max_attempts"] = 3
        policy.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        typo = run(
            "create_task_package.py", self.root, "--task-id", "TASK-TYPO",
            "--owner", "engineering_lead", "--reviewer", "qa", "--objective", "Test typo",
            "--task-type", "securty_review",
        )
        self.assertEqual(typo.returncode, 2, typo.stdout)
        self.assertIn("invalid choice: 'securty_review'", typo.stdout)

    def test_invalid_project_status_fails_closed_instead_of_defaulting_standard(self) -> None:
        status = self.root / "docs/project-status.json"
        status.write_text("{invalid", encoding="utf-8")
        result = run(
            "create_task_package.py", self.root, "--task-id", "TASK-BAD-STATUS",
            "--owner", "engineering_lead", "--reviewer", "qa", "--objective", "Must block",
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("routing fails closed", result.stdout)

    def test_installed_skill_is_reused_and_unknown_source_blocks(self) -> None:
        skill = self.root / ".agents/skills/local-tool"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: local-tool\ndescription: local\n---\n", encoding="utf-8")
        pending = run("resolve_capabilities.py", self.root, "--required", "local-tool")
        self.assertEqual(pending.returncode, 3, pending.stdout)
        self.assertIn('"status": "DISCOVERED_NOT_RUNTIME_VERIFIED"', pending.stdout)
        inventory_path = self.root / ".codex/orchestration/runtime-inventory.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        inventory["available_skills"] = ["local-tool"]
        inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        satisfied = run("resolve_capabilities.py", self.root, "--required", "local-tool")
        self.assertEqual(satisfied.returncode, 0, satisfied.stdout)
        self.assertIn('"status": "SATISFIED"', satisfied.stdout)
        blocked = run("resolve_capabilities.py", self.root, "--required", "unknown-community-tool")
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn('"status": "BLOCKED_DISCOVERY"', blocked.stdout)
        escaped = run("resolve_capabilities.py", self.root, "--required", "../../escape")
        self.assertEqual(escaped.returncode, 2, escaped.stdout)
        self.assertIn("Invalid capability id", escaped.stdout)
        broken = self.root / ".agents/skills/broken"
        broken.mkdir(parents=True)
        (broken / "SKILL.md").write_text("", encoding="utf-8")
        invalid_manifest = run("resolve_capabilities.py", self.root, "--required", "broken")
        self.assertEqual(invalid_manifest.returncode, 3, invalid_manifest.stdout)
        self.assertIn('"status": "BLOCKED_DISCOVERY"', invalid_manifest.stdout)

    def test_task_generator_rejects_escaping_capability_id(self) -> None:
        result = run(
            "create_task_package.py", self.root, "--task-id", "TASK-BAD-CAP",
            "--owner", "engineering_lead", "--reviewer", "qa", "--objective", "Test",
            "--required-capability", "../../escape",
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("invalid capability id", result.stdout)

    def test_oauth_mcp_blocks_without_attempting_authentication(self) -> None:
        self.write_catalog({
            "private-mcp": {
                "kind": "mcp_http", "permission": "read", "allowed_tools": ["get"],
                "source": {"type": "mcp_http", "url": "https://example.invalid/mcp", "credential_mode": "oauth"},
            }
        })
        result = run("resolve_capabilities.py", self.root, "--required", "private-mcp", "--apply")
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('"status": "BLOCKED_AUTH"', result.stdout)
        self.assertFalse((self.root / ".codex/config.toml").exists())

    def test_unmanaged_mcp_is_not_assumed_read_only(self) -> None:
        config = self.root / ".codex/config.toml"
        config.write_text('[mcp_servers.ambient]\nurl = "https://example.invalid/mcp"\n', encoding="utf-8")
        result = run("resolve_capabilities.py", self.root, "--required", "ambient")
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('"status": "BLOCKED_CONFIG_DRIFT"', result.stdout)

    def test_github_skill_install_is_hash_checked_and_path_safe(self) -> None:
        def archive(member: str) -> bytes:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as bundle:
                bundle.writestr(member, "---\nname: safe-skill\ndescription: test\n---\n")
            return buffer.getvalue()

        payload = archive("repository-commit/skill/SKILL.md")
        policy = json.loads((self.root / ".codex/orchestration/capability-policy.json").read_text(encoding="utf-8"))
        policy["allowed_github_repositories"] = ["trusted/repository"]
        candidate = {
            "kind": "skill", "license": "MIT", "contains_executable_code": False,
            "source": {
                "type": "github", "repository": "trusted/repository", "commit": "a" * 40,
                "subdirectory": "skill", "archive_sha256": "0" * 64,
            },
        }
        with mock.patch("resolve_capabilities.urllib.request.urlopen", return_value=io.BytesIO(payload)):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                download_skill(self.root, "safe-skill", candidate, policy)
        self.assertFalse((self.root / ".agents/skills/safe-skill").exists())

        candidate["source"]["archive_sha256"] = hashlib.sha256(payload).hexdigest()
        with mock.patch("resolve_capabilities.urllib.request.urlopen", return_value=io.BytesIO(payload)):
            evidence = download_skill(self.root, "safe-skill", candidate, policy)
        self.assertTrue((self.root / ".agents/skills/safe-skill/SKILL.md").is_file())
        self.assertEqual(evidence["commit"], "a" * 40)

        malicious = archive("repository-commit/../../escape/SKILL.md")
        candidate["source"]["archive_sha256"] = hashlib.sha256(malicious).hexdigest()
        with mock.patch("resolve_capabilities.urllib.request.urlopen", return_value=io.BytesIO(malicious)):
            with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                download_skill(self.root, "escape-skill", candidate, policy)
        self.assertFalse((self.root / "escape/SKILL.md").exists())

        oversized_id = "oversized-skill"
        oversized = archive("repository-commit/skill/SKILL.md")
        oversized_candidate = json.loads(json.dumps(candidate))
        oversized_candidate["source"]["archive_sha256"] = hashlib.sha256(oversized).hexdigest()
        tight_policy = dict(policy)
        tight_policy["maximum_extracted_bytes"] = 10
        with mock.patch("resolve_capabilities.urllib.request.urlopen", return_value=io.BytesIO(oversized)):
            with self.assertRaisesRegex(ValueError, "extracted size exceeds"):
                download_skill(self.root, oversized_id, oversized_candidate, tight_policy)
        self.assertFalse((self.root / f".agents/skills/{oversized_id}").exists())

        platform_roots = {
            "cursor": ".cursor",
            "claude-code": ".claude",
            "opencode": ".opencode",
        }
        candidate["source"]["archive_sha256"] = hashlib.sha256(payload).hexdigest()
        for platform, directory in platform_roots.items():
            with self.subTest(platform=platform):
                project = Path(self.temp.name) / f"project-{platform}"
                project.mkdir()
                outside = Path(self.temp.name) / f"outside-{platform}"
                outside.mkdir()
                (project / directory).symlink_to(outside, target_is_directory=True)
                with mock.patch("resolve_capabilities.urllib.request.urlopen", return_value=io.BytesIO(payload)):
                    with self.assertRaisesRegex(ValueError, "traverses a symlink"):
                        download_skill(project, "safe-skill", candidate, policy, platform)
                self.assertEqual(list(outside.iterdir()), [])

    def test_capability_lock_and_mcp_config_hardlinks_never_modify_external_files(self) -> None:
        candidate = {
            "public-read": {
                "kind": "mcp_http", "permission": "read", "allowed_tools": ["get"],
                "source": {"type": "mcp_http", "url": "https://example.invalid/mcp", "credential_mode": "none"},
            }
        }
        self.write_catalog(candidate)

        lock = self.root / ".codex/orchestration/capability-lock.json"
        outside_lock = Path(self.temp.name) / "outside-lock.json"
        outside_lock.write_bytes(lock.read_bytes())
        lock.unlink()
        os.link(outside_lock, lock)
        before = hashlib.sha256(outside_lock.read_bytes()).hexdigest()
        blocked = run("resolve_capabilities.py", self.root, "--required", "public-read", "--apply")
        self.assertEqual(blocked.returncode, 2, blocked.stdout)
        self.assertEqual(hashlib.sha256(outside_lock.read_bytes()).hexdigest(), before)
        lock.unlink()
        lock.write_text('{"lock_version":"1.0.0","resolved":{}}\n', encoding="utf-8")

        config = self.root / ".codex/config.toml"
        outside_config = Path(self.temp.name) / "outside-config.toml"
        outside_config.write_text("DO_NOT_MODIFY\n", encoding="utf-8")
        os.link(outside_config, config)
        before = hashlib.sha256(outside_config.read_bytes()).hexdigest()
        blocked = run("resolve_capabilities.py", self.root, "--required", "public-read", "--apply")
        self.assertIn(blocked.returncode, (2, 3), blocked.stdout)
        self.assertEqual(hashlib.sha256(outside_config.read_bytes()).hexdigest(), before)

        project = Path(self.temp.name) / "v3-native-path"
        project.mkdir()
        external_parent = Path(self.temp.name) / "outside-codex-parent"
        external_parent.mkdir()
        (project / ".codex").symlink_to(external_parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "traverses a symlink"):
            configure_mcp(project, "public-read", candidate["public-read"])
        self.assertEqual(list(external_parent.iterdir()), [])

    def test_credential_free_read_mcp_is_idempotently_configured(self) -> None:
        self.write_catalog({
            "public-read": {
                "kind": "mcp_http", "permission": "read", "allowed_tools": ["get", "search"],
                "source": {"type": "mcp_http", "url": "https://example.invalid/mcp", "credential_mode": "none"},
            },
            "second-read": {
                "kind": "mcp_http", "permission": "read", "allowed_tools": ["list"],
                "source": {"type": "mcp_http", "url": "https://second.example.invalid/mcp", "credential_mode": "none"},
            },
        })
        planned = run("resolve_capabilities.py", self.root, "--required", "public-read")
        self.assertEqual(planned.returncode, 0, planned.stdout)
        self.assertIn('"status": "AUTO_PROVISIONABLE"', planned.stdout)
        applied = run("resolve_capabilities.py", self.root, "--required", "public-read", "--apply")
        self.assertEqual(applied.returncode, 3, applied.stdout)
        self.assertIn('"status": "PROVISIONED_PENDING_RUNTIME"', applied.stdout)
        second = run("resolve_capabilities.py", self.root, "--required", "public-read", "--apply")
        self.assertEqual(second.returncode, 3, second.stdout)
        self.assertIn('"status": "PROVISIONED_PENDING_RUNTIME"', second.stdout)
        inventory_path = self.root / ".codex/orchestration/runtime-inventory.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        inventory["available_mcp_servers"] = ["public-read"]
        inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        satisfied = run("resolve_capabilities.py", self.root, "--required", "public-read")
        self.assertEqual(satisfied.returncode, 0, satisfied.stdout)
        self.assertIn('"status": "SATISFIED"', satisfied.stdout)
        added = run("resolve_capabilities.py", self.root, "--required", "second-read", "--apply")
        self.assertEqual(added.returncode, 3, added.stdout)
        config = (self.root / ".codex/config.toml").read_text(encoding="utf-8")
        self.assertEqual(config.count("[mcp_servers.public-read]"), 1)
        self.assertIn('enabled_tools = ["get", "search"]', config)
        self.assertIn('[mcp_servers.second-read]', config)
        self.assertIn('enabled_tools = ["list"]', config)

        config_path = self.root / ".codex/config.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                'enabled_tools = ["get", "search"]', 'enabled_tools = ["delete", "get", "search"]'
            ),
            encoding="utf-8",
        )
        drift = run("resolve_capabilities.py", self.root, "--required", "public-read")
        self.assertEqual(drift.returncode, 3, drift.stdout)
        self.assertIn('"status": "BLOCKED_CONFIG_DRIFT"', drift.stdout)


if __name__ == "__main__":
    unittest.main()
