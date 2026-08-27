# Cross-domain adaptation

Keep the orchestration, document contract, gates, role boundaries, and evidence rules stable. Replace only domain facts and domain-specific checks.

## Adaptation procedure

1. Rewrite the one-sentence goal, problem, business model, actors, payer/beneficiary, success metrics, scope and non-goals in `00-project-context.md`.
2. Replace domain objects, lifecycles, numbered rules, permissions, money movement, notifications, admin operations, compliance and external systems in `01-domain-rules.md`.
3. Normalize vocabulary in `02-glossary.md`; do not reuse the same term for different concepts.
4. Rebuild every matrix and completeness disposition. Do not copy the previous domain’s `NOT_APPLICABLE` or `DEFERRED` results.
5. Reassess complexity and active roles. A familiar interface does not make financial, privacy, AI, or multi-tenant behavior Simple.
6. Add domain experts only when a concrete regulatory, safety, scientific, security, data, or operational decision requires them. The expert advises; Orchestrator still owns global routing.

## Examples of what changes

- Home services: provider assignment, service address, schedule, cancellation, worker proof, complaint and settlement.
- E-commerce: catalog/SKU, inventory, cart, order, promotion, payment, shipment, refund and after-sales.
- CRM: tenant, lead, account/contact, pipeline stage, activity, ownership, import/export and data scope.
- SaaS: organization, membership, plan/subscription, entitlement, billing, metering, audit and tenant isolation.
- AI Agent: prompt/tool policy, model/provider, retrieval data, run state, human approval, evaluation, cost limits, privacy and unsafe/uncertain output recovery.

Industry rules are project inputs, not universal Skill rules. Mark regulatory or legal conclusions as blocking unknown until an authorized source confirms them.
