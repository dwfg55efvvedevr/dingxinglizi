# Task-mode routing

Classify the current delta before initialization, lifecycle loading, run creation, or delegation. Project complexity describes the surrounding system; task mode controls the current execution. A Complex project does not make every change governed.

## Modes and default budgets

| Task mode | Typical delta | Child Agents | Time expectation | Reference budget | Validation |
|---|---|---:|---:|---:|---|
| `QUICK_PATCH` | local copy/style/config or isolated low-risk bug | 0 | 3–15 min | at most 3 directly relevant files | user-visible artifact plus targeted checks |
| `BOUNDED_CHANGE` | bounded multi-file or frontend/API change, reversible, no high-risk contract | at most 1 active; at most 2 sequential role sessions | 15–45 min | only delta-relevant rules/contracts | targeted validation, one final regression, independent QA when medium/high risk |
| `GOVERNED_DELIVERY` | new/major module, broad product decision, permissions, payment, privacy, migration, concurrency, irreversible data or production action | quota and plan | report before work | full required gate set | governed packages and independent QA |

The first route result must state `task_mode`, confirmed scope, reasons, active Agents, expected time, validation plan, and escalation triggers. Explicit Skill invocation, “use the full Orchestrator,” or “走全流程” means a closed scope-to-validation loop; it does not authorize every lifecycle gate or Agent. A separately and explicitly selected `requested_mode` may raise the governance level, but it can never lower the task's computed safety floor.

## Fast-path rules

`QUICK_PATCH` stays in the main session, creates no run/ledger or Task Package by default, does not load full product/UX/architecture/knowledge references, and never runs the full suite unless a risk trigger is discovered. Inspect the nearest effective `AGENTS.md`, the directly relevant contract, and affected files. Verify the artifact the user actually consumes before declaring completion.

For a `BOUNDED_CHANGE`, use this overlay:

`impact scan → Compact Delta Contract → one Engineering Lead → targeted validation → independent QA → at most one focused repair/re-review`

The one-Agent limit is concurrency, not permission to omit independent QA. The bounded lifecycle cap is two professional sessions total—Engineering Lead and QA—unless an escalation converts the work to Governed Delivery.

Requirements and Quality Governor are not default participants. The main Orchestrator may write the compact contract when existing facts are sufficient. Use a separate Requirements Agent only for a blocking business-rule conflict; use Quality Governor only for a current-task risk trigger.

## Classification and escalation

Prefer `QUICK_PATCH` when the goal and acceptance are local, reversible, testable, and do not change business flow or a material contract. More than three business files, more than two surfaces, two applications, more than 15 minutes, or a request to “make it consistent everywhere” are scope-warning signals—not automatic escalation.

Return `SCOPE_CONFIRMATION_REQUIRED` before expanding a confirmed local delta to multiple pages, applications, roles, or system-wide behavior. State the narrow confirmed interpretation and the broader alternative with impact. Without confirmation, execute only the narrow reversible interpretation.

Use `GOVERNED_DELIVERY` when any current-task trigger exists: payment/refund/settlement; authorization or cross-tenant data scope; security/privacy/compliance; migration or irreversible data; concurrency/consistency; production credentials/external side effects; major state-machine or public-contract redesign; conflicting authoritative facts; multiple writers/teams; P0/P1 incident risk. A single file with one of these risks is not Quick.

If a budget is exceeded, stop adding Agents, identify why, report completed and remaining scope, and return `TAKEOVER_OR_REPLAN` or request scope expansion. Two consecutive waits without substantive progress require a precise blocker; three require takeover or replanning. Waiting is never evidence of progress.

Time, reference, planning-overhead, active-Agent, and total-session values are declared advisory ceilings unless a host adapter supplies observed receipts; the portable CLI cannot observe every host session or token counter. Budget output is labeled `DECLARED_CALLER_REPORTED_NOT_HOST_OBSERVED`. Today the CLI validates only explicitly supplied wait/time and QA/repair inputs. It compares declared Engineering and QA session IDs, conclusion, evidence references, and P0/P1 count before `DELTA_DONE`; it does not authenticate those identities, prove the evidence file exists, persist an iteration ledger, or enforce cumulative session/reference ceilings. Never describe a declared counter as host-enforced.

## Control-plane severity

- `EXECUTION_SAFETY_BLOCKER`: ownership collision, active conflicting task, unsafe permission/production action, high-risk model floor, missing authority, or evidence needed to prevent a harmful write. This blocks execution.
- `GOVERNANCE_METADATA_DEGRADED`: stale closed run, old role-plan fingerprint, or unverified model inventory for a local reversible Quick/Bounded task. Record it, use the host default as `UNVERIFIED` when safe, and repair metadata without blocking the code delta.

Independent QA remains fail-closed whenever the selected mode or risk requires it. Metadata degradation never permits implementation self-acceptance.
