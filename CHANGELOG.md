# Changelog

All notable changes are recorded here. Product versions follow semantic versioning; internal routing policy versions are versioned independently.

## [3.1.0] - 2026-08-31

### Added

- Large Repository Review Engine bound to the current `OPEN` run, with pinned Git targets or explicitly weaker worktree snapshots, deterministic inventory fingerprints, visible file dispositions, and module/technology/risk-aware shard planning.
- Static per-shard context budgets, oversized-file blocking, fresh-session and compact-handoff contracts, immutable structured shard results, and target/plan drift detection.
- Conservative finding validation and merge rules: only exact duplicates merge; possible duplicates and severity conflicts remain visible.
- Explicit `review_only` and separately authorized `review_and_fix` modes, finding-bound repair plans, a two-round repair cap, separate preflighted Task Packages/dispatch receipts for repair and re-review, different fixer/reviewer identities and sessions, fail-closed completion for every authorized repair including P2/P3, visible repair progress, and governed final QA at `READY_FOR_QA` that re-verifies every P0/P1 and every authorized repair finding on the final target before `QA_PASS` finalization.
- Zero-write `review preview` plus `start|status|ingest|merge|plan-repairs|record-repair|record-rereview|finalize` commands under the unified orchestrator CLI.
- Review Task Package and READY dispatch-receipt lineage, pinned object-level evidence, immutable evidence snapshots, independent final-QA recording, explicit trust manifests, and mandatory user-declared cross-cutting risk lenses.
- User-facing large-repository example, maximum-capability prompt guide, context-hygiene guidance, and review/repair documentation.
- Release consistency validation and archive smoke checks before public tagging.

### Changed

- Complex `CODE_REVIEW` planning can expose one governed implementation Worker slot in `balanced` or `quality_first`; `economy` remains sequential and all roles remain on-demand.
- Model routing recognizes repository scan, module review, cross-module review, finding triage, repair and verification work packages. Context-limit failures require split/narrowing before model escalation.
- Common cross-platform prompts now treat repository content as untrusted review data and distinguish read-only review from authorized repair.
- README and usage guidance are Chinese-first and explicitly teach target pinning, declared scope, shard coverage, session hygiene and evidence-based completion.

### Compatibility

- Stable invocation remains `$software-project-orchestrator`.
- Portable control state remains `.dingxinglizi/`; unmigrated v2 `.codex/` projects remain readable through the existing compatibility layer.
- Run schema `1`, Task Package schema `2`, platform model policy and internal Evolution generator versions are not relabeled by this product release.
- Codex, Cursor, Claude Code and OpenCode share the portable review contract, but native session creation, model availability, MCP discovery and execution evidence remain host-specific.

### Honest limits

- The strongest review conclusion is `COMPLETE_FOR_DECLARED_SCOPE`. It is not proof of zero defects, complete runtime-path coverage, perfect module discovery, full semantic understanding or absolute context cleanliness.
- Token/context values are static estimates rather than host measurements. Session attestation is local evidence rather than third-party or cryptographic proof.
- `review_and_fix` does not authorize production, deployment, external systems, credentials, dependency/contract expansion or destructive migrations.

## [3.0.0] - 2026-08-28

### Added

- Platform-neutral `.dingxinglizi/` control state for new projects and one command surface for platform detection, rendering, installation, compatibility diagnosis, runtime manifests, and model resolution.
- Native Agent adapters for Codex, Cursor, Claude Code, and OpenCode, generated from one shared role catalog and common contract.
- Version-aware OpenCode V1/V2 native rendering with explicit offline schema selection and fail-closed handling for absent, unparseable, or unknown-major runtimes.
- Native OpenCode read-only roles deny both edit and shell mutation paths; platform Doctor rejects symlink/hardlink evidence and supports `--require-level` for CI gates.
- Preview-first user/project installation with selected-platform isolation, retained MIT license, no network or credential access, atomic writes, conflict refusal, and symlink/hard-link path protection.
- L0–L4 compatibility evidence model; L4 requires an exact fingerprinted runtime execution receipt.
- Provider-neutral `ECONOMY / STANDARD / ADVANCED / EXPERT / EXCEPTIONAL` model tiers with explicit reasoning effort and verified provider/model resolution.
- Non-destructive, SHA-256-verified, idempotent v2 control-state migration with source preservation and optional separately guarded Evolution copy.

