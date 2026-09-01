#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from iteration_state import transition_iteration  # noqa: E402
from model_routing import route_task  # noqa: E402
from role_routing import route_roles  # noqa: E402
from route_task import apply_user_model_override  # noqa: E402
from task_mode import classify_task_mode, governance_severity  # noqa: E402
from wait_budget import wait_decision  # noqa: E402


class TaskModeTriageTests(unittest.TestCase):
    def test_complex_project_single_page_remains_quick(self) -> None:
        result = classify_task_mode(
            project_complexity="Complex",
            signals=["single_page", "style_change", "reversible", "explicit_skill_invocation"],
            estimated_business_files=1,
            estimated_minutes=8,
        )
        self.assertEqual(result["task_mode"], "QUICK_PATCH")
        self.assertEqual(result["budget"]["max_subagents"], 0)
        self.assertEqual(result["budget"]["max_active_subagents"], 0)
        self.assertEqual(result["budget"]["max_total_role_sessions"], 1)
        self.assertIn("explicit-skill-means-complete-closure-not-all-gates", result["routing_reasons"])

    def test_group_buy_pickup_location_is_bounded(self) -> None:
        result = classify_task_mode(
            project_complexity="Complex",
            signals=["single_page", "backend_frontend", "api_delta", "map_integration", "targeted_qa"],
            estimated_business_files=3,
            estimated_minutes=35,
        )
        self.assertEqual(result["task_mode"], "BOUNDED_CHANGE")
        self.assertEqual(result["first_route_summary"]["max_subagents"], 1)

    def test_payment_permission_migration_and_concurrency_are_governed(self) -> None:
        for signal in (
            "payment", "permissions", "migration", "concurrency", "external_side_effects",
            "blocking_unknown", "evidence_conflict", "high_impact", "repeated_failure",
        ):
            with self.subTest(signal=signal):
                result = classify_task_mode(project_complexity="Simple", signals=[signal])
                self.assertEqual(result["task_mode"], "GOVERNED_DELIVERY")

    def test_explicit_skill_and_full_process_do_not_upgrade(self) -> None:
        result = classify_task_mode(
            project_complexity="Standard",
            signals=["copy_change", "explicit_skill_invocation", "full_process_requested"],
        )
        self.assertEqual(result["task_mode"], "QUICK_PATCH")

    def test_explicit_higher_requested_mode_is_honored(self) -> None:
        result = classify_task_mode(
            project_complexity="Simple",
            signals=["copy_change"],
            requested_mode="GOVERNED_DELIVERY",
            estimated_business_files=1,
            estimated_minutes=5,
        )
        self.assertEqual(result["task_mode"], "GOVERNED_DELIVERY")
        self.assertEqual(result["budget"]["max_subagents"], "quota_and_plan")
        self.assertIn("user-requested-higher-governance-mode", result["routing_reasons"])

    def test_explicit_bounded_requested_mode_upgrades_quick(self) -> None:
        result = classify_task_mode(
            project_complexity="Simple",
            signals=["copy_change"],
            requested_mode="BOUNDED_CHANGE",
        )
        self.assertEqual(result["task_mode"], "BOUNDED_CHANGE")

    def test_requested_quick_cannot_downgrade_computed_bounded_floor(self) -> None:
        result = classify_task_mode(
            project_complexity="Complex", signals=["backend_frontend", "api_delta"],
            requested_mode="QUICK_PATCH",
        )
        self.assertEqual(result["task_mode"], "BOUNDED_CHANGE")

    def test_role_router_revalidates_governed_risk_against_claimed_bounded_mode(self) -> None:
        plan = route_roles(
            complexity="Complex", stage="DISCOVERY", task_mode="BOUNDED_CHANGE",
            signals=["permissions"],
        )
        self.assertEqual(plan["task_mode"], "GOVERNED_DELIVERY")
        self.assertIn("requirements", plan["planned_roles"])

    def test_scope_expansion_requires_confirmation_and_keeps_narrow_default(self) -> None:
        result = classify_task_mode(
            project_complexity="Complex", signals=["single_page", "scope_expansion_requested"],
        )
        self.assertEqual(result["status"], "SCOPE_CONFIRMATION_REQUIRED")
        self.assertEqual(result["task_mode"], "QUICK_PATCH")
        self.assertEqual(result["proposed_mode"], "QUICK_PATCH")
        self.assertIn("scope-expansion-not-confirmed:keep-narrow", result["routing_reasons"])

    def test_confirmed_scope_expansion_is_not_quick(self) -> None:
        result = classify_task_mode(
            project_complexity="Complex", signals=["scope_expansion_confirmed"],
        )
        self.assertEqual(result["task_mode"], "BOUNDED_CHANGE")


