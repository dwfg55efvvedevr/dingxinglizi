# On-demand role routing

Role files are an installed capability library, not a promise to start every Agent. The Orchestrator stays in the main thread and routes only the current gate. A role exits after returning its bounded artifact; later work reads that artifact from project documents instead of keeping the role alive.

## Runtime sequence

1. Read `docs/project-status.json` and route the current stage with `python3 "$SKILL_DIR/scripts/route_roles.py"`.
2. Create Task Packages only for `required_now`, or for a `delegable_workers` entry under the currently active Engineering Lead. Never spawn `deferred_available` roles.
3. `required_now` is only the first unfinished wave; `deferred_sequence` is a preview, not permission to start those roles.
4. Before starting, require `python3 "$SKILL_DIR/scripts/check_execution_plan.py" ... --record-ready` to create its dispatch receipt. Stop a role after its handoff is persisted, mark the Task Package `COMPLETED`, and record a successful handoff plus artifacts/evidence files that exist inside the project. Re-route with `--completed-role ROLE --completed-task ROLE=tasks/TASK.yaml`; the router verifies the prior READY receipt and completion proof before the next unfinished wave becomes `required_now`.
5. Final QA is always a different Agent/session from Engineering Lead, but is not started until `READY_FOR_QA`.

Completed roles accumulate inside one `routing_cycle_id`, so a two-wave gate ends after both verified handoffs instead of restarting wave one. Completion proof must keep the exact stage, complexity, quota mode, and normalized signals of the current cycle. A stage, signal, quota, complexity, or unclaimed input change starts a new cycle and clears prior completion claims.

## Quota modes

| Mode | Concurrent subagents | Use |
|---|---:|---|
| `economy` | 1 | Default. Sequential roles, minimum calls, all hard gates retained. |
| `balanced` | up to 2 | Parallel read-only work only when inputs and file ownership are independent. |
| `quality_first` | up to 2 | Adds independent Quality Governor reviews at the three quality subgates. |

Quota mode controls concurrency and optional independent review; it never merges final QA into development, skips a hard gate, or permits silent assumptions.

One active role maps to one active task. A second task for the same professional role is blocked even when a balanced slot is free. The second slot is usable only when the generated current wave contains a different read-only role, or for the explicit Engineering Lead + one governed Worker pattern.

In `economy`, Engineering Lead implements directly because a child Worker would consume a second active slot. In `balanced` or `quality_first`, `--signal implementation_workers` exposes a bounded `delegable_workers` pool during `IN_DEVELOPMENT`; Engineering Lead and at most one Worker may be active together. A Worker must return to/review with Engineering Lead and cannot spawn anything.

At `CODE_REVIEW`, the evidenced signal `large_repository_review` enables the same one-Worker slot only in `balanced` or `quality_first`. Each repository shard uses one fresh, bounded, read-only Worker task and exits before another shard starts. `economy` keeps the slot closed, so Engineering Lead coordinates or performs shards sequentially. Large scope never raises the two-session ceiling and never activates every Worker at once. Cross-module contract review remains a later Architect wave when the normal architecture signals require it; final QA activates only at `READY_FOR_QA`.

## Complexity means availability across the lifecycle

- `Simple`: Requirements may cover product-completeness responsibility; UX may cover UI; Engineering Lead may cover low-risk architecture. Separate specialists activate only on a signal.
- `Standard`: Requirements and Product Auditor are separate. UX may cover ordinary UI; UI and Architect activate when their specific surfaces or contracts exist.
- `Complex`: all professional roles are available across the lifecycle, but only the current gate's roles activate. Complex never means “spawn all roles now.”

## Activation signals

Pass only evidenced signals: `unclear_requirements`, `novel_problem`, `evidence_conflict`, `coverage_risk`, `user_facing`, `flow_complexity`, `visual_system`, `accessibility`, `new_contracts`, `architecture_risk`, `cross_module`, `contract_delta`, `implementation_workers`, `large_repository_review`, `high_impact`, `regulated`, `release_risk`, or `repeated_failure`.

Examples:

```bash
python3 "$SKILL_DIR/scripts/route_roles.py" PROJECT_DIR --stage DISCOVERY --signal unclear_requirements
python3 "$SKILL_DIR/scripts/route_roles.py" PROJECT_DIR --stage UX_READY --signal visual_system --quota balanced --write
python3 "$SKILL_DIR/scripts/route_roles.py" PROJECT_DIR --stage CODE_REVIEW --signal contract_delta \
  --completed-role engineering_lead \
  --completed-task engineering_lead=tasks/TASK-CODE-REVIEW.yaml \
  --write
python3 "$SKILL_DIR/scripts/route_roles.py" PROJECT_DIR --stage READY_FOR_QA --write
```

Unknown stages, signals, completed roles, handoff proofs, policies, and quota modes fail closed. `--write` persists the role plan and synchronizes `quota_mode` plus `max_active_subagents` in `docs/project-status.json`; it does not start Agents. A switch to a smaller quota is rejected while too many sessions remain active.

For an independent Problem Quality review, Requirements runs in wave 1. After its complete Task Contract, handoff, and updated input documents are persisted, close the session and re-route with the same quality-triggering signals plus its verified `--completed-role/--completed-task` proof. The fresh plan then contains only Quality Governor. Do not pre-create or pre-start the second-wave task against the old input fingerprint.
