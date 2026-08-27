# Project document contract

## Source of truth

Project documents are the shared business memory. Requirements maintains business facts but is not their sole holder. Every role reads the documents, and any approved change is written back before downstream work relies on it.

Precedence, highest first:

1. current explicit user decision;
2. approved decision record in `docs/decisions/`;
3. current approved task package;
4. approved stage documents;
5. project context, domain rules, and glossary;
6. historical chat or drafts.

Conflicts are never resolved silently. Record the conflict, affected requirements/artifacts, proposed resolution, decision owner, and version impact.

## Required structure

- `docs/00-project-context.md`: goal, problem, business model, success, scope, constraints, fact register.
- `docs/01-domain-rules.md`: numbered rules, objects, flows, state machines, permissions, money, notifications, operations, compliance.
- `docs/02-glossary.md`: one canonical definition per term.
- `docs/03-role-journey-matrix.md`: role-page, page-feature, and front-office/back-office matrices.
- `docs/04-prd.md`: requirements, priorities, scope, non-goals, acceptance intent.
- `docs/05-state-permission-matrix.md`: feature-state and role-resource permission matrices.
- `docs/06-ux-spec.md`: navigation, flows, actions, feedback, errors, recovery.
- `docs/07-design-system.md`: tokens, components, copy, accessibility, responsive states.
- `docs/08-system-design.md`: boundaries, state machines, consistency, security, logging, deployment and ADR links.
- `docs/09-api-data-contract.md`: APIs/events, data models, errors, auth, idempotency and migrations.
- `docs/10-test-plan.md`: acceptance matrix, test levels, fixtures, evidence and regression.
- `docs/decisions/`: immutable or superseding decision records.
- `tasks/`: one current execution contract per task.
- `evidence/`: referenced screenshots, logs, reports, responses, or manifests; never secrets or real personal data.

## Version awareness

Each maintained Markdown document includes `status`, `version`, `last_updated`, `owner`, and `source_of_truth`. Use `DRAFT`, `IN_REVIEW`, `APPROVED`, or `SUPERSEDED`. Do not rewrite history for consequential decisions; create a decision record and increment affected document versions. A downstream stage consumes only approved baselines unless its task explicitly authorizes draft exploration.

## Fact states

Use only `CONFIRMED`, `EVIDENCE_INFERRED`, `DEFAULT_ASSUMPTION`, `NOT_APPLICABLE`, or `BLOCKING_UNKNOWN`. A reversible default must name its evidence, impact, and replacement trigger. Business priority, compliance, licensing, intellectual property, customer acceptance, or irreversible action cannot be defaulted.
