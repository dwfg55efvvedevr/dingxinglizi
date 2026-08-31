from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from large_repository_review import (  # noqa: E402
    finalize_review,
    ingest_result,
    merge_findings,
    plan_repairs,
    preview_review,
    record_repair,
    record_rereview,
    record_qa,
    repair_contract,
    shard_contract,
    start_review,
    status_review,
)
from project_layout import control_path  # noqa: E402
from review_planning import build_review_plan, technology_surface  # noqa: E402
from review_repository import capture_worktree_snapshot  # noqa: E402
from dispatch_receipt import record_dispatch_receipt  # noqa: E402


RUN_ID = "RUN-20260831T000000Z-abc123"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True,
    )
    return result.stdout.strip()


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def init_git(root: Path, *, legacy: bool = False) -> str:
    git(root, "init", "-q")
    git(root, "config", "user.email", "review@example.invalid")
    git(root, "config", "user.name", "Review Test")
    control = ".codex" if legacy else ".dingxinglizi"
    write(root, ".gitignore", ".dingxinglizi/\n.codex/\n")
    write(root, "apps/web/package.json", '{"name":"web"}\n')
    write(root, "apps/web/src/main.ts", "export const ready = true;\n")
    write(root, "services/api/pyproject.toml", "[project]\nname='api'\nversion='1'\n")
    write(root, "services/api/auth/service.py", "def allowed():\n    return True\n")
    write(root, "db/migrations/001.sql", "create table test(id int);\n")
    write(root, "vendor/copied.py", "copied = True\n")
    (root / control / "runs" / RUN_ID).mkdir(parents=True)
    write(root, f"{control}/runs/{RUN_ID}/run.json", json.dumps({
        "schema_version": 1, "run_id": RUN_ID, "status": "OPEN", "project": "review-test",
    }))
    git(root, "add", ".")
    git(root, "commit", "-qm", "initial")
    return git(root, "rev-parse", "HEAD")


def review_task(root: Path, shard: dict) -> str:
    contract = shard_contract(root, shard["shard_id"])
    task_id = "TASK-" + shard["shard_id"].replace("SHARD-", "REVIEW-").replace("-", "_")
    owner = str(contract["suggested_owner"])
    reviewer = "engineering_lead" if owner.endswith("_worker") else "orchestrator"
    included = "\n".join(f"    - {json.dumps(path)}" for path in contract["included_files"])
    risk_lenses = "\n".join(f"    - {json.dumps(value)}" for value in contract["risk_lenses"])
    objects = json.dumps(contract["pinned_file_objects"], sort_keys=True)
    output = str(contract["findings_output"])
    evidence_output = str(contract["evidence_output"])
    text = f'''schema_version: 2
run_id: {json.dumps(RUN_ID)}
source_input_fingerprint: {json.dumps('a' * 64)}
task_id: {json.dumps(task_id)}
status: "READY_FOR_DISPATCH"
project: "review-test"
stage: "CODE_REVIEW"
owner: {json.dumps(owner)}
reviewer: {json.dumps(reviewer)}
return_to: {json.dumps('engineering_lead' if owner.endswith('_worker') else 'orchestrator')}
task_type: {json.dumps(contract['task_type'])}
objective: "Review one immutable repository shard and return bounded evidence."
role_execution:
  role_plan_fingerprint: {json.dumps('b' * 64)}
execution_profile:
  route_fingerprint: {json.dumps('c' * 64)}
capability_requirements:
  required: []
business_context:
  value: "Inspect the pinned shard for correctness and declared risk lenses."
input_documents:
  - ".gitignore"
scope:
  - "Review only the pinned shard objects."
out_of_scope: []
deliverables:
  - "Structured shard result with evidence."
acceptance_criteria:
  - id: "AC-REVIEW"
    given: "A pinned review shard and immutable object map"
    when: "The reviewer inspects every included file"
    then: "The result covers every file and records findings"
    evidence: "A project-local evidence file and structured result"
allowed_files:
  - {json.dumps(output)}
  - {json.dumps(evidence_output)}
validation:
  commands: []
  manual:
    - "Verify every included object and result lineage."
review_contract:
  status: "ROUTED"
  review_id: {json.dumps(contract['review_id'])}
  mode: {json.dumps(contract['mode'])}
  phase: {json.dumps(contract['phase'])}
  shard_id: {json.dumps(contract['shard_id'])}
  target_fingerprint: {json.dumps(contract['target_fingerprint'])}
  repository_manifest_fingerprint: {json.dumps(contract['repository_manifest_fingerprint'])}
  review_plan_fingerprint: {json.dumps(contract['review_plan_fingerprint'])}
  shard_input_fingerprint: {json.dumps(contract['shard_input_fingerprint'])}
  trust_policy_fingerprint: {json.dumps(contract['trust_policy_fingerprint'])}
  trusted_instruction_files: []
  repository_execution_authorized: false
  default_execution_policy: {json.dumps(contract['default_execution_policy'])}
  included_files:
{included}
  pinned_file_objects_json: {json.dumps(objects)}
  findings_output: {json.dumps(output)}
  evidence_output: {json.dumps(evidence_output)}
  source_write_authorized: false
  fresh_session_required: true
  compact_handoff_required: true
  session_attestation_required: true
  risk_lenses:
{risk_lenses if risk_lenses else '    []'}
  context_budget:
    max_files: {contract['context_budget']['max_files']}
    max_bytes: {contract['context_budget']['max_bytes']}
    max_estimated_tokens: {contract['context_budget']['max_estimated_tokens']}
    estimated_files: {contract['context_budget']['estimated_files']}
    estimated_bytes: {contract['context_budget']['estimated_bytes']}
    estimated_tokens: {contract['context_budget']['estimated_tokens']}
'''
    write(root, f"tasks/{task_id}.yaml", text)
    record_dispatch_receipt(root, text)
    return task_id


