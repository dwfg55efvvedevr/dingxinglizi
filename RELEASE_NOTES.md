# Software Project Orchestrator v3.1.0

`dingxinglizi` v3.1.0 adds a governed Large Repository Review Engine to the portable `$software-project-orchestrator` workflow. Large codebases no longer need to be handed to one long-lived Agent session: the control plane pins the target, inventories declared scope and exclusions, creates budgeted module/risk shards, validates immutable results, merges findings conservatively, and optionally governs bounded repair with independent re-review and QA.

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
git clone --branch v3.1.0 https://github.com/lizi-product-studio/dingxinglizi.git /tmp/dingxinglizi
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
