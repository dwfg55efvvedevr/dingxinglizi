# Evaluation contract

`python3 "$SKILL_DIR/scripts/orchestrator.py" eval` runs the versioned offline suite in `evals/routing-v2.json`.

The suite checks deterministic control-plane properties, including:

- smallest sufficient current-stage roles;
- Engineering Lead/final QA separation;
- economy/balanced concurrency ceilings;
- conditional Quality Governor activation;
- logical capability floors/reasoning levels, v2 Codex compatibility mapping, and v3 provider resolution invariants;
- fail-closed behavior when a required model is unavailable;
- valid failure escalation and non-escalation for environment failures;
- exhausted-attempt and unknown-input blocking.

Every policy change must add or update a representative case before release. A failure blocks release until either the implementation or the explicitly reviewed expectation is corrected.

Evolution Core may generate draft regression candidates under the active control root's `evolution/eval-candidates/`. They are project-local, `DRAFT`, and `REVIEW_REQUIRED`; the formal `eval` command does not discover or count them. Promotion requires an independent reviewer to validate the scenario and manually add an appropriate case in a separately authorized source change. A candidate cannot edit formal expectations, lower gates, or count itself as a passing evaluation.

These evals do not measure Agent intelligence, product-market fit, semantic requirement quality, end-to-end application behavior, or real account quota. Those require project acceptance tests, independent QA, and representative task evaluations. Never publish the offline pass count as a product-quality percentage.
