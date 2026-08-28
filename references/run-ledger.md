# Run ledger

The v2 control plane stores resumable, auditable local run state under `<project>/.codex/runs/RUN-ID/`. Project documents remain the source of business truth; the ledger records orchestration state and evidence references.

## Ownership and contents

Only Orchestrator writes the global ledger. A run contains:

- `run.json`: run identity, state, timestamps, current safe action, and source fingerprint;
- `project-snapshot.json`: lifecycle and execution-control snapshot at start;
- `routing-decisions.json`: the exact role plan and fingerprints used;
- `checkpoint.json`: latest persisted handoff/gate checkpoint;
- `events.jsonl`: append-only sanitized events;
- `evidence-index.json`: references to project-local evidence;
- `final-report.md`: derived report generated on demand.

Agents write only their owned artifacts and Task Package handoff, then return evidence references to Orchestrator. Never put credentials, tokens, customer secrets, unnecessary personal data, or unredacted production logs in a run.

## Invariants

- A new run fails closed while `docs/project-status.json` declares uncertain active sessions.
- A source-input change invalidates safe continuation until re-planning.
- A role-plan fingerprint change requires re-planning; it is never silently accepted.
- A report is derived evidence, not approval and not a substitute for independent QA.
- Run deletion or rewriting is not an automatic recovery action.

## Trusted checkpoint contracts

An event name alone is never evidence:

- `TASK_STARTED` requires a current-stage role plan, a Task Package bound to the same run, `READY_FOR_DISPATCH`, and a matching dispatch receipt.
- `HANDOFF_PERSISTED` requires the same lineage, a valid `COMPLETED` Task Package, a successful handoff conclusion, and project-local artifact/evidence references declared by that handoff.
- `GATE_DECISION` requires a supported conclusion, current-stage gate validation, and at least one evidence file.
- `TASK_BLOCKED` requires a Task ID and blocking note.
- `STATE_RECONCILED` requires a fresh current-stage plan, no uncertain active work, and reconciliation evidence.
- `RUN_COMPLETED` requires persisted `DONE`, no active work, a successful independent QA conclusion, the full `DONE` gate, and indexed release evidence.

Every accepted checkpoint refreshes the project snapshot and routing lineage. An empty checkpoint cannot re-trust a stale plan, and a hand-edited `DONE` state cannot convert an open run into a completed run.

Use `python3 "$SKILL_DIR/scripts/orchestrator.py" run PROJECT_DIR`, `checkpoint`, `resume`, and `report`. A competing OPEN/BLOCKED run is rejected until the current run is reconciled or completed. The Python control plane does not start Codex Agents itself.
