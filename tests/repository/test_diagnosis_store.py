import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from queue import Queue
from threading import Barrier, Thread

import pytest

from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    SqliteCaseStoreSession,
    connect_sqlite,
    initialize_schema,
)
from oceanpilot.application.errors import (
    ConcurrentCaseWrite,
    DiagnosisInputStale,
    PersistenceInvariantViolation,
)
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
    WriteOutcome,
)
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.evidence_policy import (
    assess_readiness,
    build_active_evidence_view,
    create_evidence_item,
)
from oceanpilot.domain.models import (
    AuditEvent,
    DiagnosisSnapshot,
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    Hypothesis,
    HypothesisDraft,
    MerchantSuccessCase,
    RoutingDecision,
    TicketDraft,
)
from oceanpilot.domain.state_machine import status_after_creation, status_after_evidence

CASE_ID = "00000000-0000-4000-8000-000000000010"
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
HYPOTHESIS_ID = "00000000-0000-4000-8000-000000000301"
BASE_TIME = datetime(2026, 7, 18, 4, 0, tzinfo=UTC)


def _factory(db_path: Path) -> SqliteCaseStoreFactory:
    initialize_schema(db_path)
    return SqliteCaseStoreFactory(db_path)


def _audit(
    event_type: AuditEventType,
    *,
    event_id: str,
    action: str,
    from_status: CaseStatus | None,
    to_status: CaseStatus,
    case_revision: int,
    evidence_revision: int,
    case_id: str = CASE_ID,
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        event_type=event_type,
        event_version="1",
        case_id=case_id,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        actor_type=AuditActorType.SYNTHETIC_ADAPTER,
        action=action,
        from_status=from_status,
        to_status=to_status,
        case_revision=case_revision,
        evidence_revision=evidence_revision,
        occurred_at=BASE_TIME + timedelta(minutes=case_revision),
        result="CREATED",
        reason_code=None,
        sanitized_metadata={"event": event_type.value},
        synthetic=True,
    )


def _evidence(
    evidence_id: str,
    code: EvidenceCode,
    value: str | datetime,
    *,
    case_id: str = CASE_ID,
) -> EvidenceItem:
    return create_evidence_item(
        EvidenceCreate(
            evidence_id=evidence_id,
            evidence_code=code,
            availability=EvidenceAvailability.AVAILABLE,
            typed_value=value,
            observed_at=BASE_TIME + timedelta(minutes=5),
            source_ref="synthetic:diagnosis-store",
        ),
        case_id=case_id,
        origin=EvidenceOrigin(
            source_type=SourceType.SYNTHETIC_ADAPTER,
            source_reliability=SourceReliability.SYNTHETIC_TEST,
            synthetic=True,
        ),
        collected_at=BASE_TIME + timedelta(minutes=10),
    )


def _ready_evidence() -> tuple[EvidenceItem, ...]:
    return (
        _evidence(
            "00000000-0000-4000-8000-000000000101",
            EvidenceCode.TRANSACTION_REFERENCE,
            "txn_001",
        ),
        _evidence(
            "00000000-0000-4000-8000-000000000102",
            EvidenceCode.TRANSACTION_OCCURRED_AT,
            BASE_TIME + timedelta(minutes=1),
        ),
        _evidence(
            "00000000-0000-4000-8000-000000000103",
            EvidenceCode.CONTEXT_ENVIRONMENT,
            "PROD",
        ),
        _evidence(
            "00000000-0000-4000-8000-000000000104",
            EvidenceCode.SYMPTOM_STATUS,
            "FAILED",
        ),
        _evidence(
            "00000000-0000-4000-8000-000000000105",
            EvidenceCode.INTEGRATION_TYPE,
            "API",
        ),
    )


def _prepare_ready_case(factory: SqliteCaseStoreFactory) -> None:
    empty_readiness = assess_readiness(build_active_evidence_view(()))
    case = MerchantSuccessCase(
        case_id=CASE_ID,
        case_type=CaseType.PAYMENT_INCIDENT,
        status=status_after_creation(empty_readiness),
        schema_version="1",
        case_revision=1,
        evidence_revision=0,
        synthetic=True,
        summary="Synthetic payment incident",
        merchant_ref="merchant_demo_001",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        current_diagnosis_id=None,
        readiness=empty_readiness,
    )
    with factory() as store:
        store.create_case_atomic(
            case=case,
            audit=_audit(
                AuditEventType.CASE_CREATED,
                event_id="00000000-0000-4000-8000-000000000060",
                action="create_case",
                from_status=None,
                to_status=CaseStatus.NEED_INFO,
                case_revision=1,
                evidence_revision=0,
            ),
        )

    existing: list[EvidenceItem] = []
    current_status = CaseStatus.NEED_INFO
    for index, item in enumerate(_ready_evidence(), start=1):
        readiness = assess_readiness(build_active_evidence_view((*existing, item)))
        target_status = status_after_evidence(current_status, readiness)
        audit_types = [AuditEventType.EVIDENCE_ADDED]
        if target_status is not current_status:
            audit_types.append(AuditEventType.STATE_TRANSITIONED)
        audits = tuple(
            _audit(
                event_type,
                event_id=f"00000000-0000-4000-8000-{1000 + index * 10 + offset:012d}",
                action="append_evidence",
                from_status=current_status,
                to_status=target_status,
                case_revision=index + 1,
                evidence_revision=index,
            )
            for offset, event_type in enumerate(audit_types)
        )
        with factory() as store:
            store.append_evidence_atomic(
                expected_case_revision=index,
                expected_evidence_revision=index - 1,
                evidence=item,
                readiness=readiness,
                target_status=target_status,
                audit_events=audits,
            )
        existing.append(item)
        current_status = target_status


