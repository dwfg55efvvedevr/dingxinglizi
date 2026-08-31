# Review and repair control

Read this only when the user has authorized both review and source repair. The default large-repository mode is `review_only`.

## Authority split

Review shards are always read-only with respect to business source. A merged finding does not itself authorize a change. The Orchestrator may create a repair contract only when:

- the review mode is `review_and_fix`;
- the finding is current and has valid target/shard lineage;
- the responsible source owner is identified;
- the allowed source files are explicit;
- the proposed change remains inside the user's scope;
- no production, credential, external, destructive, irreversible or new dependency authority is being inferred.

If any condition is missing, use `BLOCKED_REPAIR_AUTHORITY` or the matching upstream rework state.

## Repair loop

```text
merged finding
  → source-owner routing
  → finding-bound repair contract
  → repair Task Package + READY dispatch receipt
  → Engineering Lead / one Worker fixes within allowed files
  → tests and compact repair evidence
  → new target/snapshot and affected-shard invalidation
  → re-review Task Package + READY dispatch receipt
  → different fresh Engineering Lead/Architect session re-reviews
  → READY_FOR_QA task + independent QA regression on final target
  → close, accept risk, defer with authority, or block
```

The ordinary maximum is two reasonable repair attempts per finding. A failed reasoning attempt may raise effort, then capability. Environment or authorization failures do not spend a model escalation. Repeated failure, scope expansion, unresolved evidence conflict or unsafe rollback requires Orchestrator review instead of an infinite loop.

## Separation invariants

- Review session does not repair.
- Repair session does not close its own finding.
- Repair and re-review records are rejected without their own completed Task Package, matching READY dispatch receipt and contract-bound evidence output.
- Re-review session differs from the repair session and should differ from the original review session.
- Re-review records a concrete bounded verification note for every finding; a bare `PASS` outcome is invalid.
- Engineering Lead normally re-reviews Worker repairs at `CODE_REVIEW`; Architect re-reviews when Engineering Lead is the fixer. Final QA is a later `qa`-owned task at `READY_FOR_QA` and differs from Engineering Lead and all implementation Workers.
- Final QA re-verifies every P0/P1 and every finding that entered an authorized repair plan against the final effective target, so a later same-file repair cannot silently stale an earlier P2/P3 closure.
- One writer owns a mutable file at a time.
- A new source target invalidates affected old coverage until re-reviewed.

## Finding disposition

- `OPEN`: valid and not repaired/accepted.
- `REPAIR_PLANNED`: authorized bounded repair exists.
- `REPAIRED_PENDING_REREVIEW`: repair evidence exists but the finding remains open.
- `REREVIEW_PASS`: a different session verified the current target.
- `REREVIEW_FAIL`: still reproducible or repair caused a new issue.
- `ACCEPTED_RISK`: an authorized decision owner accepted a material risk with evidence.
- `DEFERRED`: explicitly outside the current release/scope with owner and follow-up.
- `BLOCKED`: missing authority, environment, decision or safe correction.

P0/P1 cannot be silently deferred or treated as fixed. `ACCEPTED_RISK` is not invented by QA or the repair Agent.

## Finalization

`review_and_fix` can reach its strongest conclusion only when the declared-scope coverage is current, every finding that entered an authorized repair plan—including P2/P3—has an independent re-review PASS, P0/P1 disposition satisfies project gates, a governed final QA task and per-finding final-target verification are present, the project has reached `QA_PASS`, conflicts/possible duplicates are resolved or explicitly retained, and no target/plan drift exists. `status` and the final report expose repair-plan status counts, authorized findings, verified findings, and any unverified repair findings; historical failed rounds remain visible.

This is a controlled repair system, not a promise that every issue is automatically solvable.
