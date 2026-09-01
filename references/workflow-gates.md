# Lifecycle states and quality gates

## Canonical states

`BACKLOG → DISCOVERY → REQUIREMENTS_APPROVED → PRODUCT_APPROVED → UX_READY/UI_READY + ARCHITECTURE_READY → READY_FOR_BUILD → IN_DEVELOPMENT → CODE_REVIEW → READY_FOR_QA → QA_PASS → RELEASE_READY → DONE`

Because UI and architecture may proceed in parallel after UX stabilizes, `docs/project-status.json` records individual gates as well as one `current_state`. `READY_FOR_BUILD` requires `requirements`, `product`, `ux`, `ui`, and `architecture` gates to be `APPROVED`. A Simple project may merge role ownership, but it still records approval evidence for every gate.

## Delta gate overlay

The canonical lifecycle governs a new product, major module, or `GOVERNED_DELIVERY`; it is not a mandatory state transition sequence for every local iteration. `QUICK_PATCH` and `BOUNDED_CHANGE` record an `iteration_state` without advancing, reopening, or rewriting the project's global state.

- Quick: `TRIAGED → IMPLEMENTING → TARGETED_VALIDATION → COMPLETE`.
- Bounded: `DELTA_DRAFT → DELTA_READY → IMPLEMENTING → TARGETED_VALIDATION → QA → DELTA_DONE`, with at most one `QA → IMPLEMENTING → TARGETED_VALIDATION → QA` focused-repair loop.

The overlay inherits approved business facts and global constraints. Escalate to the canonical lifecycle only when a task-mode risk trigger or contradictory fact makes the delta unsafe. A reviewer may request a focused correction in the same Compact Delta Contract; a nonmaterial correction does not require new lifecycle planning, role-plan regeneration, or a new full Task Package.

For governed lifecycle work, the three cross-cutting quality subgates remain mandatory. A separate Quality Governor is triggered only by current-task risk. Delta overlays use their compact acceptance and QA evidence instead of manufacturing lifecycle approvals. See [quality-governance.md](quality-governance.md).

| Gate | Required evidence | Failure/rework owner |
|---|---|---|
| Requirements | approved context, domain rules, glossary, PRD; no P0/P1 blocking unknown | Requirements |
| Product | all completeness items disposed; required matrices complete; front/back-office closure | Product Auditor or Requirements |
| UX | page map, flows, states, exception/recovery paths | UX |
| UI | tokens/components, hierarchy, responsive/accessibility and state coverage | UI |
| Architecture | system design, API/data/permission/state contracts, ADRs/rollback where needed | Architect |
| Build | code, tests, migrations, review record, documented deviations | Engineering Lead |
| QA | independent acceptance evidence, regression result, defects closed or risk accepted | QA and defect source |
| Release | release/rollback plan, operations notes, required authorization | Orchestrator; user for external release |

## Blocking and rework

Use `BLOCKED` when an external dependency, missing authority, environment, data, or P0/P1 unknown prevents a valid conclusion. Record `blocked_from`, reason, owner, unblock evidence, and next review.

Use exactly one source-specific rework state: `REWORK_REQUIREMENTS`, `REWORK_PRODUCT`, `REWORK_UX`, `REWORK_UI`, `REWORK_ARCHITECTURE`, `REWORK_ENGINEERING`, or `REWORK_QA`. The defect record must contain the failed criterion, evidence, severity, responsible source, affected artifacts, required correction, and re-entry gate. Orchestrator alone changes the global state after evidence is reviewed.

## READY_FOR_BUILD hard stop

Do not approve until all of the following are present and traceable:

- role → page;
- page → feature;
- feature → state, including loading/empty/success/failure/offline/unauthorized/expired where applicable;
- front-office action → back-office handler/object/status/audit;
- role/resource/action/data-scope permissions;
- requirement/feature → acceptance criterion → evidence type.

Run all scripts in `scripts/`. `check_project_status.py --target READY_FOR_BUILD` is the deterministic aggregate check, but Orchestrator still evaluates business meaning rather than treating a script exit code as approval.
