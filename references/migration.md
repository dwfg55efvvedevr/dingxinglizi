# Migration and rollback

v3 keeps stable invocation `$software-project-orchestrator`, run schema `1`, Task Package schema `2`, project document contracts, on-demand roles, and independent QA. New platform-neutral projects use model policy `2.0.0`; unmigrated v2 Codex projects keep executable legacy model policy `1.2.0`.

The migration command copies the existing control state and therefore preserves policy `1.2.0`. It does not perform a semantic policy upgrade to `2.0.0`, convert vendor bindings, or enable cross-provider routing. That larger change requires a separately reviewed policy conversion and fresh platform runtime evidence.

## Layout selection

One command selects one control root:

1. if `.dingxinglizi/` exists, use it;
2. otherwise, if `.codex/orchestration`, `.codex/runs`, or `.codex/evolution` exists, use legacy `.codex/`;
3. otherwise, new state belongs under `.dingxinglizi/`.

Commands never mix v2 and v3 state. An existing v2 project remains usable without migration.

## v2 to v3

Preview first:

```bash
python3 "$SKILL_DIR/scripts/orchestrator.py" migrate PROJECT_DIR
```

The preview scans `.codex/orchestration` and `.codex/runs`, rejects symlinks and non-single-link files, enforces file-count and total-size limits, and records source size/SHA-256. Apply only after review:

```bash
python3 "$SKILL_DIR/scripts/orchestrator.py" migrate PROJECT_DIR --apply
```

Apply copies into project-local staging, verifies every copy, writes `.dingxinglizi/migration-v3.json`, and atomically promotes the destination. It does not change or delete `.codex/`. Re-running reports `ALREADY_MIGRATED` only after revalidating the exact manifest contract and rescanning every included source/destination directory. The actual path/size/SHA-256 sets must exactly equal the manifest, so missing, changed, duplicate, or unmanifested extra files are blocking integrity errors.

Evolution is excluded by default. To include it:

1. add `.dingxinglizi/evolution/` to the effective project ignore rules;
2. verify no destination Evolution file is tracked;
3. back up the existing local sidecar;
4. preview/apply with `--include-evolution`.

The migration refuses Evolution copy when the destination ignore rule is not effective.

## Native adapter changes

Migrating control state does not guess the next host. Render only the selected host:

```bash
python3 "$SKILL_DIR/scripts/orchestrator.py" platform render PROJECT_DIR --platform cursor
```

Existing native files are not overwritten without `--update`. Keep one active generated platform adapter per project unless there is a documented multi-host workflow and explicit ownership rules.

## Rollback

Before rollback, back up `.dingxinglizi/` and verify no newer run, task, decision, or Evolution record exists only there. Because migration preserves `.codex/`, a v2-compatible Skill can read the original state after `.dingxinglizi/` is moved aside through an explicit, recoverable user action. Never delete either tree merely because a migration command succeeded.

Rollback does not convert v3-only runtime manifests, provider mappings, or host profiles into v2 contracts. Preserve them as evidence and reconcile manually.

## v1 projects

Do not run the v2-to-v3 copier on an uninitialized v1 tree. First merge the current document contract, one effective `AGENTS.md`, role/model policies, Task Package v2 fields, runtime inventory provenance, and project status. Run `doctor` and `validate` until the legacy project is valid; then optionally migrate its v2 control state.
