from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from oceanpilot.application.case_service import CaseService
from oceanpilot.application.commands import DiagnoseCaseCommand
from oceanpilot.application.errors import CaseNotReady, DiagnosisInputStale
from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    EvidenceAvailability,
    EvidenceCode,
    Priority,
    ResponsibleTeam,
    ReviewReason,
    SourceReliability,
    SourceType,
    StopReason,
    WriteOutcome,
)
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.evidence_policy import create_evidence_item
from oceanpilot.domain.models import (
    AuditEvent,
    CaseInputSnapshot,
    CaseView,
    CommandResult,
    CommitDiagnosisResult,
    DiagnosisDraft,
    DiagnosisSnapshot,
    DiagnosisView,
    EvidenceCreate,
    EvidenceOrigin,
    Hypothesis,
    HypothesisDraft,
    MerchantSuccessCase,
    ReadinessAssessment,
    RoutingDecision,
    TicketDraft,
)

CASE_ID = "00000000-0000-4000-8000-000000000010"
EVIDENCE_ID = "00000000-0000-4000-8000-000000000011"
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"
NOW = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
POLICY_VERSION = "POLICY_V1"
ENGINE_VERSION = "RULES_V1"


class _IdFactory:
    def __init__(self) -> None:
        self.consumed = 0

    def __call__(self) -> str:
        self.consumed += 1
        return f"00000000-0000-4000-8000-{1000 + self.consumed:012d}"


class _Clock:
    def __init__(self) -> None:
        self.consumed = 0

    def __call__(self) -> datetime:
        value = NOW + timedelta(minutes=self.consumed)
        self.consumed += 1
        return value


class _RecordingEngine:
    def __init__(self, draft: DiagnosisDraft) -> None:
        self._draft = draft
        self.calls: list[tuple[MerchantSuccessCase, object, str]] = []

    def evaluate(
        self,
        case: MerchantSuccessCase,
        view: object,
        *,
        policy_version: str,
    ) -> DiagnosisDraft:
        self.calls.append((case, view, policy_version))
        return self._draft


class _ExplodingDependency:
    def __init__(self, label: str) -> None:
        self._label = label
        self.consumed = 0

    def __call__(self):
        self.consumed += 1
        raise AssertionError(f"{self._label} must not be called")


class _FakeStore:
    def __init__(
        self,
        snapshots: Sequence[CaseInputSnapshot],
        *,
        commit_effects: Sequence[Exception | None] = (),
    ) -> None:
        self._snapshots = tuple(snapshots)
        self._commit_effects = tuple(commit_effects)
        self._load_index = 0
        self._commit_index = 0
        self._last_loaded: CaseInputSnapshot | None = None
        self.calls: list[str] = []
        self.session_count = 0
        self.find_calls: list[tuple[str, int, str]] = []
        self.commits: list[
            tuple[int, int, DiagnosisSnapshot, CaseStatus, tuple[AuditEvent, ...]]
        ] = []

    @contextmanager
    def factory(self) -> Iterator["_FakeStore"]:
        self.session_count += 1
        yield self

    def load_case_snapshot(self, case_id: str) -> CaseInputSnapshot | None:
        self.calls.append("load_case_snapshot")
        assert case_id == CASE_ID
        index = min(self._load_index, len(self._snapshots) - 1)
        self._load_index += 1
        self._last_loaded = self._snapshots[index].model_copy(deep=True)
        return self._last_loaded.model_copy(deep=True)

    def find_diagnosis(
        self,
        *,
        case_id: str,
        evidence_revision: int,
        policy_version: str,
    ) -> DiagnosisSnapshot | None:
        self.calls.append("find_diagnosis")
        self.find_calls.append((case_id, evidence_revision, policy_version))
        current = self._last_loaded
        if current is None or current.current_diagnosis is None:
            return None
        diagnosis = current.current_diagnosis
        if (
            diagnosis.evidence_revision == evidence_revision
            and diagnosis.policy_version == policy_version
        ):
            return diagnosis.model_copy(deep=True)
        return None

    def commit_diagnosis_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        snapshot: DiagnosisSnapshot,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> CommitDiagnosisResult:
        self.calls.append("commit_diagnosis_atomic")
        self.commits.append(
            (
                expected_case_revision,
                expected_evidence_revision,
                snapshot.model_copy(deep=True),
                target_status,
                tuple(event.model_copy(deep=True) for event in audit_events),
            )
        )
        index = self._commit_index
        self._commit_index += 1
        if index < len(self._commit_effects):
            effect = self._commit_effects[index]
            if effect is not None:
                raise effect

        current = self._last_loaded
        assert current is not None
        updated_case = current.case.model_copy(
            update={
                "status": target_status,
                "case_revision": expected_case_revision + 1,
                "current_diagnosis_id": snapshot.diagnosis_id,
                "updated_at": max(current.case.updated_at, snapshot.created_at),
            },
            deep=True,
        )
        view = CaseView(
            case=updated_case,
            evidence=current.evidence,
            current_diagnosis=snapshot.model_copy(deep=True),
        )
        return CommitDiagnosisResult(
            outcome=WriteOutcome.CREATED,
            case_view=view,
            diagnosis=snapshot.model_copy(deep=True),
        )


