# Security policy

Do not report credentials, tokens, personal data, private project documents, or exploitable production details in a public issue.

For a suspected vulnerability, use GitHub's private vulnerability reporting for this repository when available. Include the affected version, minimal reproduction, impact, and proposed mitigation. Do not test against systems you do not own or have permission to assess.

This project treats capability provisioning as a supply-chain boundary. Floating revisions, hash mismatches, executable installers, unknown community code, unexpected archive paths, unapproved licenses, credentials, OAuth, write access, global installation, and production access must fail closed or require explicit authorization.

Run-ledger and acceptance evidence must be sanitized. Never store secrets or unnecessary production data in the active `.dingxinglizi/runs/` or legacy `.codex/runs/`, or in `evidence/`.

Evolution runtime data under the active `.dingxinglizi/evolution/` or legacy `.codex/evolution/` must remain local, ignored, and untracked. Ordinary evidence content is not copied: Evolution stores its path, hash, and size. A separately supplied `execution_attestation` is different: its allowlisted model, reasoning, token, cost, quota, and runtime facts are copied into the Outcome together with provenance references. Filenames, roles, categories, run IDs, those execution facts, and process observations can disclose project metadata. Use generic evidence filenames; never record credentials, customer identifiers, private keys, personal data, internal URLs, source code, raw chats, prompts, logs, or commercial secrets.

Platform installation is preview-first, single-platform, non-networked, non-authenticating, and non-overwriting by default. Portable Skill installs retain the repository `LICENSE`. Project control state, runtime evidence, capability locks, run ledgers, native Skill destinations, and managed Codex MCP configuration reject symlink traversal and abnormal hard links; security-sensitive replacements are atomic and revalidated. Runtime manifests must not contain credentials. L4 receipts attest selected execution facts only; they are local integrity records, not signatures or proof against an actor with full write access.

Evolution artifacts are unsigned. Their validators detect schema, path, fingerprint, resource, and lineage inconsistencies, not a coherent rewrite by an actor with full local write access. Generated proposals and eval candidates have no authority to modify code, Git, gates, formal evaluations, external systems, or their own evidence policy.