def _diagnosis_snapshot() -> DiagnosisSnapshot:
    evidence_refs = (
        "00000000-0000-4000-8000-000000000101",
        "00000000-0000-4000-8000-000000000103",
    )
    hypothesis = Hypothesis(
        hypothesis_id=HYPOTHESIS_ID,
        cause_code="THREEDS_CALLBACK_INCOMPLETE",
        explanation="Authentication callback was not completed",
        evidence_refs=evidence_refs,
        confidence_score=Decimal("0.91"),
        confidence_method="HEURISTIC_V1",
        next_verification_action="Verify the callback delivery log",
        rule_id="THREEDS_INCOMPLETE_V1",
    )
    draft = HypothesisDraft(
        cause_code=hypothesis.cause_code,
        explanation=hypothesis.explanation,
        evidence_refs=hypothesis.evidence_refs,
        confidence_score=hypothesis.confidence_score,
        confidence_method=hypothesis.confidence_method,
        next_verification_action=hypothesis.next_verification_action,
        rule_id=hypothesis.rule_id,
    )
    route = RoutingDecision(
        responsible_team=ResponsibleTeam.TECHNICAL_SUPPORT,
        priority=Priority.MEDIUM,
        reason="Authentication callback evidence indicates an integration issue",
        evidence_refs=evidence_refs,
        requires_human=False,
        review_reasons=frozenset(),
    )
    return DiagnosisSnapshot(
        diagnosis_id=DIAGNOSIS_ID,
        case_id=CASE_ID,
        evidence_revision=5,
        policy_version="POLICY_V1",
        engine_version="ENGINE_V1",
        status=DiagnosisStatus.CURRENT,
        hypotheses=(hypothesis,),
        routing_decision=route,
        ticket_draft=TicketDraft(
            title="Synthetic diagnosis ticket",
            summary=hypothesis.explanation,
            evidence_summary=("Synthetic evidence set",),
            missing_material=(),
            hypotheses=(draft,),
            next_action=hypothesis.next_verification_action,
            responsible_team=route.responsible_team,
            synthetic=True,
        ),
        requires_human=False,
        review_reasons=frozenset(),
        synthetic=True,
        created_at=BASE_TIME + timedelta(hours=1),
    )


def _diagnosis_audits() -> Sequence[AuditEvent]:
    return tuple(
        _audit(
            event_type,
            event_id=f"00000000-0000-4000-8000-{2000 + offset:012d}",
            action="commit_diagnosis",
            from_status=CaseStatus.EVIDENCE_READY,
            to_status=CaseStatus.DIAGNOSED,
            case_revision=7,
            evidence_revision=5,
        )
        for offset, event_type in enumerate(
            (
                AuditEventType.DIAGNOSIS_CREATED,
                AuditEventType.ROUTING_PROPOSED,
                AuditEventType.STATE_TRANSITIONED,
            )
        )
    )


def test_commit_diagnosis_persists_complete_graph_across_database_reopen(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    snapshot = _diagnosis_snapshot()

    with factory() as store:
        result = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=snapshot,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    assert result.outcome is WriteOutcome.CREATED
    assert result.diagnosis == snapshot
    assert result.case_view.case.status is CaseStatus.DIAGNOSED
    assert result.case_view.case.case_revision == 7
    assert result.case_view.case.current_diagnosis_id == DIAGNOSIS_ID
    assert result.case_view.case.updated_at == snapshot.created_at

    with factory() as reopened_store:
        persisted = reopened_store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )
        case_view = reopened_store.get_case_view(CASE_ID)

    assert persisted == snapshot
    assert case_view is not None
    assert case_view.current_diagnosis == snapshot