class TaskModeRoleTests(unittest.TestCase):
    def test_quick_stays_in_main_thread(self) -> None:
        plan = route_roles(
            complexity="Complex", stage="DISCOVERY", task_mode="QUICK_PATCH",
            signals=["explicit_skill_invocation"],
        )
        self.assertEqual(plan["required_now"], [])
        self.assertEqual(plan["task_complexity"], "QUICK_PATCH")
        self.assertEqual(plan["first_route_summary"]["planned_agent_count"], 0)

    def test_bounded_starts_engineering_not_requirements_or_qg(self) -> None:
        plan = route_roles(
            complexity="Complex", stage="DISCOVERY", task_mode="BOUNDED_CHANGE",
            iteration_state="DELTA_READY", signals=["api_delta", "map_integration"],
        )
        self.assertEqual(plan["required_now"], ["engineering_lead"])
        self.assertNotIn("requirements", plan["planned_roles"])
        self.assertNotIn("quality_governor", plan["planned_roles"])
        self.assertEqual(plan["quality_review_status"], "NOT_AT_QUALITY_GATE")

    def test_bounded_qa_is_independent_and_sequential(self) -> None:
        plan = route_roles(
            complexity="Complex", stage="DISCOVERY", task_mode="BOUNDED_CHANGE",
            iteration_state="QA", signals=["targeted_qa"],
        )
        self.assertEqual(plan["required_now"], ["qa"])
        self.assertNotIn("engineering_lead", plan["planned_roles"])

    def test_complex_alone_does_not_trigger_quality_governor(self) -> None:
        plan = route_roles(complexity="Complex", stage="DISCOVERY", task_mode="GOVERNED_DELIVERY")
        self.assertEqual(plan["required_now"], ["requirements"])
        self.assertNotIn("quality_governor", plan["planned_roles"])
        risk_plan = route_roles(
            complexity="Complex", stage="DISCOVERY", task_mode="GOVERNED_DELIVERY",
            signals=["evidence_conflict"],
        )
        self.assertIn("quality_governor", risk_plan["planned_roles"])

    def test_every_governed_trigger_is_accepted_and_cannot_stay_bounded(self) -> None:
        from task_mode import GOVERNED_TRIGGERS

        for signal in sorted(GOVERNED_TRIGGERS):
            with self.subTest(signal=signal):
                plan = route_roles(
                    complexity="Complex", stage="DISCOVERY", task_mode="BOUNDED_CHANGE",
                    signals=[signal],
                )
                self.assertEqual(plan["task_mode"], "GOVERNED_DELIVERY")


