# Contributing

Thank you for improving Software Project Orchestrator.

## Before a pull request

1. Keep `$software-project-orchestrator` stable unless a breaking rename has been explicitly approved.
2. Preserve one Orchestrator, on-demand role activation, one writer per mutable file, and independent final QA.
3. Do not turn MCP, credentials, a paid service, or unknown downloaded code into a core dependency.
4. Do not claim the Python CLI authenticates, starts, or restores native host Agents, knows remaining account quota, or proves a concrete model without runtime evidence.
5. Add a deterministic eval case for any role/model/recovery policy change.
6. Add or update unit tests for scripts, templates, schema fields, domain packs, and fail-closed behavior.
7. Keep Evolution data local and candidates review-required. Never weaken evidence thresholds, protected invariants, stage/acceptance/release gates, formal eval expectations, or candidate non-execution.
8. An Evolution eval candidate is input for review, not a formal test. Promote it manually only after independent validation and add a regression test for the promotion path itself.
9. Keep platform adapters isolated and generated from the common role catalog. Update official-format evidence and adapter tests when fields change; never use one host's config syntax as another host's fallback.
10. Preserve v2 legacy reading and non-destructive migration unless a separately approved breaking release provides a tested migration and rollback path.

Run:

```bash
SPO_SKILL="${SPO_SKILL:-$(pwd)}" # run from the cloned Skill root

python3 -m py_compile scripts/*.py
python3 -m unittest discover -s scripts/tests -v
python3 "$SPO_SKILL/scripts/orchestrator.py" eval
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor
```

Describe the user problem, scope, behavior change, evidence, compatibility impact, and any accepted risk in the pull request.