def shard_result(root: Path, review: dict, shard: dict, *, finding: dict | None = None, attested: bool = True) -> dict:
    session = "session-" + shard["shard_id"].lower()
    contract = shard_contract(root, shard["shard_id"])
    evidence = str(contract["evidence_output"])
    write(root, evidence, "bounded shard evidence\n")
    value = {
        "task_id": review_task(root, shard),
        "review_id": contract["review_id"],
        "reviewer_id": contract["suggested_owner"],
        "review_session_id": session,
        "target_fingerprint": review["target_fingerprint"],
        "inventory_fingerprint": contract["repository_manifest_fingerprint"],
        "plan_fingerprint": contract["review_plan_fingerprint"],
        "shard_input_fingerprint": contract["shard_input_fingerprint"],
        "trust_policy_fingerprint": contract["trust_policy_fingerprint"],
        "status": "COMPLETE",
        "reviewed_files": shard["files"],
        "reviewed_objects": contract["pinned_file_objects"],
        "file_evidence": [
            {
                "path": path,
                "object_id": contract["pinned_file_objects"][path],
                "checks_performed": ["control-flow", "failure-paths", "declared-risk-lenses"],
                "observation": "Pinned object inspected under the bounded shard contract.",
            }
            for path in shard["files"]
        ],
        "evidence_refs": [evidence],
        "findings": [finding] if finding else [],
        "handoff_summary": "Bounded shard review complete",
    }
    if attested:
        value["session_attestation"] = {
            "session_id": session, "shard_id": shard["shard_id"],
            "fresh_session_attested": True, "compact_handoff_attested": True,
            "attested_by": "orchestrator",
        }
    return value


def qa_task(root: Path, evidence_refs: list[str], task_id: str = "TASK-FINAL-QA") -> str:
    evidence_yaml = "\n".join(f"    - {json.dumps(value)}" for value in evidence_refs)
    text = f'''schema_version: 2
run_id: {json.dumps(RUN_ID)}
source_input_fingerprint: {json.dumps('a' * 64)}
task_id: {json.dumps(task_id)}
status: "COMPLETED"
project: "review-test"
stage: "READY_FOR_QA"
owner: "qa"
reviewer: "orchestrator"
return_to: "orchestrator"
task_type: "qa"
objective: "Independently verify review coverage, findings, target lineage and residual risk."
role_execution:
  role_plan_fingerprint: {json.dumps('b' * 64)}
execution_profile:
  route_fingerprint: {json.dumps('c' * 64)}
capability_requirements:
  required: []
business_context:
  value: "Final independent QA for the bounded repository review."
input_documents:
  - ".gitignore"
scope:
  - "Verify current target, coverage, evidence, findings and review claims."
out_of_scope: []
deliverables:
  - "Independent final QA conclusion with project-local evidence."
acceptance_criteria:
  - id: "AC-QA"
    given: "Complete shard coverage and merged findings"
    when: "QA independently checks lineage and evidence"
    then: "Only supported completion claims pass"
    evidence: "Project-local final QA evidence"
allowed_files: []
validation:
  commands: []
  manual:
    - "Verify review target, coverage, findings, evidence and limitations."
review_contract:
  status: "NOT_APPLICABLE"
handoff:
  conclusion: "PASS"
  inputs_checked: []
  artifacts: []
  evidence:
{evidence_yaml}
  deviations: []
  downstream_decisions: []
'''
    write(root, f"tasks/{task_id}.yaml", text)
    record_dispatch_receipt(root, text)
    return task_id


def repair_lifecycle_task(
    root: Path,
    repair_plan_id: str,
    phase: str,
    task_id: str,
) -> tuple[str, str]:
    contract = repair_contract(root, repair_plan_id, phase=phase)
    evidence = str(contract["evidence_output"])
    write(root, evidence, f"{phase.lower()} evidence for {repair_plan_id}\n")
    allowed_yaml = "\n".join(f"  - {json.dumps(value)}" for value in contract["allowed_files"])
    finding_yaml = "\n".join(f"    - {json.dumps(value)}" for value in contract["finding_ids"])
    source_yaml = "\n".join(f"    - {json.dumps(value)}" for value in contract["allowed_source_files"])
    owner = str(contract["owner"])
    reviewer = "qa" if owner.endswith("_worker") else "orchestrator"
    text = f'''schema_version: 2
run_id: {json.dumps(RUN_ID)}
source_input_fingerprint: {json.dumps('a' * 64)}
task_id: {json.dumps(task_id)}
status: "COMPLETED"
project: "review-test"
stage: "CODE_REVIEW"
owner: {json.dumps(owner)}
reviewer: {json.dumps(reviewer)}
return_to: {json.dumps('engineering_lead' if owner.endswith('_worker') else 'orchestrator')}
task_type: {json.dumps(contract['task_type'])}
objective: "Execute one governed repair lifecycle package."
role_execution:
  role_plan_fingerprint: {json.dumps('b' * 64)}
execution_profile:
  route_fingerprint: {json.dumps('c' * 64)}
capability_requirements:
  required: []
business_context:
  value: "Resolve or independently verify the finding-bound repair plan."
input_documents:
  - ".gitignore"
scope:
  - "Execute only the governed repair contract."
out_of_scope: []
deliverables:
  - "Repair lifecycle evidence and compact handoff."
acceptance_criteria:
  - id: "AC-REPAIR"
    given: "A fingerprinted finding-bound repair contract"
    when: "The assigned owner completes its bounded phase"
    then: "Source and evidence stay inside the authorized paths"
    evidence: "The contract-bound repair lifecycle evidence"
allowed_files:
{allowed_yaml}
validation:
  commands: []
  manual:
    - "Verify finding, target, file boundary and evidence lineage."
review_contract:
  status: "NOT_APPLICABLE"
repair_contract:
  status: "ROUTED"
  review_id: {json.dumps(contract['review_id'])}
  repair_plan_id: {json.dumps(contract['repair_plan_id'])}
  repair_plan_fingerprint: {json.dumps(contract['repair_plan_fingerprint'])}
  phase: {json.dumps(contract['phase'])}
  finding_ids:
{finding_yaml}
  allowed_source_files:
{source_yaml}
  target_fingerprint: {json.dumps(contract['target_fingerprint'])}
  source_write_authorized: {str(contract['source_write_authorized']).lower()}
  evidence_output: {json.dumps(evidence)}
handoff:
  conclusion: "COMPLETED"
  inputs_checked: []
  artifacts: []
  evidence:
    - {json.dumps(evidence)}
  deviations: []
  downstream_decisions: []
'''
    write(root, f"tasks/{task_id}.yaml", text)
    record_dispatch_receipt(root, text)
    return task_id, evidence


