# Software Project Orchestrator — usage

This folder is a complete reusable Codex Skill. It creates a durable project memory, selects a Simple/Standard/Complex role set, enforces pre-build matrices, generates task packages, routes defects to their source, and requires independent QA evidence before completion.

The architecture is deliberately separated:

| Layer | Responsibility | Location |
|---|---|---|
| Skill | workflow, routing, gates, validation | this Skill folder |
| Custom Agents | professional role behavior | generated project `.codex/agents/` |
| Project `AGENTS.md` | durable operating constraints | generated project root |
| Project documents | business facts, approved baselines, decisions and evidence | generated `docs/`, `tasks/`, `evidence/` |
| MCP/connectors | optional external data/actions | configured separately, only when needed |

## Install or place the Skill

Choose one scope. Copy or symlink the whole `software-project-orchestrator` folder; do not copy only `SKILL.md`.

- Personal, available across projects: `$HOME/.agents/skills/software-project-orchestrator/`
- Repository-specific: `<repository>/.agents/skills/software-project-orchestrator/`

Codex discovers skills from these locations. If it does not appear after copying, restart Codex. This delivery is generated in the workspace only; it is not automatically installed or published.

The Skill keeps the platform default of allowing both automatic matching and explicit invocation. When other orchestration skills have overlapping descriptions, invoke this one explicitly so your intended workflow is unambiguous.

## Invoke it

In Codex, mention:

```text
$software-project-orchestrator initialize this project, collect the business context, classify complexity, and prepare the first approved task package.
```

It may also activate automatically for substantial product/module work that matches the `SKILL.md` description. It should not activate for a small isolated fix or ordinary review.

## Initialize a new project

From the installed Skill folder:

```bash
python3 scripts/init_project.py /path/to/project \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard
```

Preview without writing:

```bash
python3 scripts/init_project.py /path/to/project \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard \
  --dry-run
```

The initializer is non-overwriting. If any target contract file already exists, it stops before writing and lists the conflicts. For an existing repository with an `AGENTS.md` or equivalent documents, preview first, then manually merge compatible missing rules while preserving stricter existing rules. Never replace an effective project contract silently.

Initialization creates:

- the stable `AGENTS.md` contract;
- `docs/00` through `docs/10`, the completeness checklist, status JSON, and decision template;
- `.codex/agents/` with the 8 baseline roles and 5 optional Worker profiles;
- task and evidence templates.

## Inject business background

Fill documents in this order:

1. `docs/00-project-context.md`: one-sentence goal, problem, business model, users, objects, flows, state machines, rules, permissions, money, notifications, operations, scope/non-goals, technical/compliance constraints, success metrics, open questions, and complexity.
2. `docs/01-domain-rules.md`: numbered, testable rules and object lifecycles.
3. `docs/02-glossary.md`: one canonical definition per term.
4. `docs/04-prd.md`: `REQ-*` requirements and acceptance intent.
5. `docs/checklists/product-completeness.md`: every catalog item gets `REQUIRED`, `NOT_APPLICABLE`, or `DEFERRED`, plus `COVERED`, `GAP`, or `BLOCKED`.
6. Build the role-page, page-feature, feature-state, front/back-office, permission, and acceptance matrices.

Use fact states exactly as defined in the templates. `BLOCKING_UNKNOWN` is honest and blocks downstream approval; it is not a failure of the template. Replace it only with sourced facts or authorized reversible defaults.

## Choose or change the Agent team

All role profiles are installed so they are available, but they are not all started for every project.

- `Simple`: Orchestrator, a merged Requirements/Product Lead, Engineering Lead, independent QA. Add UX/UI or Architect only when the work needs them.
- `Standard`: Orchestrator, Requirements, Product Auditor, Design Lead (UX/UI may merge), Technical Lead (Architect/Engineering may merge when moderate risk), independent QA.
- `Complex`: all eight baseline roles, plus only the specialists needed by concrete work packages.

Runtime IDs use underscores: `product_auditor` and `engineering_lead`. Human-facing documents may use Product Auditor and Engineering Lead. Do not create duplicate identities with hyphenated IDs.

To add a specialist, create a narrow `.codex/agents/<name>.toml` using only current supported fields, make it read `.codex/agents/shared-rules.md`, define its unique responsibility and prohibitions, and assign it through Orchestrator. To remove a role from a project run, stop routing tasks to it; do not delete its responsibilities. If roles merge, name who owns every artifact and retain independent QA.

Only Engineering Lead may assign `frontend_worker`, `backend_worker`, `ai_worker`, `data_worker`, or `test_worker`. A Worker task uses `return_to: engineering_lead`, bounded files, and `may_spawn_agents: false`. This is an explicit governance constraint; whether a host can enforce it technically depends on the current Codex runtime.

## Generate a task package

```bash
python3 scripts/create_task_package.py /path/to/project \
  --task-id TASK-001 \
  --owner engineering_lead \
  --reviewer qa \
  --stage READY_FOR_BUILD \
  --objective "Implement the approved customer profile flow"
```

The generator refuses duplicate task IDs and owner/reviewer equality. Fill scope, exclusions, deliverables, allowed files, Given/When/Then acceptance criteria, validation, evidence, risks, and handoff before dispatch.

## Run gates

```bash
python3 scripts/validate_documents.py /path/to/project
python3 scripts/check_missing_modules.py /path/to/project
python3 scripts/check_traceability.py /path/to/project
python3 scripts/check_project_status.py /path/to/project --target READY_FOR_BUILD
```

The initialized scaffold passes structural validation but intentionally fails completeness and traceability until real project facts and matrices are filled. The aggregate status check also requires approved document versions, gate evidence, and zero open P0/P1 items.

Scripts prove structure and traceability, not whether the business decisions are correct. Orchestrator and independent QA remain responsible for semantic review.

## Switch industries

Do not clone the previous domain’s facts or applicability decisions. Keep the workflow and replace the project-specific layers:

- Home services: providers, addresses, scheduling, assignment, service evidence, cancellation, complaints and settlement.
- E-commerce: catalog/SKU, inventory, cart, order, promotion, payment, shipment, refund and after-sales.
- CRM: tenant, lead, account/contact, pipeline, activity, owner, import/export and data scope.
- SaaS: organization, membership, plan, entitlement, subscription, billing, metering, audit and tenant isolation.
- AI Agent: model/provider, prompt/tool policy, retrieval data, run states, human approval, evaluation, cost limits, privacy and uncertainty recovery.

Rebuild the glossary, rules, matrices, completeness disposition, complexity classification, team, architecture and tests for the new domain. Legal, regulatory and IP conclusions remain blocking until an authorized source confirms them.

## MCP is optional

Read `references/mcp-guide.md` when GitHub, Figma, browser automation, Linear/Jira, Obsidian/files, database, or deployment access is useful. The Skill declares no required MCP dependency. Grant tools per role and task, read-only first, and obtain separate authorization for production writes, credentials, sensitive data, external messages, purchases, releases or irreversible actions.

## Approval and DONE defaults

The generated `docs/project-status.json` deliberately leaves approval and risk-acceptance authority as `BLOCKING_UNKNOWN`; set them from the project’s real decision structure. By default, `DONE` means the requested local deliverable is implemented, documented and independently accepted. It does not authorize production deployment or public release.

## Validate the Skill itself

Run from this folder:

```bash
python3 -m unittest discover -s scripts/tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py .
```

The second command uses Codex’s bundled `skill-creator` validator and may require its Python environment. The first command uses only the Python standard library.

Current official references used for the packaging decisions:

- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
