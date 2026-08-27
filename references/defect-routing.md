# Defect and rework routing

Route a defect to the earliest responsibility source that can correct the cause. Do not send every failure to Engineering Lead. For a cross-layer defect, assign one `primary_owner` and list `contributors`; Orchestrator coordinates the re-entry sequence.

| Defect source | Primary owner | Rework state |
|---|---|---|
| incorrect or missing business rule, role, scope, or acceptance intent | Requirements | `REWORK_REQUIREMENTS` |
| missing page, function, state, admin module, permission coverage, or front/back-office closure | Product Auditor | `REWORK_PRODUCT` |
| confusing flow, navigation, feedback, exception or recovery path | UX | `REWORK_UX` |
| visual hierarchy, component, responsive/accessibility state, or product copy | UI | `REWORK_UI` |
| API, data model, permission enforcement, state machine, consistency, migration or deployment design | Architect | `REWORK_ARCHITECTURE` |
| implementation, integration, regression, build, or developer test failure | Engineering Lead | `REWORK_ENGINEERING` |
| missing/invalid test, fixture, evidence, coverage or QA procedure | QA | `REWORK_QA` |

Each defect record includes ID, severity P0–P3, failed criterion, environment/preconditions, reproduction, expected/actual, evidence, source owner, contributors, affected artifacts, correction required, re-entry gate, retest and regression range.

QA reports `PASS`, `PASS_WITH_ACCEPTED_RISKS`, `FAIL`, or `BLOCKED`. Only an authorized decision owner may accept a material risk; QA records but does not invent that acceptance. P0/P1 defects and unaccepted risks block `QA_PASS`.
