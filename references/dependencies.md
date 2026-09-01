# Dependencies and capability limits

Run this before first use, after moving the Skill to another machine, or when a validator or host command is unavailable:

```bash
python3 "$SKILL_DIR/scripts/orchestrator.py" dependencies
python3 "$SKILL_DIR/scripts/orchestrator.py" dependencies --json
```

## Runtime requirements

| Dependency | Required | Missing impact |
|---|---:|---|
| Python 3.9+ | yes | deterministic control-plane scripts cannot run |
| Third-party Python packages | no | none; the portable runtime uses the standard library only |
| MCP/connectors | no | only the corresponding external integration is unavailable |

PyYAML is **not** imported by `software-project-orchestrator` and is not a runtime dependency.

## Optional feature dependencies

- Git: required only for Git target pinning, Git-native repository review evidence, and Git-aware migration/exposure checks. Non-Git reduced-strength review remains separately labeled.
- `codex`, `cursor`, `claude`, or `opencode`: required only to detect or verify the corresponding native host. The portable Skill does not require every host executable.
- External Skills/MCP: required only when a current Task Package explicitly needs that capability. Resolve them through the Capability Broker.

## Development-only validation

OpenAI's system `skill-creator/scripts/quick_validate.py` imports the third-party `yaml` module supplied by PyYAML. If that validator's Python environment lacks PyYAML, it may fail with `ModuleNotFoundError: yaml`.

That failure means only:

- the optional external developer validator could not run in that Python environment;
- it does not stop Codex from discovering `SKILL.md`;
- it does not stop this Skill's standard-library CLI, Doctor, tests, evals, release checks, or platform installer.

If the external validator is required, install PyYAML into the **same Python interpreter/environment that runs `quick_validate.py`**. Do not silently install it, do not add it to this Skill's runtime requirements, and do not claim that installing it into a different interpreter fixed the validator.

The release fallback is: parse `SKILL.md` and `agents/openai.yaml`, run `orchestrator.py doctor`, run the full unit tests and bundled evals, run `check_release_consistency.py`, validate local links, and compare archive contents and checksum. Report the unavailable external validator honestly rather than describing it as a runtime failure.
