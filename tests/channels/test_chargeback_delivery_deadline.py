from datetime import UTC, datetime, timedelta

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.adapters.persistence.chargeback_memory import InMemoryChargebackCaseStore
from oceanpilot.application.channels import InboundKind, NormalizedInbound
from oceanpilot.application.chargeback_agents import (
    ChargebackAssessAgent,
    EvidenceAgent,
    IntakeAgent,
)
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.chargeback_deadline import DeadlinePhase, DeadlineTracker
from oceanpilot.application.chargeback_supervisor import ChargebackSupervisor

_CREATED = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)


class _FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _supervisor():
    model = ScriptedModelProvider(default_text="（合成）")
    return ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )


def _service(now: datetime) -> ChargebackChannelService:
    store = InMemoryChargebackCaseStore(clock=_FixedClock(_CREATED))
    return ChargebackChannelService(
        _supervisor(), store, deadline=DeadlineTracker(_FixedClock(now))
    )


def _open(service: ChargebackChannelService):
    return service.handle(
        NormalizedInbound(kind=InboundKind.OPEN_CASE, channel="test", description="没收到货")
    )


def test_delivery_includes_evidence_window_deadline():
    # 5 days after creation -> 10 days remain in the 15-day evidence window.
    delivery = _open(_service(_CREATED + timedelta(days=5)))
    assert delivery.deadline is not None
    assert delivery.deadline.phase == DeadlinePhase.COLLECTING_EVIDENCE.value
    assert delivery.deadline.days_remaining == 10
    assert delivery.deadline.overdue is False
    assert delivery.deadline.deadline_at.startswith("2026-08-16")


def test_overdue_evidence_window_is_flagged():
    delivery = _open(_service(_CREATED + timedelta(days=20)))
    assert delivery.deadline is not None
    assert delivery.deadline.overdue is True
    assert delivery.deadline.days_remaining < 0


def test_no_tracker_means_no_deadline():
    service = ChargebackChannelService(_supervisor(), InMemoryChargebackCaseStore())
    assert _open(service).deadline is None
