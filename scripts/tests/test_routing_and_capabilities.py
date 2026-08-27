#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
import io
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
from resolve_capabilities import download_skill  # noqa: E402


def run(script: str, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPTS / script), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


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


class CapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        result = run(
            "init_project.py", self.root,
            "--project-name", "Automation Test", "--domain", "SaaS", "--complexity", "Standard",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        inventory = self.root / ".codex/orchestration/runtime-inventory.json"
        inventory.write_text(json.dumps({
            "schema_version": 1,
            "status": "VERIFIED",
            "available_models": ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"],
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
        result = run(
            "create_task_package.py", self.root, "--task-id", "TASK-AUTO-1",
            "--owner", "engineering_lead", "--reviewer", "qa",
            "--objective", "Implement approved permissions", "--task-type", "implementation",
            "--risk", "permissions", "--required-capability", "github-read",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        text = (self.root / "tasks/TASK-AUTO-1.yaml").read_text(encoding="utf-8")
        self.assertIn('preferred_model: "gpt-5.6-sol"', text)
        self.assertIn('model_reasoning_effort: "high"', text)
        self.assertIn('required:\n    - "github-read"', text)
        blocked = run("check_execution_plan.py", self.root, "tasks/TASK-AUTO-1.yaml")
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn("BLOCKED_CAPABILITY", blocked.stdout)
        skill = self.root / ".agents/skills/github-read"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: github-read\ndescription: test\n---\n", encoding="utf-8")
        ready = run("check_execution_plan.py", self.root, "tasks/TASK-AUTO-1.yaml")
        self.assertEqual(ready.returncode, 0, ready.stdout)

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
        self.assertIn("unsupported task_type", typo.stdout)

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
        self.assertEqual(applied.returncode, 0, applied.stdout)
        self.assertIn('"status": "PROVISIONED"', applied.stdout)
        second = run("resolve_capabilities.py", self.root, "--required", "public-read", "--apply")
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertIn('"status": "SATISFIED"', second.stdout)
        added = run("resolve_capabilities.py", self.root, "--required", "second-read", "--apply")
        self.assertEqual(added.returncode, 0, added.stdout)
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
