# Offline control-plane evaluations

`routing-v2.json` contains human-authored expectations for deterministic role and model routing. It is versioned separately from the Skill release and intentionally performs no network, MCP, GitHub, or model calls.

Run it with:

```bash
python3 "$SKILL_DIR/scripts/orchestrator.py" eval
```

Passing this suite proves routing invariants such as minimum-role activation, QA separation, quota bounds, model risk floors, and bounded escalation. It does **not** prove real model intelligence, product-market fit, or end-to-end project quality.
