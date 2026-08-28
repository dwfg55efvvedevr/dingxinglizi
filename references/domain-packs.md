# Versioned domain packs

Domain packs accelerate discovery by proposing common business objects, lifecycles, risk signals, completeness additions, and test scenarios. They are candidate input, never authoritative business facts or legal conclusions.

Bundled packs: `ecommerce`, `crm`, `saas`, `group-buying`, `ai-agent`, and `home-services`.

## Safe use

1. Inspect with `python3 "$SKILL_DIR/scripts/orchestrator.py" domains list` and `domains inspect PACK`.
2. Apply to an initialized project with `domains apply PROJECT_DIR PACK --dry-run`, then without `--dry-run`.
3. Review `docs/domain-pack.md`; mark each relevant item with a valid fact state in the authoritative project documents.
4. Record confirmed rules with IDs, owners, sources, and versions. Leave legal, compliance, licensing, money, and permission assumptions blocking until authorized evidence exists.

Application is non-overwriting and creates `.codex/orchestration/domain-lock.json` with the exact pack version and SHA-256. Reapplying the same locked pack is idempotent; a different pack or modified destination requires explicit manual reconciliation.

To add a pack, create `assets/domain-packs/<id>/pack.json`, keep it free of project-specific facts, and add tests that load every bundled pack. Do not include executable code, credentials, vendor secrets, or claims that a jurisdictional requirement is satisfied.
