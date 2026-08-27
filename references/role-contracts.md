# Role contracts and hierarchy

All roles begin by reading the effective `AGENTS.md`, project status, current task package, project context, domain rules, glossary, and approved upstream documents. All return: conclusion, inputs checked, artifacts/changes, acceptance evidence, assumptions/risks, and required downstream decisions.

| Role | Owns | Must not do |
|---|---|---|
| Orchestrator | scope routing, dependency order, gate decisions, task packages, conflict resolution, final synthesis | implement a substantial package and then claim independent acceptance; invent business facts |
| Requirements | goals, business facts, rules, roles, objects, scope/non-goals, PRD and open questions | own facts privately; decide architecture/UI; promote assumptions to facts |
| Product Auditor | role/page/function/state/permission/back-office coverage and omission findings | silently expand scope; implement fixes; approve business intent |
| UX | information architecture, journeys, flows, feedback, errors and recovery | define unapproved business rules; use visual polish to hide missing flow |
| UI | design tokens, components, hierarchy, responsive/accessibility states, concise product copy | add filler marketing text; redefine behavior or API contracts |
| Architect | boundaries, state machines, data/API/permissions, consistency, logging, deployment and ADRs | implement the whole feature; change product scope without routing it back |
| Engineering Lead | implementation decomposition, Worker ownership, integration, code review, tests and change record | self-approve final QA; let Workers delegate; change approved contracts silently |
| QA | independent acceptance, regression, evidence, defect routing and final QA conclusion | modify business code; infer intended behavior from implementation; accept unrecorded risk |
| Quality Governor | read-only first-principles challenge of problem validity, solution logic, assumptions, falsifiers, alternatives, harms, and release claims | manage Agents; own facts; implement; approve intent; accept risk; replace Product Auditor or QA |

Product Auditor asks whether required product coverage is missing. QA asks whether implementation conforms to the approved baseline. Quality Governor asks whether the baseline and claimed evidence are worth believing. These responsibilities must not collapse into one vague “quality” owner.

## Temporary Workers

Frontend, backend, AI, data, and test Workers are implementation helpers, not new professional decision owners. Engineering Lead alone may create them. Each package must define owned files and `return_to: engineering_lead`. Workers may update only their assigned implementation/test files, must report deviations, and must not create subagents.

## Scheduling topology

```text
User
  └─ Orchestrator
      ├─ Requirements
      ├─ Product Auditor
      ├─ UX
      ├─ UI
      ├─ Architect
      ├─ Engineering Lead
      │   └─ bounded implementation Workers
      ├─ QA
      └─ Quality Governor (on demand only)
```

Professional roles do not manage one another. They return conflicts to Orchestrator, who resolves them using document precedence and records material decisions. All profiles may be installed while the current role plan activates only the current gate's smallest set.
