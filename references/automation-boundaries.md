# Automation boundaries

“Fully automated” in this Skill means that routine orchestration proceeds without asking the user to choose roles, models, reasoning effort or already approved capabilities. It does not mean bypassing trust, authentication, payment, release or destructive-action authority.

## Automatic path

`DISCOVER_CONTEXT → CLASSIFY_COMPLEXITY → SELECT_ROLES → CREATE_TASK → ROUTE_MODEL → RESOLVE_CAPABILITIES → SPAWN_WITH_EXPLICIT_ROUTE → VALIDATE → CLASSIFY_FAILURE → RETRY_OR_ESCALATE → INDEPENDENT_QA`

No user prompt is needed when facts are sufficient, the task is reversible and in scope, the model is available, capabilities are already installed or safely allowlisted, no credentials are needed, and acceptance is testable.

## Pause states

- `BLOCKED_CONTEXT`: a business fact would materially change the solution.
- `BLOCKED_MODEL_UNAVAILABLE`: the required model floor is unavailable.
- `BLOCKED_DISCOVERY` or `BLOCKED_TRUST`: no approved capability candidate exists.
- `BLOCKED_AUTH`: OAuth, a credential or an external account is required.
- `BLOCKED_PERMISSION`: the capability exceeds the task's permission ceiling.
- `BLOCKED_LICENSE`: the license is not approved.
- `BLOCKED_PROVISIONING`: download, hash, archive or configuration validation failed.
- `ROUTE_MISMATCH`: the runtime launch differs from the approved Task Package route.
- `BLOCKED_ATTEMPTS_EXHAUSTED`: bounded retries are exhausted.

Each pause must report the exact missing authority or corrective action. Do not convert it to success, fabricate a connector result, or silently broaden access.

Agents may recommend or discover capabilities, but only the Orchestrator modifies the catalog, trust policy, lock or MCP managed configuration. Engineering Lead may request capabilities for Workers; Workers cannot provision capabilities or spawn Agents.
