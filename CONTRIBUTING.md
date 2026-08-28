# Contributing

Thank you for improving Software Project Orchestrator.

## Before a pull request

1. Keep `$software-project-orchestrator` stable unless a breaking rename has been explicitly approved.
2. Preserve one Orchestrator, on-demand role activation, one writer per mutable file, and independent final QA.
3. Do not turn MCP, credentials, a paid service, or unknown downloaded code into a core dependency.
4. Do not claim the Python CLI starts/restores Codex Agents or knows remaining account quota.
5. Add a deterministic eval case for any role/model/recovery policy change.
6. Add or update unit tests for scripts, templates, schema fields, domain packs, and fail-closed behavior.

Run:

```bash
SPO_SKILL="${SPO_SKILL:-$(pwd)}" # run from the cloned Skill root

python3 -m py_compile scripts/*.py
python3 -m unittest discover -s scripts/tests -v
python3 "$SPO_SKILL/scripts/orchestrator.py" eval
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor
```

Describe the user problem, scope, behavior change, evidence, compatibility impact, and any accepted risk in the pull request.