class BudgetAndOverrideTests(unittest.TestCase):
    def test_wait_stagnation_forces_takeover(self) -> None:
        self.assertEqual(
            wait_decision(task_mode="BOUNDED_CHANGE", consecutive_no_progress=2)["status"],
            "PROGRESS_BLOCKER_REQUIRED",
        )
        self.assertEqual(
            wait_decision(task_mode="BOUNDED_CHANGE", consecutive_no_progress=3)["status"],
            "TAKEOVER_OR_REPLAN",
        )

    def test_bounded_repair_is_capped_at_one(self) -> None:
        first = transition_iteration("QA", "IMPLEMENTING", repair_rounds=0)
        self.assertEqual(first["repair_rounds"], 1)
        with self.assertRaises(ValueError):
            transition_iteration("QA", "IMPLEMENTING", repair_rounds=1)

    def test_bounded_done_requires_independent_qa_pass_and_evidence(self) -> None:
        with self.assertRaises(ValueError):
            transition_iteration("QA", "DELTA_DONE")
        result = transition_iteration(
            "QA", "DELTA_DONE", engineering_session="eng-1", qa_session="qa-1",
            qa_conclusion="PASS", qa_evidence=["evidence/qa.json"], unaccepted_p0_p1=0,
        )
        self.assertTrue(result["qa_verified"])

    def test_low_risk_user_model_override_is_accepted(self) -> None:
        recommendation = route_task(
            complexity="Complex", task_type="implementation", role="engineering_lead",
        )
        result = apply_user_model_override(
            recommendation,
            requested_model="gpt-5.6-terra", requested_reasoning="high", approved=True,
            available_models=["gpt-5.6-terra", "gpt-5.6-sol"],
        )
        self.assertEqual(result["status"], "ROUTED")
        self.assertEqual(result["selected_model"], "gpt-5.6-terra")
        self.assertEqual(result["policy_recommendation"]["model"], "gpt-5.6-sol")
        self.assertEqual(result["user_approved_override"]["status"], "ACCEPTED")
        self.assertFalse(result["actual_launch_attestation"]["attested"])

    def test_high_risk_override_cannot_drop_below_floor(self) -> None:
        recommendation = route_task(
            complexity="Standard", task_type="implementation", role="engineering_lead",
            risk_flags=["payment"],
        )
        result = apply_user_model_override(
            recommendation,
            requested_model="gpt-5.6-terra", approved=True,
            available_models=["gpt-5.6-terra", "gpt-5.6-sol"],
        )
        self.assertEqual(result["status"], "BLOCKED_MODEL_OVERRIDE_BELOW_FLOOR")

    def test_high_risk_override_cannot_lower_reasoning_floor(self) -> None:
        recommendation = route_task(
            complexity="Standard", task_type="implementation", role="engineering_lead",
            risk_flags=["payment"],
        )
        result = apply_user_model_override(
            recommendation,
            requested_model="gpt-5.6-sol", requested_reasoning="low", approved=True,
            available_models=["gpt-5.6-sol"],
        )
        self.assertEqual(result["status"], "BLOCKED_REASONING_OVERRIDE_BELOW_FLOOR")

    def test_governance_metadata_is_not_safety_blocker_for_bounded(self) -> None:
        self.assertEqual(
            governance_severity(
                "STALE_ROLE_PLAN: non-safety fingerprint drift",
                task_mode="BOUNDED_CHANGE", risk_flags=[],
            ),
            "GOVERNANCE_METADATA_DEGRADED",
        )
        self.assertEqual(
            governance_severity(
                "STALE_ROLE_PLAN", task_mode="BOUNDED_CHANGE", risk_flags=["permissions"],
            ),
            "EXECUTION_SAFETY_BLOCKER",
        )


class TaskModeCliTests(unittest.TestCase):
    def test_first_route_cli_reports_mode_scope_agents_and_time(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "orchestrator.py"), "triage",
                "--project-complexity", "Complex", "--signal", "api_delta",
                "--signal", "map_integration", "--explicit-skill",
                "--estimated-business-files", "3", "--estimated-minutes", "30",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('"task_mode": "BOUNDED_CHANGE"', result.stdout)
        self.assertIn('"max_subagents": 1', result.stdout)
        self.assertIn('"time_expectation"', result.stdout)

    def test_quick_command_is_preview_only_and_non_initializing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "orchestrator.py"), "quick", str(root),
                    "--goal", "Fix one label", "--target", "admin/page.tsx",
                    "--verify", "run targeted UI test",
                ],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('"task_mode": "QUICK_PATCH"', result.stdout)
            self.assertIn('"writes_performed": false', result.stdout)
            self.assertFalse((root / ".dingxinglizi").exists())

    def test_change_command_outputs_compact_delta_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "orchestrator.py"), "change", str(root),
                    "--goal", "Harden pickup location configuration",
                    "--surface", "admin map", "--surface", "location API",
                    "--verify", "map failure prevents save",
                ],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('"task_mode": "BOUNDED_CHANGE"', result.stdout)
            self.assertIn('"compact_delta_contract"', result.stdout)
            self.assertIn('"independent_qa"', result.stdout)
            self.assertFalse((root / ".dingxinglizi").exists())


if __name__ == "__main__":
    unittest.main()