def test_commit_diagnosis_replays_the_existing_unique_revision_and_policy(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    original = _diagnosis_snapshot()
    with factory() as store:
        created = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=original,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    competing_hypothesis = original.hypotheses[0].model_copy(
        update={"hypothesis_id": "00000000-0000-4000-8000-000000000302"}
    )
    competing = original.model_copy(
        update={
            "diagnosis_id": "00000000-0000-4000-8000-000000000051",
            "hypotheses": (competing_hypothesis,),
            "created_at": original.created_at + timedelta(minutes=1),
        }
    )
    replay_audits = tuple(
        event.model_copy(
            update={"event_id": f"00000000-0000-4000-8000-{2100 + index:012d}"}
        )
        for index, event in enumerate(_diagnosis_audits())
    )
    with factory() as store:
        replayed = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=competing,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=replay_audits,
        )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )

    assert created.outcome is WriteOutcome.CREATED
    assert replayed.outcome is WriteOutcome.REPLAY
    assert replayed.diagnosis == original
    assert replayed.case_view == created.case_view
    assert persisted == original


def test_commit_diagnosis_rejects_stale_evidence_before_unique_key_replay(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    snapshot = _diagnosis_snapshot()
    with factory() as store:
        store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=snapshot,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    added = _evidence(
        "00000000-0000-4000-8000-000000000106",
        EvidenceCode.PAYMENT_METHOD,
        "CARD",
    )
    readiness = assess_readiness(build_active_evidence_view((*_ready_evidence(), added)))
    with factory() as store:
        store.append_evidence_atomic(
            expected_case_revision=7,
            expected_evidence_revision=5,
            evidence=added,
            readiness=readiness,
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=tuple(
                _audit(
                    event_type,
                    event_id=f"00000000-0000-4000-8000-{2200 + index:012d}",
                    action="append_evidence",
                    from_status=CaseStatus.DIAGNOSED,
                    to_status=CaseStatus.EVIDENCE_READY,
                    case_revision=8,
                    evidence_revision=6,
                )
                for index, event_type in enumerate(
                    (
                        AuditEventType.EVIDENCE_ADDED,
                        AuditEventType.DIAGNOSIS_SUPERSEDED,
                        AuditEventType.STATE_TRANSITIONED,
                    )
                )
            ),
        )

    with factory() as store:
        with pytest.raises(DiagnosisInputStale):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=snapshot,
                target_status=CaseStatus.DIAGNOSED,
                audit_events=_diagnosis_audits(),
            )
        current = store.get_case_view(CASE_ID)

    assert current is not None
    assert current.case.case_revision == 8
    assert current.case.evidence_revision == 6
    assert current.case.current_diagnosis_id is None


def test_commit_diagnosis_canonicalizes_evidence_reference_order(db_path: Path) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    original = _diagnosis_snapshot()
    reversed_refs = tuple(reversed(original.hypotheses[0].evidence_refs))
    hypothesis = original.hypotheses[0].model_copy(
        update={"evidence_refs": reversed_refs}
    )
    route = original.routing_decision
    ticket = original.ticket_draft
    assert route is not None
    assert ticket is not None
    snapshot = original.model_copy(
        update={
            "hypotheses": (hypothesis,),
            "routing_decision": route.model_copy(update={"evidence_refs": reversed_refs}),
            "ticket_draft": ticket.model_copy(
                update={
                    "hypotheses": (
                        ticket.hypotheses[0].model_copy(
                            update={"evidence_refs": reversed_refs}
                        ),
                    )
                }
            ),
        }
    )

    with factory() as store:
        result = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=snapshot,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    persisted = result.diagnosis
    assert persisted.hypotheses[0].evidence_refs == original.hypotheses[0].evidence_refs
    assert persisted.routing_decision is not None
    assert persisted.routing_decision.evidence_refs == original.hypotheses[0].evidence_refs
    assert persisted.ticket_draft is not None
    assert (
        persisted.ticket_draft.hypotheses[0].evidence_refs
        == original.hypotheses[0].evidence_refs
    )


def test_commit_diagnosis_rejects_case_revision_conflict_without_writing(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)

    with factory() as store:
        with pytest.raises(ConcurrentCaseWrite):
            store.commit_diagnosis_atomic(
                expected_case_revision=5,
                expected_evidence_revision=5,
                snapshot=_diagnosis_snapshot(),
                target_status=CaseStatus.DIAGNOSED,
                audit_events=_diagnosis_audits(),
            )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )
        current = store.get_case_view(CASE_ID)

    assert persisted is None
    assert current is not None
    assert current.case.status is CaseStatus.EVIDENCE_READY
    assert current.case.case_revision == 6
    assert current.case.current_diagnosis_id is None


