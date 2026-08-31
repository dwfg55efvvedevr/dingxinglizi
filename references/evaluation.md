# Evaluation contract

`python3 "$SKILL_DIR/scripts/orchestrator.py" eval` runs the versioned offline suite in `evals/routing-v2.json`.

The suite checks deterministic control-plane properties, including:

- smallest sufficient current-stage roles;
- Engineering Lead/final QA separation;
- economy/balanced concurrency ceilings;
- conditional Quality Governor activation;
- large-repository `CODE_REVIEW` Worker-slot behavior without eager team startup;
- logical capability floors/reasoning levels, v2 Codex compatibility mapping, and v3 provider resolution invariants;
- repository scan, module review and cross-module review capability routing;
- fail-closed behavior when a required model is unavailable;
- valid failure escalation, non-escalation for environment failures, and split/narrow behavior for context-limit failures;
- exhausted-attempt and unknown-input blocking.

Every policy change must add or update a representative case before release. A failure blocks release until either the implementation or the explicitly reviewed expectation is corrected.

Evolution Core may generate draft regression candidates under the active control root's `evolution/eval-candidates/`. They are project-local, `DRAFT`, and `REVIEW_REQUIRED`; the formal `eval` command does not discover or count them. Promotion requires an independent reviewer to validate the scenario and manually add an appropriate case in a separately authorized source change. A candidate cannot edit formal expectations, lower gates, or count itself as a passing evaluation.

The large-repository engine also has deterministic unit/contract tests for target and inventory lineage, module/risk shard planning, static budget blocking, structured result ingestion, conservative finding merge, coverage, repair/rereview separation and finalization. Keep those tests separate from the formal routing expectation file unless a routing policy invariant is actually changing.

For a real repository review, offline PASS is only a release-control prerequisite. The project-level acceptance evidence must include:

- pinned target or explicit worktree snapshot and current fingerprints;
- declared inventory plus visible exclusions/dispositions;
- completed primary shard for every included file;
- completed cross-cut shard for every required risk lens;
- structured findings and retained possible-duplicate/severity-conflict evidence;
- repair and re-review lineage when fixes occur;
- independent QA and explicit remaining risks.

The strongest `review_only` result is `COMPLETE_FOR_DECLARED_SCOPE`; repair mode uses a distinct initial-coverage-plus-repair-QA claim. Do not convert either into a numerical code-quality score or claim that all defects, runtime paths or semantic relationships were found.

These evals do not measure Agent intelligence, product-market fit, semantic requirement quality, end-to-end application behavior, actual context/token use, native host session isolation, or real account quota. Those require project acceptance tests, independent QA, runtime evidence, and representative task evaluations. Never publish the offline pass count as a product-quality percentage.
