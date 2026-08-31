# Platform-neutral model routing

Route per Task Package, never permanently per role. The portable policy decides required capability and reasoning; a selected platform resolves those logical requirements to a concrete provider/model from verified runtime evidence.

## Logical capability tiers

`ECONOMY < STANDARD < ADVANCED < EXPERT < EXCEPTIONAL`

- Economy: bounded extraction, scanning, classification, and mechanical low-risk work.
- Standard: routine analysis, documentation, and narrow implementation.
- Advanced: normal professional implementation/design with moderate ambiguity.
- Expert: architecture, security, permissions, migrations, concurrency, high-impact QA, or repeated valid reasoning failure.
- Exceptional: rare, explicitly escalated work after schema conflict, high-impact ambiguity, or repeated valid failure; never the default.

Large-review examples: repository inventory/manifest classification may use Economy; ordinary module review, finding triage, repair and re-review use Advanced at normal risk; cross-module contracts and security/permission/migration review require Expert. Actual provider/model selection still comes only from verified host runtime evidence.

Reasoning effort is a separate requirement: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or `ultra`. A provider mapping may expose only a subset.

## Evidence chain

1. `platform detect` proves only an executable/version probe.
2. A runtime manifest records platform, executable evidence, model inventory source, model IDs, providers, tiers, and supported efforts.
3. `--models-verified` requires an explicit file and evidence source; an unverified declaration cannot authorize a high-risk route.
4. `model-resolve` selects the lowest available model meeting or exceeding the requested tier and, where required, the exact reasoning effort.
5. A Task Package records platform, provider, selected model, reasoning, policy versions, risks, and `actual_model_attested: false` before launch.
6. A real host execution receipt separately attests actual provider/model/reasoning/runtime; only then can platform compatibility reach L4.

For policy `2.0.0`, `task` and `preflight` reject the legacy `--available-model` override. Without a currently valid manifest, the generated route is `BLOCKED_RUNTIME_MANIFEST_REQUIRED` with unresolved platform/provider/model fields. This prevents a caller-supplied vendor slug from being promoted into verified runtime evidence.

## Risk floors

Security, privacy, financial/payment, compliance, production, migration, permissions, irreversible change, regulated work, and AI-safety flags are high-risk. High-risk resolution requires verified executable and model inventory evidence and cannot silently bind a missing reasoning level.

If no model meets the floor, return `BLOCKED_MODEL_UNAVAILABLE`. If the runtime or inventory is unverified for high risk, return `BLOCKED_UNVERIFIED_HIGH_RISK_RUNTIME`. If the selected model cannot bind the required effort, return `BLOCKED_REASONING_EFFORT_UNAVAILABLE`.

## Failure escalation

Classify failure before escalation:

- quality/reasoning failure: increase reasoning within the current capability when supported, then raise capability tier;
- context-limit failure: narrow the task, improve inputs, or split the package before model escalation;
- network, authentication, permission, missing input, unavailable tool, quota, or rate limit: fix the environment or block; do not spend a model escalation;
- incorrect problem or acceptance contract: route back to the responsible upstream role, not to a stronger implementation model.

Escalation is bounded by policy attempts and must preserve failure evidence. A later lower route needs a new, genuinely narrower/lower-risk Task Package; never rewrite a failed high-risk route in place.

## v2 Codex compatibility

Unmigrated v2 Codex projects retain policy `1.2.0`, the legacy `--available-model` snapshot input, and its Luna/Terra/Sol mapping. v3 accepts that exact policy for backward compatibility. Those slugs are not portable defaults and must not appear in platform-neutral policy `2.0.0` or other providers' role files.
