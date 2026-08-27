# UX and UI quality rules

## UX contract

- Give each page one default primary task and a clear entry, success exit, cancellation path, and recovery path.
- Prefer one primary button. Additional actions must be visibly secondary and justified by the task.
- Define loading, empty, success, failure, offline, unauthorized, expired, disabled, validation, and destructive-confirmation behavior where applicable.
- Preserve user input through recoverable failures when safe. Explain what happened and how to recover.
- Do not invent a flow to compensate for unresolved business rules; route the unknown to Requirements.

## UI and copy guardrails

Prohibit:

- meaningless marketing claims or generic adjectives without evidence;
- excessive explanatory text or paragraphs that restate the interface;
- cards, sections, or copy added only to fill empty space;
- repeated explanations of what a clearly labelled button does;
- decorative card grids that weaken comparison or task flow;
- multiple competing primary actions.

Require:

- visual hierarchy through layout, spacing, typography, contrast, state, and components before adding prose;
- concise, action-specific labels such as “Submit refund” rather than vague calls to action;
- consistent tokens and components with responsive, keyboard, focus, contrast, disabled, error, and permission states;
- realistic content and edge cases, not only ideal placeholder data;
- rendered evidence at relevant viewport sizes when a runnable interface exists.

UI may improve wording and presentation but may not change approved business behavior, permissions, or scope. Route those conflicts to Orchestrator.
