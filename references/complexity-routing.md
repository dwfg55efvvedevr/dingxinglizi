# Complexity routing

Maintain two separate decisions:

- `project_complexity: Simple | Standard | Complex` describes lifecycle-wide system scope and available responsibilities.
- `task_mode: QUICK_PATCH | BOUNDED_CHANGE | GOVERNED_DELIVERY` describes the current delta and controls roles, gates, budgets, and validation.

Route the task first with [task-mode-routing.md](task-mode-routing.md). Project complexity may raise a risk floor when current-task evidence supports it, but it must never activate the full lifecycle, Requirements, Architect, or Quality Governor by itself. A Complex platform plus a local copy fix is still `QUICK_PATCH`; a bounded pickup-map plus API fail-closed change is normally `BOUNDED_CHANGE`; a payment-state migration is `GOVERNED_DELIVERY` even if it changes one file.

For project complexity, select the lowest level whose conditions cover the whole system. Complexity is based on scope, ambiguity, coupling, and risk—not estimated lines of code.

## Simple

Use when the outcome is bounded, the domain and acceptance are clear, there are few roles/states, no sensitive or irreversible workflow exists, and changes are local.

- Available responsibilities across the lifecycle: Orchestrator, Requirements/Product Lead, Engineering Lead, independent QA. Activate only the current gate's role; they are not simultaneous.
- Add UX/UI only for user-facing behavior whose flow or visual quality is material.
- Architect may be folded into Engineering Lead only when no new API/data/permission/state-machine contract is needed.
- Maximum management depth: Orchestrator → professional role; Engineering Lead → optional Worker.

## Standard

Use when several pages or modules interact, the product has multiple roles or state transitions, front-office actions need back-office handling, or design and architecture both matter.

- Available responsibilities across the lifecycle: Orchestrator, Requirements, Product Auditor, UX/UI, Architect/Engineering Lead, independent QA. Route them gate by gate.
- Separate UX and UI when navigation/flows and visual system can be evaluated independently.
- Add bounded frontend, backend, data, AI, or test Workers only for disjoint implementation packages.

## Complex

Use when scope spans multiple applications/services, permissions or financial flows are material, requirements are highly ambiguous, migrations/concurrency/external side effects exist, regulatory/privacy/security impact is meaningful, or failure is costly.

- Available across the lifecycle: all baseline roles plus the optional Quality Governor. Complex does not mean starting them together; the current role plan usually activates one and never more than the quota wave permits.
- Add domain, security, compliance, data, AI, frontend, backend, or test specialists only for concrete work packages.
- Require explicit architecture decisions, rollback strategy, failure injection where relevant, and stronger independent QA.

## Mandatory invariants

- Engineering Lead and final QA are never the same Agent or session.
- Product completeness cannot disappear when roles are merged; the merged role must still produce the matrices and disposition every checklist item.
- Orchestrator remains the only global scheduler. Engineering Lead may schedule Workers only; Workers may not delegate.
- Upgrade one level when evidence conflicts, P0/P1 unknowns persist, two reasonable attempts fail, or security/privacy/financial/production risk appears.
- Downgrade only after the risky decision is resolved and the remaining work is bounded, reversible, and test-protected.
- Role configuration files do not consume a subagent call. Only an actual delegated execution does. Default to `economy` (one active subagent); allow two only for explicit independent read-only work.

Record project complexity separately from the current task mode and reasons. A task-mode change creates a new delta decision; it does not rewrite the project's global lifecycle. Complexity changes lifecycle availability, not simultaneous activity, truthfulness, authorization, or independent QA.
