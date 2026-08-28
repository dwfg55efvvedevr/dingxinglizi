# Complex example — multi-party marketplace

## Input

- Roles: buyer, supplier, operator, finance, customer service, auditor.
- Objects: catalog, inventory, order, payment, fulfillment, refund, dispute, settlement.
- Risks: money, permissions, concurrency, idempotency, external integrations, reconciliation, migration, compliance unknowns.

## Expected route

- Complexity: `Complex`, but not all roles start together.
- DISCOVERY and product gates route Requirements/Product Auditor and conditional Quality Governor in ordered waves.
- UX/UI and Architecture become current only at their gates; parallel work is limited to disjoint read-only packages.
- Engineering Lead may govern one Worker when the role plan allows it.
- Architecture/security/permission/migration packages route to Sol-class capability; absence of the verified floor blocks rather than downgrades.
- Independent QA owns final acceptance and Release Evidence may trigger Quality Governor.

## Runnable control-plane example

```bash
SPO_SKILL="${SPO_SKILL:-$HOME/.agents/skills/software-project-orchestrator}"

python3 "$SPO_SKILL/scripts/orchestrator.py" init /tmp/marketplace-v2 \
  --project-name "Marketplace v2" --domain ecommerce --complexity Complex --domain-pack ecommerce
python3 "$SPO_SKILL/scripts/orchestrator.py" transition /tmp/marketplace-v2 --target DISCOVERY
python3 "$SPO_SKILL/scripts/orchestrator.py" plan /tmp/marketplace-v2 --quota quality_first --write
python3 "$SPO_SKILL/scripts/orchestrator.py" run /tmp/marketplace-v2
python3 "$SPO_SKILL/scripts/orchestrator.py" resume /tmp/marketplace-v2
python3 "$SPO_SKILL/scripts/orchestrator.py" report /tmp/marketplace-v2
```

Expected DISCOVERY waves are Requirements followed by the on-demand Quality Governor; they are sequential, not two permanent Agents. With unchanged inputs and no uncertain active session, resume returns `RESUME_SAFE`. If the project records an uncertain active session, expect `RECONCILIATION_REQUIRED`; do not clear it or start a duplicate role until runtime evidence is reconciled.

The `/tmp/marketplace-v2` target must be empty. For a repeat run, use a new directory; the initializer intentionally refuses to overwrite an existing project contract.
