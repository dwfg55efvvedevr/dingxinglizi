# Automation boundaries

“Fully automated” in this Skill means that routine orchestration proceeds without asking the user to choose roles, models, reasoning effort or already approved capabilities. It does not mean bypassing trust, authentication, payment, release or destructive-action authority.

## Automatic path

`DISCOVER_CONTEXT → CLASSIFY_COMPLEXITY → SELECT_ROLES → CREATE_TASK → ROUTE_MODEL → RESOLVE_CAPABILITIES → SPAWN_WITH_EXPLICIT_ROUTE → VALIDATE → CLASSIFY_FAILURE → RETRY_OR_ESCALATE → INDEPENDENT_QA`

No user prompt is needed when facts are sufficient, the task is reversible and in scope, the model is available, capabilities are already installed or safely allowlisted, no credentials are needed, and acceptance is testable.

## Pause states

- `BLOCKED_CONTEXT`: a business fact would materially change the solution.
- `BLOCKED_MODEL_UNAVAILABLE`: the required model floor is unavailable.
- `BLOCKED_UNVERIFIED_HIGH_RISK_RUNTIME`: high-risk runtime or model inventory lacks evidence.
- `BLOCKED_REASONING_EFFORT_UNAVAILABLE`: the verified model cannot bind the required reasoning level.
- `BLOCKED_DISCOVERY` or `BLOCKED_TRUST`: no approved capability candidate exists.
- `BLOCKED_AUTH`: OAuth, a credential or an external account is required.
- `BLOCKED_PERMISSION`: the capability exceeds the task's permission ceiling.
- `BLOCKED_LICENSE`: the license is not approved.
- `BLOCKED_PROVISIONING`: download, hash, archive or configuration validation failed.
- `ROUTE_MISMATCH`: the runtime launch differs from the approved Task Package route.
- `BLOCKED_ATTEMPTS_EXHAUSTED`: bounded retries are exhausted.

Each pause must report the exact missing authority or corrective action. Do not convert it to success, fabricate a connector result, or silently broaden access.

Agents may recommend or discover capabilities, but only the Orchestrator modifies the catalog, trust policy, lock or MCP managed configuration. Engineering Lead may request capabilities for Workers; Workers cannot provision capabilities or spawn Agents.

## What the v3 control plane does not claim

The local Python CLI deterministically prepares plans, native adapters, Task Packages, validation results, run ledgers, recovery decisions, domain-pack locks, offline evaluations, and reports. The selected host performs actual Agent dispatch and session management. The CLI cannot authenticate a host, read remaining account quota, prove a model without runtime evidence, restore an interrupted native session, configure unsupported host MCP, bypass OAuth/credentials, or determine that unknown downloaded code is trustworthy.

Evolution Core adds local evidence aggregation, deterministic retrospectives, and review-required improvement/eval candidates. It does not self-edit, run semantic learning, establish causality, prove an improvement, promote a test, change protected gates, use Git, publish, or deploy. “Fully automated” never includes applying an Evolution candidate.

On interruption, use [recovery.md](recovery.md). Never translate a stale session record into permission to launch a duplicate Agent.
