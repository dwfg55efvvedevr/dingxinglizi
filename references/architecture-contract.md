# Architecture contract

Architect translates approved product behavior into explicit technical contracts without changing its intent.

Cover when applicable:

- module/service boundaries and ownership;
- domain entities, identifiers, invariants, lifecycle/state transitions, and invalid transitions;
- API/event inputs, outputs, errors, versioning, retries, timeouts, idempotency, and compatibility;
- authentication, authorization, data scope, sensitive fields, audit logs, and retention;
- transaction boundaries, concurrency, ordering, consistency, outbox/queue behavior, and recovery;
- schema changes, migrations, backfills, feature flags, rollback, and deployment sequence;
- observability, operational dashboards/alerts, capacity, performance, and failure modes;
- external provider uncertainty and limits on automatic retries.

Write consequential choices as decision records in `docs/decisions/`. A decision states context, options, decision, consequences, rollback/reversal, affected documents, and approval status.

Architecture gate fails when APIs/data/permissions/state behavior required for implementation remains ambiguous, when an irreversible migration lacks recovery, when a client-hidden control is mistaken for backend authorization, or when external side effects cannot meet the product promise.

Engineering may propose corrections but cannot silently reinterpret an approved contract. Route product meaning changes to Requirements/Product and technical contract changes to Architect through Orchestrator.
