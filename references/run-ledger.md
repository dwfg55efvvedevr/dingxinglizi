# Run ledger

The control plane stores resumable, auditable local run state under the active control root's `runs/RUN-ID/`: `.dingxinglizi/runs/` for v3 projects or `.codex/runs/` for unmigrated v2 projects. Project documents remain the source of business truth; the ledger records orchestration state and evidence references.

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

Use `python3 "$SKILL_DIR/scripts/orchestrator.py" run PROJECT_DIR`, `checkpoint`, `resume`, and `report`. A competing OPEN/BLOCKED run is rejected until the current run is reconciled or completed. The Python control plane does not start native Agent sessions itself.

## Evolution collection

Evolution may derive a sanitized Outcome from a structurally consistent completed run. Collection revalidates all six ledger files, exact event sequence, DONE and independent-QA conclusion, project-local indexed evidence, routing lineage, resource limits, and stable file hashes. It does not copy notes, logs, evidence contents, source code, project prose, or customer data.

Run files are unsigned local evidence. Structural validation detects corruption and inconsistency, not a coherent malicious rewrite by an actor who can replace every related file. A changed fingerprint for an already collected Run returns lineage drift instead of creating a second Outcome.

An OPEN, BLOCKED, inconsistent, oversized or changing Run is not a collectible Outcome. Record a failed or blocked lesson through explicit sanitized Evolution Feedback rather than editing run history. See [evolution-core.md](evolution-core.md).
