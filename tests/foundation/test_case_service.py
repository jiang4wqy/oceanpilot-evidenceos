from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.application.case_service import CaseService
from oceanpilot.application.commands import AddEvidenceCommand, CreateCaseCommand
from oceanpilot.application.errors import (
    CaseNotFound,
    CaseTypeNotEnabled,
    ConcurrentCaseWrite,
)
from oceanpilot.domain.enums import (
    AuditEventType,
    CaseStatus,
    CaseType,
    EvidenceAvailability,
    EvidenceCode,
    SourceReliability,
    SourceType,
    WriteOutcome,
)
from oceanpilot.domain.evidence_policy import (
    assess_readiness,
    build_active_evidence_view,
    create_evidence_item,
)
from oceanpilot.domain.models import (
    AppendEvidenceResult,
    AuditEvent,
    CaseInputSnapshot,
    CaseView,
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    MerchantSuccessCase,
    ReadinessAssessment,
)

CASE_ID = "00000000-0000-4000-8000-000000000010"
EVIDENCE_ID = "00000000-0000-4000-8000-000000000011"
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"
CASE_CREATED_EVENT_ID = "00000000-0000-4000-8000-000000000060"
EVIDENCE_ADDED_EVENT_ID = "00000000-0000-4000-8000-000000000061"
DIAGNOSIS_SUPERSEDED_EVENT_ID = "00000000-0000-4000-8000-000000000062"
STATE_TRANSITIONED_EVENT_ID = "00000000-0000-4000-8000-000000000063"
NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)


class _IdFactory:
    def __init__(self) -> None:
        self._values = (
            CASE_ID,
            CASE_CREATED_EVENT_ID,
            EVIDENCE_ADDED_EVENT_ID,
            DIAGNOSIS_SUPERSEDED_EVENT_ID,
            STATE_TRANSITIONED_EVENT_ID,
        )
        self.consumed = 0

    def __call__(self) -> str:
        value = self._values[self.consumed]
        self.consumed += 1
        return value


def _copy_view(view: CaseView | None) -> CaseView | None:
    return None if view is None else view.model_copy(deep=True)


class _FakeStore:
    def __init__(
        self,
        *,
        case_view: CaseView | None,
        append_error: Exception | None,
    ) -> None:
        self._case_view = _copy_view(case_view)
        self._append_error = append_error
        self.calls: list[str] = []
        self.session_count = 0
        self.load_count = 0
        self.created_case: MerchantSuccessCase | None = None
        self.created_audit: AuditEvent | None = None
        self.appended_evidence: EvidenceItem | None = None
        self.appended_readiness: ReadinessAssessment | None = None
        self.appended_audits: tuple[AuditEvent, ...] = ()

    @contextmanager
    def factory(self) -> Iterator[_FakeStore]:
        self.session_count += 1
        yield self

    def create_case_atomic(
        self,
        *,
        case: MerchantSuccessCase,
        audit: AuditEvent,
    ) -> CaseView:
        self.calls.append("create_case_atomic")
        self.created_case = case.model_copy(deep=True)
        self.created_audit = audit.model_copy(deep=True)
        return CaseView(
            case=self.created_case.model_copy(deep=True),
            evidence=(),
            current_diagnosis=None,
        )

    def get_case_view(self, case_id: str) -> CaseView | None:
        self.calls.append("get_case_view")
        assert case_id == CASE_ID
        return _copy_view(self._case_view)

    def load_case_snapshot(self, case_id: str) -> CaseInputSnapshot | None:
        self.calls.append("load_case_snapshot")
        self.load_count += 1
        assert case_id == CASE_ID
        view = _copy_view(self._case_view)
        if view is None:
            return None
        return CaseInputSnapshot(
            case=view.case,
            evidence=view.evidence,
            current_diagnosis=view.current_diagnosis,
        )

    def append_evidence_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        evidence: EvidenceItem,
        readiness: ReadinessAssessment,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> AppendEvidenceResult:
        self.calls.append("append_evidence_atomic")
        self.appended_evidence = evidence.model_copy(deep=True)
        self.appended_readiness = readiness.model_copy(deep=True)
        self.appended_audits = tuple(event.model_copy(deep=True) for event in audit_events)
        if self._append_error is not None:
            raise self._append_error

        view = _copy_view(self._case_view)
        assert view is not None
        replay = any(item.evidence_id == evidence.evidence_id for item in view.evidence)
        if replay:
            return AppendEvidenceResult(
                outcome=WriteOutcome.REPLAY,
                case_view=view,
            )

        updated_case = view.case.model_copy(
            update={
                "status": target_status,
                "case_revision": expected_case_revision + 1,
                "evidence_revision": expected_evidence_revision + 1,
                "updated_at": max(view.case.updated_at, evidence.collected_at),
                "current_diagnosis_id": None,
                "readiness": readiness.model_copy(deep=True),
            },
            deep=True,
        )
        return AppendEvidenceResult(
            outcome=WriteOutcome.CREATED,
            case_view=CaseView(
                case=updated_case,
                evidence=(*view.evidence, evidence.model_copy(deep=True)),
                current_diagnosis=None,
            ),
        )


def create_command(
    *,
    case_type: CaseType = CaseType.PAYMENT_INCIDENT,
) -> CreateCaseCommand:
    return CreateCaseCommand(
        case_type=case_type,
        summary="Synthetic payment incident",
        merchant_ref="merchant_demo_001",
        synthetic=True,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
    )


