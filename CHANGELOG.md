# Changelog

All notable changes are recorded here. Product versions follow semantic versioning; internal routing policy versions are versioned independently.

## [2.0.0] - 2026-08-28

### Added

- Unified `scripts/orchestrator.py` control-plane CLI.
- Validated, atomic canonical lifecycle `transition` command.
- Read-only Skill/project `doctor` with actionable readiness states.
- Project-local run ledger, explicit sanitized checkpoints, evidence index, duplicate-run protection, deterministic `resume`, and derived `report`.
- Versioned domain packs for ecommerce, CRM, SaaS, group buying, AI agents, and home services.
- Deterministic offline role/model routing evaluation suite.
- Task Package v2 lineage fields (`schema_version`, `run_id`, source-input fingerprint).
- Runtime inventory provenance plus explicit verified Skill/MCP capability lists.
- Recovery, run-ledger, evaluation, domain-pack, and v1 migration references.
- Simple, Standard, and Complex usage examples.
- GitHub Actions CI across supported Python versions.

### Changed

- Canonical user installation path is `~/.agents/skills/software-project-orchestrator`, matching current Codex local Skill discovery.
- Skill entry flow now distinguishes initialization, continuation, recovery, and status/report requests.
- Role plans expose current required roles, execution waves, deferred availability, concurrency, quality gate, signals, and fingerprints.
- Shared Agent return conclusions are role-specific for ordinary roles, independent QA, and Quality Governor.
- Orchestrator is the sole run-ledger writer and must reconcile uncertain sessions before dispatch.
- Task creation binds the current open run; dispatch receipts preserve the same run and source-input lineage.
- Checkpoint event types enforce event-specific Task, handoff, gate, evidence, and completion contracts.
- `DONE` resume/completion re-runs the full lifecycle gate instead of trusting a hand-edited state.
- Capability provisioning records `PROVISIONED_PENDING_RUNTIME`; disk/config presence cannot satisfy dispatch until a fresh runtime verifies discovery.

### Preserved

- Stable invocation name: `$software-project-orchestrator`.
- Simple/Standard/Complex role policy, on-demand dispatch, development/QA separation, model routing, capability broker, product gates, and legacy single-purpose scripts.
- Internal role/model policy version `1.2.0`, because v2 does not silently relabel an unchanged policy algorithm.

### Honest limits

- The local CLI does not spawn or restore Codex Agent sessions, read account quota, bypass authentication, or safely auto-install unknown community code.
- Offline evals validate deterministic control rules, not end-to-end Agent or product quality.
