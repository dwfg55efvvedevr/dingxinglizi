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
PYTHON = sys.executable
sys.path.insert(0, str(SCRIPTS))

from evolution import collect, eval_candidates, feedback, propose, retrospect, status  # noqa: E402
from evolution_store import EvolutionBlocked, evolution_root, initialize_workspace, require_utc_timestamp  # noqa: E402
from init_project import initialize  # noqa: E402
from state_io import atomic_write_json  # noqa: E402


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPTS / "orchestrator.py"), *args],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


class EvolutionCoreTests(unittest.TestCase):
    def make_project(self, parent: Path) -> Path:
        root = parent / "project"
        initialize(root, "Evolution Test", "SaaS", "Standard", False)
        return root

    def completed_run(self, root: Path, suffix: str = "abc123") -> str:
        run_id = f"RUN-20260828T120000Z-{suffix}"
        run_dir = root / ".codex/runs" / run_id
        run_dir.mkdir(parents=True)
        evidence = root / "evidence" / f"qa-{suffix}.txt"
        evidence.write_text("independent QA passed\n", encoding="utf-8")
        input_fp = "a" * 64
        role_fp = "b" * 64
        created, completed = "2026-08-28T12:00:00+00:00", "2026-08-28T12:05:00+00:00"
        atomic_write_json(run_dir / "run.json", {
            "schema_version": 1, "run_id": run_id, "project": "Evolution Test",
            "created_at": created, "updated_at": completed, "status": "DONE",
            "start_state": "RELEASE_READY", "current_state": "DONE",
            "input_fingerprint": input_fp, "role_plan_fingerprint": role_fp,
        })
        atomic_write_json(run_dir / "checkpoint.json", {
            "schema_version": 1, "run_id": run_id, "last_event_sequence": 2,
            "last_event_type": "RUN_COMPLETED", "last_conclusion": "PASS",
            "current_state": "DONE", "input_fingerprint": input_fp,
            "role_plan_fingerprint": role_fp,
        })
        events = [
            {"sequence": 1, "timestamp": created, "run_id": run_id, "event_type": "RUN_CREATED", "status": "OPEN", "stage_before": "RELEASE_READY", "stage_after": "RELEASE_READY", "input_fingerprint": input_fp, "role_plan_fingerprint": role_fp},
            {"sequence": 2, "timestamp": completed, "run_id": run_id, "event_type": "RUN_COMPLETED", "status": "DONE", "stage_before": "RELEASE_READY", "stage_after": "DONE", "input_fingerprint": input_fp, "role_plan_fingerprint": role_fp, "conclusion": "PASS"},
        ]
        (run_dir / "events.jsonl").write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in events), encoding="utf-8")
        ref = evidence.relative_to(root).as_posix()
        atomic_write_json(run_dir / "evidence-index.json", {
            "schema_version": 1, "artifacts": [],
            "evidence": [{"ref": ref, "task_id": None, "recorded_at": completed, "sequence": 2}],
        })
        atomic_write_json(run_dir / "routing-decisions.json", {
            "schema_version": 1, "role_plan_fingerprint": role_fp,
            "routing_cycle_id": "cycle-1", "required_now": ["qa"],
            "history": [{"sequence": 1, "captured_at": created, "role_plan_fingerprint": role_fp, "routing_cycle_id": "cycle-1", "required_now": ["qa"]}],
        })
        atomic_write_json(run_dir / "project-snapshot.json", {
            "captured_at": completed, "current_state": "DONE", "input_fingerprint": input_fp,
            "role_plan_fingerprint": role_fp, "routing_cycle_id": "cycle-1", "required_now": ["qa"],
        })
        return run_id

    def add_feedback(self, root: Path, name: str, *, severity: str = "P2", kind: str = "repeated_defect") -> dict[str, object]:
        proof = root / "evidence" / f"{name}.txt"
        proof.write_text(f"sanitized proof {name}\n", encoding="utf-8")
        return feedback(
            root, kind=kind, result="FAIL", severity=severity,
            category="implementation", summary="A bounded implementation defect recurred.",
            evidence_paths=[proof.relative_to(root).as_posix()],
        )

    def eligible_chain(self, root: Path) -> tuple[Path, Path, Path]:
        for name in ("one", "two", "three"):
            self.add_feedback(root, name)
        retro = retrospect(root)
        retro_path = evolution_root(root) / "retrospectives" / f"{retro['retrospective_id']}.json"
        proposals = propose(root, retro_path.name)
        proposal_path = evolution_root(root) / "candidates" / f"{proposals['created'][0]}.json"
        candidate = eval_candidates(root, proposal_path.name)
        eval_path = evolution_root(root) / "eval-candidates" / f"{candidate['eval_candidate_id']}.json"
        return retro_path, proposal_path, eval_path

    def assert_status_blocked_cli(self, root: Path, reason: str) -> dict[str, object]:
        result = cli("evolution", "status", str(root))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["reason_code"], reason)
        self.assertEqual(payload["counts"], "UNAVAILABLE")
        return payload

    def test_template_initializes_ignored_local_workspace_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            self.assertTrue((root / ".gitignore").read_text(encoding="utf-8").find(".codex/evolution/") >= 0)
            report = status(root)
            self.assertEqual(report["status"], "READY")
            self.assertEqual(report["counts"]["outcomes"], 0)
            self.assertFalse((evolution_root(root) / ".write-lock").exists())

    def test_existing_project_requires_explicit_atomic_init(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            shutil.rmtree(evolution_root(root))
            self.assertEqual(status(root)["status"], "NOT_INITIALIZED")
            with self.assertRaises(EvolutionBlocked) as caught:
                self.add_feedback(root, "blocked")
            self.assertEqual(caught.exception.reason_code, "NOT_INITIALIZED")
            result = initialize_workspace(root)
            self.assertEqual(result["status"], "INITIALIZED")
            self.assertEqual(initialize_workspace(root)["status"], "ALREADY_INITIALIZED")

    def test_collect_validates_six_file_lineage_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run_id = self.completed_run(root)
            first = collect(root, run_id)
            second = collect(root, run_id)
            self.assertEqual(first["outcome_id"], second["outcome_id"])
            self.assertEqual(second["status"], "EXISTING")
            outcome = json.loads((evolution_root(root) / "outcomes.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(outcome["actual_execution"]["model"], "UNAVAILABLE")
            self.assertNotIn("independent QA passed", json.dumps(outcome))

    def test_collect_accepts_only_indexed_execution_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run_id = self.completed_run(root)
            attestation = root / "evidence" / "execution-attestation.json"
            attestation.write_text(json.dumps({
                "schema_version": 1, "type": "execution_attestation", "run_id": run_id,
                "recorded_by": "engineering_lead", "recorded_at": "2026-08-28T12:04:00+00:00",
                "actual_execution": {"model": "gpt-5.6-terra", "reasoning": "high", "tokens": 1234},
            }) + "\n", encoding="utf-8")
            index_path = root / ".codex/runs" / run_id / "evidence-index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["evidence"].append({"ref": "evidence/execution-attestation.json", "task_id": None, "recorded_at": "2026-08-28T12:04:00+00:00", "sequence": 2})
            atomic_write_json(index_path, index)
            result = collect(root, run_id)
            outcome = json.loads((evolution_root(root) / "outcomes.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(outcome["outcome_id"], result["outcome_id"])
            self.assertEqual(outcome["actual_execution"]["model"], "gpt-5.6-terra")
            self.assertEqual(outcome["actual_execution"]["tokens"], 1234)
            self.assertNotIn("actual_model", outcome["unknowns"])

    def test_utc_timestamp_contract_accepts_only_explicit_zero_offset(self) -> None:
        require_utc_timestamp("2026-08-28T12:00:00Z", "valid")
        require_utc_timestamp("2026-08-28T12:00:00+00:00", "valid")
        for invalid in ("ordinary string", "2026-08-28T12:00:00", "2026-08-28T20:00:00+08:00"):
            with self.subTest(invalid=invalid), self.assertRaises(EvolutionBlocked):
                require_utc_timestamp(invalid, "invalid")

    def test_outcome_tamper_and_attestation_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run_id = self.completed_run(root)
            attestation = root / "evidence" / "attestation-drift.json"
            attestation.write_text(json.dumps({
                "schema_version": 1, "type": "execution_attestation", "run_id": run_id,
                "recorded_by": "qa", "recorded_at": "2026-08-28T12:04:00Z",
                "actual_execution": {"model": "gpt-5.6-terra"},
            }) + "\n", encoding="utf-8")
            index_path = root / ".codex/runs" / run_id / "evidence-index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["evidence"].append({"ref": "evidence/attestation-drift.json", "task_id": None, "recorded_at": "2026-08-28T12:04:00Z", "sequence": 2})
            atomic_write_json(index_path, index)
            collect(root, run_id)
            ledger = evolution_root(root) / "outcomes.jsonl"
            outcome = json.loads(ledger.read_text(encoding="utf-8"))
            outcome["counts"]["events"] = 999
            ledger.write_text(json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaises(EvolutionBlocked) as tampered:
                collect(root, run_id)
            self.assertEqual(tampered.exception.reason_code, "CORRUPT_LEDGER")
            outcome["counts"]["events"] = 2
            ledger.write_text(json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8")
            attestation.write_text(attestation.read_text(encoding="utf-8").replace("gpt-5.6-terra", "gpt-5.6-sol"), encoding="utf-8")
            blocked = status(root)
            self.assertEqual(blocked["status"], "BLOCKED")
            self.assertEqual(blocked["counts"], "UNAVAILABLE")

    def test_persisted_outcome_nested_type_corruption_is_json_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run_id = self.completed_run(root)
            collect(root, run_id)
            ledger = evolution_root(root) / "outcomes.jsonl"
            outcome = json.loads(ledger.read_text(encoding="utf-8"))
            outcome["source"] = 42
            ledger.write_text(json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8")
            self.assert_status_blocked_cli(root, "CORRUPT_LEDGER")

    def test_collect_rejects_ambiguous_and_lineage_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            first = self.completed_run(root, "abc123")
            self.completed_run(root, "def456")
            with self.assertRaises(EvolutionBlocked) as caught:
                collect(root)
            self.assertEqual(caught.exception.reason_code, "AMBIGUOUS_INPUT")
            collect(root, first)
            run_path = root / ".codex/runs" / first / "run.json"
            value = json.loads(run_path.read_text(encoding="utf-8"))
            value["updated_at"] = "2026-08-28T12:06:00+00:00"
            atomic_write_json(run_path, value)
            with self.assertRaises(EvolutionBlocked) as drift:
                collect(root, first)
            self.assertEqual(drift.exception.reason_code, "BLOCKED_RUN_LINEAGE_DRIFT")

    def test_feedback_rejects_sensitive_summary_and_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            proof = root / "evidence" / "proof.txt"
            proof.write_text("safe\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sensitive-looking"):
                feedback(root, kind="user_correction", result="CORRECTED", severity="P1", category="business_rule", summary="token=secret-value", evidence_paths=["evidence/proof.txt"])
            with self.assertRaises(ValueError):
                feedback(root, kind="user_correction", result="CORRECTED", severity="P1", category="business_rule", summary="A sanitized correction.", evidence_paths=["../outside"])
            self.assertEqual((evolution_root(root) / "feedback.jsonl").read_text(encoding="utf-8"), "")

    def test_overlapping_evidence_forms_one_independent_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            for name in ("a", "b"):
                (root / "evidence" / f"{name}.txt").write_text(name + "\n", encoding="utf-8")
            for paths in (["evidence/a.txt"], ["evidence/a.txt", "evidence/b.txt"], ["evidence/b.txt"]):
                feedback(root, kind="repeated_defect", result="FAIL", severity="P2", category="implementation", summary=f"Sanitized defect observation {len(paths)}.", evidence_paths=paths)
            result = retrospect(root)
            retro = json.loads((evolution_root(root) / "retrospectives" / f"{result['retrospective_id']}.json").read_text(encoding="utf-8"))
            pattern = next(item for item in retro["patterns"] if item["category"] == "implementation")
            self.assertEqual(pattern["evidence_count"], 1)
            self.assertEqual(pattern["threshold_reason"], "INSUFFICIENT")
            with self.assertRaises(EvolutionBlocked) as caught:
                propose(root, f"{result['retrospective_id']}.json")
            self.assertEqual(caught.exception.reason_code, "INSUFFICIENT_EVIDENCE")

    def test_complete_feedback_to_draft_eval_candidate_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            for name in ("one", "two", "three"):
                self.add_feedback(root, name)
            retro = retrospect(root)
            proposals = propose(root, f"{retro['retrospective_id']}.json")
            self.assertEqual(len(proposals["created"]), 1)
            proposal_id = proposals["created"][0]
            candidate = eval_candidates(root, f"{proposal_id}.json")
            self.assertEqual(candidate["artifact_status"], "DRAFT")
            self.assertEqual(candidate["review_status"], "REVIEW_REQUIRED")
            again = eval_candidates(root, f"{proposal_id}.json")
            self.assertEqual(again["status"], "EXISTING")
            formal = cli("eval", "--json")
            self.assertEqual(formal.returncode, 0, formal.stderr)
            self.assertEqual(json.loads(formal.stdout)["failed"], 0)

    def test_artifact_selectors_and_existing_candidate_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            for name in ("one", "two", "three"):
                self.add_feedback(root, name)
            retro = retrospect(root)
            with self.assertRaises(ValueError):
                propose(root, f"../{retro['retrospective_id']}.json")
            generated = propose(root, f"{retro['retrospective_id']}.json")
            proposal_id = generated["created"][0]
            path = evolution_root(root) / "candidates" / f"{proposal_id}.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["title"] = "A locally modified but still sanitized title"
            atomic_write_json(path, value)
            with self.assertRaises(EvolutionBlocked) as caught:
                propose(root, f"{retro['retrospective_id']}.json")
            self.assertEqual(caught.exception.reason_code, "CORRUPT_ARTIFACT")

    def test_derived_artifact_tampering_cannot_upgrade_or_rewrite_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            self.add_feedback(root, "single-p2")
            retro_result = retrospect(root)
            retro_path = evolution_root(root) / "retrospectives" / f"{retro_result['retrospective_id']}.json"
            retro = json.loads(retro_path.read_text(encoding="utf-8"))
            retro["patterns"][0].update({"severity_max": "P0", "eligible": True, "threshold_reason": "P0_SINGLE"})
            retro["candidate_eligibility"]["eligible_categories"] = ["implementation"]
            retro["candidate_eligibility"]["insufficient_categories"] = []
            atomic_write_json(retro_path, retro)
            with self.assertRaises(EvolutionBlocked) as upgraded:
                propose(root, retro_path.name)
            self.assertEqual(upgraded.exception.reason_code, "CORRUPT_ARTIFACT")

            # Generate a clean chain in another project and tamper Proposal/Eval controlled fields.
            clean = Path(directory) / "clean"
            initialize(clean, "Clean Evolution", "SaaS", "Standard", False)
            for name in ("one", "two", "three"):
                self.add_feedback(clean, name)
            clean_retro = retrospect(clean)
            proposal_result = propose(clean, f"{clean_retro['retrospective_id']}.json")
            proposal_id = proposal_result["created"][0]
            proposal_path = evolution_root(clean) / "candidates" / f"{proposal_id}.json"
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            proposal["evidence_refs"] = ["https://example.invalid/evidence"]
            atomic_write_json(proposal_path, proposal)
            with self.assertRaises(EvolutionBlocked) as url_tamper:
                eval_candidates(clean, proposal_path.name)
            self.assertEqual(url_tamper.exception.reason_code, "CORRUPT_ARTIFACT")
            # Restore deterministically, generate Eval, then alter its scenario.
            proposal_path.unlink()
            proposal_id = propose(clean, f"{clean_retro['retrospective_id']}.json")["created"][0]
            eval_result = eval_candidates(clean, f"{proposal_id}.json")
            eval_path = evolution_root(clean) / "eval-candidates" / f"{eval_result['eval_candidate_id']}.json"
            eval_value = json.loads(eval_path.read_text(encoding="utf-8"))
            eval_value["scenario"] = "A different sanitized scenario."
            atomic_write_json(eval_path, eval_value)
            with self.assertRaises(EvolutionBlocked) as scenario_tamper:
                eval_candidates(clean, f"{proposal_id}.json")
            self.assertEqual(scenario_tamper.exception.reason_code, "CORRUPT_ARTIFACT")

    def test_persisted_derived_nested_type_fuzz_is_json_blocked(self) -> None:
        mutations = [
            ("retro-by-category", "retro", lambda value: value["counts"].__setitem__("by_category", 42)),
            ("retro-eligibility", "retro", lambda value: value.__setitem__("candidate_eligibility", 42)),
            ("retro-source-id", "retro", lambda value: value["source_records"][0].__setitem__("id", [])),
            ("proposal-source", "proposal", lambda value: value.__setitem__("source_retrospective", 42)),
            ("eval-source", "eval", lambda value: value.__setitem__("source_proposal", 42)),
        ]
        for name, target, mutate in mutations:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = self.make_project(Path(directory))
                retro_path, proposal_path, eval_path = self.eligible_chain(root)
                path = {"retro": retro_path, "proposal": proposal_path, "eval": eval_path}[target]
                value = json.loads(path.read_text(encoding="utf-8"))
                mutate(value)
                atomic_write_json(path, value)
                self.assert_status_blocked_cli(root, "CORRUPT_ARTIFACT")

    def test_persisted_artifact_json_symlinks_are_json_blocked(self) -> None:
        for directory_name in ("retrospectives", "candidates", "eval-candidates"):
            with self.subTest(directory=directory_name), tempfile.TemporaryDirectory() as directory:
                root = self.make_project(Path(directory))
                target = Path(directory) / "outside.json"
                target.write_text("{}\n", encoding="utf-8")
                (evolution_root(root) / directory_name / "linked.json").symlink_to(target)
                self.assert_status_blocked_cli(root, "CORRUPT_ARTIFACT")

    def test_run_role_without_task_requires_planned_routing_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            run_id = self.completed_run(root)
            accepted = feedback(
                root, kind="process_gap", result="OBSERVED", severity="P2", category="process",
                summary="The planned QA role produced a sanitized observation.",
                evidence_paths=["evidence/qa-abc123.txt"], run_id=run_id, role="qa",
            )
            self.assertEqual(accepted["status"], "RECORDED")
            with self.assertRaisesRegex(ValueError, "planned-routing lineage"):
                feedback(
                    root, kind="process_gap", result="OBSERVED", severity="P2", category="process",
                    summary="A different planned-role observation.",
                    evidence_paths=["evidence/qa-abc123.txt"], run_id=run_id, role="architect",
                )

    def test_symlink_evidence_and_partial_workspace_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            outside = Path(directory) / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            link = root / "evidence" / "linked.txt"
            link.symlink_to(outside)
            with self.assertRaises(ValueError):
                feedback(root, kind="process_gap", result="OBSERVED", severity="P2", category="process", summary="A sanitized observation.", evidence_paths=["evidence/linked.txt"])
            shutil.rmtree(evolution_root(root))
            evolution_root(root).mkdir()
            blocked = status(root)
            self.assertEqual(blocked["reason_code"], "BLOCKED_PARTIAL_INIT")
            self.assertEqual(blocked["counts"], "UNAVAILABLE")

    def test_p0_threshold_has_priority_over_three_lineages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            self.add_feedback(root, "one", severity="P0")
            self.add_feedback(root, "two")
            self.add_feedback(root, "three")
            retro = retrospect(root)
            generated = propose(root, f"{retro['retrospective_id']}.json")
            proposal_id = generated["created"][0]
            value = json.loads((evolution_root(root) / "candidates" / f"{proposal_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(value["priority"], "HIGH")
            self.assertEqual(value["authority"], {"auto_apply": False, "commit": False, "merge": False, "push": False, "release": False})

    def test_corrupt_ledger_and_stale_lock_fail_closed_without_blocking_formal_eval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            (evolution_root(root) / "feedback.jsonl").write_text("{}", encoding="utf-8")
            report = status(root)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["counts"], "UNAVAILABLE")
            formal = cli("eval", "--json")
            self.assertEqual(formal.returncode, 0)
            (evolution_root(root) / "feedback.jsonl").write_text("", encoding="utf-8")
            (evolution_root(root) / ".write-lock").write_text("stale\n", encoding="utf-8")
            self.assertEqual(status(root)["reason_code"], "BLOCKED_LOCKED")

    def test_git_tracked_evolution_blocks_writes_without_index_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "-f", ".codex/evolution/manifest.json"], check=True)
            proof = root / "evidence" / "git-risk.txt"
            proof.write_text("safe\n", encoding="utf-8")
            before = subprocess.run(["git", "-C", str(root), "ls-files", "--", ".codex/evolution"], capture_output=True, text=True, check=True).stdout
            with self.assertRaises(EvolutionBlocked) as caught:
                feedback(root, kind="process_gap", result="OBSERVED", severity="P2", category="process", summary="A sanitized local observation.", evidence_paths=["evidence/git-risk.txt"])
            self.assertEqual(caught.exception.reason_code, "GIT_EXPOSURE_RISK")
            after = subprocess.run(["git", "-C", str(root), "ls-files", "--", ".codex/evolution"], capture_output=True, text=True, check=True).stdout
            self.assertEqual(before, after)

    def test_cli_exit_contract_for_not_initialized_and_summary_violation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(Path(directory))
            shutil.rmtree(evolution_root(root))
            blocked = cli("evolution", "retrospect", str(root))
            self.assertEqual(blocked.returncode, 3, blocked.stderr)
            self.assertEqual(json.loads(blocked.stdout)["reason_code"], "NOT_INITIALIZED")
            initialize_workspace(root)
            proof = root / "evidence" / "cli.txt"
            proof.write_text("safe\n", encoding="utf-8")
            invalid = cli("evolution", "feedback", str(root), "--kind", "process_gap", "--result", "OBSERVED", "--severity", "P2", "--category", "process", "--summary", "person@example.com", "--evidence", "evidence/cli.txt")
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("sensitive-looking", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