def add_environment_command() -> AddEvidenceCommand:
    return AddEvidenceCommand(
        case_id=CASE_ID,
        evidence=EvidenceCreate(
            evidence_id=EVIDENCE_ID,
            evidence_code=EvidenceCode.CONTEXT_ENVIRONMENT,
            availability=EvidenceAvailability.AVAILABLE,
            typed_value="PROD",
            observed_at=NOW,
            source_ref="synthetic:fixture",
        ),
        origin=EvidenceOrigin(
            source_type=SourceType.SYNTHETIC_ADAPTER,
            source_reliability=SourceReliability.SYNTHETIC_TEST,
            synthetic=True,
        ),
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
    )


def empty_case_view() -> CaseView:
    readiness = assess_readiness(build_active_evidence_view(()))
    return CaseView(
        case=MerchantSuccessCase(
            case_id=CASE_ID,
            case_type=CaseType.PAYMENT_INCIDENT,
            status=CaseStatus.NEED_INFO,
            schema_version="1",
            case_revision=1,
            evidence_revision=0,
            synthetic=True,
            summary="Synthetic payment incident",
            merchant_ref="merchant_demo_001",
            created_at=NOW,
            updated_at=NOW,
            current_diagnosis_id=None,
            readiness=readiness,
        ),
        evidence=(),
        current_diagnosis=None,
    )


def case_view_with_environment() -> CaseView:
    command = add_environment_command()
    evidence = create_evidence_item(
        command.evidence,
        case_id=command.case_id,
        origin=command.origin,
        collected_at=NOW,
    )
    readiness = assess_readiness(build_active_evidence_view((evidence,)))
    view = empty_case_view()
    return CaseView(
        case=view.case.model_copy(
            update={
                "case_revision": 2,
                "evidence_revision": 1,
                "readiness": readiness,
            },
            deep=True,
        ),
        evidence=(evidence,),
        current_diagnosis=None,
    )


def make_service(
    *,
    case_view: CaseView | None = None,
    append_error: Exception | None = None,
) -> tuple[CaseService, _FakeStore, _IdFactory]:
    fake = _FakeStore(case_view=case_view, append_error=append_error)
    ids = _IdFactory()
    service = CaseService(
        fake.factory,
        RuleDiagnosisEngine(),
        clock=lambda: NOW,
        uuid_factory=ids,
    )
    return service, fake, ids


def test_create_case_builds_revision_one_and_case_created_audit():
    service, fake, ids = make_service()
    view = service.create_case(create_command())
    assert view.case.case_revision == 1
    assert view.case.evidence_revision == 0
    assert fake.created_audit is not None
    assert fake.created_audit.event_type is AuditEventType.CASE_CREATED
    assert ids.consumed == 2  # case ID, event ID
    assert fake.session_count == 1
    assert fake.calls == ["create_case_atomic"]


def test_create_case_uses_internal_preallocated_case_id_without_allocating_one():
    service, fake, ids = make_service()

    view = service.create_case(create_command().model_copy(update={"case_id": CASE_ID}))

    assert view.case.case_id == CASE_ID
    assert ids.consumed == 1  # event ID only


def test_get_case_raises_stable_not_found():
    service, fake, _ = make_service(case_view=None)
    with pytest.raises(CaseNotFound):
        service.get_case(CASE_ID)
    assert fake.session_count == 1
    assert fake.calls == ["get_case_view"]


def test_create_rejects_disabled_case_type_without_store_call():
    service, fake, _ = make_service()
    with pytest.raises(CaseTypeNotEnabled):
        service.create_case(create_command(case_type=CaseType.ONBOARDING_RECOMMENDATION))
    assert fake.calls == []


def test_add_evidence_recomputes_readiness_and_emits_exact_audits():
    service, fake, _ = make_service(case_view=empty_case_view())
    result = service.add_evidence(add_environment_command())
    assert result.outcome is WriteOutcome.CREATED
    assert fake.appended_evidence is not None
    assert fake.appended_readiness == assess_readiness(
        build_active_evidence_view((fake.appended_evidence,))
    )
    assert {event.event_type for event in fake.appended_audits} == {
        AuditEventType.EVIDENCE_ADDED,
    }
    assert fake.session_count == 1
    assert fake.calls == ["load_case_snapshot", "append_evidence_atomic"]


def test_existing_evidence_uses_store_replay_without_allocating_audit_ids():
    service, fake, ids = make_service(case_view=case_view_with_environment())
    result = service.add_evidence(add_environment_command())
    assert result.outcome is WriteOutcome.REPLAY
    assert fake.appended_audits == ()
    assert ids.consumed == 0
    assert fake.session_count == 1
    assert fake.calls == ["load_case_snapshot", "append_evidence_atomic"]


def test_foundation_service_does_not_retry_concurrent_write():
    service, fake, _ = make_service(
        case_view=empty_case_view(), append_error=ConcurrentCaseWrite()
    )
    with pytest.raises(ConcurrentCaseWrite):
        service.add_evidence(add_environment_command())
    assert fake.load_count == 1
    assert fake.session_count == 1
    assert fake.calls == ["load_case_snapshot", "append_evidence_atomic"]
