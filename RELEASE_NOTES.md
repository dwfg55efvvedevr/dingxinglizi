# Software Project Orchestrator v3.2.2

`dingxinglizi` v3.2.2 fixes workflow inflation while preserving intentional governance escalation and making dependencies explicit. It classifies the current delta before initialization or delegation as `QUICK_PATCH`, `BOUNDED_CHANGE`, or `GOVERNED_DELIVERY`. Project complexity remains useful context, but no longer forces a local change through the whole project lifecycle. Explicit Skill invocation requests a complete closed loop, not every Agent and gate; a separately explicit higher `requested_mode` is honored, while a lower request cannot bypass the computed safety floor. The portable runtime requires Python 3.9+ and no third-party Python package; a new dependency report explains optional Git/host features and identifies PyYAML as development-only for OpenAI skill-creator's external validator.

## Task-sized delivery

- Quick: main session, zero child Agents, user-visible artifact first, targeted checks, no full control-plane initialization by default.
- Bounded: Compact Delta Contract, one Engineering Lead, targeted validation, independent QA when required, and at most one focused repair; no default Requirements or Quality Governor.
- Governed: existing lifecycle and independent QA for payment, permission/data-scope, privacy/security/compliance, migration/irreversible data, concurrency/consistency, production/external actions, major contracts, or conflicting facts.
- Quality Governor is now triggered by current-task risk. Wording precision that does not change safety, implementation, money, permissions, data writes, or recoverability is a nonblocking note.
- Execution safety blockers are distinct from stale governance metadata. Low/medium-risk local work may proceed with honest `UNVERIFIED` runtime evidence; high-risk floors remain fail-closed.
- Policy recommendation, user-approved model override, and actual launch attestation coexist without pretending an override proves launch.
- Wait and time budgets trigger `TAKEOVER_OR_REPLAN`; scope expansion triggers `SCOPE_CONFIRMATION_REQUIRED`.

Portable time/wait/session counters are caller-reported and labeled as such; native enforcement requires matching host receipts. The iteration-transition command fails closed on independent QA inputs before `DELTA_DONE`, but remains a non-persisting validator rather than a hidden background workflow.

The reference case—pickup-point map configuration plus API fail-closed behavior in a Complex group-buy platform, with no migration or payment/permission change—now routes to Bounded Engineering → QA instead of Requirements/QG lifecycle churn.

## Large Repository Review Engine (retained and faster)

Large codebases no longer need to be handed to one long-lived Agent session: the control plane pins the target, inventories declared scope and exclusions, creates budgeted module/risk shards, validates immutable results, merges findings conservatively, and optionally governs bounded repair with independent re-review and QA. v3.2 indexes planning lookups and reads Git blobs through one validated batch process where supported; the 10,000-file regression completes planning in well under a second on the release machine.

## Highlights

- Pinned Git baseline/target with manifest fingerprints; non-Git worktree snapshots are explicit and carry weaker claims.
- Deterministic inventory with visible dispositions for included, generated, vendor, cache/build, binary, LFS, submodule, symlink, oversized and excluded inputs.
- Module/technology primary shards plus cross-cutting security, money, migration, API-contract, deployment, concurrency and supply-chain risk shards when evidence requires them.
- Static `max_files`, `max_bytes` and `max_estimated_tokens` budgets; a single oversized file blocks rather than being silently dropped.
- Fresh-session and compact-handoff contracts for shards, repair, re-review and QA. Attestation remains local evidence and is reported as verified or unverified.
- Structured finding schema with exact target/shard/file lineage. Only exact duplicates merge; possible duplicates and severity conflicts remain visible.
- Every shard result is bound to a validated review Task Package and READY dispatch receipt, and COMPLETE requires concrete evidence for every pinned file object.
- Repository content is untrusted by default. Explicitly trusted instruction files and repository-execution authority are fingerprinted into the review contract.
- Repeatable mandatory risk lenses cover material risks that filenames cannot reveal.
- Default `review_only` mode and explicit `review_and_fix --authorize-fix` mode.
- Finding-bound repair plans, maximum two repair rounds, separate preflighted Task Packages/dispatch receipts for repair and re-review, different fixer/reviewer identities and sessions, independent re-review for every authorized repair regardless of severity, visible repair progress, and a governed READY_FOR_QA Task Package that re-verifies every P0/P1 and every authorized repair finding on the final target before `QA_PASS` finalization.
- Context-limit failures split or narrow the Task Package before model escalation.
- Chinese-first README, complete review CLI guide, concrete prompts, a large-repository walkthrough, and explicit Codex/Cursor/Claude Code/OpenCode boundaries.
- Release artifacts are built and smoke-tested before tagging; existing releases receive refreshed notes before asset upload.

## Honest completion claim

The strongest possible review conclusion is:

```text
COMPLETE_FOR_DECLARED_SCOPE
```

It means the current declared inventory was assigned, required primary and cross-cut shards returned valid evidence, exclusions remain visible, and fingerprints are current. It does **not** mean zero defects, complete runtime-path coverage, perfect module discovery, full semantic understanding, exact runtime token measurement, absolute session isolation, or verified native execution on every supported host.

## Quick start

```bash
git clone --branch v3.2.2 https://github.com/lizi-product-studio/dingxinglizi.git /tmp/dingxinglizi
cd /tmp/dingxinglizi
python3 scripts/orchestrator.py platform detect
python3 scripts/orchestrator.py platform install --platform codex --scope user
python3 scripts/orchestrator.py platform install --platform codex --scope user --apply
```

Start a review after the project has an `OPEN` run:

```bash
python3 scripts/orchestrator.py review preview /path/to/project \
  --baseline main --target HEAD --mode review_only \
  --required-risk permissions --required-risk privacy
python3 scripts/orchestrator.py review start /path/to/project \
  --baseline main --target HEAD --mode review_only \
  --required-risk permissions --required-risk privacy
python3 scripts/orchestrator.py review status /path/to/project
```

The `preview` command is zero-write. Inspect its target, exclusions, blockers, module basis, shard plan, and budget; then run `start` with the same arguments to persist review state. Use `review_and_fix --authorize-fix` only when local source repair is explicitly authorized. The engine computes effective repair snapshots; users should never invent artifact hashes, and any supplied fingerprint must match the computed source snapshot.

## Upgrade and compatibility

Re-run the selected platform installer with `--apply --update` after previewing its plan. Existing v2 projects remain usable without migration; v3 projects continue to use `.dingxinglizi/`. The stable invocation, run schema, Task Package schema, provider-neutral model policy and internal Evolution generator version are not silently relabeled.

Codex, Cursor, Claude Code and OpenCode share the portable Skill and review records. Native Agent launch, model/reasoning inventory, MCP setup, session isolation and execution receipts are host-specific. A generated profile is never proof that a host launched the requested session or model.

## Authorization boundary

`--authorize-fix` covers only the bounded local repair plan. It does not grant production deployment, external writes, credentials, purchases, customer messages, dependency/contract scope expansion, destructive migrations or public release. Those actions still require separate authorization.

See [USAGE.md](USAGE.md), [the large repository example](examples/large-repository-review/README.md), and [the maximum-capability guide](references/max-capability-guide.md).