def _readiness(*, ready: bool) -> ReadinessAssessment:
    return ReadinessAssessment(
        ready=ready,
        missing_fields=() if ready else ("transaction.reference", "symptom.status"),
        known_unknown_fields=(),
        next_question=None if ready else "Provide the transaction reference",
        question_reason=None if ready else "Required for diagnosis",
        target_role=None,
        completion_ratio=Decimal("1") if ready else Decimal("0.50"),
        stop_reason=StopReason.READY if ready else StopReason.NEED_MORE_EVIDENCE,
    )


def _evidence():
    return create_evidence_item(
        EvidenceCreate(
            evidence_id=EVIDENCE_ID,
            evidence_code=EvidenceCode.CONTEXT_ENVIRONMENT,
            availability=EvidenceAvailability.AVAILABLE,
            typed_value="PROD",
            observed_at=NOW,
            source_ref="synthetic:diagnose-service",
        ),
        case_id=CASE_ID,
        origin=EvidenceOrigin(
            source_type=SourceType.SYNTHETIC_ADAPTER,
            source_reliability=SourceReliability.SYNTHETIC_TEST,
            synthetic=True,
        ),
        collected_at=NOW,
    )


def _case_input(
    *,
    status: CaseStatus,
    case_revision: int,
    evidence_revision: int,
    diagnosis: DiagnosisSnapshot | None = None,
) -> CaseInputSnapshot:
    ready = status is not CaseStatus.NEED_INFO
    return CaseInputSnapshot(
        case=MerchantSuccessCase(
            case_id=CASE_ID,
            case_type=CaseType.PAYMENT_INCIDENT,
            status=status,
            schema_version="1",
            case_revision=case_revision,
            evidence_revision=evidence_revision,
            synthetic=True,
            summary="Synthetic payment incident",
            merchant_ref="merchant_demo_001",
            created_at=NOW,
            updated_at=NOW,
            current_diagnosis_id=(diagnosis.diagnosis_id if diagnosis is not None else None),
            readiness=_readiness(ready=ready),
        ),
        evidence=(_evidence(),),
        current_diagnosis=diagnosis,
    )


def _draft() -> DiagnosisDraft:
    hypothesis = HypothesisDraft(
        cause_code="SYNTHETIC_CAUSE",
        explanation="Synthetic evidence matches the deterministic rule",
        evidence_refs=(EVIDENCE_ID,),
        confidence_score=Decimal("0.94"),
        confidence_method="HEURISTIC_V1",
        next_verification_action="Verify the synthetic callback",
        rule_id="SYNTHETIC_RULE_V1",
    )
    route = RoutingDecision(
        responsible_team=ResponsibleTeam.TECHNICAL_SUPPORT,
        priority=Priority.MEDIUM,
        reason="Synthetic technical route",
        evidence_refs=(EVIDENCE_ID,),
        requires_human=False,
        review_reasons=frozenset(),
    )
    return DiagnosisDraft(
        hypotheses=(hypothesis,),
        routing_decision=route,
        ticket_draft=TicketDraft(
            title="Synthetic diagnosis",
            summary=hypothesis.explanation,
            evidence_summary=("context.environment=PROD",),
            missing_material=(),
            hypotheses=(hypothesis,),
            next_action=hypothesis.next_verification_action,
            responsible_team=route.responsible_team,
            synthetic=True,
        ),
        requires_human=False,
        review_reasons=frozenset(),
    )


