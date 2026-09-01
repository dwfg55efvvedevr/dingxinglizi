#!/usr/bin/env python3
"""Bounded-change delta overlay that does not mutate the project lifecycle."""

from __future__ import annotations

from typing import Iterable


STATES = ("DELTA_DRAFT", "DELTA_READY", "IMPLEMENTING", "TARGETED_VALIDATION", "QA", "DELTA_DONE", "BLOCKED")
TRANSITIONS = {
    "DELTA_DRAFT": {"DELTA_READY", "BLOCKED"},
    "DELTA_READY": {"IMPLEMENTING", "BLOCKED"},
    "IMPLEMENTING": {"TARGETED_VALIDATION", "BLOCKED"},
    "TARGETED_VALIDATION": {"QA", "IMPLEMENTING", "BLOCKED"},
    "QA": {"DELTA_DONE", "IMPLEMENTING", "BLOCKED"},
    "DELTA_DONE": set(),
    "BLOCKED": {"DELTA_DRAFT", "DELTA_READY", "IMPLEMENTING"},
}


def transition_iteration(
    current: str,
    target: str,
    *,
    repair_rounds: int = 0,
    engineering_session: str = "",
    qa_session: str = "",
    qa_conclusion: str = "",
    qa_evidence: Iterable[str] = (),
    unaccepted_p0_p1: int = 0,
) -> dict[str, object]:
    if current not in STATES or target not in STATES:
        raise ValueError("unsupported bounded iteration state")
    if target not in TRANSITIONS[current]:
        raise ValueError(f"invalid bounded iteration transition: {current} -> {target}")
    if current == "QA" and target == "IMPLEMENTING" and repair_rounds >= 1:
        raise ValueError("bounded change permits at most one targeted repair round")
    evidence = [value for value in qa_evidence if value and value.strip()]
    if current == "QA" and target == "DELTA_DONE":
        if not engineering_session or not qa_session or engineering_session == qa_session:
            raise ValueError("DELTA_DONE requires an independent QA session distinct from Engineering")
        if qa_conclusion not in {"PASS", "PASS_WITH_ACCEPTED_RISKS"}:
            raise ValueError("DELTA_DONE requires QA PASS or PASS_WITH_ACCEPTED_RISKS")
        if not evidence:
            raise ValueError("DELTA_DONE requires at least one QA evidence reference")
        if unaccepted_p0_p1:
            raise ValueError("DELTA_DONE is blocked while unaccepted P0/P1 defects remain")
    return {
        "project_state_unchanged": True,
        "iteration_state": target,
        "repair_rounds": repair_rounds + (1 if current == "QA" and target == "IMPLEMENTING" else 0),
        "qa_verified": current == "QA" and target == "DELTA_DONE",
        "qa_evidence": evidence,
        "persistence_status": "VALIDATED_INPUT_NOT_PERSISTED_BY_THIS_COMMAND",
    }
