# Task packages

A task package must let an Agent with no chat history complete bounded work safely. Use `assets/templates/project/tasks/TASK.template.yaml` or `scripts/create_task_package.py`.

Required fields:

- `task_id`, `project`, `stage`, `status`, `owner`, `reviewer`, `return_to`;
- `objective`, `business_context`, `input_documents`;
- `scope`, `out_of_scope`, `deliverables`, `acceptance_criteria`;
- `allowed_files`, `forbidden`;
- dependencies, assumptions/risks, validation/evidence, and handoff.

Rules:

- One owner and one reviewer; reviewer differs from owner for approval or QA work.
- State business value and affected roles/objects/states, not only a technical command.
- Express acceptance as observable Given/When/Then outcomes with an evidence type.
- Enumerate files or bounded directories. “Anywhere needed” is not a safe ownership boundary.
- `forbidden` includes scope, business rule, contract, dependency, or external action the task may not change.
- A temporary Worker must set `return_to: engineering_lead` and include `may_spawn_agents: false`.
- Deviations are reported, not hidden. Orchestrator decides whether to amend the package or route upstream.

Completion requires every acceptance item to have evidence, required documents to be current, tests to pass, and the designated reviewer/QA to return a conclusion. Owner self-tests are evidence, not final acceptance.
