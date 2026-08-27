# Complexity routing

Select the lowest level whose conditions cover the work. Complexity is based on scope, ambiguity, coupling, and risk—not estimated lines of code.

## Simple

Use when the outcome is bounded, the domain and acceptance are clear, there are few roles/states, no sensitive or irreversible workflow exists, and changes are local.

- Active roles: Orchestrator, Requirements/Product Lead (Requirements may also perform product completeness), Engineering Lead, independent QA.
- Add UX/UI only for user-facing behavior whose flow or visual quality is material.
- Architect may be folded into Engineering Lead only when no new API/data/permission/state-machine contract is needed.
- Maximum management depth: Orchestrator → professional role; Engineering Lead → optional Worker.

## Standard

Use when several pages or modules interact, the product has multiple roles or state transitions, front-office actions need back-office handling, or design and architecture both matter.

- Active roles: Orchestrator, Requirements, Product Auditor, UX/UI (may be one Design Lead), Architect/Engineering Lead (may be one technical lead when risk is moderate), independent QA.
- Separate UX and UI when navigation/flows and visual system can be evaluated independently.
- Add bounded frontend, backend, data, AI, or test Workers only for disjoint implementation packages.

## Complex

Use when scope spans multiple applications/services, permissions or financial flows are material, requirements are highly ambiguous, migrations/concurrency/external side effects exist, regulatory/privacy/security impact is meaningful, or failure is costly.

- Active roles: all eight baseline roles: Orchestrator, Requirements, Product Auditor, UX, UI, Architect, Engineering Lead, independent QA.
- Add domain, security, compliance, data, AI, frontend, backend, or test specialists only for concrete work packages.
- Require explicit architecture decisions, rollback strategy, failure injection where relevant, and stronger independent QA.

## Mandatory invariants

- Engineering Lead and final QA are never the same Agent or session.
- Product completeness cannot disappear when roles are merged; the merged role must still produce the matrices and disposition every checklist item.
- Orchestrator remains the only global scheduler. Engineering Lead may schedule Workers only; Workers may not delegate.
- Upgrade one level when evidence conflicts, P0/P1 unknowns persist, two reasonable attempts fail, or security/privacy/financial/production risk appears.
- Downgrade only after the risky decision is resolved and the remaining work is bounded, reversible, and test-protected.

Record the selected level and reasons in `docs/00-project-context.md` and `docs/project-status.json`. A level changes the active team, not the required truthfulness, authorization boundaries, or independent QA.
