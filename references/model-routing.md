# Task-level model routing

Route a model for each Task Package, not permanently for a role. The same Agent may use Luna for a bounded scan, Terra for normal analysis or implementation, and Sol for security, permissions, migrations, concurrency, production risk, complex architecture, or independent high-impact QA.

## Stable routing contract

Run `scripts/route_task.py` or use `scripts/create_task_package.py`, which calls the same pure routing function. Identical structured inputs and policy version produce the same route. The route records its policy, capability tier, preferred and selected model, reasoning effort, risk flags, reason codes, attempts, fallback and downgrade policy.

Before task creation, Orchestrator records a verified runtime model snapshot in `.codex/orchestration/runtime-inventory.json`. The initialized file is deliberately `UNVERIFIED`; it does not pretend every account or host exposes every model. Command-line callers may provide the same evidence explicitly by repeating `--available-model` when creating and preflighting a task. An empty or unverified snapshot blocks dispatch.

```bash
python3 scripts/route_task.py \
  --complexity Complex \
  --task-type architecture \
  --role architect \
  --risk security \
  --risk migration
```

Supported task types are `scan`, `extract`, `format`, `documentation`, `test_run`, `requirements`, `product_audit`, `ux`, `ui`, `implementation`, `code_review`, `qa`, `architecture`, `security_review`, `permission_design`, `migration_design`, and `release_review`. Unknown task or risk names fail closed instead of silently receiving a cheaper route.

The composition rule takes the highest requirement from role, project complexity, task type, and hard risk flags. The complete result receives a SHA-256 `route_fingerprint`; launch preflight recomputes it and compares every launch-critical field so inheritance, attempts, fallback or reasoning policy cannot be silently changed.

| Tier | Default model | Default effort | Typical work |
|---|---|---|---|
| Economy | `gpt-5.6-luna` | low | extraction, formatting, deterministic scans and fixed test runs |
| Standard | `gpt-5.6-terra` | medium | bounded analysis and ordinary implementation |
| Advanced | `gpt-5.6-terra` | high | cross-file integration, product work, code review and normal independent QA |
| Expert | `gpt-5.6-sol` | high | architecture, permissions, security, migrations and complex delivery control |
| Exceptional | `gpt-5.6-sol` | xhigh | repeated semantic failure or unusually consequential ambiguity |

Role floors prevent a high-impact coordinator or reviewer from being routed like a mechanical Worker:

| Role | Simple | Standard | Complex |
|---|---|---|---|
| Orchestrator | Terra medium | Terra high | Sol high |
| Requirements / Product Auditor / UX / UI | Terra medium | Terra medium | Terra high |
| Architect | Terra high | Terra high | Sol high |
| Engineering Lead | Terra medium | Terra high | Sol high |
| Independent QA | Terra high | Terra high | Sol high |
| Temporary Worker | Luna for mechanical tasks; task/risk rules may raise it | Luna/Terra | Terra or Sol when risk requires |

These are floors, not permanent role bindings. Hard risk flags and repeated valid quality failure may raise them.

The router never uses `max` or `ultra` by default. Add them only after project-specific evaluation shows a material benefit.

## Runtime precedence and inheritance

Keep all role TOML files free of `model` and `model_reasoning_effort`. This prevents static role settings from defeating task-level routing. Runtime precedence is:

1. resolved `execution_profile` in the Task Package;
2. Orchestrator's explicit `model` and `reasoning_effort` values when spawning the Agent;
3. a runtime Agent default, if configured outside this Skill;
4. parent inheritance only when no explicit task route exists.

For governed work, steps 1 and 2 are mandatory. Before spawning, the Orchestrator must confirm `execution_profile.status: ROUTED`, then pass `selected_model` and `model_reasoning_effort` explicitly. If the actual launch cannot match the route, record `ROUTE_MISMATCH` and do not claim task completion.

## Failure escalation

Classify failure before changing the model:

- `network`, `rate_limit`, `auth`, `permission`, `missing_input`, `tool_unavailable`: repair or block the environment; never upgrade the model merely because a tool failed.
- `quality`, `reasoning`, `acceptance`, `qa_defect`, `evidence_conflict`: first valid failure raises reasoning effort; a repeated valid failure raises one capability tier.
- Three failed attempts: stop and return to Orchestrator for re-planning, source-level rework, or explicit user direction. Never retry indefinitely.

High-risk tasks that require Sol become `BLOCKED_MODEL_UNAVAILABLE` when Sol is unavailable. They never silently fall back to Terra or Luna. Low-risk mechanical tasks may use a recorded controlled downgrade. Any later downgrade requires a new, narrower, lower-risk Task Package; it may not rewrite the route of a failed task in place.

Model choice is reproducible policy selection, not a guarantee that model output is deterministic. Keep tests and independent QA as the final quality control.
