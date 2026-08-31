# Offline control-plane evaluations

`routing-v2.json` contains human-authored expectations for deterministic role and model routing. It is versioned separately from the Skill release and intentionally performs no network, MCP, GitHub, host Agent, or model calls.

Run it with:

```bash
python3 "$SKILL_DIR/scripts/orchestrator.py" eval
```

Passing this suite checks routing invariants such as minimum-role activation, QA separation, quota bounds, review Worker-slot policy, repository-scan/cross-module capability floors, and bounded failure escalation. A context-limit case must request shard splitting/narrowing rather than automatic model escalation.

Large Repository Review Engine state, inventory, shard-budget, finding, repair/rereview and finalization behavior is also covered by the repository's deterministic unit/contract tests. Those tests are intentionally distinct from the human-authored routing suite; do not publish their pass count as a review-accuracy percentage.

Neither suite proves real model intelligence, semantic completeness, product-market fit, zero defects, native four-host execution, actual runtime token use, or end-to-end product quality. A real review additionally needs a pinned target, declared-scope coverage, visible exclusions, valid shard evidence, independent QA and representative project tests.