def test_find_diagnosis_rejects_sensitive_persisted_content(db_path: Path) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    with factory() as store:
        store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=_diagnosis_snapshot(),
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    connection = connect_sqlite(db_path)
    try:
        ticket_raw = connection.execute(
            "SELECT ticket_json FROM diagnosis_snapshots WHERE diagnosis_id = ?",
            (DIAGNOSIS_ID,),
        ).fetchone()[0]
        ticket = json.loads(ticket_raw)
        sensitive = "Authorization: Bearer synthetic-secret"
        ticket["summary"] = sensitive
        ticket["hypotheses"][0]["explanation"] = sensitive
        connection.execute(
            "UPDATE hypotheses SET explanation = ? WHERE hypothesis_id = ?",
            (sensitive, HYPOTHESIS_ID),
        )
        connection.execute(
            "UPDATE diagnosis_snapshots SET ticket_json = ? WHERE diagnosis_id = ?",
            (json.dumps(ticket, separators=(",", ":"), sort_keys=True), DIAGNOSIS_ID),
        )
    finally:
        connection.close()

    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation) as captured:
            store.find_diagnosis(
                case_id=CASE_ID,
                evidence_revision=5,
                policy_version="POLICY_V1",
            )
        missing = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="MISSING_POLICY",
        )

    assert str(captured.value) == "persistence invariant was violated"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert missing is None


def _assert_commit_diagnosis_rejects_evidence_owned_by_another_case_atomically(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    foreign_case_id = "00000000-0000-4000-8000-000000000020"
    empty_readiness = assess_readiness(build_active_evidence_view(()))
    foreign_case = MerchantSuccessCase(
        case_id=foreign_case_id,
        case_type=CaseType.PAYMENT_INCIDENT,
        status=CaseStatus.NEED_INFO,
        schema_version="1",
        case_revision=1,
        evidence_revision=0,
        synthetic=True,
        summary="Second synthetic incident",
        merchant_ref="merchant_demo_002",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        current_diagnosis_id=None,
        readiness=empty_readiness,
    )
    foreign_evidence = _evidence(
        "00000000-0000-4000-8000-000000000901",
        EvidenceCode.TRANSACTION_REFERENCE,
        "txn_foreign",
        case_id=foreign_case_id,
    )
    foreign_readiness = assess_readiness(build_active_evidence_view((foreign_evidence,)))
    with factory() as store:
        store.create_case_atomic(
            case=foreign_case,
            audit=_audit(
                AuditEventType.CASE_CREATED,
                event_id="00000000-0000-4000-8000-000000000920",
                action="create_case",
                from_status=None,
                to_status=CaseStatus.NEED_INFO,
                case_revision=1,
                evidence_revision=0,
                case_id=foreign_case_id,
            ),
        )
        store.append_evidence_atomic(
            expected_case_revision=1,
            expected_evidence_revision=0,
            evidence=foreign_evidence,
            readiness=foreign_readiness,
            target_status=CaseStatus.NEED_INFO,
            audit_events=(
                _audit(
                    AuditEventType.EVIDENCE_ADDED,
                    event_id="00000000-0000-4000-8000-000000000921",
                    action="append_evidence",
                    from_status=CaseStatus.NEED_INFO,
                    to_status=CaseStatus.NEED_INFO,
                    case_revision=2,
                    evidence_revision=1,
                    case_id=foreign_case_id,
                ),
            ),
        )

    original = _diagnosis_snapshot()
    refs = (original.hypotheses[0].evidence_refs[0], foreign_evidence.evidence_id)
    hypothesis = original.hypotheses[0].model_copy(update={"evidence_refs": refs})
    route = original.routing_decision
    ticket = original.ticket_draft
    assert route is not None
    assert ticket is not None
    snapshot = original.model_copy(
        update={
            "hypotheses": (hypothesis,),
            "routing_decision": route.model_copy(update={"evidence_refs": refs}),
            "ticket_draft": ticket.model_copy(
                update={
                    "hypotheses": (
                        ticket.hypotheses[0].model_copy(update={"evidence_refs": refs}),
                    )
                }
            ),
        }
    )
    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=snapshot,
                target_status=CaseStatus.DIAGNOSED,
                audit_events=_diagnosis_audits(),
            )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )
        current = store.get_case_view(CASE_ID)

    assert persisted is None
    assert current is not None
    assert current.case.status is CaseStatus.EVIDENCE_READY
    assert current.case.case_revision == 6
    assert current.case.current_diagnosis_id is None


def test_commit_diagnosis_rolls_back_snapshot_and_case_when_audit_write_fails(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    connection = connect_sqlite(db_path)
    try:
        connection.execute(
            """
            CREATE TRIGGER fail_diagnosis_audit
            BEFORE INSERT ON audit_events
            WHEN NEW.event_type = 'DIAGNOSIS_CREATED'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic audit failure');
            END
            """
        )
    finally:
        connection.close()

    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=_diagnosis_snapshot(),
                target_status=CaseStatus.DIAGNOSED,
                audit_events=_diagnosis_audits(),
            )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )
        current = store.get_case_view(CASE_ID)

    assert persisted is None
    assert current is not None
    assert current.case.status is CaseStatus.EVIDENCE_READY
    assert current.case.case_revision == 6
    assert current.case.current_diagnosis_id is None


