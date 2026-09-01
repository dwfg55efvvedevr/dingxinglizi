# Deterministic recovery

Recovery reconstructs the next safe orchestration action from project files and the latest run ledger. It never assumes an in-memory Agent or tool call survived a restart.

## Decisions

- `RESUME_SAFE`: inputs and route fingerprints still match, no uncertain active session exists, and the last checkpoint is reusable.
- `REPLAN_REQUIRED`: authoritative inputs or role routing changed. Re-run `plan --write` before dispatch.
- `RECONCILIATION_REQUIRED`: project state still lists an active session. Inspect the actual runtime/session, persist any valid handoff, or explicitly close the stale record; do not clear it automatically.
- `BLOCKED`: required files, valid state, or trustworthy recovery evidence are missing.
- `DONE`: the run is already terminal; generate/read its report rather than restarting it.
- `GOVERNANCE_METADATA_DEGRADED`: stale but non-active control metadata exists and the current delta is local, reversible, ownership-safe, and not high risk. Record the degradation and continue through a lightweight patch/change session.
- `TAKEOVER_OR_REPLAN`: two progress requests produced no useful update and a third wait would exceed the execution budget. The Orchestrator takes over the last bounded work or creates a smaller plan; it does not wait indefinitely.

## Recovery sequence

1. Run `doctor PROJECT_DIR`.
2. Run `resume PROJECT_DIR [--run-id RUN-ID]`.
3. Follow only the returned decision and corrective action.
4. If re-planning, compare the new plan to the recorded routing decision and create a fresh Task Package/dispatch receipt when its contract changed.
5. If reconciling, do not launch a duplicate role until the uncertain session is resolved.
6. After continuation, checkpoint the verified handoff and regenerate the report.

Environment failures do not count as reasoning failures and must not trigger model escalation. If auth, permissions, credentials, a missing tool, or an external system caused interruption, route to the matching pause state in [automation-boundaries.md](automation-boundaries.md).

Classify control-plane problems separately. An active conflicting writer, unsafe permission, missing high-risk authority, or uncertain production action is an `EXECUTION_SAFETY_BLOCKER`. A closed old run, stale role-plan fingerprint, or unverified low-risk model inventory is metadata degradation, not an implementation blocker for a local reversible Quick/Bounded delta. Independent QA requirements remain fail-closed.
