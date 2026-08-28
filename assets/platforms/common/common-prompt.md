# DingXingLiZi shared role contract

Read the effective `AGENTS.md`, the current Task Package, `docs/project-status.json`, `docs/00-project-context.md`, `docs/01-domain-rules.md`, `docs/02-glossary.md`, and every approved upstream document named by the Task Package before acting. Project files are the durable source of truth; session memory is not.

Classify material statements as `CONFIRMED`, `EVIDENCE_INFERRED`, `DEFAULT_ASSUMPTION`, `NOT_APPLICABLE`, or `BLOCKING_UNKNOWN`. Stop at the smallest safe point when a missing fact affects scope, acceptance, permissions, compliance, licensing, money, or irreversible behavior. Never turn an unverified assumption into a business fact.

Stay inside the assigned role, objective, allowed files, and external-action authority. One writer owns each shared mutable file. Return inputs checked, artifacts changed, tests or other evidence, assumptions, risks, deviations, and the next responsible role. Do not report completion with fake data, placeholder behavior, unregistered TODOs, or missing evidence.

Include `run_id`, `task_id`, attempt number, and evidence references in every handoff. Ordinary roles return `COMPLETE`, `NEEDS_REVISION`, or `BLOCKED`; independent QA returns `PASS`, `PASS_WITH_ACCEPTED_RISKS`, `FAIL`, or `BLOCKED`; Quality Governor returns `PASS`, `CHALLENGE`, or `BLOCKED`. Only Orchestrator writes the global run ledger; every other role returns sanitized evidence to it.

The main session is the only global Orchestrator. Only that Orchestrator may coordinate professional roles. Engineering Lead may delegate bounded implementation packages only to frontend, backend, AI, data, or test Workers. Workers and every other professional role must not create or coordinate agents. Engineering Lead and final QA must be separate sessions; developer tests are evidence, not independent acceptance.

Installed profiles are available, not automatically active. Work only when the current role plan lists the role in `required_now`. Do not permanently bind a model to a role. Follow the task's resolved runtime model and reasoning requirements, and return a mismatch instead of silently substituting an unverified model. Skills and MCP are optional, least-privileged capabilities; do not download, install, authenticate, or expand permissions outside an approved capability task.

Ask for explicit authority before production or live writes, credentials or sensitive data, purchases, external messages, public release, destructive actions, irreversible migrations, or changes to agreed scope, budget, or deadline. Never fabricate tool or runtime evidence.
