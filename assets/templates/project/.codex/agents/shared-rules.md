# Shared role rules

These rules apply to every professional Agent and temporary Worker in this project.

1. Read the effective `AGENTS.md`, `docs/project-status.json`, `docs/00-project-context.md`, `docs/01-domain-rules.md`, `docs/02-glossary.md`, current task package, and approved upstream documents before acting.
2. Project documents are shared memory. Do not rely on session memory as the only source of business facts. Treat unrecorded chat as input until it is written to the proper document.
3. Classify facts as `CONFIRMED`, `EVIDENCE_INFERRED`, `DEFAULT_ASSUMPTION`, `NOT_APPLICABLE`, or `BLOCKING_UNKNOWN`. Never make a silent assumption that changes scope, priority, business rules, permissions, compliance, licensing, acceptance, or irreversible behavior.
4. Stay inside your role, task objective, allowed files, and external-action authority. One Agent owns each shared mutable file at a time. Report conflicts and deviations to Orchestrator.
5. Only Orchestrator coordinates professional Agents. Engineering Lead may coordinate implementation Workers only. Workers may not create Agents. Other roles do not create or manage Agents.
5a. A profile being installed does not make it active. You may run only when the current role plan lists you in `required_now`; exit after your handoff is persisted and file ownership is released. Reviewers activate only after owner handoff.
6. Engineering Lead and final QA must be separate Agents or sessions. Self-tests are evidence, not independent acceptance.
7. Do not claim completion without linked evidence. Never use unregistered TODO/FIXME, fake buttons, fake success states, placeholder workflows, fabricated responses, or fake data as completion.
8. Return inputs checked, artifacts/changes, evidence/tests, assumptions/risks, and decisions/downstream work. Ordinary roles use `COMPLETE`, `NEEDS_REVISION`, or `BLOCKED`; independent QA uses `PASS`, `PASS_WITH_ACCEPTED_RISKS`, `FAIL`, or `BLOCKED`; Quality Governor uses `PASS`, `CHALLENGE`, or `BLOCKED`.
9. Ask for explicit authority before production/live writes, credentials or sensitive data, purchases, external/customer messages, public release, destructive actions, irreversible migrations, or changes to agreed scope/budget/deadline.
10. MCP/connectors are optional and least-privileged. Never fabricate tool results when a connector is missing.
11. Read the Task Package `execution_profile`. Do not override its model, reasoning effort, attempts, risk flags, capability tier, or downgrade rule. A runtime mismatch returns to Orchestrator.
12. Declare capability needs in the Task Package. Only Orchestrator may discover, catalog, download, install, authenticate, lock, or configure Skills/MCP. Workers and professional Agents must not modify `.agents/skills`, `.codex/config.toml`, or `.codex/orchestration/`.
13. Include `run_id`, `task_id`, attempt number, and evidence references in every handoff. Only Orchestrator writes the global run ledger; return sanitized evidence to it instead of editing `.codex/runs/` directly.
