#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
PYTHON = sys.executable
sys.path.insert(0, str(SCRIPTS))

from doctor import diagnose  # noqa: E402
from check_missing_modules import check as check_missing_modules  # noqa: E402
from check_traceability import check as check_traceability  # noqa: E402
from domain_packs import apply_pack, list_packs  # noqa: E402
from evaluate_routing import evaluate  # noqa: E402
from lifecycle import transition  # noqa: E402
from init_project import initialize  # noqa: E402
from run_state import checkpoint, create_run, report, resume  # noqa: E402
from route_roles import route_project  # noqa: E402
from state_io import safe_project_path  # noqa: E402
from validate_documents import check as validate_documents  # noqa: E402


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPTS / "orchestrator.py"), *args],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )


class V2ControlPlaneTests(unittest.TestCase):
    def make_project(self, parent: Path, complexity: str = "Standard") -> Path:
        root = parent / "project"
        initialize(root, "Control Plane Test", "CRM", complexity, False)
        return root

    def test_unified_cli_version_doctor_and_eval(self) -> None:
        version = cli("version")
        self.assertEqual(version.returncode, 0, version.stdout)
        self.assertEqual(version.stdout.strip(), "2.0.0")
        doctor = cli("doctor", "--json")
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
        self.assertEqual(json.loads(doctor.stdout)["status"], "READY")
        evaluation = cli("eval", "--json")
        self.assertEqual(evaluation.returncode, 0, evaluation.stdout)
        payload = json.loads(evaluation.stdout)
        self.assertEqual(payload["failed"], 0)
        self.assertGreaterEqual(payload["total"], 15)

    def test_unified_validate_aggregates_checker_lists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            document_errors, document_warnings = validate_documents(root)
            module_errors, module_warnings = check_missing_modules(root)
            trace_errors, trace_warnings = check_traceability(root)
            expected_errors = len(document_errors) + len(module_errors) + len(trace_errors)
            expected_warnings = len(document_warnings) + len(module_warnings) + len(trace_warnings)
            result = cli("validate", str(root))
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn(f"FAIL: {expected_errors} error(s), {expected_warnings} warning(s)", result.stdout)
            self.assertNotIn("ERROR: []", result.stdout)

    def test_doctor_treats_unverified_inventory_as_limitation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            result = diagnose(root)
            self.assertEqual(result["status"], "READY_WITH_LIMITATIONS")
            inventory = next(item for item in result["checks"] if item["id"] == "runtime.model-inventory")
            self.assertEqual(inventory["status"], "WARN")

    def test_lifecycle_transition_persists_only_a_valid_next_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            result = transition(root, "DISCOVERY")
            self.assertEqual(result["status"], "TRANSITIONED")
            status = json.loads((root / "docs/project-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["previous_state"], "BACKLOG")
            self.assertEqual(status["current_state"], "DISCOVERY")
            with self.assertRaisesRegex(ValueError, "transition DISCOVERY -> PRODUCT_APPROVED is blocked"):
                transition(root, "PRODUCT_APPROVED")
            with self.assertRaisesRegex(ValueError, "instead of rewinding state"):
                transition(root, "BACKLOG")
            unchanged = json.loads((root / "docs/project-status.json").read_text(encoding="utf-8"))
            self.assertEqual(unchanged["current_state"], "DISCOVERY")

    def test_doctor_blocks_tampered_policy_orphan_worker_and_unknown_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            policy_path = root / ".codex/orchestration/role-routing-policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["final_qa_separate_from_engineering"] = False
            policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
            status_path = root / "docs/project-status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["execution_control"]["active_sessions"] = [{
                "session_id": "worker-orphan", "task_id": "TASK-WORKER-1",
                "role": "frontend_worker", "parent_role": "engineering_lead", "access_mode": "write",
            }]
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            inventory_path = root / ".codex/orchestration/runtime-inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory.update({
                "status": "VERIFIED", "available_models": ["made-up-model"],
                "verified_at": "2026-08-28T00:00:00Z", "verified_by": "test",
                "evidence_source": "test",
            })
            inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
            result = diagnose(root)
            self.assertEqual(result["status"], "BLOCKED_CONFIGURATION")
            evidence = "\n".join(item["evidence"] for item in result["checks"])
            self.assertIn("does not match executable policy", evidence)
            self.assertIn("active Worker requires an active Engineering Lead", evidence)
            self.assertIn("unsupported model slug", evidence)

    def test_doctor_does_not_create_a_missing_run_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            runs = root / ".codex/runs"
            shutil.rmtree(runs)
            result = diagnose(root)
            self.assertFalse(runs.exists())
            ledger = next(item for item in result["checks"] if item["id"] == "project.run-ledger")
            self.assertEqual(ledger["status"], "WARN")
            with self.assertRaisesRegex(ValueError, "No run ledger exists"):
                resume(root)
            self.assertFalse(runs.exists())

    def test_run_resume_report_and_stale_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run = create_run(root)
            self.assertEqual(resume(root, run["run_id"])["decision"], "RESUME_SAFE")
            context = root / "docs/00-project-context.md"
            context.write_text(context.read_text(encoding="utf-8") + "\nChanged input.\n", encoding="utf-8")
            decision = resume(root, run["run_id"])
            self.assertEqual(decision["decision"], "REPLAN_REQUIRED")
            content, path = report(root, run["run_id"])
            self.assertTrue(path.is_file())
            self.assertIn("does not claim", content)

    def test_stale_plan_cannot_be_retrusted_by_an_empty_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            route_project(root, stage="BACKLOG", quota="economy", write=True)
            run = create_run(root)
            context = root / "docs/00-project-context.md"
            context.write_text(context.read_text(encoding="utf-8") + "\nMaterial change.\n", encoding="utf-8")
            self.assertEqual(resume(root, run["run_id"])["decision"], "REPLAN_REQUIRED")
            with self.assertRaisesRegex(ValueError, "role plan is stale|stage differs"):
                checkpoint(root, run["run_id"], event_type="GATE_DECISION")
            proof = root / "evidence/reconciliation.txt"
            proof.write_text("fresh role plan reviewed\n", encoding="utf-8")
            route_project(root, stage="BACKLOG", quota="economy", write=True)
            checkpoint(
                root, run["run_id"], event_type="STATE_RECONCILED",
                evidence_refs=["evidence/reconciliation.txt"],
            )
            self.assertEqual(resume(root, run["run_id"])["decision"], "RESUME_SAFE")

    def test_checkpoint_refreshes_trusted_state_and_indexes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run = create_run(root)
            context = root / "docs/00-project-context.md"
            context.write_text(context.read_text(encoding="utf-8") + "\nConfirmed project input.\n", encoding="utf-8")
            artifact = root / "docs/decisions/DEC-001.md"
            artifact.write_text("# Decision\n", encoding="utf-8")
            proof = root / "evidence/AC-001.txt"
            proof.write_text("reviewed evidence\n", encoding="utf-8")
            route_project(root, stage="BACKLOG", quota="economy", write=True)
            result = checkpoint(
                root, run["run_id"], event_type="STATE_RECONCILED",
                conclusion="COMPLETE", artifact_refs=["docs/decisions/DEC-001.md"],
                evidence_refs=["evidence/AC-001.txt"],
            )
            self.assertEqual(result["sequence"], 2)
            self.assertEqual(resume(root, run["run_id"])["decision"], "RESUME_SAFE")
            content, _ = report(root, run["run_id"])
            self.assertIn("Indexed artifacts: 1", content)
            self.assertIn("Indexed acceptance evidence: 1", content)

    def test_competing_run_and_escaping_checkpoint_reference_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run = create_run(root)
            with self.assertRaisesRegex(ValueError, "still OPEN"):
                create_run(root)
            with self.assertRaisesRegex(ValueError, "escapes project root"):
                checkpoint(root, run["run_id"], event_type="GATE_DECISION", artifact_refs=["../outside"])

    def test_run_completion_requires_done_state_and_independent_qa(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run = create_run(root)
            with self.assertRaisesRegex(ValueError, "project state DONE"):
                checkpoint(root, run["run_id"], event_type="RUN_COMPLETED", conclusion="PASS")
            status_path = root / "docs/project-status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["previous_state"] = "RELEASE_READY"
            status["current_state"] = "DONE"
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            proof = root / "evidence/fake-qa.txt"
            proof.write_text("not sufficient\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "full DONE gate"):
                checkpoint(
                    root, run["run_id"], event_type="RUN_COMPLETED", conclusion="PASS",
                    evidence_refs=["evidence/fake-qa.txt"],
                )
            self.assertEqual(resume(root, run["run_id"])["decision"], "BLOCKED")

    def test_resume_never_clears_uncertain_active_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run = create_run(root)
            status_path = root / "docs/project-status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["execution_control"]["active_sessions"] = [{"role": "requirements", "task_id": "TASK-001"}]
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            result = resume(root, run["run_id"])
            self.assertEqual(result["decision"], "RECONCILIATION_REQUIRED")
            persisted = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(len(persisted["execution_control"]["active_sessions"]), 1)

    def test_domain_pack_is_locked_idempotently_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(ValueError, "initialized project"):
                apply_pack(empty, "crm")
            root = self.make_project(Path(directory))
            first = apply_pack(root, "crm")
            self.assertEqual(first["status"], "APPLIED")
            second = apply_pack(root, "crm")
            self.assertEqual(second["status"], "ALREADY_APPLIED")
            with self.assertRaisesRegex(ValueError, "different or modified"):
                apply_pack(root, "ecommerce")
            text = (root / "docs/domain-pack.md").read_text(encoding="utf-8")
            self.assertIn("not confirmed business facts", text)
            self.assertIn("never confirms legal conclusions", text)

    def test_all_bundled_domain_packs_validate(self) -> None:
        ids = {item["id"] for item in list_packs()}
        self.assertEqual(ids, {"ai-agent", "crm", "ecommerce", "group-buying", "home-services", "saas"})

    def test_safe_project_path_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "escapes project root"):
                safe_project_path(root, "../outside")

    def test_offline_evaluation_detects_bad_expectation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            suite = Path(directory) / "bad.json"
            suite.write_text(json.dumps({
                "schema_version": 1,
                "cases": [{
                    "id": "deliberate-failure", "kind": "role_route",
                    "input": {"complexity": "Simple", "stage": "DISCOVERY", "quota_mode": "economy", "signals": []},
                    "expect": {"required_now": ["qa"]},
                }],
            }), encoding="utf-8")
            result = evaluate(suite)
            self.assertEqual(result["failed"], 1)


if __name__ == "__main__":
    unittest.main()
