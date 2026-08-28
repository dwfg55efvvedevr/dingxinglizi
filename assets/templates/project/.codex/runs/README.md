# Local run ledger

This directory is written only by Orchestrator. Each run receives an immutable ID and contains input snapshots, routing decisions, checkpoints, a sanitized event stream, an evidence index, and a derived final report.

Run records support recovery and auditability. They do not replace approved project documents and must never contain credentials, tokens, customer secrets, unnecessary personal data, or unredacted production logs.
