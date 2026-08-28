#!/usr/bin/env python3

from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
PYTHON = sys.executable
sys.path.insert(0, str(SCRIPTS))

from platform_install import install_platform  # noqa: E402
from orchestrator import main as orchestrator_main  # noqa: E402
from platform_runtime import (  # noqa: E402
    PLATFORM_CHOICES,
    build_runtime_manifest,
    doctor_platform,
    load_runtime_manifest,
    load_role_catalog,
    render_project_adapter,
    resolve_opencode_schema,
    resolve_model,
    write_json_non_overwriting,
    _execution_receipt_fingerprint,
)


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPTS / "orchestrator.py"), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def manifest(platform: str, *, verified: bool, dispatch: bool = False) -> dict[str, object]:
    evidence_status = "VERIFIED" if verified else "DECLARED_UNVERIFIED"
    return {
        "schema_version": 1,
        "platform": platform,
        "captured_at": "2026-08-28T08:00:00Z",
        "status": "VERIFIED_WITH_MODEL_INVENTORY" if verified else "RUNTIME_VERIFIED_MODELS_UNVERIFIED",
        "runtime": {
            "status": "VERIFIED",
            "executable": "/fixture/runtime",
            "version": "fixture-1",
            "evidence_source": "test fixture",
        },
        "model_inventory": {
            "evidence": {"status": evidence_status, "source": "fixture", "sha256": "a" * 64},
            "models": [
                {
                    "id": "%s/economy" % platform,
                    "provider": "fixture",
                    "capability_tier": "ECONOMY",
                    "reasoning_efforts": ["low"],
                    "evidence_status": evidence_status,
                },
                {
                    "id": "%s/advanced" % platform,
                    "provider": "fixture",
                    "capability_tier": "ADVANCED",
                    "reasoning_efforts": ["medium", "high"],
                    "evidence_status": evidence_status,
                },
                {
                    "id": "%s/expert" % platform,
                    "provider": "fixture",
                    "capability_tier": "EXPERT",
                    "reasoning_efforts": ["high", "xhigh"],
                    "evidence_status": evidence_status,
                },
            ],
        },
        "dispatch_evidence": {
            "status": "VERIFIED" if dispatch else "NOT_PROVIDED",
            "path": "/fixture/receipt.json" if dispatch else "",
            "sha256": "b" * 64 if dispatch else "",
            "consistency": "CROSS_CHECKED" if dispatch else "NOT_CHECKED",
            "facts": {
                "task_id": "TASK-42",
                "agent": "qa",
                "actual_provider": "fixture",
                "actual_model": "%s/expert" % platform,
                "actual_reasoning": "high",
                "runtime_version": "fixture-1",
                "recorded_at": "2026-08-28T08:00:00Z",
                "evidence_source": "fixture launch log",
            } if dispatch else {},
        },
        "claims": {
            "authenticated": "UNKNOWN",
            "native_dispatch_completed": dispatch,
            "actual_model_used": "ATTESTED_BY_RECEIPT" if dispatch else "UNKNOWN",
        },
    }


class RoleCatalogTests(unittest.TestCase):
    def test_topology_has_one_orchestrator_and_no_worker_delegation(self) -> None:
        roles = {role["id"]: role for role in load_role_catalog()}
        self.assertEqual([role["id"] for role in roles.values() if role["category"] == "primary"], ["orchestrator"])
        professionals = {role["id"] for role in roles.values() if role["category"] == "professional"}
        workers = {role["id"] for role in roles.values() if role["category"] == "worker"}
        self.assertEqual(set(roles["orchestrator"]["delegates_to"]), professionals)
        self.assertEqual(set(roles["engineering_lead"]["delegates_to"]), workers)
        for worker in workers:
            self.assertEqual(roles[worker]["delegates_to"], [])


class AdapterRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_each_platform_renders_only_its_native_directory(self) -> None:
        expected = {
            "codex": Path(".codex/agents"),
            "cursor": Path(".cursor/agents"),
            "claude-code": Path(".claude/agents"),
            "opencode": Path(".opencode/agents"),
        }
        for platform in PLATFORM_CHOICES:
            project = self.root / platform
            result = render_project_adapter(
                project, platform,
                opencode_schema="v2" if platform == "opencode" else "auto",
            )
            self.assertEqual(result["status"], "RENDERED")
            files = list((project / expected[platform]).glob("*"))
            self.assertEqual(len(files), len(load_role_catalog()))
            for other, directory in expected.items():
                if other != platform:
                    self.assertFalse((project / directory).exists())

    def test_cursor_and_claude_use_verified_native_frontmatter(self) -> None:
        cursor_root = self.root / "cursor"
        render_project_adapter(cursor_root, "cursor")
        qa = (cursor_root / ".cursor/agents/qa.md").read_text(encoding="utf-8")
        self.assertIn('name: "qa"', qa)
        self.assertIn("model: inherit", qa)
        self.assertIn("readonly: true", qa)
        claude_root = self.root / "claude"
        render_project_adapter(claude_root, "claude-code")
        worker = (claude_root / ".claude/agents/frontend-worker.md").read_text(encoding="utf-8")
        self.assertIn("disallowedTools:\n  - Agent", worker)
        orchestrator = (claude_root / ".claude/agents/orchestrator.md").read_text(encoding="utf-8")
        self.assertNotIn("disallowedTools", orchestrator)
        self.assertIn("Only Orchestrator writes the global run ledger", orchestrator)
        self.assertIn("PASS_WITH_ACCEPTED_RISKS", orchestrator)

    def test_opencode_v1_permissions_enforce_tree_topology(self) -> None:
        render_project_adapter(self.root, "opencode", opencode_schema="v1")
        orchestrator = (self.root / ".opencode/agents/orchestrator.md").read_text(encoding="utf-8")
        self.assertIn("permission:\n  task:", orchestrator)
        self.assertNotIn("permissions:", orchestrator)
        self.assertIn('"*": deny', orchestrator)
        self.assertIn('"engineering-lead": allow', orchestrator)
        lead = (self.root / ".opencode/agents/engineering-lead.md").read_text(encoding="utf-8")
        self.assertIn('"frontend-worker": allow', lead)
        self.assertNotIn('"architect": allow', lead)
        worker = (self.root / ".opencode/agents/frontend-worker.md").read_text(encoding="utf-8")
        self.assertNotIn("allow", worker.split("---", 2)[1])
        for role in ("qa", "product-auditor", "quality-governor"):
            frontmatter = (self.root / ".opencode/agents" / f"{role}.md").read_text(
                encoding="utf-8"
            ).split("---", 2)[1]
            self.assertIn("edit: deny", frontmatter)
            self.assertIn("bash: deny", frontmatter)

    def test_opencode_v2_permissions_enforce_tree_topology(self) -> None:
        render_project_adapter(self.root, "opencode", opencode_schema="v2")
        orchestrator = (self.root / ".opencode/agents/orchestrator.md").read_text(encoding="utf-8")
        frontmatter = orchestrator.split("---", 2)[1]
        self.assertIn("permissions:\n  - action: subagent", frontmatter)
        self.assertNotIn("\npermission:", frontmatter)
        self.assertNotIn("action: task", frontmatter)
        self.assertIn('resource: "*"\n    effect: deny', frontmatter)
        self.assertIn('resource: "engineering-lead"\n    effect: allow', frontmatter)
        lead = (self.root / ".opencode/agents/engineering-lead.md").read_text(encoding="utf-8")
        self.assertIn('resource: "frontend-worker"\n    effect: allow', lead)
        self.assertNotIn('resource: "architect"\n    effect: allow', lead)
        worker = (self.root / ".opencode/agents/frontend-worker.md").read_text(encoding="utf-8")
        self.assertNotIn("effect: allow", worker.split("---", 2)[1])
        for role in ("qa", "product-auditor", "quality-governor"):
            frontmatter = (self.root / ".opencode/agents" / f"{role}.md").read_text(
                encoding="utf-8"
            ).split("---", 2)[1]
            self.assertIn("action: edit", frontmatter)
            self.assertIn("action: shell", frontmatter)

    def test_opencode_auto_schema_is_major_aware_and_fails_closed(self) -> None:
        with patch("platform_runtime._runtime_probe", return_value={
            "status": "VERIFIED", "version": "opencode 1.2.3",
        }):
            self.assertEqual(resolve_opencode_schema("auto"), "v1")
        with patch("platform_runtime._runtime_probe", return_value={
            "status": "VERIFIED", "version": "OpenCode v2.0.7",
        }):
            self.assertEqual(resolve_opencode_schema("auto"), "v2")
            self.assertEqual(resolve_opencode_schema("v2"), "v2")
            with self.assertRaises(ValueError):
                resolve_opencode_schema("v1")
        for version in ("", "dev-build", "opencode 3.0.0"):
            with self.subTest(version=version), patch(
                "platform_runtime._runtime_probe",
                return_value={"status": "NOT_FOUND", "version": version},
            ):
                with self.assertRaises(ValueError):
                    resolve_opencode_schema("auto")
        with patch("platform_runtime._runtime_probe", return_value={
            "status": "VERIFIED", "version": "opencode 3.0.0",
        }):
            with self.assertRaises(ValueError):
                resolve_opencode_schema("v2")

    def test_non_overwrite_then_explicit_update(self) -> None:
        render_project_adapter(self.root, "cursor")
        target = self.root / ".cursor/agents/qa.md"
        target.write_text("user-owned\n", encoding="utf-8")
        blocked = render_project_adapter(self.root, "cursor")
        self.assertEqual(blocked["status"], "BLOCKED_CONFLICT")
        self.assertEqual(target.read_text(encoding="utf-8"), "user-owned\n")
        updated = render_project_adapter(self.root, "cursor", update=True)
        self.assertEqual(updated["status"], "RENDERED")
        self.assertIn("DingXingLiZi shared role contract", target.read_text(encoding="utf-8"))