def _persisted_diagnosis() -> DiagnosisSnapshot:
    draft = _draft()
    hypothesis = draft.hypotheses[0]
    return DiagnosisSnapshot(
        diagnosis_id="00000000-0000-4000-8000-000000000050",
        case_id=CASE_ID,
        evidence_revision=1,
        policy_version=POLICY_VERSION,
        engine_version=ENGINE_VERSION,
        status=DiagnosisStatus.CURRENT,
        hypotheses=(
            Hypothesis(
                hypothesis_id="00000000-0000-4000-8000-000000000051",
                **hypothesis.model_dump(mode="python"),
            ),
        ),
        routing_decision=draft.routing_decision,
        ticket_draft=draft.ticket_draft,
        requires_human=draft.requires_human,
        review_reasons=draft.review_reasons,
        synthetic=True,
        created_at=NOW,
    )


def _command() -> DiagnoseCaseCommand:
    return DiagnoseCaseCommand(case_id=CASE_ID, request_id=REQUEST_ID, trace_id=TRACE_ID)


def _service(
    store: _FakeStore,
    *,
    engine: Callable | None = None,
    clock: Callable | None = None,
    ids: Callable | None = None,
) -> tuple[CaseService, object, object, object]:
    resolved_engine = engine or _RecordingEngine(_draft())
    resolved_clock = clock or _Clock()
    resolved_ids = ids or _IdFactory()
    service = CaseService(
        store.factory,
        resolved_engine,
        clock=resolved_clock,
        uuid_factory=resolved_ids,
        policy_version=POLICY_VERSION,
        engine_version=ENGINE_VERSION,
    )
    return service, resolved_engine, resolved_clock, resolved_ids


def test_diagnose_need_info_raises_before_find_engine_clock_or_uuid() -> None:
    store = _FakeStore(
        [_case_input(status=CaseStatus.NEED_INFO, case_revision=3, evidence_revision=1)]
    )
    engine = _ExplodingDependency("engine")
    clock = _ExplodingDependency("clock")
    ids = _ExplodingDependency("uuid")
    service, _, _, _ = _service(store, engine=engine, clock=clock, ids=ids)

    with pytest.raises(CaseNotReady) as caught:
        service.diagnose(_command())

    assert caught.value.case_id == CASE_ID
    assert caught.value.missing_fields == ("transaction.reference", "symptom.status")
    assert caught.value.current_revision == 3
    assert store.calls == ["load_case_snapshot"]
    assert store.session_count == 1
    assert engine.consumed == clock.consumed == ids.consumed == 0


def test_diagnose_replays_current_same_policy_before_engine_or_allocations() -> None:
    diagnosis = _persisted_diagnosis()
    store = _FakeStore(
        [
            _case_input(
                status=CaseStatus.DIAGNOSED,
                case_revision=4,
                evidence_revision=1,
                diagnosis=diagnosis,
            )
        ]
    )
    engine = _ExplodingDependency("engine")
    clock = _ExplodingDependency("clock")
    ids = _ExplodingDependency("uuid")
    service, _, _, _ = _service(store, engine=engine, clock=clock, ids=ids)

    result = service.diagnose(_command())

    assert result == CommandResult(
        outcome=WriteOutcome.REPLAY,
        value=DiagnosisView(
            case_id=CASE_ID,
            case_status=CaseStatus.DIAGNOSED,
            case_revision=4,
            evidence_revision=1,
            diagnosis=diagnosis,
        ),
    )
    assert store.calls == ["load_case_snapshot", "find_diagnosis"]
    assert store.commits == []
    assert engine.consumed == clock.consumed == ids.consumed == 0


def test_diagnose_creates_snapshot_and_exact_audits() -> None:
    store = _FakeStore(
        [_case_input(status=CaseStatus.EVIDENCE_READY, case_revision=6, evidence_revision=1)]
    )
    service, engine, clock, ids = _service(store)

    result = service.diagnose(_command())

    assert result.outcome is WriteOutcome.CREATED
    assert result.value.case_status is CaseStatus.DIAGNOSED
    assert result.value.case_revision == 7
    assert result.value.evidence_revision == 1
    assert len(engine.calls) == 1
    assert engine.calls[0][2] == POLICY_VERSION
    assert clock.consumed == 1
    assert ids.consumed == 5
    assert store.calls == [
        "load_case_snapshot",
        "find_diagnosis",
        "commit_diagnosis_atomic",
    ]
    expected_case_revision, expected_evidence_revision, snapshot, target, audits = store.commits[0]
    assert (expected_case_revision, expected_evidence_revision) == (6, 1)
    assert snapshot == result.value.diagnosis
    assert snapshot.policy_version == POLICY_VERSION
    assert snapshot.engine_version == ENGINE_VERSION
    assert snapshot.status is DiagnosisStatus.CURRENT
    assert snapshot.created_at == NOW
    assert snapshot.hypotheses[0].hypothesis_id == ("00000000-0000-4000-8000-000000001002")
    assert target is CaseStatus.DIAGNOSED
    assert tuple(event.event_type for event in audits) == (
        AuditEventType.DIAGNOSIS_CREATED,
        AuditEventType.ROUTING_PROPOSED,
        AuditEventType.STATE_TRANSITIONED,
    )
    assert all(event.actor_type is AuditActorType.INTERNAL_SYSTEM for event in audits)
    assert all(event.action == "diagnose" for event in audits)
    assert all(event.from_status is CaseStatus.EVIDENCE_READY for event in audits)
    assert all(event.to_status is CaseStatus.DIAGNOSED for event in audits)
    assert all(event.case_revision == 7 for event in audits)
    assert all(event.evidence_revision == 1 for event in audits)
    assert all(event.request_id == REQUEST_ID for event in audits)
    assert all(event.trace_id == TRACE_ID for event in audits)
    assert all(event.occurred_at == NOW for event in audits)


