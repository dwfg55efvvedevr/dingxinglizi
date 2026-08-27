# Quality governance

Quality has two independent responsibilities:

- QA asks whether the approved product was implemented and verified correctly.
- Quality Governor asks whether the problem, solution logic, and release claim are defensible in the first place.

The Quality Governor is a read-only challenger, not a permanent manager and not a second Orchestrator. Its finding is routed to the earliest source owner, so the lifecycle keeps the existing `REWORK_*` states.

## Three quality subgates

| Subgate | Before | Core question | Evidence |
|---|---|---|---|
| Problem Quality | `REQUIREMENTS_APPROVED` | Is the problem real, important, evidenced, and bounded? | `docs/checklists/problem-quality.md` |
| Solution Challenge | `READY_FOR_BUILD` | Does the solution follow from the problem, beat alternatives, and form the smallest valuable test? | `docs/checklists/solution-challenge.md` |
| Release Evidence Challenge | `RELEASE_READY` | Do behavior, outcomes, guardrails, operations, and risks support the release claim? | `docs/checklists/quality-case.md` |

Every project completes the light checklist. `mode: INLINE` lets the Orchestrator record it for low-risk work. `mode: INDEPENDENT` requires a separate `quality_governor` Task Package and evidence. Independent mode is required for Complex projects at solution challenge, for `quality_first`, or when routing sees novelty, evidence conflict, high impact, regulation, release risk, or repeated failure.

## Adversarial review rules

- Seek disconfirming evidence, not just supporting evidence.
- State the claim, causal mechanism, assumptions, alternatives, falsifier, and decision consequence.
- Distinguish “users asked for it” from observed behavior, willingness to switch, or willingness to pay.
- Prefer a reversible smallest valuable test over a large solution when uncertainty is high.
- Check failure modes, abuse, exclusion, privacy, accessibility, operational burden, and downstream incentives.
- Do not block on taste. A challenge must identify material evidence, a falsifiable risk, or an acceptance/guardrail gap.
