# v3 platform-neutral architecture decision

Status: accepted for v3.0.0

## Context

v2 combined portable workflow state with Codex-native `.codex` paths and Luna/Terra/Sol routing. Reusing the delivery system on Cursor, Claude Code, and OpenCode requires separating project truth/control contracts from host configuration without breaking existing projects.

## Decision

1. New projects store portable control state under `.dingxinglizi/`.
2. If `.dingxinglizi/` is absent and v2 control state exists, the entire command uses legacy `.codex/`; it never mixes roots.
3. Migration is explicit, preview-first, non-destructive, hash-verified, bounded, idempotent, and source-preserving.
4. A common role catalog and common prompt generate one selected host's native profiles.
5. Portable model policy names capability tiers and reasoning effort. Concrete provider/model mapping comes only from a sourced runtime manifest.
6. Native execution is a separate claim. L4 needs an exact fingerprinted execution receipt.
7. Skill preparation selects a host-native project Skill directory. Automatic MCP rendering remains Codex-only until each additional host renderer is verified.
8. Evolution candidates remain local, review-required, and non-executing under whichever control root is active.

## Consequences

- v2 projects remain usable before migration.
- Core code can reason about one control root while host adapters evolve independently.
- Four profile formats can be contract-tested without falsely claiming that all four hosts ran a native session.
- Users must provide or capture trustworthy model inventory evidence; the system cannot infer subscriptions or provider catalogs.
- Multi-host projects need an explicit ownership decision; generating multiple native trees is not proof they share session state.

## Rejected alternatives

- Continue using `.codex/` for portable state: leaks one host into every project and collides with Codex-native configuration.
- Copy Codex TOML semantics to other hosts: fields and permission models are not equivalent.
- Hard-code one vendor model per role: breaks runtime availability, pricing, provider, and task-risk routing.
- Auto-migrate/delete `.codex/`: risks loss of recovery and evidence lineage.
- Call generated profiles “fully supported”: confuses configuration with runtime execution.
