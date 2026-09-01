#!/usr/bin/env python3
"""Budget progress waits and force takeover/replanning after stagnation."""

from __future__ import annotations

from task_mode import MODE_BUDGETS, TASK_MODES


def wait_decision(*, task_mode: str, consecutive_no_progress: int, elapsed_minutes: int = 0) -> dict[str, object]:
    if task_mode not in TASK_MODES:
        raise ValueError("unsupported task_mode")
    if consecutive_no_progress < 0 or elapsed_minutes < 0:
        raise ValueError("wait counters cannot be negative")
    budget = MODE_BUDGETS[task_mode]
    wait_limit = int(budget["max_wait_cycles_without_progress"])
    blocker_cycle = int(budget["progress_blocker_required_cycle"])
    time_budget = budget["expected_minutes"]
    over_time = isinstance(time_budget, dict) and elapsed_minutes > int(time_budget["max"])
    takeover = consecutive_no_progress >= wait_limit or over_time
    blocker_required = not takeover and consecutive_no_progress >= blocker_cycle
    return {
        "status": (
            "TAKEOVER_OR_REPLAN" if takeover
            else "PROGRESS_BLOCKER_REQUIRED" if blocker_required
            else "WAIT_ALLOWED"
        ),
        "task_mode": task_mode,
        "consecutive_no_progress": consecutive_no_progress,
        "elapsed_minutes": elapsed_minutes,
        "reason": (
            "no-progress-or-time-budget-exhausted" if takeover
            else "second-consecutive-no-progress-wait-needs-explicit-blocker" if blocker_required
            else "within-budget"
        ),
        "next_action": (
            "stop-new-agents; inspect-current-output; narrow-scope-or-take-over"
            if takeover else "record-progress-blocker-before-one-final-wait"
            if blocker_required else "one-bounded-wait"
        ),
    }