def _assert_concurrent_diagnosis_unique_key_creates_once_and_replays_once(
    db_path: Path,
    attempt: int,
) -> None:
    del attempt
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    barrier = Barrier(2)
    outcomes: Queue[object] = Queue()

    def commit() -> None:
        try:
            with factory() as store:
                barrier.wait()
                outcomes.put(
                    store.commit_diagnosis_atomic(
                        expected_case_revision=6,
                        expected_evidence_revision=5,
                        snapshot=_diagnosis_snapshot(),
                        target_status=CaseStatus.DIAGNOSED,
                        audit_events=_diagnosis_audits(),
                    )
                )
        except BaseException as error:
            outcomes.put(error)

    workers = [Thread(target=commit), Thread(target=commit)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert all(not worker.is_alive() for worker in workers)
    results = [outcomes.get_nowait(), outcomes.get_nowait()]
    assert outcomes.empty()
    assert all(not isinstance(result, BaseException) for result in results)
    assert {result.outcome for result in results} == {
        WriteOutcome.CREATED,
        WriteOutcome.REPLAY,
    }
    assert all(result.diagnosis == _diagnosis_snapshot() for result in results)
    with factory() as store:
        current = store.get_case_view(CASE_ID)
    assert current is not None
    assert current.case.case_revision == 7
    assert current.case.current_diagnosis_id == DIAGNOSIS_ID
    assert current.case.updated_at == _diagnosis_snapshot().created_at
    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()


@pytest.mark.parametrize(
    "review_reason",
    (ReviewReason.POLICY_GAP, ReviewReason.CONFLICTING_EVIDENCE),
)
def test_human_only_diagnosis_round_trips_without_route_or_ticket(
    db_path: Path,
    review_reason: ReviewReason,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    snapshot = _diagnosis_snapshot().model_copy(
        update={
            "hypotheses": (),
            "routing_decision": None,
            "ticket_draft": None,
            "requires_human": True,
            "review_reasons": frozenset({review_reason}),
        }
    )
    audits = tuple(
        event.model_copy(update={"to_status": CaseStatus.HUMAN_REVIEW})
        for event in _diagnosis_audits()
        if event.event_type is not AuditEventType.ROUTING_PROPOSED
    )

    with factory() as store:
        result = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=snapshot,
            target_status=CaseStatus.HUMAN_REVIEW,
            audit_events=audits,
        )
    with factory() as reopened_store:
        persisted = reopened_store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )

    assert result.outcome is WriteOutcome.CREATED
    assert result.case_view.case.status is CaseStatus.HUMAN_REVIEW
    assert persisted == snapshot
    assert persisted is not None
    assert persisted.routing_decision is None
    assert persisted.ticket_draft is None


def test_human_review_route_and_ticket_round_trip_strict_flags(db_path: Path) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    original = _diagnosis_snapshot()
    route = original.routing_decision
    ticket = original.ticket_draft
    assert route is not None
    assert ticket is not None
    reasons = frozenset({ReviewReason.RISK_DECISION})
    snapshot = original.model_copy(
        update={
            "routing_decision": route.model_copy(
                update={
                    "responsible_team": ResponsibleTeam.RISK,
                    "priority": Priority.HIGH,
                    "requires_human": True,
                    "review_reasons": reasons,
                }
            ),
            "ticket_draft": ticket.model_copy(
                update={"responsible_team": ResponsibleTeam.RISK}
            ),
            "requires_human": True,
            "review_reasons": reasons,
        }
    )
    audits = tuple(
        event.model_copy(update={"to_status": CaseStatus.HUMAN_REVIEW})
        for event in _diagnosis_audits()
    )

    with factory() as store:
        result = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=snapshot,
            target_status=CaseStatus.HUMAN_REVIEW,
            audit_events=audits,
        )
    with factory() as reopened_store:
        persisted = reopened_store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )

    assert result.case_view.case.status is CaseStatus.HUMAN_REVIEW
    assert persisted == snapshot
    assert persisted is not None
    assert persisted.requires_human is True
    assert persisted.synthetic is True
    assert persisted.routing_decision is not None
    assert persisted.routing_decision.requires_human is True
    assert persisted.routing_decision.responsible_team is ResponsibleTeam.RISK
    assert persisted.routing_decision.priority is Priority.HIGH
    assert persisted.ticket_draft is not None
    assert persisted.ticket_draft.responsible_team is ResponsibleTeam.RISK


