from datetime import UTC, datetime, timedelta

from oceanpilot.application.chargeback_deadline import (
    EVIDENCE_WINDOW_DAYS,
    DeadlinePhase,
    DeadlineTracker,
)
from oceanpilot.application.scheduling import Clock

CREATED = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
SUBMITTED = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _tracker(moment: datetime) -> DeadlineTracker:
    return DeadlineTracker(FixedClock(moment))


def test_fixed_clock_satisfies_clock_protocol():
    assert isinstance(FixedClock(CREATED), Clock)


def test_evidence_phase_on_track_no_reminder():
    outcome = _tracker(CREATED + timedelta(days=1)).evaluate(created_at=CREATED)
    assert outcome.phase is DeadlinePhase.COLLECTING_EVIDENCE
    assert outcome.days_remaining == 14
    assert outcome.overdue is False
    assert outcome.reminder_due is False
    assert outcome.auto_lost is False


def test_reminders_fire_at_t7_t3_t1():
    for offset in (7, 3, 1):
        moment = CREATED + timedelta(days=EVIDENCE_WINDOW_DAYS - offset)
        outcome = _tracker(moment).evaluate(created_at=CREATED)
        assert outcome.days_remaining == offset
        assert outcome.reminder_due is True
        assert outcome.reminder_offset == offset


def test_no_reminder_on_non_node_day():
    moment = CREATED + timedelta(days=EVIDENCE_WINDOW_DAYS - 5)  # T-5
    outcome = _tracker(moment).evaluate(created_at=CREATED)
    assert outcome.days_remaining == 5
    assert outcome.reminder_due is False
    assert outcome.reminder_offset is None


def test_evidence_overdue_auto_loses():
    outcome = _tracker(CREATED + timedelta(days=16)).evaluate(created_at=CREATED)
    assert outcome.overdue is True
    assert outcome.auto_lost is True
    assert outcome.reminder_due is False


def test_review_phase_uses_45_day_window():
    outcome = _tracker(SUBMITTED + timedelta(days=40)).evaluate(
        created_at=CREATED, submitted_at=SUBMITTED
    )
    assert outcome.phase is DeadlinePhase.AWAITING_REVIEW
    assert outcome.days_remaining == 5
    assert outcome.overdue is False


def test_review_overdue_is_not_merchant_auto_loss():
    outcome = _tracker(SUBMITTED + timedelta(days=46)).evaluate(
        created_at=CREATED, submitted_at=SUBMITTED
    )
    assert outcome.phase is DeadlinePhase.AWAITING_REVIEW
    assert outcome.overdue is True
    assert outcome.auto_lost is False  # issuer's clock, escalated not lost


def test_resolved_case_is_closed():
    outcome = _tracker(CREATED + timedelta(days=100)).evaluate(created_at=CREATED, resolved=True)
    assert outcome.phase is DeadlinePhase.CLOSED
    assert outcome.deadline_at is None
    assert outcome.overdue is False
