# Task packages

A task package must let an Agent with no chat history complete bounded work safely. Use `assets/templates/project/tasks/TASK.template.yaml` or `scripts/create_task_package.py`.

Required fields:

- `task_id`, `project`, `stage`, `status`, `owner`, `reviewer`, `return_to`;
- `objective`, `business_context`, `input_documents`;
- `task_type`, `risk_profile`, and the script-resolved `execution_profile`;
- `role_execution`, including current role-plan fingerprint, quota mode, activation reason, merged responsibilities, concurrency slot, and deferred reviewer activation;
- `quality_review` for a quality task: gate, decision question, input fingerprint, selected lenses, adversarial tests, and quality-case reference;
- `review_contract` for a large-repository review or repair task: review/mode/phase/shard lineage, pinned baseline/target, repository and plan fingerprints, included modules/files, exclusions, risk lenses, findings output, source-write authority, fresh-session/compact-handoff requirements, and the static context budget;
- `capability_requirements`, including required/optional capabilities, permission ceiling, resolution and blockers;
- `scope`, `out_of_scope`, `deliverables`, `acceptance_criteria`;
- `allowed_files`, `forbidden`;
- dependencies, assumptions/risks, validation/evidence, and handoff.

Rules:

- Generation always produces `status: DRAFT`; a generated file is never dispatchable by itself.
- `task_id` must match `TASK-[A-Z0-9][A-Z0-9_-]*`; separators, absolute paths, and `..` are invalid. Dispatch receipts are additionally resolved inside `evidence/dispatch/` and fail closed on symlink escape.
- Fill concrete `business_context.value`, non-empty `scope`, `deliverables`, and `input_documents`; every input document must exist inside the project.
- Add at least one `AC-*` acceptance criterion with concrete Given/When/Then/evidence, bound writers with `allowed_files`, and provide a validation command or manual check. Quality Governor tasks must also complete `quality_review` with an independent mode, gate, decision question, routed input fingerprint, and quality-case reference.
- Orchestrator reviews the completed contract and changes only the top-level status to `READY_FOR_DISPATCH`. Then run `check_execution_plan.py ... --record-ready`; its `BLOCKED_*` messages identify missing contract, role, model/runtime, capability, permission, or stage requirements. Only a final `READY` with `evidence/dispatch/TASK-ID.ready.json` permits spawning.
- After execution, persist the handoff, include at least one artifact or evidence file that exists inside the project, set a successful handoff conclusion, and change the top-level status to `COMPLETED`. Store a sanitized local evidence record when the original proof is external; URLs and missing/out-of-project paths do not advance a wave. Advancement requires this exact Task Package through `--completed-task ROLE=PATH` plus its matching dispatch receipt; a bare completion claim or a task that was blocked at dispatch is rejected.
- One owner and one reviewer; reviewer differs from owner for approval or QA work.
- The owner must be in the current role plan's `required_now`. A reviewer is metadata until owner handoff and must not be started early.
- Orchestrator remains in the main thread. Never create a Task Package to launch another Orchestrator Agent.
- State business value and affected roles/objects/states, not only a technical command.
- Express acceptance as observable Given/When/Then outcomes with an evidence type.
- Enumerate files or bounded directories. “Anywhere needed” is not a safe ownership boundary.
- `forbidden` includes scope, business rule, contract, dependency, or external action the task may not change.
- A temporary Worker must set `return_to: engineering_lead` and include `may_spawn_agents: false`.
- A review shard is read-only even when the same Worker profile may implement in another phase. Its business source appears under `review_contract.included_files`, while `allowed_files` contains only the authorized findings/evidence output. A repair task is separate, requires `review_and_fix`, explicit source-write authority, finding-bound allowed files, and a different later re-review session.
- A Worker is dispatchable only when the current `IN_DEVELOPMENT` role plan lists it in `delegable_workers`, Engineering Lead is the current wave, and a shared quota slot is free. Economy mode never opens a Worker slot.
- Deviations are reported, not hidden. Orchestrator decides whether to amend the package or route upstream.
- Orchestrator computes the execution profile from the current policy. Owners and reviewers do not hand-edit the chosen model, reasoning effort, risk flags or escalation history.
- `role_execution.status` and `execution_profile.status` must be `ROUTED`; the role and model fingerprints must match current policies; all required capabilities must be ready before dispatch.
- Model launch values must match `selected_model` and `model_reasoning_effort`. Record and block a `ROUTE_MISMATCH`.
- A reasoning-quality failure may raise effort and then model tier within `max_attempts`; environment, authorization, input or capability failures do not justify a model upgrade.
- A context-limit failure narrows inputs, rolls over to a compact new Task Package, or splits the shard before any model escalation. Static token estimates are not host usage evidence. A single over-budget file must be blocked or explicitly range-split; never silently truncate it and claim coverage.
- Capability discovery is read-only. Only Orchestrator may update the trusted catalog/lock or invoke provisioning; the owner never installs its own dependencies.

Completion requires every acceptance item to have evidence, required documents to be current, tests to pass, and the designated reviewer/QA to return a conclusion. Owner self-tests are evidence, not final acceptance.