def _assert_concurrent_different_policy_loser_gets_case_revision_conflict(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    first = _diagnosis_snapshot()
    second_hypothesis = first.hypotheses[0].model_copy(
        update={"hypothesis_id": "00000000-0000-4000-8000-000000000302"}
    )
    second = first.model_copy(
        update={
            "diagnosis_id": "00000000-0000-4000-8000-000000000052",
            "policy_version": "POLICY_V2",
            "hypotheses": (second_hypothesis,),
        }
    )
    second_audits = tuple(
        event.model_copy(
            update={"event_id": f"00000000-0000-4000-8000-{2300 + index:012d}"}
        )
        for index, event in enumerate(_diagnosis_audits())
    )
    barrier = Barrier(2)
    outcomes: Queue[object] = Queue()

    def commit(snapshot: DiagnosisSnapshot, audits: Sequence[AuditEvent]) -> None:
        try:
            with factory() as store:
                barrier.wait()
                outcomes.put(
                    store.commit_diagnosis_atomic(
                        expected_case_revision=6,
                        expected_evidence_revision=5,
                        snapshot=snapshot,
                        target_status=CaseStatus.DIAGNOSED,
                        audit_events=audits,
                    )
                )
        except BaseException as error:
            outcomes.put(error)

    workers = [
        Thread(target=commit, args=(first, _diagnosis_audits())),
        Thread(target=commit, args=(second, second_audits)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    results = [outcomes.get_nowait(), outcomes.get_nowait()]
    assert all(not worker.is_alive() for worker in workers)
    assert outcomes.empty()
    assert sum(getattr(result, "outcome", None) is WriteOutcome.CREATED for result in results) == 1
    assert sum(isinstance(result, ConcurrentCaseWrite) for result in results) == 1
    with factory() as store:
        persisted = (
            store.find_diagnosis(
                case_id=CASE_ID,
                evidence_revision=5,
                policy_version="POLICY_V1",
            ),
            store.find_diagnosis(
                case_id=CASE_ID,
                evidence_revision=5,
                policy_version="POLICY_V2",
            ),
        )
    assert sum(snapshot is not None for snapshot in persisted) == 1


@pytest.mark.parametrize(
    "invalid_input",
    ("revision", "status", "nonhuman_target", "human_target"),
)
def test_invalid_snapshot_contract_is_rejected_before_existing_unique_replay(
    db_path: Path,
    invalid_input: str,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    original = _diagnosis_snapshot()
    with factory() as store:
        created = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=original,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    snapshot = original
    target = CaseStatus.DIAGNOSED
    if invalid_input == "revision":
        snapshot = original.model_copy(update={"evidence_revision": 4})
    elif invalid_input == "status":
        snapshot = original.model_copy(update={"status": DiagnosisStatus.SUPERSEDED})
    elif invalid_input == "nonhuman_target":
        target = CaseStatus.HUMAN_REVIEW
    else:
        snapshot = original.model_copy(
            update={
                "hypotheses": (),
                "routing_decision": None,
                "ticket_draft": None,
                "requires_human": True,
                "review_reasons": frozenset({ReviewReason.POLICY_GAP}),
            }
        )
    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=snapshot,
                target_status=target,
                audit_events=_diagnosis_audits(),
            )
        current = store.get_case_view(CASE_ID)

    assert current == created.case_view


def test_sensitive_snapshot_is_rejected_before_existing_unique_replay(db_path: Path) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    original = _diagnosis_snapshot()
    with factory() as store:
        created = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=original,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    sensitive = "Authorization: Bearer synthetic-secret"
    hypothesis = original.hypotheses[0].model_copy(update={"explanation": sensitive})
    ticket = original.ticket_draft
    assert ticket is not None
    snapshot = original.model_copy(
        update={
            "hypotheses": (hypothesis,),
            "ticket_draft": ticket.model_copy(
                update={
                    "summary": sensitive,
                    "hypotheses": (
                        ticket.hypotheses[0].model_copy(update={"explanation": sensitive}),
                    ),
                }
            ),
        }
    )
    with factory() as store:
        with pytest.raises(SensitiveDataRejected):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=snapshot,
                target_status=CaseStatus.DIAGNOSED,
                audit_events=_diagnosis_audits(),
            )
        current = store.get_case_view(CASE_ID)

    assert current == created.case_view


@pytest.mark.parametrize("sensitive_location", ("route", "audit"))
def test_sensitive_route_or_audit_is_rejected_before_existing_unique_replay(
    db_path: Path,
    sensitive_location: str,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    original = _diagnosis_snapshot()
    with factory() as store:
        created = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=original,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    snapshot = original
    audits = tuple(_diagnosis_audits())
    sensitive = "Authorization: Bearer synthetic-secret"
    if sensitive_location == "route":
        route = original.routing_decision
        assert route is not None
        snapshot = original.model_copy(
            update={"routing_decision": route.model_copy(update={"reason": sensitive})}
        )
    else:
        audits = (
            audits[0].model_copy(update={"action": sensitive}),
            *audits[1:],
        )
    with factory() as store:
        with pytest.raises(SensitiveDataRejected):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=snapshot,
                target_status=CaseStatus.DIAGNOSED,
                audit_events=audits,
            )
        current = store.get_case_view(CASE_ID)

    assert current == created.case_view


@pytest.mark.parametrize("route_contract", ("missing", "unexpected"))
def test_routing_audit_presence_must_match_snapshot_route(
    db_path: Path,
    route_contract: str,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    snapshot = _diagnosis_snapshot()
    target = CaseStatus.DIAGNOSED
    audits = tuple(_diagnosis_audits())
    if route_contract == "missing":
        audits = tuple(
            event
            for event in audits
            if event.event_type is not AuditEventType.ROUTING_PROPOSED
        )
    else:
        snapshot = snapshot.model_copy(
            update={
                "hypotheses": (),
                "routing_decision": None,
                "ticket_draft": None,
                "requires_human": True,
                "review_reasons": frozenset({ReviewReason.POLICY_GAP}),
            }
        )
        target = CaseStatus.HUMAN_REVIEW
        audits = tuple(
            event.model_copy(update={"to_status": target}) for event in audits
        )
    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=snapshot,
                target_status=target,
                audit_events=audits,
            )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )

    assert persisted is None


@pytest.mark.parametrize(
    "invalid_audit",
    (
        "missing",
        "extra",
        "duplicate_type",
        "wrong_case",
        "wrong_revision",
        "wrong_evidence_revision",
        "wrong_from",
        "wrong_to",
        "mixed_request",
        "mixed_trace",
    ),
)
def test_invalid_diagnosis_audit_batch_rolls_back_the_whole_commit(
    db_path: Path,
    invalid_audit: str,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    audits = list(_diagnosis_audits())
    if invalid_audit == "missing":
        audits.pop()
    elif invalid_audit == "extra":
        audits.append(
            audits[0].model_copy(
                update={
                    "event_id": "00000000-0000-4000-8000-000000000299",
                    "event_type": AuditEventType.EVIDENCE_ADDED,
                }
            )
        )
    elif invalid_audit == "duplicate_type":
        audits[1] = audits[1].model_copy(
            update={"event_type": AuditEventType.DIAGNOSIS_CREATED}
        )
    elif invalid_audit == "wrong_case":
        audits[0] = audits[0].model_copy(
            update={"case_id": "00000000-0000-4000-8000-000000000020"}
        )
    elif invalid_audit == "wrong_revision":
        audits[0] = audits[0].model_copy(update={"case_revision": 8})
    elif invalid_audit == "wrong_evidence_revision":
        audits[0] = audits[0].model_copy(update={"evidence_revision": 4})
    elif invalid_audit == "wrong_from":
        audits[0] = audits[0].model_copy(update={"from_status": CaseStatus.NEED_INFO})
    elif invalid_audit == "wrong_to":
        audits[0] = audits[0].model_copy(update={"to_status": CaseStatus.HUMAN_REVIEW})
    elif invalid_audit == "mixed_request":
        audits[0] = audits[0].model_copy(
            update={"request_id": "00000000-0000-4000-8000-000000000031"}
        )
    else:
        audits[0] = audits[0].model_copy(
            update={"trace_id": "00000000-0000-4000-8000-000000000041"}
        )

    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=_diagnosis_snapshot(),
                target_status=CaseStatus.DIAGNOSED,
                audit_events=audits,
            )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )
        current = store.get_case_view(CASE_ID)

    assert persisted is None
    assert current is not None
    assert current.case.status is CaseStatus.EVIDENCE_READY
    assert current.case.case_revision == 6
    assert current.case.current_diagnosis_id is None


