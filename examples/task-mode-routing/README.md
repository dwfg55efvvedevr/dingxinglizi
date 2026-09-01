# Task-mode routing examples

## Complex project, one-page copy/style

Expected route: `QUICK_PATCH`; main session; zero child Agents; targeted artifact and related test only. Explicit Skill invocation does not change the route.

## Group-buy pickup configuration

Scope: admin address search, map pin, service-region configuration, API fail-closed behavior, no schema migration, no payment/permission change, reversible.

Expected route: `project_complexity=Complex`, `task_mode=BOUNDED_CHANGE`; Compact Delta Contract; Engineering Lead; targeted API/UI tests; one final regression; independent QA; at most one focused repair. Requirements and Quality Governor are not activated.

## Payment, permission, migration, or concurrency

Any payment/refund/settlement state change, authorization/data-scope boundary, irreversible migration, or concurrency/consistency redesign routes to `GOVERNED_DELIVERY` even if only one file is expected to change.

## Scope expansion

“Make it consistent everywhere” after a single-page request returns `SCOPE_CONFIRMATION_REQUIRED` when it may affect multiple pages/apps. Without confirmation, retain the narrow reversible scope.