class PlatformInstallTests(unittest.TestCase):
    def test_install_is_preview_by_default_and_selected_platform_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "home"
            preview = install_platform(root, "claude-code", scope="user")
            self.assertEqual(preview["status"], "PLANNED")
            self.assertFalse(root.exists())
            applied = install_platform(root, "claude-code", scope="user", apply=True)
            self.assertEqual(applied["status"], "INSTALLED")
            self.assertTrue((root / ".claude/skills/software-project-orchestrator/SKILL.md").is_file())
            self.assertTrue((root / ".claude/agents/orchestrator.md").is_file())
            self.assertFalse((root / ".cursor").exists())
            self.assertFalse((root / ".opencode").exists())
            self.assertFalse(applied["network_access"])
            self.assertFalse(applied["credential_access"])

    def test_install_rejects_symlinked_platform_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "home"
            outside = Path(temporary) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / ".cursor").symlink_to(outside, target_is_directory=True)
            result = install_platform(root, "cursor", scope="user", apply=True)
            self.assertEqual(result["status"], "BLOCKED_CONFLICT")
            self.assertEqual(list(outside.iterdir()), [])

    def test_doctor_and_installer_reject_linked_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)

            skill_root = base / "skill-link"
            install_platform(skill_root, "cursor", scope="project", apply=True)
            skill = skill_root / ".cursor/skills/software-project-orchestrator"
            external_skill = base / "external-skill"
            skill.rename(external_skill)
            skill.symlink_to(external_skill, target_is_directory=True)
            result = doctor_platform("cursor", skill_root)
            skill_check = next(item for item in result["checks"] if item["id"] == "portable-skill")
            self.assertEqual(skill_check["status"], "FAIL")
            self.assertEqual(result["compatibility_level"], "L0")

            profile_root = base / "profile-link"
            install_platform(profile_root, "cursor", scope="project", apply=True)
            profile = profile_root / ".cursor/agents/qa.md"
            external_profile = base / "external-profile.md"
            profile.rename(external_profile)
            profile.symlink_to(external_profile)
            result = doctor_platform("cursor", profile_root)
            profile_check = next(item for item in result["checks"] if item["id"] == "native-agent-profiles")
            self.assertEqual(profile_check["status"], "FAIL")
            self.assertTrue(any(Path(item).name == "qa.md" for item in profile_check["unsafe"]))

            hardlink_root = base / "profile-hardlink"
            install_platform(hardlink_root, "cursor", scope="project", apply=True)
            hardlink = hardlink_root / ".cursor/agents/qa.md"
            external_hardlink = base / "external-hardlink.md"
            hardlink.rename(external_hardlink)
            os.link(external_hardlink, hardlink)
            result = doctor_platform("cursor", hardlink_root)
            profile_check = next(item for item in result["checks"] if item["id"] == "native-agent-profiles")
            self.assertEqual(profile_check["status"], "FAIL")
            self.assertTrue(any(Path(item).name == "qa.md" for item in profile_check["unsafe"]))
            reinstall = install_platform(
                hardlink_root, "cursor", scope="project", apply=True, update=True,
            )
            self.assertEqual(reinstall["status"], "BLOCKED_CONFLICT")
            self.assertTrue(any(Path(item).name == "qa.md" for item in reinstall["conflicts"]))

    def test_every_platform_and_scope_install_carries_the_mit_license(self) -> None:
        expected_license = (ROOT / "LICENSE").read_bytes()
        for platform in PLATFORM_CHOICES:
            for scope in ("user", "project"):
                with self.subTest(platform=platform, scope=scope):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary) / "target"
                        result = install_platform(
                            root, platform, scope=scope, apply=True,
                            opencode_schema="v2" if platform == "opencode" else "auto",
                        )
                        self.assertEqual(result["status"], "INSTALLED")
                        spec_path = ROOT / "assets/platforms" / platform / "adapter.json"
                        spec = json.loads(spec_path.read_text(encoding="utf-8"))
                        directory = spec[
                            "user_skill_directory" if scope == "user" else "project_skill_directory"
                        ]
                        installed = root / directory / "software-project-orchestrator/LICENSE"
                        self.assertEqual(installed.read_bytes(), expected_license)


