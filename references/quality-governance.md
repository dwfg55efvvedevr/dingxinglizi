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

Governed product work completes the applicable light checklist. `mode: INLINE` lets the Orchestrator record it when the decision is bounded. `mode: INDEPENDENT` requires a separate `quality_governor` Task Package and evidence. Independent mode is triggered by the current task—not by project complexity—when problem value is genuinely disputed, evidence conflicts, the solution makes an irreversible architecture or commercial commitment, high-impact security/payment/compliance/data-consistency risk exists, two implementation attempts failed for reasoning reasons, or the user explicitly requests a first-principles challenge.

`QUICK_PATCH` and `BOUNDED_CHANGE` do not start Quality Governor by default, including inside a Complex project. Cross-frontend/API scope alone is not a trigger. A wording-precision concern that does not change implementation scope, safety, data writes, permissions, money, or recoverability is a non-blocking note and must not reopen Requirements or the lifecycle.

## Adversarial review rules

- Seek disconfirming evidence, not just supporting evidence.
- State the claim, causal mechanism, assumptions, alternatives, falsifier, and decision consequence.
- Distinguish “users asked for it” from observed behavior, willingness to switch, or willingness to pay.
- Prefer a reversible smallest valuable test over a large solution when uncertainty is high.
- Check failure modes, abuse, exclusion, privacy, accessibility, operational burden, and downstream incentives.
- Do not block on taste. A challenge must identify material evidence, a falsifiable risk, or an acceptance/guardrail gap.
