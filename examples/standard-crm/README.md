# Standard example — CRM pipeline module

## Input

- Roles: sales representative, sales manager, operations administrator.
- Objects: lead, account, contact, opportunity, activity, owner, import job.
- Risks: tenant data scope, reassignment, import/export, audit history.

## Expected route

- Complexity: `Standard`.
- Requirements and Product Auditor are separate when completeness needs review.
- UX/UI may merge into a Design Lead for moderate visual scope.
- Architect/Engineering responsibilities may merge only when permission and migration risk remain moderate.
- Final QA remains independent.

## Domain starter

```bash
SPO_SKILL="${SPO_SKILL:-$HOME/.agents/skills/software-project-orchestrator}"

python3 "$SPO_SKILL/scripts/orchestrator.py" init /tmp/acme-crm \
  --project-name "Acme CRM" --domain CRM --complexity Standard --domain-pack crm
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor /tmp/acme-crm
python3 "$SPO_SKILL/scripts/orchestrator.py" transition /tmp/acme-crm --target DISCOVERY
python3 "$SPO_SKILL/scripts/orchestrator.py" plan /tmp/acme-crm --quota economy --write
python3 "$SPO_SKILL/scripts/orchestrator.py" run /tmp/acme-crm
```

Expected initial doctor status is `READY_WITH_LIMITATIONS` because the scaffold intentionally contains unapproved business facts and an unverified runtime inventory. DISCOVERY activates Requirements first instead of opening the whole Standard role set.

The CRM pack proposes objects and risks but confirms nothing. Validate tenant boundaries, field visibility, owner transitions, audit retention, export authority, and acceptance evidence with the actual project owner.

The `/tmp/acme-crm` target must be empty. For a repeat run, use a new directory; the initializer intentionally refuses to overwrite an existing project contract.