class RuntimeAndModelTests(unittest.TestCase):
    def test_manifest_does_not_claim_models_or_auth_without_evidence(self) -> None:
        result = build_runtime_manifest("cursor")
        self.assertEqual(result["model_inventory"]["models"], [])
        self.assertEqual(result["model_inventory"]["evidence"]["status"], "NOT_PROVIDED")
        self.assertEqual(result["claims"]["authenticated"], "UNKNOWN")
        self.assertEqual(result["claims"]["actual_model_used"], "UNKNOWN")

    def test_verified_inventory_requires_named_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            models = Path(temporary) / "models.json"
            models.write_text(json.dumps({"models": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_runtime_manifest("codex", models_file=models, models_verified=True)

    def test_model_inventory_rejects_empty_whitespace_and_control_identifiers(self) -> None:
        invalid_entries = [
            {"id": "valid/model", "provider": "", "capability_tier": "EXPERT", "reasoning_efforts": ["high"]},
            {"id": "valid/model", "provider": "   ", "capability_tier": "EXPERT", "reasoning_efforts": ["high"]},
            {"id": "valid/model", "provider": "bad\nprovider", "capability_tier": "EXPERT", "reasoning_efforts": ["high"]},
            {"id": "", "provider": "valid", "capability_tier": "EXPERT", "reasoning_efforts": ["high"]},
            {"id": "bad model", "provider": "valid", "capability_tier": "EXPERT", "reasoning_efforts": ["high"]},
            {"id": "bad\nmodel", "provider": "valid", "capability_tier": "EXPERT", "reasoning_efforts": ["high"]},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            models = Path(temporary) / "models.json"
            for entry in invalid_entries:
                with self.subTest(entry=entry):
                    models.write_text(json.dumps({"models": [entry]}), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Model IDs|provider"):
                        build_runtime_manifest(
                            "codex", models_file=models,
                            evidence_source="explicit invalid fixture",
                        )

        invalid_manifest = manifest("codex", verified=True)
        invalid_manifest["model_inventory"]["models"][-1]["provider"] = ""
        with self.assertRaisesRegex(ValueError, "provider identifier"):
            resolve_model(
                invalid_manifest, "EXPERT", reasoning_effort="high",
                risk_flags=["security"],
            )

    def test_l4_receipt_requires_exact_runtime_attestation_schema_and_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            models = Path(temporary) / "models.json"
            models.write_text(json.dumps({"models": [{
                "id": "fixture-model",
                "provider": "fixture-provider",
                "capability_tier": "EXPERT",
                "reasoning_efforts": ["high"],
            }]}), encoding="utf-8")
            path = Path(temporary) / "execution.json"
            value = {
                "schema_version": 1,
                "type": "platform_execution_receipt",
                "platform": "cursor",
                "task_id": "TASK-42",
                "agent": "qa",
                "actual_provider": "fixture-provider",
                "actual_model": "fixture-model",
                "actual_reasoning": "high",
                "runtime_version": "fixture-runtime-1",
                "evidence_source": "fixture native launch log",
                "recorded_at": "2026-08-28T08:00:00Z",
                "attestation": "VERIFIED_RUNTIME",
                "receipt_fingerprint": "",
            }
            value["receipt_fingerprint"] = _execution_receipt_fingerprint(value)
            path.write_text(json.dumps(value), encoding="utf-8")
            with patch("platform_runtime._runtime_probe", return_value={
                "status": "VERIFIED", "executable": "/fixture/cursor",
                "version": "fixture-runtime-1", "evidence_source": "fixture",
            }):
                accepted = build_runtime_manifest(
                    "cursor", models_file=models, models_verified=True,
                    evidence_source="verified fixture inventory", dispatch_receipt=path,
                )
            self.assertEqual(accepted["dispatch_evidence"]["status"], "VERIFIED")
            self.assertEqual(accepted["dispatch_evidence"]["consistency"], "CROSS_CHECKED")
            value["actual_model"] = "tampered-model"
            value["receipt_fingerprint"] = _execution_receipt_fingerprint(value)
            path.write_text(json.dumps(value), encoding="utf-8")
            with patch("platform_runtime._runtime_probe", return_value={
                "status": "VERIFIED", "executable": "/fixture/cursor",
                "version": "fixture-runtime-1", "evidence_source": "fixture",
            }):
                rejected = build_runtime_manifest(
                    "cursor", models_file=models, models_verified=True,
                    evidence_source="verified fixture inventory", dispatch_receipt=path,
                )
            self.assertEqual(rejected["dispatch_evidence"]["status"], "UNVERIFIED")

    def test_receipt_cross_checks_provider_reasoning_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models.json"
            models.write_text(json.dumps({"models": [{
                "id": "provider/model-A", "provider": "provider",
                "capability_tier": "EXPERT", "reasoning_efforts": ["high"],
            }]}), encoding="utf-8")
            base = {
                "schema_version": 1, "type": "platform_execution_receipt",
                "platform": "cursor", "task_id": "TASK-99", "agent": "qa",
                "actual_provider": "provider", "actual_model": "provider/model-A",
                "actual_reasoning": "high", "runtime_version": "cursor-verified-1",
                "evidence_source": "local host log", "recorded_at": "2026-08-28T08:00:00Z",
                "attestation": "VERIFIED_RUNTIME", "receipt_fingerprint": "",
            }
            probe = {
                "status": "VERIFIED", "executable": "/fixture/cursor",
                "version": "cursor-verified-1", "evidence_source": "fixture",
            }
            for field, bad_value in (
                ("actual_provider", "evil-provider"),
                ("actual_model", "evil/not-in-inventory"),
                ("actual_reasoning", "ultra"),
                ("runtime_version", "different-runtime"),
            ):
                value = dict(base)
                value[field] = bad_value
                value["receipt_fingerprint"] = _execution_receipt_fingerprint(value)
                receipt = root / (field + ".json")
                receipt.write_text(json.dumps(value), encoding="utf-8")
                with patch("platform_runtime._runtime_probe", return_value=probe):
                    result = build_runtime_manifest(
                        "cursor", models_file=models, models_verified=True,
                        evidence_source="verified fixture inventory", dispatch_receipt=receipt,
                    )
                self.assertEqual(result["dispatch_evidence"]["status"], "UNVERIFIED", field)
                self.assertFalse(result["claims"]["native_dispatch_completed"], field)

    def test_high_risk_unverified_inventory_fails_closed(self) -> None:
        result = resolve_model(
            manifest("cursor", verified=False), "ADVANCED",
            reasoning_effort="high", risk_flags=["security"],
        )
        self.assertEqual(result["status"], "BLOCKED_UNVERIFIED_HIGH_RISK_RUNTIME")
        self.assertEqual(result["selected_model"], "")

    def test_high_risk_raises_capability_floor(self) -> None:
        result = resolve_model(
            manifest("cursor", verified=True), "STANDARD",
            reasoning_effort="high", risk_flags=["ai_safety"],
        )
        self.assertEqual(result["status"], "ROUTED")
        self.assertEqual(result["requested_capability_tier"], "EXPERT")
        self.assertEqual(result["selected_capability_tier"], "EXPERT")

    def test_verified_inventory_resolves_exact_or_controlled_upward(self) -> None:
        exact = resolve_model(manifest("opencode", verified=True), "ADVANCED", reasoning_effort="high")
        self.assertEqual(exact["status"], "ROUTED")
        self.assertEqual(exact["selected_model"], "opencode/advanced")
        upward = resolve_model(manifest("opencode", verified=True), "STANDARD", reasoning_effort="high")
        self.assertEqual(upward["selected_capability_tier"], "ADVANCED")
        self.assertFalse(upward["actual_model_attested"])

    def test_manifest_output_is_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            first = write_json_non_overwriting(path, manifest("codex", verified=True))
            self.assertEqual(first["status"], "CREATED")
            path.write_text("{}\n", encoding="utf-8")
            blocked = write_json_non_overwriting(path, manifest("codex", verified=True))
            self.assertEqual(blocked["status"], "BLOCKED_CONFLICT")
            updated = write_json_non_overwriting(path, manifest("codex", verified=True), update=True)
            self.assertEqual(updated["status"], "UPDATED")

    def test_manifest_read_rejects_leaf_ancestor_symlinks_and_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.json"
            outside.write_text("{}\n", encoding="utf-8")

            leaf = root / "leaf.json"
            leaf.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlink"):
                load_runtime_manifest(leaf)

            linked = root / "hardlink.json"
            os.link(outside, linked)
            with self.assertRaisesRegex(ValueError, "single-link"):
                load_runtime_manifest(linked)

            external_dir = root / "external"
            external_dir.mkdir()
            (external_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
            linked_dir = root / "linked-dir"
            linked_dir.symlink_to(external_dir, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "traverses a symlink"):
                load_runtime_manifest(linked_dir / "manifest.json")

    def test_loaded_manifest_revalidates_probe_time_inventory_source_and_models(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models.json"
            models.write_text(json.dumps({"models": [{
                "id": "provider/model-A", "provider": "provider",
                "capability_tier": "EXPERT", "reasoning_efforts": ["high"],
            }]}), encoding="utf-8")
            probe = {
                "status": "VERIFIED", "executable": "/fixture/cursor",
                "version": "cursor-1", "evidence_source": "fixture",
            }
            with patch("platform_runtime._runtime_probe", return_value=probe):
                value = build_runtime_manifest(
                    "cursor", models_file=models, models_verified=True,
                    evidence_source="verified fixture inventory",
                )
            path = root / "runtime.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with patch("platform_runtime._runtime_probe", return_value=probe):
                self.assertEqual(load_runtime_manifest(path)["status"], "VERIFIED_WITH_MODEL_INVENTORY")

            forged = json.loads(path.read_text(encoding="utf-8"))
            forged["runtime"] = {
                "status": "VERIFIED", "executable": "/nonexistent/cursor",
                "version": "fake", "evidence_source": "hand written",
            }
            path.write_text(json.dumps(forged), encoding="utf-8")
            with patch("platform_runtime._runtime_probe", return_value=probe):
                with self.assertRaisesRegex(ValueError, "current host"):
                    load_runtime_manifest(path)

            value["captured_at"] = "2099-01-01T00:00:00Z"
            path.write_text(json.dumps(value), encoding="utf-8")
            with patch("platform_runtime._runtime_probe", return_value=probe):
                with self.assertRaisesRegex(ValueError, "future"):
                    load_runtime_manifest(path)

            with patch("platform_runtime._runtime_probe", return_value=probe):
                value = build_runtime_manifest(
                    "cursor", models_file=models, models_verified=True,
                    evidence_source="verified fixture inventory",
                )
            value["model_inventory"]["models"][0]["id"] = "fake/model"
            path.write_text(json.dumps(value), encoding="utf-8")
            with patch("platform_runtime._runtime_probe", return_value=probe):
                with self.assertRaisesRegex(ValueError, "normalized models"):
                    load_runtime_manifest(path)

            with patch("platform_runtime._runtime_probe", return_value=probe):
                value = build_runtime_manifest(
                    "cursor", models_file=models, models_verified=True,
                    evidence_source="verified fixture inventory",
                )
            path.write_text(json.dumps(value), encoding="utf-8")
            models.write_text('{"models": []}', encoding="utf-8")
            with patch("platform_runtime._runtime_probe", return_value=probe):
                with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
                    load_runtime_manifest(path)

    def test_doctor_never_calls_rendered_profiles_l4_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = install_platform(root, "cursor", scope="project", apply=True)
            self.assertEqual(installed["status"], "INSTALLED")
            with patch("platform_runtime._runtime_probe", return_value={
                "status": "VERIFIED", "executable": "/fixture/cursor",
                "version": "1", "evidence_source": "fixture",
            }):
                level3 = doctor_platform("cursor", root, manifest=manifest("cursor", verified=True))
                self.assertEqual(level3["compatibility_level"], "L3")
                level4 = doctor_platform("cursor", root, manifest=manifest("cursor", verified=True, dispatch=True))
                self.assertEqual(level4["compatibility_level"], "L4")


class PlatformCliTests(unittest.TestCase):
    def _in_process_cli(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["orchestrator.py", *args]), redirect_stdout(stdout), redirect_stderr(stderr):
            result = orchestrator_main()
        return result, stdout.getvalue(), stderr.getvalue()

    def test_opencode_init_schema_failure_is_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for name, version, schema in (
                ("missing", "", "auto"),
                ("mismatch", "opencode 1.9.0", "v2"),
                ("future", "opencode 3.0.0", "v2"),
            ):
                project = base / name
                with self.subTest(name=name), patch(
                    "platform_runtime._runtime_probe",
                    return_value={"status": "NOT_FOUND", "version": version},
                ):
                    code, _, error = self._in_process_cli(
                        "init", str(project), "--project-name", name,
                        "--domain", "SaaS", "--platform", "opencode",
                        "--opencode-schema", schema,
                    )
                    self.assertEqual(code, 2)
                    self.assertIn("ERROR:", error)
                    self.assertFalse(project.exists())

    def test_opencode_init_adapter_conflict_is_zero_additional_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            profile = project / ".opencode/agents/orchestrator.md"
            profile.parent.mkdir(parents=True)
            profile.write_text("user-owned\n", encoding="utf-8")
            with patch(
                "platform_runtime._runtime_probe",
                return_value={"status": "NOT_FOUND", "version": ""},
            ):
                code, _, error = self._in_process_cli(
                    "init", str(project), "--project-name", "Conflict",
                    "--domain", "SaaS", "--platform", "opencode",
                    "--opencode-schema", "v2",
                )
            self.assertEqual(code, 2)
            self.assertIn("already exist", error)
            self.assertEqual(profile.read_text(encoding="utf-8"), "user-owned\n")
            self.assertFalse((project / "docs").exists())
            self.assertFalse((project / ".dingxinglizi").exists())

    def test_opencode_init_symlinked_adapter_root_is_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            outside = base / "outside"
            project.mkdir()
            outside.mkdir()
            (project / ".opencode").symlink_to(outside, target_is_directory=True)
            with patch(
                "platform_runtime._runtime_probe",
                return_value={"status": "NOT_FOUND", "version": ""},
            ):
                code, _, error = self._in_process_cli(
                    "init", str(project), "--project-name", "Symlink",
                    "--domain", "SaaS", "--platform", "opencode",
                    "--opencode-schema", "v2",
                )
            self.assertEqual(code, 2)
            self.assertIn("already exist", error)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((project / "docs").exists())
            self.assertFalse((project / ".dingxinglizi").exists())

    def test_cli_render_and_platform_neutral_init(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            result = cli(
                "init", str(project), "--project-name", "Portable Test",
                "--domain", "SaaS", "--complexity", "Simple", "--platform", "cursor",
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue((project / ".cursor/agents/orchestrator.md").is_file())
            self.assertTrue((project / ".dingxinglizi/orchestration").is_dir())
            self.assertFalse((project / ".codex/agents").exists())
            self.assertFalse((project / ".claude").exists())

    def test_cli_model_resolve_returns_blocking_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            models = Path(temporary) / "models.json"
            models.write_text(json.dumps({"models": [{
                "id": "declared/model", "provider": "declared",
                "capability_tier": "EXPERT", "reasoning_efforts": ["high"],
            }]}), encoding="utf-8")
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps(build_runtime_manifest(
                "claude-code", models_file=models,
                evidence_source="unverified test declaration",
            )), encoding="utf-8")
            result = cli(
                "platform", "model-resolve", str(path), "--tier", "EXPERT",
                "--reasoning", "high", "--risk", "security",
            )
            self.assertEqual(result.returncode, 3, result.stdout)
            self.assertIn("BLOCKED_UNVERIFIED_HIGH_RISK_RUNTIME", result.stdout)

    def test_cli_runtime_manifest_defaults_to_active_project_control_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            initialized = cli(
                "init", str(project), "--project-name", "Manifest Test",
                "--domain", "CRM", "--platform", "opencode",
                "--opencode-schema", "v2",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout)
            result = cli(
                "platform", "runtime-manifest", "--platform", "opencode",
                "--project-dir", str(project),
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            path = project / ".dingxinglizi/orchestration/runtime-manifest.json"
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["platform"], "opencode")

    def test_project_manifest_write_rejects_symlink_escape_and_hardlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)

            def initialized_project(name: str) -> Path:
                project = base / name
                result = cli(
                    "init", str(project), "--project-name", name,
                    "--domain", "SaaS", "--platform", "codex",
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                return project

            project = initialized_project("leaf-symlink")
            outside = base / "outside-leaf.json"
            outside.write_text("DO_NOT_OVERWRITE\n", encoding="utf-8")
            target = project / ".dingxinglizi/orchestration/runtime-manifest.json"
            target.symlink_to(outside)
            result = cli(
                "platform", "runtime-manifest", "--platform", "codex",
                "--project-dir", str(project), "--update",
            )
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("symlink", result.stdout)
            self.assertEqual(outside.read_text(encoding="utf-8"), "DO_NOT_OVERWRITE\n")

            project = initialized_project("ancestor-symlink")
            orchestration = project / ".dingxinglizi/orchestration"
            preserved = project / ".dingxinglizi/orchestration-preserved"
            orchestration.rename(preserved)
            external_dir = base / "outside-orchestration"
            external_dir.mkdir()
            orchestration.symlink_to(external_dir, target_is_directory=True)
            result = cli(
                "platform", "runtime-manifest", "--platform", "codex",
                "--project-dir", str(project), "--update",
            )
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("symlink", result.stdout)
            self.assertEqual(list(external_dir.iterdir()), [])

            project = initialized_project("hardlink")
            outside_hardlink = base / "outside-hardlink.json"
            outside_hardlink.write_text("DO_NOT_OVERWRITE\n", encoding="utf-8")
            hardlink_target = project / ".dingxinglizi/orchestration/runtime-manifest.json"
            os.link(outside_hardlink, hardlink_target)
            result = cli(
                "platform", "runtime-manifest", "--platform", "codex",
                "--project-dir", str(project), "--update",
            )
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("single-link", result.stdout)
            self.assertEqual(outside_hardlink.read_text(encoding="utf-8"), "DO_NOT_OVERWRITE\n")

    def test_non_codex_mcp_provisioning_fails_closed_without_writing_codex_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            initialized = cli(
                "init", str(project), "--project-name", "MCP Boundary",
                "--domain", "SaaS", "--platform", "cursor",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout)
            catalog_path = project / ".dingxinglizi/orchestration/capability-catalog.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog["capabilities"]["docs-read"] = {
                "kind": "mcp_http",
                "source": {
                    "url": "https://example.invalid/mcp",
                    "credential_mode": "none",
                },
                "permission": "read",
                "allowed_tools": ["search"],
            }
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            result = cli(
                "capabilities", str(project), "--required", "docs-read", "--apply",
            )
            self.assertEqual(result.returncode, 3, result.stdout)
            self.assertIn("BLOCKED_PLATFORM_CONFIGURATION", result.stdout)
            self.assertFalse((project / ".codex/config.toml").exists())


if __name__ == "__main__":
    unittest.main()