def test_commit_diagnosis_rolls_back_when_final_hydration_detects_corruption(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    connection = connect_sqlite(db_path)
    try:
        connection.execute(
            """
            CREATE TRIGGER corrupt_new_diagnosis
            AFTER INSERT ON diagnosis_snapshots
            BEGIN
                UPDATE diagnosis_snapshots
                SET review_reasons_json = 'not-json'
                WHERE case_id = NEW.case_id AND diagnosis_id = NEW.diagnosis_id;
            END
            """
        )
    finally:
        connection.close()

    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=_diagnosis_snapshot(),
                target_status=CaseStatus.DIAGNOSED,
                audit_events=_diagnosis_audits(),
            )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )
        current = store.get_case_view(CASE_ID)

    assert persisted is None
    assert current is not None
    assert current.case.status is CaseStatus.EVIDENCE_READY
    assert current.case.case_revision == 6
    assert current.case.current_diagnosis_id is None


def test_commit_diagnosis_never_moves_case_updated_at_backwards(db_path: Path) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    snapshot = _diagnosis_snapshot().model_copy(
        update={"created_at": BASE_TIME + timedelta(minutes=5)}
    )

    with factory() as store:
        before = store.get_case_view(CASE_ID)
        result = store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=snapshot,
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    assert before is not None
    assert result.case_view.case.updated_at == before.case.updated_at


