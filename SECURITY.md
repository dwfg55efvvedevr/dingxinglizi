# Security policy

Do not report credentials, tokens, personal data, private project documents, or exploitable production details in a public issue.

For a suspected vulnerability, use GitHub's private vulnerability reporting for this repository when available. Include the affected version, minimal reproduction, impact, and proposed mitigation. Do not test against systems you do not own or have permission to assess.

This project treats capability provisioning as a supply-chain boundary. Floating revisions, hash mismatches, executable installers, unknown community code, unexpected archive paths, unapproved licenses, credentials, OAuth, write access, global installation, and production access must fail closed or require explicit authorization.

Run-ledger and acceptance evidence must be sanitized. Never store secrets or unnecessary production data in `.codex/runs/` or `evidence/`.
