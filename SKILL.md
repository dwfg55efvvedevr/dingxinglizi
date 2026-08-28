---
name: software-project-orchestrator
description: Initialize, route, resume, govern, and verify substantial multi-agent software delivery from discovery through independent QA. Use for new products, major modules, or cross-stack iterations that need durable business facts, Simple/Standard/Complex routing, on-demand roles, product and architecture gates, governed task packages, model and capability routing, recovery, defect routing, and evidence-based completion. Do not use for a small isolated fix or ordinary code review that does not need project orchestration.
---

# Software Project Orchestrator

Run one evidence-based delivery system: this Skill owns the workflow; Custom Agents own professional responsibilities; the project `AGENTS.md` owns durable rules; project documents own business facts; MCP/connectors provide optional external capability. Do not make MCP a core dependency.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`. Every bundled command below must use the absolute Skill path, `python3 "$SKILL_DIR/scripts/orchestrator.py" ...`, regardless of the current project working directory.

## Choose the entry path

1. Read the nearest effective `AGENTS.md`, then inspect `docs/project-status.json` and `.codex/runs/`.
2. New or uninitialized project: run `python3 "$SKILL_DIR/scripts/orchestrator.py" init PROJECT_DIR --project-name "NAME" --domain "DOMAIN" --complexity Standard`. Use `--domain-pack PACK` only as candidate input; never promote pack content to confirmed project facts.
3. Existing initialized project with no interrupted run: run `python3 "$SKILL_DIR/scripts/orchestrator.py" doctor PROJECT_DIR`, read the authoritative documents, then create the current-stage plan.
4. Existing interrupted run: read [recovery.md](references/recovery.md), run `python3 "$SKILL_DIR/scripts/orchestrator.py" resume PROJECT_DIR`, and obey its decision. Never assume an Agent session survived a restart.
5. Status or evidence request: use `status` or `report`; do not create a new run merely to answer.

Read [migration.md](references/migration.md) before changing an initialized v1.x project. Initialization is non-overwriting; merge one effective project-level `AGENTS.md` without weakening existing rules.

## Establish project truth

1. Read `docs/00-project-context.md`, `01-domain-rules.md`, `02-glossary.md`, `04-prd.md`, `docs/project-status.json`, the current task package, and approved stage documents. Chat history is input, not authoritative memory.
2. Classify material statements as `CONFIRMED`, `EVIDENCE_INFERRED`, `DEFAULT_ASSUMPTION`, `NOT_APPLICABLE`, or `BLOCKING_UNKNOWN`.
3. Ask only for an unknown that would materially change scope, safety, acceptance, compliance, licensing, money, permissions, or an irreversible decision. Record reversible defaults instead of interrupting repeatedly.
4. Requirements maintains business facts, but every role reads them from project documents.
5. Read [document-contract.md](references/document-contract.md) for the document precedence, version, approval, and decision rules. For a new industry, read [domain-adaptation.md](references/domain-adaptation.md) and optionally [domain-packs.md](references/domain-packs.md).

## Route only the current work

1. Choose `Simple`, `Standard`, or `Complex` with [complexity-routing.md](references/complexity-routing.md). Complexity describes lifecycle responsibilities, not the number of Agents to launch.
2. Read [on-demand-role-routing.md](references/on-demand-role-routing.md), persist a validated stage change with `transition` when needed, then preview with `python3 "$SKILL_DIR/scripts/orchestrator.py" plan PROJECT_DIR --quota economy`. Omit `--stage` in the normal flow so the plan cannot drift from persisted lifecycle state.
3. Persist with `--write` only after inputs are accurate. Activate only `required_now`, in `execution_waves`; profiles on disk are inactive capabilities.
4. Keep Orchestrator in the main thread. Default to one active subagent; allow two only for a generated two-role read-only wave, or Engineering Lead plus one governed Worker.
5. Only Orchestrator coordinates professional Agents. Engineering Lead may coordinate temporary frontend/backend/AI/data/test Workers. Workers never create Agents.
6. Development and final QA must be different Agents or sessions at every complexity level.
7. Read [role-contracts.md](references/role-contracts.md) before assigning or merging roles.

## Govern a run and Task Packages

1. Run `python3 "$SKILL_DIR/scripts/orchestrator.py" run PROJECT_DIR` once to create the project-local ledger. Read [run-ledger.md](references/run-ledger.md). Orchestrator is its sole writer.
2. Before dispatch, verify the actual runtime inventory in `.codex/orchestration/runtime-inventory.json`. A model route cannot claim availability from a static assumption.
3. Create a DRAFT package with `python3 "$SKILL_DIR/scripts/orchestrator.py" task ...`. The generator binds the current open `run_id`; fill business context, inputs, scope, exclusions, deliverables, acceptance criteria, allowed files, validation, evidence locations, capabilities, and return target. Read [task-packages.md](references/task-packages.md).
4. Route model and reasoning per Task Package using [model-routing.md](references/model-routing.md). Do not bind a permanent model in role TOML. A valid reasoning failure raises effort before capability; environment, permission, auth, missing-input, or unavailable-tool failures do not waste a model escalation.
5. Resolve capabilities centrally with [capability-resolution.md](references/capability-resolution.md). Agents may declare needs or candidates, but only Orchestrator may approve, lock, install, authenticate, or configure Skills/MCP.
6. Set a complete reviewed package to `READY_FOR_DISPATCH`, then run `python3 "$SKILL_DIR/scripts/orchestrator.py" preflight PROJECT_DIR tasks/TASK.yaml --record-ready`. Dispatch only when the matching receipt says `READY`.
7. After each persisted handoff or gate decision, run `python3 "$SKILL_DIR/scripts/orchestrator.py" checkpoint PROJECT_DIR --event HANDOFF_PERSISTED --task-id TASK-ID --artifact PATH --evidence PATH`. A completed owner records artifacts and evidence, sets the Task Package to `COMPLETED`, releases ownership, and exits before the reviewer starts.
8. Re-plan with the verified completion package. Never consume a blocked or unverified handoff as completion proof.

## Enforce product and release gates

Use the canonical lifecycle:

`BACKLOG → DISCOVERY → REQUIREMENTS_APPROVED → PRODUCT_APPROVED → (UX_READY and UI_READY) + ARCHITECTURE_READY → READY_FOR_BUILD → IN_DEVELOPMENT → CODE_REVIEW → READY_FOR_QA → QA_PASS → RELEASE_READY → DONE`

Interrupt with `BLOCKED` or the appropriate `REWORK_REQUIREMENTS`, `REWORK_PRODUCT`, `REWORK_UX`, `REWORK_UI`, `REWORK_ARCHITECTURE`, `REWORK_ENGINEERING`, or `REWORK_QA`. Restore a gate only after its documented re-entry evidence exists.

- Before changing a stage, read [workflow-gates.md](references/workflow-gates.md) and run `python3 "$SKILL_DIR/scripts/orchestrator.py" transition PROJECT_DIR --target TARGET_STATE`; the command validates the gate before persisting. `BLOCKED` and `REWORK_*` still require their structured reason/defect records.
- Do not enter `READY_FOR_BUILD` without approved role-page, page-feature, feature-state, front/back-office, permission, and acceptance matrices.
- Read [product-completeness.md](references/product-completeness.md) for requirements/product review, [ui-quality.md](references/ui-quality.md) for UX/UI, and [architecture-contract.md](references/architecture-contract.md) for API/data/permission work.
- Use [product-thinking-kernel.md](references/product-thinking-kernel.md) for product decisions. Load [product-lenses.md](references/product-lenses.md) only for a matching trigger.
- Complete the lightweight Problem, Solution, and Release Evidence checks. Invoke the read-only Quality Governor only when [quality-governance.md](references/quality-governance.md) and the role plan require an independent challenge.
- Route defects to the earliest responsibility source using [defect-routing.md](references/defect-routing.md).
- Do not enter `DONE` without [qa-and-completion.md](references/qa-and-completion.md): independent QA evidence, no unaccepted P0/P1 defect, accurate project documents, and explicit accepted risks.

## Boundaries and evaluation

- Read [automation-boundaries.md](references/automation-boundaries.md) before auth, credentials, permissions, downloads, production, external messages, purchases, releases, destructive actions, or irreversible migrations.
- Read [mcp-guide.md](references/mcp-guide.md) only when an external system is needed; grant least privilege per current task.
- Run `python3 "$SKILL_DIR/scripts/orchestrator.py" eval` after changing routing policy or recovery behavior. Read [evaluation.md](references/evaluation.md). Offline evals prove deterministic policy behavior, not Agent intelligence or end-to-end product quality.
- The local control plane creates plans, checks, ledgers, recovery decisions, and reports. It does not claim to spawn or restore Codex Agent sessions, read account quota, bypass authentication, or safely install unknown community code.

Finish by returning final state, artifacts, evidence, tests, accepted risks, unresolved blockers, and the exact next authorization if one remains.
