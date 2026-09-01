from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import sys

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from migrate_project import apply, plan  # noqa: E402
from check_execution_plan import check as check_execution_plan  # noqa: E402
from create_task_package import create as create_task  # noqa: E402
from init_project import initialize  # noqa: E402
from model_routing import route_with_platform_manifest  # noqa: E402
from project_layout import control_path, layout_report  # noqa: E402
from run_state import checkpoint, create_run  # noqa: E402
from lifecycle import transition  # noqa: E402


class ProjectLayoutV3Tests(unittest.TestCase):
    def _initialized_project(self, *, platform_neutral: bool) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / "project"
        initialize(
            root,
            "Routing Boundary Test",
            "SaaS",
            "Complex",
            False,
            platform_neutral=platform_neutral,
        )
        return temp, root

    def _legacy_project(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        orchestration = root / ".codex/orchestration"
        runs = root / ".codex/runs/RUN-20260828T000000Z-abcdef"
        orchestration.mkdir(parents=True)
        runs.mkdir(parents=True)
        (orchestration / "runtime-inventory.json").write_text(
            json.dumps({"schema_version": 1, "status": "UNVERIFIED"}) + "\n",
            encoding="utf-8",
        )
        (runs / "run.json").write_text('{"schema_version":1}\n', encoding="utf-8")
        return temp, root

    def test_v2_layout_remains_active_until_explicit_migration(self) -> None:
        temp, root = self._legacy_project()
        self.addCleanup(temp.cleanup)
        self.assertEqual(control_path(root, "orchestration").relative_to(root.resolve()), Path(".codex/orchestration"))
        self.assertEqual(layout_report(root)["layout"], "legacy-v2")

    def test_initialized_task_template_uses_layout_model_policy_only_for_execution(self) -> None:
        for platform_neutral, expected in ((False, "1.2.0"), (True, "2.0.0")):
            with self.subTest(platform_neutral=platform_neutral):
                temp, root = self._initialized_project(platform_neutral=platform_neutral)
                self.addCleanup(temp.cleanup)
                template = (root / "tasks/TASK.template.yaml").read_text(encoding="utf-8")
                role_section, execution_section = template.split("execution_profile:", 1)
                self.assertIn('role_execution:\n  policy_version: "1.3.0"', role_section)
                self.assertIn(f'  policy_version: "{expected}"', execution_section)
                self.assertNotIn("{{MODEL_POLICY_VERSION}}", template)

    def test_active_control_roots_and_children_reject_symlink_escape(self) -> None:
        for platform_neutral, control_name in ((True, ".dingxinglizi"), (False, ".codex")):
            with self.subTest(platform_neutral=platform_neutral, kind="root"):
                temp, root = self._initialized_project(platform_neutral=platform_neutral)
                self.addCleanup(temp.cleanup)
                control = root / control_name
                preserved = root / (control_name + "-preserved")
                control.rename(preserved)
                control.symlink_to(preserved, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "control root must not be a symlink"):
                    control_path(root, "orchestration/role-plan.json")

            with self.subTest(platform_neutral=platform_neutral, kind="broken-root"):
                temp, root = self._initialized_project(platform_neutral=platform_neutral)
                self.addCleanup(temp.cleanup)
                control = root / control_name
                preserved = root / (control_name + "-preserved")
                control.rename(preserved)
                control.symlink_to(root / "missing-control", target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "control root must not be a symlink"):
                    layout_report(root)

        for child, relative in (
            ("orchestration", "orchestration/role-plan.json"),
            ("runs", "runs/RUN-TEST/run.json"),
            ("evolution", "evolution/state.json"),
        ):
            with self.subTest(child=child):
                temp, root = self._initialized_project(platform_neutral=True)
                self.addCleanup(temp.cleanup)
                source = root / ".dingxinglizi" / child
                source.mkdir(parents=True, exist_ok=True)
                preserved = root / ".dingxinglizi" / (child + "-preserved")
                source.rename(preserved)
                source.symlink_to(preserved, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
                    control_path(root, relative)

    def test_control_plane_leaf_hardlinks_are_rejected(self) -> None:
        temp, root = self._initialized_project(platform_neutral=True)
        self.addCleanup(temp.cleanup)
        outside = root / "outside-control.json"
        outside.write_text("{}\n", encoding="utf-8")
        for relative in (
            "orchestration/capability-lock.json",
            "runs/RUN-TEST/events.jsonl",
        ):
            with self.subTest(relative=relative):
                target = root / ".dingxinglizi" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()
                os.link(outside, target)
                with self.assertRaisesRegex(ValueError, "single-link"):
                    control_path(root, relative)
                target.unlink()

    def test_project_artifact_writers_reject_parent_symlink_escape(self) -> None:
        temp, root = self._initialized_project(platform_neutral=True)
        self.addCleanup(temp.cleanup)
        base = root.parent

        outside_tasks = base / "outside-tasks"
        (root / "tasks").rename(outside_tasks)
        (root / "tasks").symlink_to(outside_tasks, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
            create_task(
                root, "TASK-ESCAPE", "requirements", "qa", "escape test",
                "BACKLOG", "orchestrator",
            )
        self.assertFalse((outside_tasks / "TASK-ESCAPE.yaml").exists())

        (root / "tasks").unlink()
        outside_tasks.rename(root / "tasks")
        outside_docs = base / "outside-docs"
        (root / "docs").rename(outside_docs)
        (root / "docs").symlink_to(outside_docs, target_is_directory=True)
        before = (outside_docs / "project-status.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
            transition(root, "DISCOVERY")
        self.assertEqual((outside_docs / "project-status.json").read_bytes(), before)

    def test_task_writer_rejects_existing_leaf_hardlink(self) -> None:
        temp, root = self._initialized_project(platform_neutral=True)
        self.addCleanup(temp.cleanup)
        outside = root.parent / "outside-task.yaml"
        outside.write_text("DO_NOT_CHANGE\n", encoding="utf-8")
        target = root / "tasks/TASK-HARDLINK.yaml"
        os.link(outside, target)
        with self.assertRaises(ValueError):
            create_task(
                root, "TASK-HARDLINK", "requirements", "qa", "hardlink test",
                "BACKLOG", "orchestrator",
            )
        self.assertEqual(outside.read_text(encoding="utf-8"), "DO_NOT_CHANGE\n")

    def test_run_event_hardlink_and_run_directory_symlink_cannot_escape(self) -> None:
        temp, root = self._initialized_project(platform_neutral=True)
        self.addCleanup(temp.cleanup)
        run = create_run(root)
        run_id = run["run_id"]
        events = root / ".dingxinglizi/runs" / run_id / "events.jsonl"
        outside = root / "outside-events.jsonl"
        outside.write_bytes(events.read_bytes())
        events.unlink()
        os.link(outside, events)
        before = outside.read_bytes()
        with self.assertRaisesRegex(ValueError, "single-link"):
            checkpoint(root, run_id, event_type="TASK_BLOCKED", note="test block")
        self.assertEqual(outside.read_bytes(), before)

        events.unlink()
        events.write_bytes(before)
        run_directory = events.parent
        preserved = run_directory.parent / (run_id + "-preserved")
        run_directory.rename(preserved)
        run_directory.symlink_to(preserved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
            checkpoint(root, run_id, event_type="TASK_BLOCKED", note="test block")

    def test_migration_is_non_destructive_verified_and_idempotent(self) -> None:
        temp, root = self._legacy_project()
        self.addCleanup(temp.cleanup)
        preview = plan(root)
        self.assertEqual(preview["status"], "READY_TO_MIGRATE")
        self.assertFalse((root / ".dingxinglizi").exists())

        result = apply(root)
        self.assertEqual(result["status"], "MIGRATED")
        self.assertTrue((root / ".codex/orchestration/runtime-inventory.json").is_file())
        self.assertTrue((root / ".dingxinglizi/orchestration/runtime-inventory.json").is_file())
        self.assertTrue((root / ".dingxinglizi/migration-v3.json").is_file())
        self.assertEqual(layout_report(root)["layout"], "platform-neutral-v3")

        repeated = apply(root)
        self.assertEqual(repeated["status"], "ALREADY_MIGRATED")
        self.assertGreaterEqual(repeated["verified_files"], 1)

    def test_existing_migration_revalidates_destination_source_and_manifest(self) -> None:
        temp, root = self._legacy_project()
        self.addCleanup(temp.cleanup)
        apply(root)
        destination = root / ".dingxinglizi/orchestration/runtime-inventory.json"
        destination.write_text('{"tampered":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "destination file failed integrity"):
            plan(root)

        temp2, root2 = self._legacy_project()
        self.addCleanup(temp2.cleanup)
        apply(root2)
        source = root2 / ".codex/orchestration/runtime-inventory.json"
        source.write_text('{"tampered":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source file failed integrity"):
            plan(root2)

        temp3, root3 = self._legacy_project()
        self.addCleanup(temp3.cleanup)
        apply(root3)
        manifest_path = root3 / ".dingxinglizi/migration-v3.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["unexpected"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported or missing fields"):
            plan(root3)

        temp4, root4 = self._legacy_project()
        self.addCleanup(temp4.cleanup)
        apply(root4)
        (root4 / ".dingxinglizi/orchestration/unmanifested.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "destination inventory does not exactly match"):
            plan(root4)

        temp5, root5 = self._legacy_project()
        self.addCleanup(temp5.cleanup)
        apply(root5)
        (root5 / ".codex/orchestration/unmanifested.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source inventory does not exactly match"):
            plan(root5)

    def test_migration_refuses_symlinks(self) -> None:
        temp, root = self._legacy_project()
        self.addCleanup(temp.cleanup)
        outside = root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        (root / ".codex/orchestration/linked.json").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "refuses symlink"):
            plan(root)

    def test_migration_refuses_symlinked_control_roots_and_broken_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            external = base / "external"
            project.mkdir()
            (external / "orchestration").mkdir(parents=True)
            (external / "orchestration/outside.json").write_text("{}\n", encoding="utf-8")
            (project / ".codex").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "legacy control root"):
                plan(project)

        temp, root = self._legacy_project()
        self.addCleanup(temp.cleanup)
        (root / ".dingxinglizi").symlink_to(root / "missing-destination", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked destination"):
            plan(root)

        temp2, root2 = self._legacy_project()
        self.addCleanup(temp2.cleanup)
        runs = root2 / ".codex/runs"
        for child in runs.iterdir():
            if child.is_dir():
                for item in child.iterdir():
                    item.unlink()
                child.rmdir()
        runs.rmdir()
        outside_runs = root2 / "outside-runs"
        outside_runs.mkdir()
        (root2 / ".codex/runs").symlink_to(outside_runs, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "source directory"):
            plan(root2)

    def test_platform_manifest_resolves_task_model_without_vendor_core_default(self) -> None:
        manifest = {
            "schema_version": 1,
            "platform": "cursor",
            "runtime": {"status": "VERIFIED"},
            "model_inventory": {
                "evidence": {"status": "VERIFIED"},
                "models": [
                    {
                        "id": "vendor/model-standard",
                        "provider": "vendor",
                        "capability_tier": "ADVANCED",
                        "reasoning_efforts": ["medium", "high"],
                        "evidence_status": "VERIFIED",
                    }
                ],
            },
        }
        route = route_with_platform_manifest(
            manifest=manifest,
            availability_source="fixture",
            complexity="Standard",
            task_type="implementation",
            role="engineering_lead",
            risk_flags=[],
            failed_attempts=0,
            failure_type="none",
        )
        self.assertEqual(route["policy_version"], "2.0.0")
        self.assertEqual(route["selected_model"], "vendor/model-standard")
        self.assertEqual(route["selected_provider"], "vendor")
        self.assertEqual(route["status"], "ROUTED")

        blocked = route_with_platform_manifest(
            manifest=manifest,
            availability_source="fixture",
            complexity="Complex",
            task_type="security_review",
            role="architect",
            risk_flags=["security"],
            failed_attempts=0,
            failure_type="none",
        )
        self.assertEqual(blocked["status"], "BLOCKED_MODEL_UNAVAILABLE")
        self.assertEqual(blocked["selected_model"], "")

    def test_platform_route_keeps_attempt_exhaustion_blocked(self) -> None:
        manifest = {
            "schema_version": 1,
            "platform": "cursor",
            "runtime": {"status": "VERIFIED"},
            "model_inventory": {
                "evidence": {"status": "VERIFIED"},
                "models": [{
                    "id": "vendor/expert",
                    "provider": "vendor",
                    "capability_tier": "EXPERT",
                    "reasoning_efforts": ["high"],
                    "evidence_status": "VERIFIED",
                }],
            },
        }
        route = route_with_platform_manifest(
            manifest=manifest,
            availability_source="fixture",
            complexity="Complex",
            task_type="architecture",
            role="architect",
            risk_flags=["security"],
            failed_attempts=3,
            failure_type="quality",
        )
        self.assertEqual(route["status"], "BLOCKED_ATTEMPTS_EXHAUSTED")
        self.assertEqual(route["selected_model"], "")

    def test_v3_without_manifest_is_provider_neutral_and_blocked(self) -> None:
        temp, root = self._initialized_project(platform_neutral=True)
        self.addCleanup(temp.cleanup)
        task = create_task(
            root,
            "TASK-V3-NO-MANIFEST",
            "architect",
            "qa",
            "Review the security boundary",
            "BACKLOG",
            "orchestrator",
            task_type="security_review",
            risk_flags=["security"],
        )
        text = task.read_text(encoding="utf-8")
        self.assertIn('policy_version: "2.0.0"', text)
        self.assertIn('status: "BLOCKED_RUNTIME_MANIFEST_REQUIRED"', text)
        self.assertIn('platform: "unresolved"', text)
        self.assertIn('selected_provider: ""', text)
        self.assertIn('selected_model: ""', text)
        self.assertNotIn("gpt-5.6-", text)

        errors = check_execution_plan(root, task)
        self.assertIn("Execution route is blocked: BLOCKED_RUNTIME_MANIFEST_REQUIRED", errors)

    def test_v3_rejects_available_model_override_in_creation_and_preflight(self) -> None:
        temp, root = self._initialized_project(platform_neutral=True)
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ValueError, "legacy-v2 only"):
            create_task(
                root,
                "TASK-V3-FORGED-MODEL",
                "architect",
                "qa",
                "Review the security boundary",
                "BACKLOG",
                "orchestrator",
                task_type="security_review",
                risk_flags=["security"],
                available_models=["gpt-5.6-sol"],
            )
        self.assertFalse((root / "tasks/TASK-V3-FORGED-MODEL.yaml").exists())

        task = create_task(
            root,
            "TASK-V3-PREFLIGHT",
            "architect",
            "qa",
            "Review the security boundary",
            "BACKLOG",
            "orchestrator",
            task_type="security_review",
            risk_flags=["security"],
        )
        errors = check_execution_plan(root, task, ["gpt-5.6-sol"])
        self.assertTrue(any(error.startswith("BLOCKED_PLATFORM_MODEL_OVERRIDE") for error in errors))

    def test_v2_available_model_override_remains_legacy_compatible(self) -> None:
        temp, root = self._initialized_project(platform_neutral=False)
        self.addCleanup(temp.cleanup)
        task = create_task(
            root,
            "TASK-V2-MODEL",
            "requirements",
            "qa",
            "Build the approved flow",
            "BACKLOG",
            "orchestrator",
            available_models=["gpt-5.6-terra"],
        )
        text = task.read_text(encoding="utf-8")
        self.assertIn('policy_version: "1.2.0"', text)
        self.assertIn('platform: "legacy-codex"', text)
        self.assertIn('selected_provider: "openai"', text)
        self.assertIn('selected_model: "gpt-5.6-terra"', text)

    def test_v2_policy_ignores_v3_manifest_in_both_control_layouts(self) -> None:
        for migrated in (False, True):
            with self.subTest(migrated=migrated):
                temp, root = self._initialized_project(platform_neutral=False)
                self.addCleanup(temp.cleanup)
                if migrated:
                    apply(root)
                manifest_path = control_path(root, "orchestration/runtime-manifest.json")
                manifest_path.write_text("{}\n", encoding="utf-8")
                task = create_task(
                    root,
                    "TASK-V2-WITH-MANIFEST",
                    "requirements",
                    "qa",
                    "Confirm legacy routing remains executable",
                    "BACKLOG",
                    "orchestrator",
                    available_models=["gpt-5.6-terra"],
                )
                text = task.read_text(encoding="utf-8")
                self.assertIn('policy_version: "1.2.0"', text)
                self.assertIn('platform: "legacy-codex"', text)
                errors = check_execution_plan(root, task, ["gpt-5.6-terra"])
                self.assertIsInstance(errors, list)


if __name__ == "__main__":
    unittest.main()
