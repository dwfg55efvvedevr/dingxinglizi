# Evaluation contract

`python3 "$SKILL_DIR/scripts/orchestrator.py" eval` runs the versioned offline suite in `evals/routing-v2.json`.

The suite checks deterministic control-plane properties, including:

- smallest sufficient current-stage roles;
- Engineering Lead/final QA separation;
- economy/balanced concurrency ceilings;
- conditional Quality Governor activation;
- Luna/Terra/Sol capability floors and reasoning levels;
- fail-closed behavior when a required model is unavailable;
- valid failure escalation and non-escalation for environment failures;
- exhausted-attempt and unknown-input blocking.

Every policy change must add or update a representative case before release. A failure blocks release until either the implementation or the explicitly reviewed expectation is corrected.

These evals do not measure Agent intelligence, product-market fit, semantic requirement quality, end-to-end application behavior, or real account quota. Those require project acceptance tests, independent QA, and representative task evaluations. Never publish the offline pass count as a product-quality percentage.
