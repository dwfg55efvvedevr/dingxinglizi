# Migrating v1.x projects to v2

v2 keeps the stable Skill invocation `$software-project-orchestrator` and the existing project document contract. The product version is `2.0.0`; internal routing policy versions remain independent and change only when their algorithm or schema changes.

## Existing project

1. Commit or back up current project files.
2. Install v2 of the Skill; do not run initialization over an existing project.
3. Run `python3 "$SKILL_DIR/scripts/orchestrator.py" doctor PROJECT_DIR`.
4. Compare the v2 project template with the effective project `AGENTS.md`, shared Agent rules, role plan, runtime inventory, and Task Package template. Merge missing fields without overwriting stricter project rules or approved business documents.
5. Add `.codex/runs/README.md` or allow the first `run` command to create the ledger directory.
6. Persist a fresh current-stage role plan. Existing Task Packages remain historical evidence; create a new v2 Task Package when dispatching new work.
7. Run unit tests, offline evals, document validation, and the relevant lifecycle gate.

There is no destructive auto-migration command. v2 reads existing initialized projects where required core files are present; `doctor` reports missing or stale contracts. An unverified runtime inventory still blocks actual dispatch by design.
