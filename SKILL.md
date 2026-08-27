---
name: software-project-orchestrator
description: Initialize, route, govern, and verify multi-agent software projects from discovery through independent QA. Use for new products, major modules, or substantial cross-stack iterations that need shared project facts, dynamic Simple/Standard/Complex role selection, product-completeness gates, task packages, defect routing, and evidence-based completion. Do not use for a small isolated fix or ordinary code review that does not need project orchestration.
---

# Software Project Orchestrator

Operate one project delivery system in which the Skill owns workflow, Custom Agents own professional roles, the project `AGENTS.md` owns durable operating rules, project documents own business facts, and MCP supplies optional external capabilities. Never make an MCP server a prerequisite for the core workflow.

## Start or resume

1. Read the nearest effective `AGENTS.md` and inspect existing project documents before creating anything.
2. Resolve bundled script paths relative to this Skill directory. If the project has not been initialized, run `python3 scripts/init_project.py PROJECT_DIR --project-name "NAME" --domain "DOMAIN"`. Do not overwrite an existing project contract; merge compatible rules manually and preserve stricter rules.
3. Read `docs/00-project-context.md`, `01-domain-rules.md`, `02-glossary.md`, `04-prd.md`, `docs/project-status.json`, the current task package, and any approved stage-specific documents. Treat chat history as non-authoritative until a decision is written back.
4. Classify material facts as `CONFIRMED`, `EVIDENCE_INFERRED`, `DEFAULT_ASSUMPTION`, `NOT_APPLICABLE`, or `BLOCKING_UNKNOWN`. Ask only for unknowns that would make a safe, testable result diverge materially.
5. Choose `Simple`, `Standard`, or `Complex` using [complexity-routing.md](references/complexity-routing.md). Use the smallest role set that preserves independent final QA.
6. Build or refresh a task package with `python3 scripts/create_task_package.py PROJECT_DIR --task-id TASK-001 --owner ROLE --reviewer ROLE --objective "..."`.

## Orchestration constraints

- Keep exactly one Orchestrator responsible for global scheduling, state, conflicts, gates, and final synthesis.
- Only the Orchestrator may coordinate all professional Agents. Engineering Lead may coordinate only temporary implementation Workers. Other roles must return artifacts and findings to the Orchestrator.
- A Worker may not spawn another Agent. Give every Worker a bounded objective, owned files, acceptance criteria, and return target.
- Keep one writer per shared mutable file. Parallelize independent read-heavy audit, exploration, design, architecture, and QA work only when file ownership is disjoint.
- Development and final QA must be different sessions or Agents at every complexity level.
- Require every delegated role to read project documents; never rely on inherited session memory as the only business context.

Read [role-contracts.md](references/role-contracts.md) before assigning or changing roles. Project-ready Custom Agent configurations are in `assets/templates/project/.codex/agents/` and are copied during initialization.

## Lifecycle and gates

Use this canonical state sequence:

`BACKLOG → DISCOVERY → REQUIREMENTS_APPROVED → PRODUCT_APPROVED → (UX_READY and UI_READY) + ARCHITECTURE_READY → READY_FOR_BUILD → IN_DEVELOPMENT → CODE_REVIEW → READY_FOR_QA → QA_PASS → RELEASE_READY → DONE`

`BLOCKED` and `REWORK_REQUIREMENTS`, `REWORK_PRODUCT`, `REWORK_UX`, `REWORK_UI`, `REWORK_ARCHITECTURE`, `REWORK_ENGINEERING`, or `REWORK_QA` may interrupt the main path. Restore the previous valid gate only after the documented re-entry condition has evidence.

Before changing a stage, read [workflow-gates.md](references/workflow-gates.md) and run:

```bash
python3 scripts/validate_documents.py PROJECT_DIR
python3 scripts/check_missing_modules.py PROJECT_DIR
python3 scripts/check_traceability.py PROJECT_DIR
python3 scripts/check_project_status.py PROJECT_DIR --target READY_FOR_BUILD
```

Do not enter `READY_FOR_BUILD` unless the role-page, page-feature, feature-state, front-office/back-office, permission, and acceptance matrices are complete and the applicable upstream gates are approved. Do not enter `DONE` merely because code exists.

## Stage-specific work

- Discovery or unclear domain: read [document-contract.md](references/document-contract.md) and [domain-adaptation.md](references/domain-adaptation.md).
- Requirements and product completeness: read [product-completeness.md](references/product-completeness.md).
- UX or UI: read [ui-quality.md](references/ui-quality.md).
- Architecture, permissions, APIs, or data: read [architecture-contract.md](references/architecture-contract.md).
- Task decomposition: read [task-packages.md](references/task-packages.md).
- QA, rejection, or rework: read [defect-routing.md](references/defect-routing.md) and [qa-and-completion.md](references/qa-and-completion.md).
- External tools or services: read [mcp-guide.md](references/mcp-guide.md). Grant each role only the minimum tools and access required for its current task.

## Completion contract

Finish only when applicable acceptance criteria have linked evidence, required tests pass, no unaccepted P0/P1 defect remains, project documents and decisions reflect actual behavior, independent QA records `PASS` or an explicitly authorized `PASS_WITH_ACCEPTED_RISKS`, and any release action requiring authorization remains separate. Return the final state, artifacts, evidence, accepted risks, unresolved blockers, and exact next authorization if one is needed.