def test_diagnose_human_only_omits_route_audit_and_targets_review() -> None:
    store = _FakeStore(
        [_case_input(status=CaseStatus.EVIDENCE_READY, case_revision=6, evidence_revision=1)]
    )
    draft = DiagnosisDraft(
        hypotheses=(),
        routing_decision=None,
        ticket_draft=None,
        requires_human=True,
        review_reasons=frozenset({ReviewReason.POLICY_GAP}),
    )
    engine = _RecordingEngine(draft)
    service, _, clock, ids = _service(store, engine=engine)

    result = service.diagnose(_command())

    assert result.value.case_status is CaseStatus.HUMAN_REVIEW
    assert result.value.diagnosis.hypotheses == ()
    assert result.value.diagnosis.routing_decision is None
    assert result.value.diagnosis.ticket_draft is None
    assert result.value.diagnosis.review_reasons == frozenset({ReviewReason.POLICY_GAP})
    _, _, _, target, audits = store.commits[0]
    assert target is CaseStatus.HUMAN_REVIEW
    assert tuple(event.event_type for event in audits) == (
        AuditEventType.DIAGNOSIS_CREATED,
        AuditEventType.STATE_TRANSITIONED,
    )
    assert all(event.to_status is CaseStatus.HUMAN_REVIEW for event in audits)
    assert clock.consumed == 1
    assert ids.consumed == 3


def test_diagnose_reloads_and_reevaluates_at_most_three_stale_inputs() -> None:
    store = _FakeStore(
        [
            _case_input(
                status=CaseStatus.EVIDENCE_READY,
                case_revision=revision + 5,
                evidence_revision=revision,
            )
            for revision in (1, 2, 3)
        ],
        commit_effects=(DiagnosisInputStale(), DiagnosisInputStale(), None),
    )
    service, engine, clock, ids = _service(store)

    result = service.diagnose(_command())

    assert result.outcome is WriteOutcome.CREATED
    assert [commit[1] for commit in store.commits] == [1, 2, 3]
    assert len(engine.calls) == 3
    assert clock.consumed == 3
    assert ids.consumed == 15
    assert store.session_count == 1


def test_diagnose_raises_third_stale_input_without_a_fourth_attempt() -> None:
    store = _FakeStore(
        [
            _case_input(
                status=CaseStatus.EVIDENCE_READY,
                case_revision=revision + 5,
                evidence_revision=revision,
            )
            for revision in (1, 2, 3)
        ],
        commit_effects=(DiagnosisInputStale(), DiagnosisInputStale(), DiagnosisInputStale()),
    )
    service, engine, clock, ids = _service(store)

    with pytest.raises(DiagnosisInputStale):
        service.diagnose(_command())

    assert len(store.commits) == 3
    assert len(engine.calls) == 3
    assert clock.consumed == 3
    assert ids.consumed == 15
    assert store.session_count == 1


def test_diagnose_rejects_sensitive_command_before_opening_store() -> None:
    store = _FakeStore(
        [_case_input(status=CaseStatus.EVIDENCE_READY, case_revision=6, evidence_revision=1)]
    )
    service, engine, clock, ids = _service(store)
    command = _command().model_copy(update={"case_id": "Authorization: Bearer synthetic-secret"})

    with pytest.raises(SensitiveDataRejected):
        service.diagnose(command)

    assert store.session_count == 0
    assert store.calls == []
    assert engine.calls == []
    assert clock.consumed == ids.consumed == 0
