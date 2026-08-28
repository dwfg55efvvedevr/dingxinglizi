# Evolution Core

Evolution Core is a supervised, project-local learning loop. It converts validated run outcomes and explicit evidence-linked feedback into deterministic retrospectives, draft improvement proposals, and draft regression-evaluation candidates.

It does not rewrite the installed Skill, approve its own suggestions, change project facts, alter formal evals, use the network, commit, push, release, deploy, or claim that a generated candidate improved quality. The word “evolution” means evidence aggregation and review-ready candidate generation, not autonomous self-modification.

## Local workspace

Runtime state lives only under the active control root's `evolution/`: `<project>/.dingxinglizi/evolution/` for v3 or `<project>/.codex/evolution/` for unmigrated v2:

```text
manifest.json
outcomes.jsonl
feedback.jsonl
retrospectives/
candidates/
eval-candidates/
```

The workspace has a stable random project instance identity, strict schema versions, local write locks, atomic writes, deterministic fingerprints, and a protected-invariant registry. Ordinary evidence content is not copied, but the files may reveal workflow metadata and evidence paths. A separately supplied execution attestation contributes only the allowlisted execution facts described below.

For a new project, the generated `.gitignore` includes both known Evolution paths. For an existing Git project, add the active path yourself before recording experience. Every post-init write fails closed unless the active directory is confirmed ignored and untracked. The tool never edits Git configuration, the index, history, or ignore files.

## Command flow

```bash
python3 "$SKILL_DIR/scripts/orchestrator.py" evolution status PROJECT_DIR
python3 "$SKILL_DIR/scripts/orchestrator.py" evolution init PROJECT_DIR
python3 "$SKILL_DIR/scripts/orchestrator.py" evolution collect PROJECT_DIR --run-id RUN-ID
python3 "$SKILL_DIR/scripts/orchestrator.py" evolution feedback PROJECT_DIR \
  --kind repeated_defect --result FAIL --severity P1 \
  --category test_coverage --summary "Regression escaped the required boundary test" \
  --evidence evidence/AC-REGRESSION.txt
python3 "$SKILL_DIR/scripts/orchestrator.py" evolution retrospect PROJECT_DIR
python3 "$SKILL_DIR/scripts/orchestrator.py" evolution propose PROJECT_DIR \
  --retrospective RETROSPECTIVE-ID.json
python3 "$SKILL_DIR/scripts/orchestrator.py" evolution eval-candidates PROJECT_DIR \
  --proposal PROPOSAL-ID.json
```

Only explicit `evolution init` creates an Evolution workspace in an existing project. `collect` accepts only a structurally consistent completed run with independent-QA completion evidence. An OPEN, BLOCKED, incomplete, inconsistent, oversized, changing, or corrupt source fails closed. A failed or blocked project can still be learned from through explicit `feedback --result FAIL|BLOCKED`; do not fabricate a completed run.

Omitted selectors are safe only when the choice is unique. Multiple completed runs, retrospectives, or proposals return `AMBIGUOUS_INPUT`; pass an explicit ID. No command chooses “latest” by filesystem time.

## Evidence and privacy

Feedback needs one or more existing ordinary project files. Paths must remain inside the project and cannot be symlinks, hard-linked ledgers, Git metadata, Evolution state, credentials, private keys, `.env` files, token-like names, email-like names, or other sensitive patterns. Summary text is one sanitized line and is rejected rather than partially redacted when it matches a credential, email, private-key, JWT, URL-userinfo, or secret-assignment pattern.

Ordinary evidence content is hashed in bounded streaming reads and never copied into Evolution artifacts. The system records path, content hash, and size. An explicit `execution_attestation` is the narrow exception: its allowlisted model, reasoning, token, cost, quota, and runtime values are copied into the Outcome with provenance references. This reduces exposure; it does not make a sensitive filename or execution fact safe. Use generic project-local evidence names and include only the execution facts needed for review.

Run records and candidates are unsigned local files. Validation detects malformed data, path escape, unsupported schemas, inconsistent lineage and changed fingerprints. It cannot detect a coherent rewrite of every related file by an actor with full local write access.

## Evidence sufficiency

An ordinary proposal requires three structurally independent evidence lineages in the same category. All records linked to the same run count once. Unlinked feedback records sharing any evidence content hash are merged transitively into one evidence cluster, so `{A}`, `{A,B}`, and `{B}` count once.

One P0 feedback record or one record whose kind is `security_or_privacy` may produce a high-priority draft. Priority order is `P0`, then `security_or_privacy`, then three independent lineages. Structural independence is not proof that a claim is true or causally independent; a reviewer must still judge the evidence.

## Candidate safety

Every proposal and eval candidate remains both `DRAFT` and `REVIEW_REQUIRED`. Generated prose comes from controlled category templates, not feedback text. Candidates carry fixed authority flags that prohibit apply, commit, push, merge, release, and modification of:

- lifecycle, acceptance, QA, and release gates;
- authorization and least-privilege rules;
- development/final-QA separation;
- the protected-invariant registry and Evolution thresholds;
- formal eval expectations.

Draft eval candidates stay under the active `evolution/eval-candidates/`; the formal `orchestrator.py eval` command ignores them. A human must independently validate and manually promote a useful case in a separately authorized change.

## Recovery and retention

Evolution corruption blocks Evolution only. Core lifecycle, run recovery, project validation, and formal routing evals remain usable. `evolution status` reports a stable reason code and never repairs data or shows partial counts as facts.

For an abandoned lock, first verify that no matching process is running, back up the active Evolution directory, and remove only the exact lock file. The tool never guesses that a lock is stale. There is no automatic cleanup policy; backup, retention, migration, and deletion remain explicit user decisions.

Rolling the Skill back may leave a v3 sidecar unreadable to older versions. Back it up and preserve it; rollback does not change project documents or core run state.
