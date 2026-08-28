# Software Project Orchestrator v3.0.0

`dingxinglizi` v3.0 makes the stable `$software-project-orchestrator` workflow portable across Codex, Cursor, Claude Code, and OpenCode without pretending that those hosts have identical capabilities.

## Highlights

- Platform-neutral project control state under `.dingxinglizi/` for new projects.
- Non-destructive, hash-verified, idempotent migration from v2 `.codex` state; unmigrated v2 projects remain usable.
- Native role profile generation for Codex TOML and Cursor, Claude Code, and OpenCode Markdown/frontmatter formats.
- Separate OpenCode V1 and V2 renderers: V1 uses `permission.task`, V2 uses ordered `permissions/subagent`; automatic selection accepts only a parseable installed 1.x/2.x runtime and unknown versions fail closed.
- One Orchestrator topology, Engineering Lead → implementation Worker delegation only, no Worker delegation, and independent final QA.
- Preview-first user/project installer that selects one platform, carries the MIT license, refuses conflicts and symlink/hard-link escapes, and performs no network, authentication, credential, or package-manager action.
- Platform detection, adapter rendering, L0–L4 doctor, runtime manifest capture, provider/model resolution, and fingerprinted execution receipts.
- Provider-neutral capability tiers and reasoning effort, resolved only after fresh host re-probe and revalidation of explicitly sourced, hash-bound model inventory evidence.
- High-risk fail-closed behavior when runtime, model floor, or reasoning support is unverified.
- v3 rejects the legacy `--available-model` override; a missing runtime manifest yields an unresolved, blocked provider-neutral route instead of a Codex fallback.
- Project-local supervised Evolution Core retained under the active v2/v3 control directory; candidates remain review-required and non-executable.

## Compatibility claims

All four adapters have automated schema, rendering, topology, path safety, and control-contract tests. The release host detected and probed Codex CLI. Cursor, Claude Code, and OpenCode were not available for native launch testing on that host, so this release does not claim L4 for them. L4 requires a local execution declaration whose schema/fingerprint and provider/model/reasoning/runtime facts match verified inventory; it is still unsigned local evidence, not cryptographic proof.

## Install

```bash
git clone --branch v3.0.0 https://github.com/lizi-product-studio/dingxinglizi.git /tmp/dingxinglizi
cd /tmp/dingxinglizi
python3 scripts/orchestrator.py platform detect
python3 scripts/orchestrator.py platform install --platform codex --scope user
python3 scripts/orchestrator.py platform install --platform codex --scope user --apply
```

Replace `codex` with `cursor` or `claude-code` to install only that adapter. For an offline OpenCode install, use `--platform opencode --opencode-schema v1` or `v2`; an installed, parseable 1.x/2.x runtime may use automatic selection. Existing files are not overwritten unless `--update` is explicit.

## Upgrade from v2

The v3 Skill can operate an existing v2 project in place. Optional migration:

```bash
python3 scripts/orchestrator.py migrate /path/to/project
python3 scripts/orchestrator.py migrate /path/to/project --apply
```

The first command is a preview. The applied migration copies verified state to `.dingxinglizi/` and leaves `.codex/` unchanged.

## Honest limits

The control plane generates and validates contracts; it does not itself authenticate hosts, start or restore arbitrary native Agent sessions, guarantee model availability, infer account quota, configure non-Codex MCP hosts, or trust unknown community code. Runtime claims require runtime evidence. Production, credentials, external writes, public release, purchases, and destructive changes remain separately authorized actions.