class LargeRepositoryReviewTests(unittest.TestCase):
    def test_preview_is_zero_write_and_matches_persisted_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            preview = preview_review(root, baseline=commit, target=commit)
            self.assertEqual(preview["write_mode"], "PREVIEW_NO_STATE_WRITTEN")
            self.assertFalse(control_path(root, f"runs/{RUN_ID}/review").exists())
            started = start_review(root, baseline=commit, target=commit)
            self.assertEqual(started["write_mode"], "PERSISTED")
            self.assertEqual(preview["inventory_fingerprint"], started["inventory_fingerprint"])
            self.assertEqual(preview["plan_fingerprint"], started["plan_fingerprint"])
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            shard = plan["primary_shards"][0]
            contract = shard_contract(root, shard["shard_id"])
            self.assertEqual(contract["status"], "ROUTED")
            self.assertEqual(contract["included_files"], shard["files"])
            self.assertFalse(contract["source_write_authorized"])
            self.assertTrue(contract["fresh_session_required"])
            self.assertEqual(contract["completion_claim_limit"], "ONE_SHARD_RESULT_ONLY; NO_REPOSITORY_COMPLETION_CLAIM")

    def test_multilanguage_inventory_modules_risks_and_v3_control_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            result = start_review(root, baseline=commit, target=commit)
            self.assertEqual(result["status"], "READY")
            self.assertEqual(result["snapshot_kind"], "GIT_COMMIT")
            self.assertIn(".dingxinglizi/runs/", result["review_root"])
            inventory = json.loads(control_path(root, f"runs/{RUN_ID}/review/inventory.json").read_text())
            roots = {item["root"] for item in inventory["modules"]}
            self.assertIn("apps/web", roots)
            self.assertIn("services/api", roots)
            dispositions = {item["path"]: item["disposition"] for item in inventory["entries"]}
            self.assertEqual(dispositions["vendor/copied.py"], "EXCLUDED_VENDOR")
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            risks = {risk for shard in plan["cross_cut_shards"] for risk in shard["risk_dimensions"]}
            self.assertIn("security", risks)
            self.assertIn("migration", risks)
            covered = [path for shard in plan["primary_shards"] for path in shard["files"]]
            self.assertEqual(len(covered), len(set(covered)))
            self.assertEqual(set(covered), set(plan["file_coverage"]))

    def test_legacy_v2_control_root_is_used_without_mixing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root, legacy=True)
            result = start_review(root, baseline=commit, target=commit)
            self.assertIn(".codex/runs/", result["review_root"])
            self.assertFalse((root / ".dingxinglizi").exists())

    def test_budget_splits_deterministically_and_oversize_blocks(self) -> None:
        entries = [
            {"path": f"src/f{index}.py", "size_bytes": 20, "disposition": "INCLUDED"}
            for index in range(5)
        ]
        inventory = {
            "manifest_fingerprint": "a" * 64,
            "entries": entries,
            "modules": [{"module_id": "module-src", "root": "src"}],
            "disposition_counts": {"INCLUDED": 5},
        }
        first = build_review_plan(inventory, budget={"max_files": 2, "max_bytes": 100, "max_estimated_tokens": 100})
        second = build_review_plan(inventory, budget={"max_files": 2, "max_bytes": 100, "max_estimated_tokens": 100})
        self.assertEqual(first["plan_fingerprint"], second["plan_fingerprint"])
        self.assertEqual([item["file_count"] for item in first["primary_shards"]], [2, 2, 1])
        blocked = build_review_plan(inventory, budget={"max_files": 2, "max_bytes": 10, "max_estimated_tokens": 100})
        self.assertEqual(blocked["status"], "BLOCKED_OVERSIZED_FILE")
        self.assertEqual(len(blocked["oversized_files"]), 5)

    def test_explicit_risk_lens_covers_neutral_filenames(self) -> None:
        inventory = {
            "manifest_fingerprint": "a" * 64,
            "entries": [{"path": "src/plain.py", "size_bytes": 20, "disposition": "INCLUDED"}],
            "modules": [{"module_id": "module-src", "root": "src"}],
            "disposition_counts": {"INCLUDED": 1},
        }
        plan = build_review_plan(inventory, required_risks=["privacy"])
        self.assertEqual(plan["required_risk_lenses"], ["privacy"])
        self.assertEqual([item["risk_dimensions"] for item in plan["cross_cut_shards"]], [["privacy"]])
        with self.assertRaisesRegex(ValueError, "Unknown required risk"):
            build_review_plan(inventory, required_risks=["imaginary-risk"])

    def test_ai_and_test_paths_route_to_specialized_surfaces(self) -> None:
        self.assertEqual(technology_surface("services/ai/guardrails.py"), "ai")
        self.assertEqual(technology_surface("services/api/tests/test_auth.py"), "test")

    def test_non_git_requires_explicit_reduced_strength_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root, "src/main.py", "print('ok')\n")
            with self.assertRaisesRegex(ValueError, "explicit WORKTREE_SNAPSHOT"):
                capture_worktree_snapshot(root, explicit=False)
            snapshot, inventory = capture_worktree_snapshot(root, explicit=True)
            self.assertEqual(snapshot["conclusion_strength"], "REDUCED_NON_GIT_WORKTREE")
            self.assertEqual(inventory["entry_count"], 1)

    def test_target_ref_and_plan_drift_make_review_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_git(root)
            start_review(root, baseline="HEAD", target="HEAD")
            write(root, "apps/web/src/new.ts", "export const changed = true;\n")
            git(root, "add", "apps/web/src/new.ts")
            git(root, "commit", "-qm", "target moved")
            status = status_review(root)
            self.assertEqual(status["status"], "STALE")
            self.assertIn("target-ref-drift", status["drift_status"])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            start_review(root, baseline=commit, target=commit)
            plan_path = control_path(root, f"runs/{RUN_ID}/review/plan.json")
            plan = json.loads(plan_path.read_text())
            plan["budget"]["max_files"] += 1
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            status = status_review(root)
            self.assertEqual(status["status"], "STALE")
            self.assertIn("plan", status["drift_status"])

    def test_trust_policy_is_explicit_and_trusted_file_drift_stales_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            write(root, "REVIEW_RULES.md", "Only inspect pinned objects.\n")
            preview = preview_review(
                root, baseline=commit, target=commit, trusted_instructions=["REVIEW_RULES.md"],
            )
            self.assertFalse(preview["trust_policy"]["repository_execution_authorized"])
            self.assertIn("NO_REPOSITORY_COMMANDS", preview["trust_policy"]["default_execution_policy"])
            start_review(root, baseline=commit, target=commit, trusted_instructions=["REVIEW_RULES.md"])
            write(root, "REVIEW_RULES.md", "Changed instruction.\n")
            status = status_review(root)
            self.assertEqual(status["status"], "STALE")
            self.assertIn("trusted-instruction-drift", status["drift_status"])

    def test_result_requires_task_dispatch_and_concrete_per_file_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(root, baseline=commit, target=commit)
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            shard = plan["primary_shards"][0]
            result = shard_result(root, started, shard)
            result["file_evidence"] = []
            with self.assertRaisesRegex(ValueError, "file_evidence"):
                ingest_result(root, shard["shard_id"], result)
            result = shard_result(root, started, shard)
            result["reviewer_id"] = "qa" if result["reviewer_id"] != "qa" else "engineering_lead"
            with self.assertRaisesRegex(ValueError, "Task Package owner"):
                ingest_result(root, shard["shard_id"], result)
            result = shard_result(root, started, shard)
            task_path = root / "tasks" / f"{result['task_id']}.yaml"
            task_path.write_text(task_path.read_text(encoding="utf-8").replace(
                "Review one immutable repository shard", "Tampered after dispatch",
            ), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dispatch receipt"):
                ingest_result(root, shard["shard_id"], result)

    def test_review_session_id_cannot_be_reused_across_shards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(root, baseline=commit, target=commit)
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            shards = plan["primary_shards"][:2]
            self.assertEqual(len(shards), 2)
            first = shard_result(root, started, shards[0])
            ingest_result(root, shards[0]["shard_id"], first)
            second = shard_result(root, started, shards[1])
            second["review_session_id"] = first["review_session_id"]
            second["session_attestation"]["session_id"] = first["review_session_id"]
            with self.assertRaisesRegex(ValueError, "cannot be reused"):
                ingest_result(root, shards[1]["shard_id"], second)

    def test_reviewer_self_attestation_does_not_prove_session_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(root, baseline=commit, target=commit)
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            shard = plan["primary_shards"][0]
            result = shard_result(root, started, shard)
            result["session_attestation"]["attested_by"] = result["reviewer_id"]
            accepted = ingest_result(root, shard["shard_id"], result)
            self.assertEqual(accepted["session_isolation_status"], "UNVERIFIED_SESSION_ISOLATION")

    def test_governed_review_uses_code_review_then_ready_for_qa_then_qa_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            run_path = control_path(root, f"runs/{RUN_ID}/run.json")
            run = json.loads(run_path.read_text())
            run["current_state"] = "CODE_REVIEW"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            role_path = control_path(root, "orchestration/role-plan.json")
            role_path.parent.mkdir(parents=True, exist_ok=True)
            role_path.write_text(json.dumps({
                "status": "ROUTED", "current_stage": "CODE_REVIEW",
                "signals": ["large_repository_review"], "required_now": ["engineering_lead"],
            }), encoding="utf-8")
            started = start_review(root, baseline=commit, target=commit)
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            for shard in plan["primary_shards"] + plan["cross_cut_shards"]:
                ingest_result(root, shard["shard_id"], shard_result(root, started, shard))
            write(root, "evidence/qa.txt", "governed independent final QA\n")
            run["current_state"] = "READY_FOR_QA"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            role_path.write_text(json.dumps({
                "status": "ROUTED", "current_stage": "READY_FOR_QA",
                "signals": [], "required_now": ["qa"],
            }), encoding="utf-8")
            record_qa(
                root, qa_id="qa", task_id=qa_task(root, ["evidence/qa.txt"]),
                qa_session_id="governed-qa-session", evidence_refs=["evidence/qa.txt"],
                finding_verifications={},
            )
            with self.assertRaisesRegex(ValueError, "QA_PASS"):
                finalize_review(root)
            run["current_state"] = "QA_PASS"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            report = finalize_review(root)
            self.assertEqual(report["qa_status"], "PASS")

    def test_full_declared_coverage_finalize_and_unverified_session_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(root, baseline=commit, target=commit)
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            shards = plan["primary_shards"] + plan["cross_cut_shards"]
            for index, shard in enumerate(shards):
                ingest_result(root, shard["shard_id"], shard_result(root, started, shard, attested=index != 0))
            status = status_review(root)
            self.assertEqual(status["coverage"]["status"], "COMPLETE_FOR_DECLARED_SCOPE")
            with self.assertRaisesRegex(ValueError, "QA PASS"):
                finalize_review(root)
            write(root, "evidence/empty-qa.txt", "")
            empty_task = qa_task(root, ["evidence/empty-qa.txt"], "TASK-EMPTY-QA")
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                record_qa(
                    root, qa_id="qa", task_id=empty_task, qa_session_id="qa-empty-session",
                    evidence_refs=["evidence/empty-qa.txt"],
                    finding_verifications={},
                )
            write(root, "evidence/qa.txt", "independent final QA\n")
            record_qa(
                root, qa_id="qa", task_id=qa_task(root, ["evidence/qa.txt"]),
                qa_session_id="qa-final-session", evidence_refs=["evidence/qa.txt"],
                finding_verifications={},
            )
            report = finalize_review(root)
            self.assertEqual(report["completion_claim"], "COMPLETE_FOR_DECLARED_SCOPE")
            self.assertEqual(report["session_isolation"], "UNVERIFIED_SESSION_ISOLATION")
            self.assertIn("semantic", " ".join(report["limitations"]).lower())

    def test_documented_cli_final_qa_accepts_completed_task_with_pass_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(root, baseline=commit, target=commit)
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            for shard in plan["primary_shards"] + plan["cross_cut_shards"]:
                ingest_result(root, shard["shard_id"], shard_result(root, started, shard))
            write(root, "evidence/qa-cli.txt", "independent final QA through documented CLI\n")
            task_id = qa_task(root, ["evidence/qa-cli.txt"], "TASK-CLI-FINAL-QA")
            write(root, "evidence/qa-verifications.json", "{}\n")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "large_repository_review.py"), "record-qa", str(root),
                    "--qa", "qa", "--task-id", task_id, "--qa-session", "qa-cli-final-session",
                    "--evidence-refs", "evidence/qa-cli.txt",
                    "--finding-verifications-json", str(root / "evidence/qa-verifications.json"),
                ],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(json.loads(result.stdout)["status"], "PASS")
            self.assertEqual(finalize_review(root)["completion_claim"], "COMPLETE_FOR_DECLARED_SCOPE")

    def test_review_only_rejects_repairs_and_p0_blocks_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(root, baseline=commit, target=commit)
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            target_shard = next(shard for shard in plan["primary_shards"] if "services/api/auth/service.py" in shard["files"])
            finding = {
                "finding_id": "FIND-AUTH-001", "shard_id": target_shard["shard_id"],
                "target_fingerprint": started["target_fingerprint"], "path": "services/api/auth/service.py",
                "start_line": 1, "end_line": 2, "severity": "P0", "category": "security",
                "title": "Authorization bypass", "description": "The guard permits every request.",
                "evidence": "allowed always returns true", "recommendation": "Enforce policy", "status": "OPEN",
            }
            for shard in plan["primary_shards"] + plan["cross_cut_shards"]:
                current = finding if shard["shard_id"] == target_shard["shard_id"] else None
                ingest_result(root, shard["shard_id"], shard_result(root, started, shard, finding=current))
            with self.assertRaisesRegex(ValueError, "forbidden in review_only"):
                plan_repairs(root, fixer_id="backend_worker", reviewer_id="engineering_lead")
            with self.assertRaisesRegex(ValueError, "P0/P1"):
                finalize_review(root)

    def test_repair_and_independent_rereview_close_p1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(
                root, baseline=commit, target=commit, mode="review_and_fix", fix_authorized=True,
            )
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            target_shard = next(shard for shard in plan["primary_shards"] if "services/api/auth/service.py" in shard["files"])
            finding = {
                "finding_id": "FIND-AUTH-002", "shard_id": target_shard["shard_id"],
                "target_fingerprint": started["target_fingerprint"], "path": "services/api/auth/service.py",
                "start_line": 1, "end_line": 2, "severity": "P1", "category": "security",
                "title": "Missing policy", "description": "The policy check is absent.",
                "evidence": "No principal is evaluated", "recommendation": "Add principal policy", "status": "OPEN",
            }
            for shard in plan["primary_shards"] + plan["cross_cut_shards"]:
                ingest_result(root, shard["shard_id"], shard_result(
                    root, started, shard, finding=finding if shard["shard_id"] == target_shard["shard_id"] else None,
                ))
            repair_plan = plan_repairs(
                root, fixer_id="backend_worker", reviewer_id="engineering_lead",
                finding_ids=["FIND-AUTH-002"],
            )
            repair_task, repair_evidence = repair_lifecycle_task(
                root, repair_plan["repair_plan_id"], "REPAIR", "TASK-AUTH-REPAIR-01",
            )
            write(root, "services/api/auth/service.py", "def allowed():\n    return False\n")
            record_repair(
                root, repair_plan_id=repair_plan["repair_plan_id"], fixer_id="backend_worker",
                task_id=repair_task,
                fixer_session_id="fix-session-001", finding_ids=["FIND-AUTH-002"],
                evidence_refs=[repair_evidence],
            )
            rereview_task, rereview_evidence = repair_lifecycle_task(
                root, repair_plan["repair_plan_id"], "REREVIEW", "TASK-AUTH-REREVIEW-01",
            )
            write(root, "services/api/auth/service.py", "def allowed():\n    return True\n")
            with self.assertRaisesRegex(ValueError, "source changed after repair"):
                record_rereview(
                    root, repair_plan_id=repair_plan["repair_plan_id"], task_id=rereview_task,
                    reviewer_id="engineering_lead",
                    reviewer_session_id="review-session-drift", outcomes={"FIND-AUTH-002": "PASS"},
                    verification_notes={"FIND-AUTH-002": "Original authorization failure no longer reproduces."},
                    evidence_refs=[rereview_evidence],
                )
            write(root, "services/api/auth/service.py", "def allowed():\n    return False\n")
            with self.assertRaisesRegex(ValueError, "different from fixer"):
                record_rereview(
                    root, repair_plan_id=repair_plan["repair_plan_id"], task_id=rereview_task,
                    reviewer_id="backend_worker",
                    reviewer_session_id="review-session-001", outcomes={"FIND-AUTH-002": "PASS"},
                    verification_notes={"FIND-AUTH-002": "Original authorization failure no longer reproduces."},
                    evidence_refs=[rereview_evidence],
                )
            record_rereview(
                root, repair_plan_id=repair_plan["repair_plan_id"], task_id=rereview_task,
                reviewer_id="engineering_lead",
                reviewer_session_id="review-session-001", outcomes={"FIND-AUTH-002": "PASS"},
                verification_notes={"FIND-AUTH-002": "Original authorization failure no longer reproduces."},
                evidence_refs=[rereview_evidence],
            )
            write(root, "evidence/qa.txt", "independent final QA\n")
            record_qa(
                root, qa_id="qa", task_id=qa_task(root, ["evidence/qa.txt"]),
                qa_session_id="qa-final-session", evidence_refs=["evidence/qa.txt"],
                finding_verifications={
                    "FIND-AUTH-002": "Verified the repaired authorization behavior against the final target."
                },
            )
            report = finalize_review(root)
            self.assertEqual(report["p0_p1_rereview_passed"], ["FIND-AUTH-002"])
            self.assertEqual(status_review(root)["drift_status"], "FINALIZED_IMMUTABLE")

    def test_failed_rereview_allows_one_retry_but_never_a_third_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(
                root, baseline=commit, target=commit, mode="review_and_fix", fix_authorized=True,
            )
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            shard = plan["primary_shards"][0]
            finding_path = shard["files"][0]
            issue = {
                "finding_id": "FIND-RETRY-01", "shard_id": shard["shard_id"],
                "target_fingerprint": started["target_fingerprint"], "path": finding_path,
                "start_line": 1, "end_line": 1, "severity": "P1", "category": "correctness",
                "title": "Retryable defect", "description": "The first repair can fail rereview.",
                "evidence": "Deterministic fixture", "recommendation": "Repair and rereview", "status": "OPEN",
            }
            for current in plan["primary_shards"] + plan["cross_cut_shards"]:
                ingest_result(root, current["shard_id"], shard_result(
                    root, started, current, finding=issue if current["shard_id"] == shard["shard_id"] else None,
                ))
            first = plan_repairs(
                root, fixer_id="backend_worker", reviewer_id="engineering_lead",
                finding_ids=["FIND-RETRY-01"],
            )
            repair_task_one, repair_evidence_one = repair_lifecycle_task(
                root, first["repair_plan_id"], "REPAIR", "TASK-RETRY-REPAIR-01",
            )
            original = (root / finding_path).read_text(encoding="utf-8")
            write(root, finding_path, original + "# first repair\n")
            record_repair(
                root, repair_plan_id=first["repair_plan_id"], fixer_id="backend_worker",
                task_id=repair_task_one,
                fixer_session_id="fix-session-one", finding_ids=["FIND-RETRY-01"],
                evidence_refs=[repair_evidence_one],
            )
            rereview_task_one, rereview_evidence_one = repair_lifecycle_task(
                root, first["repair_plan_id"], "REREVIEW", "TASK-RETRY-REREVIEW-01",
            )
            record_rereview(
                root, repair_plan_id=first["repair_plan_id"], task_id=rereview_task_one,
                reviewer_id="engineering_lead",
                reviewer_session_id="review-session-one", outcomes={"FIND-RETRY-01": "FAIL"},
                verification_notes={"FIND-RETRY-01": "The original deterministic failure still reproduces."},
                evidence_refs=[rereview_evidence_one],
            )
            second = plan_repairs(
                root, fixer_id="backend_worker", reviewer_id="engineering_lead",
                finding_ids=["FIND-RETRY-01"],
            )
            self.assertEqual(second["round"], 2)
            repair_task_two, repair_evidence_two = repair_lifecycle_task(
                root, second["repair_plan_id"], "REPAIR", "TASK-RETRY-REPAIR-02",
            )
            write(root, finding_path, original + "# second repair\n")
            record_repair(
                root, repair_plan_id=second["repair_plan_id"], fixer_id="backend_worker",
                task_id=repair_task_two,
                fixer_session_id="fix-session-two", finding_ids=["FIND-RETRY-01"],
                evidence_refs=[repair_evidence_two],
            )
            rereview_task_two, rereview_evidence_two = repair_lifecycle_task(
                root, second["repair_plan_id"], "REREVIEW", "TASK-RETRY-REREVIEW-02",
            )
            record_rereview(
                root, repair_plan_id=second["repair_plan_id"], task_id=rereview_task_two,
                reviewer_id="engineering_lead",
                reviewer_session_id="review-session-two", outcomes={"FIND-RETRY-01": "FAIL"},
                verification_notes={"FIND-RETRY-01": "The original deterministic failure still reproduces."},
                evidence_refs=[rereview_evidence_two],
            )
            with self.assertRaisesRegex(ValueError, "no greater than 2"):
                plan_repairs(
                    root, fixer_id="backend_worker", reviewer_id="engineering_lead",
                    finding_ids=["FIND-RETRY-01"],
                )

    def test_unfinished_or_failed_p2_repair_blocks_verified_repairs_claim(self) -> None:
        for disposition in ("PLANNED", "REREVIEW_FAILED"):
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                commit = init_git(root)
                started = start_review(
                    root, baseline=commit, target=commit, mode="review_and_fix", fix_authorized=True,
                )
                plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
                shard = plan["primary_shards"][0]
                finding_path = shard["files"][0]
                finding = {
                    "finding_id": "FIND-P2-REPAIR-01", "shard_id": shard["shard_id"],
                    "target_fingerprint": started["target_fingerprint"], "path": finding_path,
                    "start_line": 1, "end_line": 1, "severity": "P2", "category": "correctness",
                    "title": "Authorized lower-severity repair", "description": "Repair is still governed.",
                    "evidence": "Deterministic P2 fixture", "recommendation": "Repair and verify", "status": "OPEN",
                }
                for current in plan["primary_shards"] + plan["cross_cut_shards"]:
                    ingest_result(root, current["shard_id"], shard_result(
                        root, started, current, finding=finding if current["shard_id"] == shard["shard_id"] else None,
                    ))
                repair_plan = plan_repairs(
                    root, fixer_id="backend_worker", reviewer_id="engineering_lead",
                    finding_ids=["FIND-P2-REPAIR-01"],
                )
                if disposition == "REREVIEW_FAILED":
                    repair_task, repair_evidence = repair_lifecycle_task(
                        root, repair_plan["repair_plan_id"], "REPAIR", "TASK-P2-REPAIR-01",
                    )
                    write(root, finding_path, (root / finding_path).read_text(encoding="utf-8") + "# p2 repair\n")
                    record_repair(
                        root, repair_plan_id=repair_plan["repair_plan_id"], task_id=repair_task,
                        fixer_id="backend_worker", fixer_session_id="p2-fix-session",
                        finding_ids=["FIND-P2-REPAIR-01"], evidence_refs=[repair_evidence],
                    )
                    rereview_task, rereview_evidence = repair_lifecycle_task(
                        root, repair_plan["repair_plan_id"], "REREVIEW", "TASK-P2-REREVIEW-01",
                    )
                    record_rereview(
                        root, repair_plan_id=repair_plan["repair_plan_id"], task_id=rereview_task,
                        reviewer_id="engineering_lead", reviewer_session_id="p2-rereview-session",
                        outcomes={"FIND-P2-REPAIR-01": "FAIL"},
                        verification_notes={"FIND-P2-REPAIR-01": "The lower-severity defect still reproduces."},
                        evidence_refs=[rereview_evidence],
                    )
                write(root, "evidence/qa-p2.txt", "final QA cannot erase incomplete authorized repair\n")
                record_qa(
                    root, qa_id="qa", task_id=qa_task(root, ["evidence/qa-p2.txt"], f"TASK-QA-{disposition}"),
                    qa_session_id=f"qa-{disposition.lower()}-session", evidence_refs=["evidence/qa-p2.txt"],
                    finding_verifications={
                        "FIND-P2-REPAIR-01": "Checked the authorized P2 finding on the final effective target."
                    },
                )
                progress = status_review(root)["repair_progress"]
                self.assertEqual(progress["status"], "INCOMPLETE_REREVIEW")
                self.assertEqual(progress["unverified_finding_ids"], ["FIND-P2-REPAIR-01"])
                with self.assertRaisesRegex(ValueError, "Every authorized repair finding"):
                    finalize_review(root)

    def test_same_file_sequential_p2_p3_repairs_require_final_target_qa_for_both(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(
                root, baseline=commit, target=commit, mode="review_and_fix", fix_authorized=True,
            )
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            shard = plan["primary_shards"][0]
            shared_path = shard["files"][0]
            findings = [
                {
                    "finding_id": "FIND-SHARED-P2", "shard_id": shard["shard_id"],
                    "target_fingerprint": started["target_fingerprint"], "path": shared_path,
                    "start_line": 1, "end_line": 1, "severity": "P2", "category": "correctness",
                    "title": "First shared-file defect", "description": "First bounded behavior is wrong.",
                    "evidence": "First shared-file fixture", "recommendation": "Repair first behavior", "status": "OPEN",
                },
                {
                    "finding_id": "FIND-SHARED-P3", "shard_id": shard["shard_id"],
                    "target_fingerprint": started["target_fingerprint"], "path": shared_path,
                    "start_line": 1, "end_line": 1, "severity": "P3", "category": "maintainability",
                    "title": "Second shared-file defect", "description": "Second bounded behavior is wrong.",
                    "evidence": "Second shared-file fixture", "recommendation": "Repair second behavior", "status": "OPEN",
                },
            ]
            for current in plan["primary_shards"] + plan["cross_cut_shards"]:
                result = shard_result(root, started, current)
                if current["shard_id"] == shard["shard_id"]:
                    result["findings"] = findings
                ingest_result(root, current["shard_id"], result)

            for index, finding_id in enumerate(("FIND-SHARED-P2", "FIND-SHARED-P3"), 1):
                repair_plan = plan_repairs(
                    root, fixer_id="backend_worker", reviewer_id="engineering_lead", finding_ids=[finding_id],
                )
                repair_task, repair_evidence = repair_lifecycle_task(
                    root, repair_plan["repair_plan_id"], "REPAIR", f"TASK-SHARED-REPAIR-{index:02d}",
                )
                write(root, shared_path, (root / shared_path).read_text(encoding="utf-8") + f"# shared repair {index}\n")
                record_repair(
                    root, repair_plan_id=repair_plan["repair_plan_id"], task_id=repair_task,
                    fixer_id="backend_worker", fixer_session_id=f"shared-fix-{index}",
                    finding_ids=[finding_id], evidence_refs=[repair_evidence],
                )
                rereview_task, rereview_evidence = repair_lifecycle_task(
                    root, repair_plan["repair_plan_id"], "REREVIEW", f"TASK-SHARED-REREVIEW-{index:02d}",
                )
                record_rereview(
                    root, repair_plan_id=repair_plan["repair_plan_id"], task_id=rereview_task,
                    reviewer_id="engineering_lead", reviewer_session_id=f"shared-rereview-{index}",
                    outcomes={finding_id: "PASS"},
                    verification_notes={finding_id: "The bounded defect no longer reproduces on this repair target."},
                    evidence_refs=[rereview_evidence],
                )

            write(root, "evidence/qa-shared.txt", "final-target regression across both shared-file repairs\n")
            qa_task_id = qa_task(root, ["evidence/qa-shared.txt"], "TASK-QA-SHARED-FINAL")
            with self.assertRaisesRegex(ValueError, "every P0/P1 and every authorized repair finding"):
                record_qa(
                    root, qa_id="qa", task_id=qa_task_id, qa_session_id="qa-shared-final",
                    evidence_refs=["evidence/qa-shared.txt"],
                    finding_verifications={
                        "FIND-SHARED-P3": "Verified only the later repair on the final target."
                    },
                )
            record_qa(
                root, qa_id="qa", task_id=qa_task_id, qa_session_id="qa-shared-final",
                evidence_refs=["evidence/qa-shared.txt"],
                finding_verifications={
                    "FIND-SHARED-P2": "Re-verified the earlier repair after the later same-file change.",
                    "FIND-SHARED-P3": "Verified the later repair on the final effective target.",
                },
            )
            report = finalize_review(root)
            self.assertEqual(report["repair_progress"]["status"], "PASS")
            self.assertEqual(
                report["repair_progress"]["final_target_qa_verified_finding_ids"],
                ["FIND-SHARED-P2", "FIND-SHARED-P3"],
            )

    def test_two_independent_round_one_repairs_finalize_at_append_chain_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = init_git(root)
            started = start_review(
                root, baseline=commit, target=commit, mode="review_and_fix", fix_authorized=True,
            )
            plan = json.loads(control_path(root, f"runs/{RUN_ID}/review/plan.json").read_text())
            first_path = "apps/web/src/main.ts"
            second_path = "services/api/auth/service.py"
            shard_by_path = {
                path: next(item for item in plan["primary_shards"] if path in item["files"])
                for path in (first_path, second_path)
            }
            findings = {
                first_path: {
                    "finding_id": "FIND-MULTI-01", "shard_id": shard_by_path[first_path]["shard_id"],
                    "target_fingerprint": started["target_fingerprint"], "path": first_path,
                    "start_line": 1, "end_line": 1, "severity": "P1", "category": "correctness",
                    "title": "First independent defect", "description": "First behavior is incorrect.",
                    "evidence": "First deterministic evidence", "recommendation": "Repair first file", "status": "OPEN",
                },
                second_path: {
                    "finding_id": "FIND-MULTI-02", "shard_id": shard_by_path[second_path]["shard_id"],
                    "target_fingerprint": started["target_fingerprint"], "path": second_path,
                    "start_line": 1, "end_line": 1, "severity": "P1", "category": "correctness",
                    "title": "Second independent defect", "description": "Second behavior is incorrect.",
                    "evidence": "Second deterministic evidence", "recommendation": "Repair second file", "status": "OPEN",
                },
            }
            for shard in plan["primary_shards"] + plan["cross_cut_shards"]:
                finding = next((value for path, value in findings.items() if shard["shard_id"] == shard_by_path[path]["shard_id"]), None)
                ingest_result(root, shard["shard_id"], shard_result(root, started, shard, finding=finding))
            for index, (finding_id, path) in enumerate((("FIND-MULTI-01", first_path), ("FIND-MULTI-02", second_path)), 1):
                repair_plan = plan_repairs(
                    root, fixer_id="backend_worker", reviewer_id="engineering_lead", finding_ids=[finding_id],
                )
                self.assertEqual(repair_plan["round"], 1)
                repair_task, repair_evidence = repair_lifecycle_task(
                    root, repair_plan["repair_plan_id"], "REPAIR", f"TASK-MULTI-REPAIR-{index:02d}",
                )
                write(root, path, (root / path).read_text(encoding="utf-8") + f"# repair {index}\n")
                record_repair(
                    root, repair_plan_id=repair_plan["repair_plan_id"], fixer_id="backend_worker",
                    task_id=repair_task,
                    fixer_session_id=f"fix-multi-{index}", finding_ids=[finding_id],
                    evidence_refs=[repair_evidence],
                )
                rereview_task, rereview_evidence = repair_lifecycle_task(
                    root, repair_plan["repair_plan_id"], "REREVIEW", f"TASK-MULTI-REREVIEW-{index:02d}",
                )
                record_rereview(
                    root, repair_plan_id=repair_plan["repair_plan_id"], task_id=rereview_task,
                    reviewer_id="engineering_lead",
                    reviewer_session_id=f"review-multi-{index}", outcomes={finding_id: "PASS"},
                    verification_notes={finding_id: "The original failure no longer reproduces on the repaired target."},
                    evidence_refs=[rereview_evidence],
                )
            write(root, "evidence/qa.txt", "independent final QA across both repairs\n")
            record_qa(
                root, qa_id="qa", task_id=qa_task(root, ["evidence/qa.txt"]),
                qa_session_id="qa-multi-final", evidence_refs=["evidence/qa.txt"],
                finding_verifications={
                    "FIND-MULTI-01": "Verified the first repair remains closed on the final combined target.",
                    "FIND-MULTI-02": "Verified the second repair remains closed on the final combined target.",
                },
            )
            report = finalize_review(root)
            self.assertEqual(report["p0_p1_rereview_passed"], ["FIND-MULTI-01", "FIND-MULTI-02"])


if __name__ == "__main__":
    unittest.main()
