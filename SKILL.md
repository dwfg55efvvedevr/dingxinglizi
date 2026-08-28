---
name: software-project-orchestrator
description: Initialize, route, resume, govern, verify, and learn from substantial multi-agent software delivery across Codex, Cursor, Claude Code, and OpenCode. Use for new products, major modules, or cross-stack iterations that need durable business facts, Simple/Standard/Complex routing, on-demand roles, product and architecture gates, governed task packages, platform-aware model and capability routing, recovery, defect routing, evidence-based completion, or supervised project-local improvement candidates. Do not use for a small isolated fix or ordinary code review that does not need project orchestration.
---

# Software Project Orchestrator

Run one evidence-based delivery system: this Skill owns the workflow; Custom Agents own professional responsibilities; the project `AGENTS.md` owns durable rules; project documents own business facts; MCP/connectors provide optional external capability. Do not make MCP a core dependency.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`. Every bundled command below must use the absolute Skill path, `python3 "$SKILL_DIR/scripts/orchestrator.py" ...`, regardless of the current project working directory.

## Choose the entry path

1. Read the nearest effective `AGENTS.md`, then inspect `docs/project-status.json`. Use `.dingxinglizi/` when present; otherwise treat an initialized v2 `.codex/orchestration|runs|evolution` tree as one legacy control root. Never mix roots within one command.
2. New or uninitialized project: detect the host with `platform detect`, then run `python3 "$SKILL_DIR/scripts/orchestrator.py" init PROJECT_DIR --project-name "NAME" --domain "DOMAIN" --complexity Standard --platform PLATFORM`. Use `--domain-pack PACK` only as candidate input; never promote pack content to confirmed project facts.
3. Existing initialized project with no interrupted run: run `python3 "$SKILL_DIR/scripts/orchestrator.py" doctor PROJECT_DIR`, read the authoritative documents, then create the current-stage plan.
4. Existing interrupted run: read [recovery.md](references/recovery.md), run `python3 "$SKILL_DIR/scripts/orchestrator.py" resume PROJECT_DIR`, and obey its decision. Never assume an Agent session survived a restart.
5. Status or evidence request: use `status` or `report`; do not create a new run merely to answer.

Read [platform-adapters.md](references/platform-adapters.md) before installing or claiming host support. Read [migration.md](references/migration.md) before migrating an initialized v1/v2 project. Initialization and migration are non-overwriting; merge one effective project-level `AGENTS.md` without weakening existing rules.

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
2. Before dispatch, verify the active control root's `orchestration/runtime-manifest.json` and runtime capability inventory. A declared model list, installed file, or rendered profile cannot claim runtime availability or actual execution.
3. Create a DRAFT package with `python3 "$SKILL_DIR/scripts/orchestrator.py" task ...`. The generator binds the current open `run_id`; fill business context, inputs, scope, exclusions, deliverables, acceptance criteria, allowed files, validation, evidence locations, capabilities, and return target. Read [task-packages.md](references/task-packages.md).
4. Route model and reasoning per Task Package using [model-routing.md](references/model-routing.md). The portable core chooses a capability tier and reasoning effort; the selected platform resolves provider/model from verified runtime evidence. Do not bind a permanent vendor model in role configuration. A valid reasoning failure raises effort before capability; environment, permission, auth, missing-input, or unavailable-tool failures do not waste a model escalation.
5. Resolve capabilities centrally with [capability-resolution.md](references/capability-resolution.md). Agents may declare needs or candidates, but only Orchestrator may approve, lock, install, authenticate, or configure Skills/MCP.
6. Set a complete reviewed package to `READY_FOR_DISPATCH`, then run `python3 "$SKILL_DIR/scripts/orchestrator.py" preflight PROJECT_DIR tasks/TASK.yaml --record-ready`. Dispatch only when the matching receipt says `READY`.
7. After each persisted handoff or gate decision, run `python3 "$SKILL_DIR/scripts/orchestrator.py" checkpoint PROJECT_DIR --event HANDOFF_PERSISTED --task-id TASK-ID --artifact PATH --evidence PATH`. A completed owner records artifacts and evidence, sets the Task Package to `COMPLETED`, releases ownership, and exits before the reviewer starts.
8. Re-plan with the verified completion package. Never consume a blocked or unverified handoff as completion proof.

## Learn without self-modifying

1. Read [evolution-core.md](references/evolution-core.md) after a substantial accepted delivery, explicit user correction, repeated defect, routing waste, model mismatch, process gap, or security/privacy finding.
2. Treat Evolution as an optional local sidecar. Existing v2 projects remain valid without it; only `python3 "$SKILL_DIR/scripts/orchestrator.py" evolution init PROJECT_DIR` creates it.
3. Before any experience write in a Git project, require the active control root's `evolution/` directory to be ignored and untracked. New v3 uses `.dingxinglizi/evolution/`; unmigrated v2 uses `.codex/evolution/`. Never edit Git state on the user's behalf.
4. Collect only structurally validated `DONE` runs. Record failed or blocked learning as explicit, sanitized, evidence-linked feedback; never rewrite a run to manufacture completion.
5. Generate deterministic retrospectives only from validated local records. Three structurally independent lineages are the ordinary proposal threshold; P0 or `security_or_privacy` feedback may create a high-priority candidate.
6. Keep every proposal and generated eval case `DRAFT` and `REVIEW_REQUIRED`. They cannot alter Skill source, project truth, formal evals, protected gates, Git, external systems, or their own evidence policy.
7. A reviewer may later implement or promote a candidate only through a separate authorized change with independent QA. Do not describe candidate generation as autonomous self-improvement.

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
- Draft Evolution eval candidates are deliberately outside the formal eval suite and never change its pass count.
- The local control plane creates plans, adapters, checks, ledgers, recovery decisions, and reports. It does not claim to authenticate a host, spawn or restore arbitrary native Agent sessions, read account quota, prove a model without runtime evidence, configure unsupported host MCP, bypass authentication, or safely install unknown community code.

Finish by returning final state, artifacts, evidence, tests, accepted risks, unresolved blockers, and the exact next authorization if one remains.
