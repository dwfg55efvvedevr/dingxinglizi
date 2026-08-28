# Platform adapters and compatibility evidence

The portable core owns business documents, lifecycle, role/model routing, Task Packages, run recovery, evidence, QA, and supervised improvement. Native platform directories contain generated host profiles only; they are never project truth.

## Supported adapters

| Platform | Native Agent format | Project Agent directory | Topology enforcement |
|---|---|---|---|
| Codex | TOML with `name`, `description`, `developer_instructions` | `.codex/agents/` | shared contract plus Orchestrator dispatch gate |
| Cursor | Markdown/YAML with `name`, `description`, `model: inherit`, `readonly` | `.cursor/agents/` | host read-only flag plus shared contract |
| Claude Code | Markdown/YAML with `name`, `description`, `model`, `permissionMode`, `disallowedTools` | `.claude/agents/` | non-delegating roles deny the Agent tool |
| OpenCode V1 | Markdown/YAML with `description`, `mode`, singular `permission` | `.opencode/agents/` | `permission.task` deny-by-default delegation map |
| OpenCode V2 | Markdown/YAML with `description`, `mode`, ordered `permissions` | `.opencode/agents/` | `subagent` deny-all followed by exact allow rules |

The control plane validates exactly one Orchestrator, Orchestrator-to-professional delegation, Engineering Lead-to-Worker delegation, no Worker delegation, and separate Engineering Lead/final QA execution. Host-native permissions reinforce those rules only where the host exposes the required controls; Codex, Cursor, and Claude Code still rely partly on generated contracts and dispatch gates rather than an identical native sandbox.

Primary format references:

- [OpenAI Codex Skills](https://developers.openai.com/codex/skills/)
- [Cursor Skills](https://cursor.com/docs/context/skills)
- [Cursor Subagents](https://cursor.com/docs/agent/subagents)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code model configuration](https://code.claude.com/docs/en/model-config)
- [OpenCode Skills](https://opencode.ai/docs/skills/)
- [OpenCode Agents](https://opencode.ai/docs/agents/)
- [OpenCode V2 permissions](https://opencode.ai/v2/docs/permissions/)
- [OpenCode V2 agents](https://opencode.ai/v2/docs/agents/)

Adapter fields are intentionally minimal. Do not add a field merely because another platform supports a similarly named option.

OpenCode V1 and V2 are separate schemas, not aliases. `auto` parses the installed runtime's semantic major version and selects only 1.x or 2.x. With no runtime, an unparseable version, or an unknown/future major version, rendering, installation, and doctor fail closed and require a verified adapter update or explicit supported schema. Offline CI and packaging therefore pass `--opencode-schema v2` explicitly. V2 rules are ordered: a broad `subagent` deny precedes exact role allow rules so the last matching rule preserves the Orchestrator/Engineering Lead tree. Read-only OpenCode review roles deny both mutation tools and shell execution (`edit` + V1 `bash` / V2 `shell`); command-running tests must be delegated to a bounded Test Worker or other write-separated runner and returned as immutable evidence.

## Install and render

`platform install` copies the portable Skill plus one platform's generated roles at user or project scope. It is preview-only unless `--apply` is supplied, non-overwriting unless `--update` is supplied, and performs no network, authentication, credential, or package-manager operation.

`platform render PROJECT --platform PLATFORM` only renders the selected platform's project Agent profiles. It is useful when the portable Skill already exists and only project profiles are needed.

`platform doctor` is diagnostic by default: L1 or above returns success. Automation should pass `--require-level L2`, `L3`, or `L4` so a lower compatibility level returns exit code 3 instead of being mistaken for the intended target.

Never interpret an installed file as a loaded Skill. Start or refresh the host, inspect its actual discovery surface, and record runtime evidence.

## Compatibility levels

- `L0`: portable package unavailable.
- `L1`: Skill structurally discoverable.
- `L2`: portable workflow, documents, scripts, and assets available.
- `L3`: native profiles match the generator, runtime executable is verified, and an explicitly sourced verified model inventory is available.
- `L4`: L3 plus a local native-execution declaration whose exact schema/fingerprint and execution facts cross-check against verified runtime/model inventory.

An L4 receipt must match `assets/platforms/common/execution-receipt.template.json`, use a canonical role and safe task ID, record provider/model/reasoning/runtime/source/time, declare `VERIFIED_RUNTIME`, and carry the canonical SHA-256 fingerprint. Its provider/model must be in the verified inventory, reasoning must be supported by that entry, and runtime version must equal the verified probe. Editing it after fingerprinting invalidates it.

The receipt and manifest are unsigned local records. These checks detect malformed or inconsistent claims; they do not independently prove that a process ran and cannot resist a coherent rewrite by an actor with full local write access. Use host-signed evidence or an independently controlled audit system when stronger assurance is required.

Rendered profiles and fixture tests can prove L1/L2 contract behavior. They cannot prove authentication, subscription access, model availability, cloud/local parity, native launch, or actual model use.

## Platform detection

`platform detect` looks up known executables and executes `--version` with a bounded timeout. Detection proves only that an executable responded. It does not prove login or model access. Automatic selection occurs only when exactly one supported executable is found; otherwise select explicitly.

## Model inventory

`platform runtime-manifest` never invents a model list. `--models-verified` requires both an existing JSON inventory and a named evidence source. Every load re-probes the current executable/version and re-reads, hashes, and normalizes the bound inventory source. A manifest older than 24 hours, a missing/changed source, future timestamp, schema drift, or probe mismatch fails closed. Verification records the stated source, not a native launch. A consistent receipt upgrades the local compatibility claim, not the cryptographic assurance level.

## MCP boundary

The portable workflow can request MCP capability on all hosts, but host configuration formats and authorization flows differ. The current automatic renderer is intentionally limited to a managed, credential-free, read-only Codex HTTPS MCP block. Other hosts require their official configuration flow and a fresh runtime verification. Never write Codex TOML into another host to simulate compatibility.
