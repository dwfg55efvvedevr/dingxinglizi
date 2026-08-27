# Product completeness

Product Auditor uses `docs/checklists/product-completeness.md`. Every row must have an applicability value of `REQUIRED`, `NOT_APPLICABLE`, or `DEFERRED`—never blank—and a coverage value of `COVERED`, `GAP`, or `BLOCKED`.

- `REQUIRED` requires `COVERED` plus one or more requirement, feature, or acceptance IDs before `READY_FOR_BUILD`.
- `NOT_APPLICABLE` requires a reason and uses `COVERED` only to mean the disposition is complete.
- `DEFERRED` requires a reason, owner, target milestone/task reference, and authorized risk owner. It must not be necessary for the current acceptance baseline.
- `GAP` or `BLOCKED` prevents the product gate from passing.

## Minimum catalog

- Identity: registration, login, verification code, forgot/reset password, logout, account deletion.
- Discovery: home, search, filter, list, detail.
- Account: notifications/messages, profile, settings, security, address/contact records.
- Support/legal: customer service, feedback, complaint, help, terms, privacy.
- Universal states: loading, empty, failure, offline, unauthorized, expired.
- Object lifecycle: create, modify, cancel, delete, restore.
- Service/commerce lifecycle where applicable: review/approval, refund, after-sales, rating/review, appeal.
- Admin: search, filter, review/approve, configuration, export, logs, permissions.
- Closure: every front-office action has a back-office/system handler, state transition, actor, audit behavior, failure/recovery path, and user-visible feedback.

## Audit sequence

1. Requirements defines roles, business objects, numbered rules, scope, and non-goals.
2. Product Auditor dispositions the complete catalog and creates the matrices.
3. UX adds entry/return/error/recovery paths; Architect adds state, permission, and backend contracts.
4. QA binds each `REQUIRED` item to acceptance evidence and tests positive and negative paths.

A `DEFERRED` item is not a polite way to hide a gap. If current flows, safety, legality, payment correctness, permissions, or acceptance depend on it, classify it as `REQUIRED` or block the baseline.
