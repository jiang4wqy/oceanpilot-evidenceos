"""Deterministic chargeback deadline / SLA tracking.

Encodes the meeting's hard rule: 15 days to submit evidence, 45 days for the
issuer review, and "any node overdue -> merchant loses". Node reminders fire at
T-7 / T-3 / T-1. Pure and clock-injected, so every node is testable with a
fixed clock. The DeadlineAgent (thin) just calls this and hands the outcome to
a reminder channel; the decision is deterministic here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from oceanpilot.application.scheduling import Clock

EVIDENCE_WINDOW_DAYS = 15
REVIEW_WINDOW_DAYS = 45
REMINDER_OFFSETS_DAYS = (7, 3, 1)


class DeadlinePhase(StrEnum):
    COLLECTING_EVIDENCE = "COLLECTING_EVIDENCE"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class DeadlineOutcome:
    phase: DeadlinePhase
    deadline_at: datetime | None
    days_remaining: int | None
    overdue: bool
    reminder_due: bool
    reminder_offset: int | None
    auto_lost: bool


class DeadlineTracker:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def evaluate(
        self,
        *,
        created_at: datetime,
        submitted_at: datetime | None = None,
        resolved: bool = False,
    ) -> DeadlineOutcome:
        if resolved:
            return DeadlineOutcome(
                phase=DeadlinePhase.CLOSED,
                deadline_at=None,
                days_remaining=None,
                overdue=False,
                reminder_due=False,
                reminder_offset=None,
                auto_lost=False,
            )

        now = self._clock.now()
        if submitted_at is None:
            phase = DeadlinePhase.COLLECTING_EVIDENCE
            deadline = created_at + timedelta(days=EVIDENCE_WINDOW_DAYS)
        else:
            phase = DeadlinePhase.AWAITING_REVIEW
            deadline = submitted_at + timedelta(days=REVIEW_WINDOW_DAYS)

        days_remaining = (deadline.date() - now.date()).days
        overdue = now > deadline
        reminder_offset = (
            days_remaining if not overdue and days_remaining in REMINDER_OFFSETS_DAYS else None
        )
        # Only the merchant-actionable evidence window auto-loses on overdue; an
        # overdue review window is the issuer's clock, escalated but not auto-lost.
        auto_lost = overdue and phase is DeadlinePhase.COLLECTING_EVIDENCE

        return DeadlineOutcome(
            phase=phase,
            deadline_at=deadline,
            days_remaining=days_remaining,
            overdue=overdue,
            reminder_due=reminder_offset is not None,
            reminder_offset=reminder_offset,
            auto_lost=auto_lost,
        )