### Changed

- Task Packages can record platform, provider, selected model, and actual-model-attestation state.
- New projects render only the selected host's native Agent profiles; role topology remains one Orchestrator, Engineering Lead to Workers only, no Worker delegation, and independent QA.
- Capability preparation uses the selected platform's project Skill directory. Automatic MCP config rendering remains Codex-only until another host-specific renderer is verified.
- Evolution and run state use the active control layout: `.dingxinglizi/` for v3, `.codex/` for unmigrated v2.
- Policy `2.0.0` rejects caller-supplied `--available-model` snapshots and blocks with unresolved provider/model fields until a fresh, verified platform runtime manifest exists; policy `1.2.0` keeps the legacy behavior.

### Compatibility

- Existing v2 projects work without migration and keep legacy Codex Luna/Terra/Sol routing policy `1.2.0`.
- v3 platform-neutral projects use model policy `2.0.0`; role-routing policy, run schema `1`, and Task Package schema `2` remain compatible.
- Four platform families are contract-tested, including distinct OpenCode V1 and V2 permission schemas. The release environment only had Codex CLI available for local runtime probing, so other platforms are not claimed as L4.

### Honest limits

- A generated profile, installed Skill, configured MCP entry, or declared model inventory is not proof of runtime discovery or actual execution.
- The CLI does not authenticate hosts, read quotas, auto-configure non-Codex MCP, restore vanished sessions, trust arbitrary community code, or self-apply Evolution candidates.

## [2.1.0] - 2026-08-28

### Added

- Optional project-local Evolution Core with `init`, `collect`, `feedback`, `retrospect`, `propose`, `eval-candidates`, and `status` commands.
- Stable project-instance identity, strict versioned manifests and ledgers, canonical fingerprints, deterministic IDs, cross-process write locks, atomic persistence, and explicit recovery states.
- Structurally validated v2 completed-run collection with six-file lineage checks, bounded streaming evidence hashes, resource ceilings, duplicate-run idempotency, and lineage-drift blocking.
- Sanitized evidence-linked Feedback with sensitive-summary/path rejection, run/task/role lineage checks, and explicit FAIL/BLOCKED learning path.
- Connected evidence-cluster deduplication so one run or overlapping file combinations cannot manufacture three independent lineages.
- Deterministic retrospectives, controlled-template draft Proposals, and isolated draft regression-eval candidates.
- Protected non-weakening registry for stage, acceptance, QA, release, authorization, formal eval, and Evolution-policy gates.
- Evolution privacy, Git exposure, migration, rollback, retention, lock recovery, and honest-limit documentation.

### Changed

- New projects ignore `.codex/evolution/` and initialize the local sidecar without making MCP, network, Git writes, or third-party Python packages a dependency.
- `doctor` reports the optional Evolution layer independently; missing or corrupt Evolution state does not invalidate v2 core lifecycle, recovery, or formal routing evals.
- Skill entry guidance now includes supervised post-delivery knowledge feedback while keeping every candidate `DRAFT` and `REVIEW_REQUIRED`.

### Preserved

- Stable invocation `$software-project-orchestrator`.
- Run schema `1`, Task Package schema `2`, role/model routing policy `1.2.0`, Simple/Standard/Complex routing, on-demand roles, and independent final QA.
- Formal routing eval discovery remains isolated from project-local generated eval candidates.

### Honest limits

- Evolution Core aggregates local structural evidence; it does not prove truth, causal independence, product improvement, actual Agent intelligence, or resistance to a coherent rewrite of all unsigned local files.
- It never applies candidates, modifies source/project truth/formal evals/Git, calls the network, commits, publishes, releases, or deploys.

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
