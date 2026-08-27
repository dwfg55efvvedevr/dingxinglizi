# Independent QA and completion

QA is independent from implementation and read-only with respect to business code. It validates approved requirements rather than reverse-engineering intended behavior from the implementation.

## Minimum QA coverage

- every in-scope role, default landing path, navigation, action visibility, permission and cross-data-scope positive/negative case;
- every required function and state, including loading, empty, failure, offline, unauthorized, expired, disabled and recovery where applicable;
- every front-office action, backend/system handling, state transition, notification/audit consequence and failure path;
- API/data contract, validation, authorization, error mapping, idempotency/concurrency/migration risks where applicable;
- rendered UI at relevant viewports, focus/keyboard/contrast, content extremes and error states;
- regression around touched modules and all linked acceptance criteria.

Skipped required tests are not a pass. If environment or data prevents a required test, report `BLOCKED` with the missing prerequisite. Store sanitized evidence under `evidence/` and link it from `docs/10-test-plan.md`; never store credentials, production personal data, or unredacted secrets.

## DONE definition

`DONE` requires:

1. all current-scope acceptance criteria are `PASS` with evidence;
2. no unaccepted P0/P1 defect remains;
3. lower-severity known issues are documented and dispositioned;
4. implementation, tests, migrations, decisions, contracts, and user-facing docs agree;
5. QA is independent and its conclusion is recorded;
6. release/rollback evidence exists when applicable;
7. Problem Quality, Solution Challenge, and Release Evidence quality gates are approved with current input fingerprints;
8. no Engineering/Worker session remains active at final QA, and no task/session remains active at `DONE`;
9. external deployment, public release, customer communication, purchase, credential use, or irreversible action has separate explicit authorization.

Report the final state, baseline versions, tests/evidence, defects, accepted risks, deferred work, and next authorization. “Code complete” or “tests passed locally” alone is not `DONE`.