def test_review_reason_json_is_persisted_in_deterministic_order(db_path: Path) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    original = _diagnosis_snapshot()
    route = original.routing_decision
    ticket = original.ticket_draft
    assert route is not None
    assert ticket is not None
    reasons = frozenset(
        {
            ReviewReason.SECURITY_SIGNAL,
            ReviewReason.RISK_DECISION,
            ReviewReason.LOW_CONFIDENCE,
        }
    )
    snapshot = original.model_copy(
        update={
            "routing_decision": route.model_copy(
                update={
                    "responsible_team": ResponsibleTeam.RISK,
                    "priority": Priority.HIGH,
                    "requires_human": True,
                    "review_reasons": reasons,
                }
            ),
            "ticket_draft": ticket.model_copy(
                update={"responsible_team": ResponsibleTeam.RISK}
            ),
            "requires_human": True,
            "review_reasons": reasons,
        }
    )
    audits = tuple(
        event.model_copy(update={"to_status": CaseStatus.HUMAN_REVIEW})
        for event in _diagnosis_audits()
    )
    with factory() as store:
        store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=snapshot,
            target_status=CaseStatus.HUMAN_REVIEW,
            audit_events=audits,
        )

    connection = connect_sqlite(db_path)
    try:
        row = connection.execute(
            """
            SELECT routing_json, review_reasons_json
            FROM diagnosis_snapshots
            WHERE case_id = ? AND diagnosis_id = ?
            """,
            (CASE_ID, DIAGNOSIS_ID),
        ).fetchone()
    finally:
        connection.close()
    expected = ["LOW_CONFIDENCE", "RISK_DECISION", "SECURITY_SIGNAL"]
    assert json.loads(row["routing_json"])["review_reasons"] == expected
    assert row["review_reasons_json"] == json.dumps(expected, separators=(",", ":"))


@pytest.mark.parametrize("failure_point", ("hypothesis", "late_audit"))
def test_late_diagnosis_write_failure_rolls_back_everything(
    db_path: Path,
    failure_point: str,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    connection = connect_sqlite(db_path)
    try:
        if failure_point == "hypothesis":
            connection.execute(
                """
                CREATE TRIGGER fail_hypothesis_insert
                BEFORE INSERT ON hypotheses
                BEGIN
                    SELECT RAISE(ABORT, 'synthetic hypothesis failure');
                END
                """
            )
        else:
            connection.execute(
                """
                CREATE TRIGGER fail_late_diagnosis_audit
                BEFORE INSERT ON audit_events
                WHEN NEW.event_type = 'STATE_TRANSITIONED'
                     AND NEW.case_revision = 7
                BEGIN
                    SELECT RAISE(ABORT, 'synthetic late audit failure');
                END
                """
            )
    finally:
        connection.close()

    with factory() as store:
        with pytest.raises(PersistenceInvariantViolation):
            store.commit_diagnosis_atomic(
                expected_case_revision=6,
                expected_evidence_revision=5,
                snapshot=_diagnosis_snapshot(),
                target_status=CaseStatus.DIAGNOSED,
                audit_events=_diagnosis_audits(),
            )
        persisted = store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        )
        current = store.get_case_view(CASE_ID)

    assert persisted is None
    assert current is not None
    assert current.case.status is CaseStatus.EVIDENCE_READY
    assert current.case.case_revision == 6
    assert current.case.current_diagnosis_id is None


def test_find_diagnosis_commits_or_rolls_back_its_short_read_transaction(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _prepare_ready_case(factory)
    with factory() as store:
        store.commit_diagnosis_atomic(
            expected_case_revision=6,
            expected_evidence_revision=5,
            snapshot=_diagnosis_snapshot(),
            target_status=CaseStatus.DIAGNOSED,
            audit_events=_diagnosis_audits(),
        )

    connection = connect_sqlite(db_path)
    try:
        store = SqliteCaseStoreSession(connection)
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        assert store.find_diagnosis(
            case_id=CASE_ID,
            evidence_revision=5,
            policy_version="POLICY_V1",
        ) == _diagnosis_snapshot()
        normalized = tuple(statement.strip().upper() for statement in statements)
        assert "BEGIN" in normalized
        assert "COMMIT" in normalized

        connection.execute(
            """
            UPDATE diagnosis_snapshots
            SET review_reasons_json = 'not-json'
            WHERE case_id = ? AND diagnosis_id = ?
            """,
            (CASE_ID, DIAGNOSIS_ID),
        )
        statements.clear()
        with pytest.raises(PersistenceInvariantViolation):
            store.find_diagnosis(
                case_id=CASE_ID,
                evidence_revision=5,
                policy_version="POLICY_V1",
            )
        normalized = tuple(statement.strip().upper() for statement in statements)
        assert "ROLLBACK" in normalized
        assert connection.in_transaction is False
        assert (
            store.find_diagnosis(
                case_id=CASE_ID,
                evidence_revision=5,
                policy_version="MISSING_POLICY",
            )
            is None
        )
    finally:
        connection.close()
