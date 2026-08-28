# Simple example — internal approval tool

## Input

- Goal: let a five-person team submit and approve equipment requests.
- Risk: no payment, no public user data, no production migration.
- Scope: login is delegated to an existing company identity provider; request create/list/detail/approve/reject and an audit trail are required.

## Expected route

- Complexity: `Simple`.
- DISCOVERY: merged Requirements/Product responsibility; no full role fan-out.
- Build: Engineering Lead.
- Acceptance: a separate QA session.
- UX/UI or Architect activates only when the current evidence contains a matching design, permission, integration, or architecture signal.

## Command flow

```bash
SPO_SKILL="${SPO_SKILL:-$HOME/.agents/skills/software-project-orchestrator}"

python3 "$SPO_SKILL/scripts/orchestrator.py" init /tmp/approval-tool \
  --project-name "Approval Tool" --domain "Internal operations" --complexity Simple
python3 "$SPO_SKILL/scripts/orchestrator.py" transition /tmp/approval-tool --target DISCOVERY
python3 "$SPO_SKILL/scripts/orchestrator.py" plan /tmp/approval-tool --quota economy --write
python3 "$SPO_SKILL/scripts/orchestrator.py" run /tmp/approval-tool
```

Expected route fields include `required_now: [requirements]`, one DISCOVERY wave, and `max_active_subagents: 1`. The run command returns a unique `RUN-...` directory under `/tmp/approval-tool/.codex/runs/`.

The initialized documents intentionally contain unknowns. Complete and approve them before the build gate; do not treat scaffold validation as product approval.

The `/tmp/approval-tool` target must be empty. For a repeat run, use a new directory; the initializer intentionally refuses to overwrite an existing project contract.
