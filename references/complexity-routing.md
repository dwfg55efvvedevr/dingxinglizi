# Complexity routing

Select the lowest level whose conditions cover the work. Complexity is based on scope, ambiguity, coupling, and risk—not estimated lines of code.

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

Record the selected level and reasons in `docs/00-project-context.md` and `docs/project-status.json`. Complexity changes lifecycle availability and quality triggers, not simultaneous activity, truthfulness, authorization, or independent QA.
