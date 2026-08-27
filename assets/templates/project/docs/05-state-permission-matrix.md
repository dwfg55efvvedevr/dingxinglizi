---
title: "{{PROJECT_NAME}} — State and Permission Matrices"
status: DRAFT
version: 0.1.0
last_updated: "{{DATE}}"
owner: architect
source_of_truth: project-document-set
---

# State and permission matrices

## Feature-state matrix

Use `REQUIRED`, `NOT_APPLICABLE`, or `DEFERRED` for each state applicability. A required state must reference behavior and acceptance evidence.

| Feature ID | Initial | Loading | Empty | Success | Failure | Offline | Unauthorized | Expired | Disabled/validation | Recovery | Acceptance refs |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Business object transition matrix

| Object ID | From state | Event/action | Actor | Guard | To state | Side effects | Failure/recovery | Rule/API/AC refs |
|---|---|---|---|---|---|---|---|---|

## Permission matrix

| Role ID | Resource | Data scope | View | Create | Modify | Delete | Approve/review | Export | Sensitive operation log | Backend enforcement | Acceptance refs |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Permission test notes

- Test at least two different roles and cross-ownership data where applicable.
- Hidden UI is not authorization; link backend enforcement and negative test evidence.
- Role/session changes, cached data, list/detail/search/export and error disclosure must use the same scope rules.
