import ast
import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import oceanpilot.adapters.persistence.sqlite as sqlite_adapter
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    connect_sqlite,
    initialize_schema,
)
from oceanpilot.application.errors import (
    CaseNotFound,
    ConcurrentCaseWrite,
    DatabaseUnavailable,
    EvidenceConflict,
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
    EvidenceValueType,
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
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    MerchantSuccessCase,
    ReadinessAssessment,
)
from oceanpilot.domain.state_machine import status_after_creation, status_after_evidence

CASE_ID = "00000000-0000-4000-8000-000000000010"
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
BASE_TIME = datetime(2026, 7, 18, 4, 0, tzinfo=UTC)
EVENT_IDS = {
    AuditEventType.CASE_CREATED: "00000000-0000-4000-8000-000000000060",
    AuditEventType.EVIDENCE_ADDED: "00000000-0000-4000-8000-000000000061",
    AuditEventType.DIAGNOSIS_SUPERSEDED: "00000000-0000-4000-8000-000000000062",
    AuditEventType.STATE_TRANSITIONED: "00000000-0000-4000-8000-000000000063",
}


def _factory(db_path: Path) -> SqliteCaseStoreFactory:
    initialize_schema(db_path)
    return SqliteCaseStoreFactory(db_path)


def _empty_readiness() -> ReadinessAssessment:
    return assess_readiness(build_active_evidence_view(()))


def _case() -> MerchantSuccessCase:
    readiness = _empty_readiness()
    return MerchantSuccessCase(
        case_id=CASE_ID,
        case_type=CaseType.PAYMENT_INCIDENT,
        status=status_after_creation(readiness),
        schema_version="1",
        case_revision=1,
        evidence_revision=0,
        synthetic=True,
        summary="合成支付异常",
        merchant_ref="merchant_demo_001",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        current_diagnosis_id=None,
        readiness=readiness,
    )


def _event(
    event_type: AuditEventType,
    *,
    from_status: CaseStatus,
    to_status: CaseStatus,
    case_revision: int,
    evidence_revision: int,
    **changes: object,
) -> AuditEvent:
    event = AuditEvent(
        event_id=EVENT_IDS[event_type],
        event_type=event_type,
        event_version="1",
        case_id=CASE_ID,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        actor_type=AuditActorType.SYNTHETIC_ADAPTER,
        action="append_evidence",
        from_status=from_status,
        to_status=to_status,
        case_revision=case_revision,
        evidence_revision=evidence_revision,
        occurred_at=BASE_TIME + timedelta(minutes=case_revision),
        result="CREATED",
        reason_code=None,
        sanitized_metadata={"event": event_type.value, "flag": True},
        synthetic=True,
    )
    return event.model_copy(update=changes)


def _create_event() -> AuditEvent:
    return AuditEvent(
        event_id=EVENT_IDS[AuditEventType.CASE_CREATED],
        event_type=AuditEventType.CASE_CREATED,
        event_version="1",
        case_id=CASE_ID,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        actor_type=AuditActorType.MERCHANT,
        action="create_case",
        from_status=None,
        to_status=CaseStatus.NEED_INFO,
        case_revision=1,
        evidence_revision=0,
        occurred_at=BASE_TIME,
        result="CREATED",
        reason_code=None,
        sanitized_metadata={},
        synthetic=True,
    )


def _evidence(
    *,
    evidence_id: str = "00000000-0000-4000-8000-000000000011",
    code: EvidenceCode = EvidenceCode.CONTEXT_ENVIRONMENT,
    value: str | bool | datetime | None = "PROD",
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE,
    collected_at: datetime = BASE_TIME + timedelta(minutes=10),
    source_ref: str = "synthetic:fixture",
) -> EvidenceItem:
    request = EvidenceCreate(
        evidence_id=evidence_id,
        evidence_code=code,
        availability=availability,
        typed_value=value if availability is EvidenceAvailability.AVAILABLE else None,
        observed_at=BASE_TIME + timedelta(minutes=5),
        source_ref=source_ref,
    )
    origin = EvidenceOrigin(
        source_type=SourceType.SYNTHETIC_ADAPTER,
        source_reliability=SourceReliability.SYNTHETIC_TEST,
        synthetic=True,
    )
    return create_evidence_item(
        request,
        case_id=CASE_ID,
        origin=origin,
        collected_at=collected_at,
    )


def _readiness(evidence: Sequence[EvidenceItem]) -> ReadinessAssessment:
    return assess_readiness(build_active_evidence_view(evidence))


def _audits(
    *,
    current_status: CaseStatus,
    target_status: CaseStatus,
    case_revision: int,
    evidence_revision: int,
    reopening: bool = False,
) -> tuple[AuditEvent, ...]:
    event_types = [AuditEventType.EVIDENCE_ADDED]
    if reopening:
        event_types.append(AuditEventType.DIAGNOSIS_SUPERSEDED)
    if target_status is not current_status:
        event_types.append(AuditEventType.STATE_TRANSITIONED)
    return tuple(
        _event(
            event_type,
            from_status=current_status,
            to_status=target_status,
            case_revision=case_revision,
            evidence_revision=evidence_revision,
        )
        for event_type in event_types
    )


def _create_case(factory: SqliteCaseStoreFactory) -> None:
    with factory() as store:
        store.create_case_atomic(case=_case(), audit=_create_event())


def _assert_safe_invariant(error: PersistenceInvariantViolation) -> None:
    assert str(error) == "persistence invariant was violated"
    assert error.__cause__ is None
    assert error.__context__ is None


def _append(
    factory: SqliteCaseStoreFactory,
    *,
    evidence: EvidenceItem,
    existing: Sequence[EvidenceItem] = (),
    expected_case_revision: int = 1,
    expected_evidence_revision: int = 0,
    current_status: CaseStatus = CaseStatus.NEED_INFO,
    audit_events: Sequence[AuditEvent] | None = None,
):
    readiness = _readiness((*existing, evidence))
    target = status_after_evidence(current_status, readiness)
    audits = (
        _audits(
            current_status=current_status,
            target_status=target,
            case_revision=expected_case_revision + 1,
            evidence_revision=expected_evidence_revision + 1,
        )
        if audit_events is None
        else tuple(audit_events)
    )
    with factory() as store:
        return store.append_evidence_atomic(
            expected_case_revision=expected_case_revision,
            expected_evidence_revision=expected_evidence_revision,
            evidence=evidence,
            readiness=readiness,
            target_status=target,
            audit_events=audits,
        )


def _with_unique_event_ids(
    events: Sequence[AuditEvent],
    sequence: int,
) -> tuple[AuditEvent, ...]:
    return tuple(
        event.model_copy(
            update={"event_id": (f"00000000-0000-4000-8000-{1000 + sequence * 10 + index:012d}")}
        )
        for index, event in enumerate(events)
    )


def _ready_evidence(
    *,
    integration_value: str | None = "API",
) -> tuple[EvidenceItem, ...]:
    integration_availability = (
        EvidenceAvailability.AVAILABLE
        if integration_value is not None
        else EvidenceAvailability.CONFIRMED_UNAVAILABLE
    )
    return (
        _evidence(
            evidence_id="00000000-0000-4000-8000-000000000101",
            code=EvidenceCode.TRANSACTION_REFERENCE,
            value="txn_001",
        ),
        _evidence(
            evidence_id="00000000-0000-4000-8000-000000000102",
            code=EvidenceCode.TRANSACTION_OCCURRED_AT,
            value=BASE_TIME + timedelta(minutes=1),
        ),
        _evidence(
            evidence_id="00000000-0000-4000-8000-000000000103",
            code=EvidenceCode.CONTEXT_ENVIRONMENT,
            value="PROD",
        ),
        _evidence(
            evidence_id="00000000-0000-4000-8000-000000000104",
            code=EvidenceCode.SYMPTOM_STATUS,
            value="FAILED",
        ),
        _evidence(
            evidence_id="00000000-0000-4000-8000-000000000105",
            code=EvidenceCode.INTEGRATION_TYPE,
            value=integration_value,
            availability=integration_availability,
        ),
    )


def _persist_sequence(
    factory: SqliteCaseStoreFactory,
    evidence: Sequence[EvidenceItem],
) -> None:
    existing: list[EvidenceItem] = []
    current_status = CaseStatus.NEED_INFO
    for index, item in enumerate(evidence, start=1):
        readiness = _readiness((*existing, item))
        target = status_after_evidence(current_status, readiness)
        audits = _with_unique_event_ids(
            _audits(
                current_status=current_status,
                target_status=target,
                case_revision=index + 1,
                evidence_revision=index,
            ),
            index,
        )
        with factory() as store:
            result = store.append_evidence_atomic(
                expected_case_revision=index,
                expected_evidence_revision=index - 1,
                evidence=item,
                readiness=readiness,
                target_status=target,
                audit_events=audits,
            )
        assert result.outcome is WriteOutcome.CREATED
        existing.append(item)
        current_status = target


def _seed_current_diagnosis(
    db_path: Path,
    *,
    case_status: CaseStatus = CaseStatus.DIAGNOSED,
    requires_human: bool = False,
) -> None:
    routing_reasons_json = '["LOW_CONFIDENCE"]' if requires_human else "[]"
    routing_json = (
        '{"evidence_refs":["00000000-0000-4000-8000-000000000101",'
        '"00000000-0000-4000-8000-000000000103"],'
        '"priority":"HIGH","reason":"合成路由",'
        f'"requires_human":{str(requires_human).lower()},'
        '"responsible_team":"TECHNICAL_SUPPORT",'
        f'"review_reasons":{routing_reasons_json}}}'
    )
    ticket_json = (
        '{"evidence_summary":["合成证据"],"hypotheses":['
        '{"cause_code":"CAUSE_A","confidence_method":"HEURISTIC_V1",'
        '"confidence_score":"0.9100","evidence_refs":['
        '"00000000-0000-4000-8000-000000000101",'
        '"00000000-0000-4000-8000-000000000103"],'
        '"explanation":"解释 A","next_verification_action":"验证 A",'
        '"rule_id":"RULE_A"}],"missing_material":[],"next_action":"验证 A",'
        '"responsible_team":"TECHNICAL_SUPPORT","summary":"解释 A",'
        '"synthetic":true,"title":"合成工单"}'
    )
    connection = connect_sqlite(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO diagnosis_snapshots (
                case_id, diagnosis_id, evidence_revision, policy_version,
                engine_version, status, routing_json, ticket_json, requires_human,
                review_reasons_json, synthetic, created_at
            ) VALUES (?, ?, 5, 'POLICY_V1', 'ENGINE_V1', 'CURRENT', ?, ?, ?, ?, 1,
                      '2026-07-18T05:00:00.000000Z')
            """,
            (
                CASE_ID,
                DIAGNOSIS_ID,
                routing_json,
                ticket_json,
                1 if requires_human else 0,
                '["LOW_CONFIDENCE"]' if requires_human else "[]",
            ),
        )
        connection.execute(
            """
            INSERT INTO hypotheses (
                case_id, hypothesis_id, diagnosis_id, cause_code, explanation,
                confidence_score, confidence_method, next_verification_action, rule_id
            ) VALUES (?, '00000000-0000-4000-8000-000000000301', ?,
                      'CAUSE_A', '解释 A', 0.91, 'HEURISTIC_V1', '验证 A', 'RULE_A')
            """,
            (CASE_ID, DIAGNOSIS_ID),
        )
        connection.execute(
            """
            INSERT INTO hypothesis_evidence_refs (case_id, hypothesis_id, evidence_id)
            VALUES (?, '00000000-0000-4000-8000-000000000301',
                    '00000000-0000-4000-8000-000000000103')
            """,
            (CASE_ID,),
        )
        connection.execute(
            """
            INSERT INTO hypothesis_evidence_refs (case_id, hypothesis_id, evidence_id)
            VALUES (?, '00000000-0000-4000-8000-000000000301',
                    '00000000-0000-4000-8000-000000000101')
            """,
            (CASE_ID,),
        )
        connection.execute(
            """
            UPDATE cases
            SET status = ?, case_revision = 7, current_diagnosis_id = ?,
                updated_at = '2026-07-18T05:00:00.000000Z'
            WHERE case_id = ?
            """,
            (case_status.value, DIAGNOSIS_ID, CASE_ID),
        )
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def test_append_writes_canonical_evidence_updates_case_and_audit(db_path: Path) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()

    result = _append(factory, evidence=evidence)

    assert result.outcome is WriteOutcome.CREATED
    assert result.case_view.evidence == (evidence,)
    assert result.case_view.case.case_revision == 2
    assert result.case_view.case.evidence_revision == 1
    assert result.case_view.case.updated_at == evidence.collected_at

    connection = connect_sqlite(db_path)
    try:
        evidence_row = connection.execute(
            """
            SELECT case_id, evidence_id, evidence_code, availability, value_type,
                   typed_value_json, source_type, source_ref, source_reliability,
                   observed_at, collected_at, synthetic, typeof(synthetic), content_hash
            FROM evidence_items
            """
        ).fetchone()
        audit_row = connection.execute(
            """
            SELECT event_type, case_revision, evidence_revision,
                   sanitized_metadata_json, synthetic, typeof(synthetic)
            FROM audit_events WHERE event_type = 'EVIDENCE_ADDED'
            """
        ).fetchone()
    finally:
        connection.close()

    assert tuple(evidence_row) == (
        CASE_ID,
        evidence.evidence_id,
        "context.environment",
        "AVAILABLE",
        "STRING",
        '"PROD"',
        "SYNTHETIC_ADAPTER",
        "synthetic:fixture",
        "SYNTHETIC_TEST",
        "2026-07-18T04:05:00.000000Z",
        "2026-07-18T04:10:00.000000Z",
        1,
        "integer",
        evidence.content_hash,
    )
    assert tuple(audit_row) == (
        "EVIDENCE_ADDED",
        2,
        1,
        '{"event":"EVIDENCE_ADDED","flag":true}',
        1,
        "integer",
    )


def test_same_canonical_evidence_replays_before_stale_revision_or_audit_validation(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()
    created = _append(factory, evidence=evidence)

    with factory() as store:
        replay = store.append_evidence_atomic(
            expected_case_revision=0,
            expected_evidence_revision=0,
            evidence=evidence,
            readiness=_readiness((evidence,)),
            target_status=CaseStatus.NEED_INFO,
            audit_events=(),
        )

    assert replay.outcome is WriteOutcome.REPLAY
    assert replay.case_view == created.case_view
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 2
    finally:
        connection.close()


def test_same_id_different_content_conflicts_before_revision_target_or_audit(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    original = _evidence()
    _append(factory, evidence=original)
    conflicting = _evidence(evidence_id=original.evidence_id, value="SANDBOX")

    with factory() as store, pytest.raises(EvidenceConflict):
        store.append_evidence_atomic(
            expected_case_revision=0,
            expected_evidence_revision=0,
            evidence=conflicting,
            readiness=_empty_readiness(),
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=(),
        )

    connection = connect_sqlite(db_path)
    try:
        row = connection.execute(
            "SELECT content_hash FROM evidence_items WHERE evidence_id = ?",
            (original.evidence_id,),
        ).fetchone()
        assert row[0] == original.content_hash
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("expected_case_revision", "expected_evidence_revision"),
    [(True, 0), (1, False), (1.0, 0), (1, 0.0), (-1, 0), (1, -1)],
)
def test_new_evidence_rejects_non_exact_or_negative_expected_revisions_without_writes(
    db_path: Path,
    expected_case_revision: object,
    expected_evidence_revision: object,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()
    readiness = _readiness((evidence,))
    target = status_after_evidence(CaseStatus.NEED_INFO, readiness)
    audits = _audits(
        current_status=CaseStatus.NEED_INFO,
        target_status=target,
        case_revision=2,
        evidence_revision=1,
    )

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=expected_case_revision,
            expected_evidence_revision=expected_evidence_revision,
            evidence=evidence,
            readiness=readiness,
            target_status=target,
            audit_events=audits,
        )

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1
        assert tuple(
            connection.execute("SELECT case_revision, evidence_revision FROM cases").fetchone()
        ) == (1, 0)
    finally:
        connection.close()


@pytest.mark.parametrize("invalid_revisions", [(True, False), (1.0, 0.0), (-1, -1)])
def test_same_id_replay_and_conflict_precede_invalid_expected_revisions(
    db_path: Path,
    invalid_revisions: tuple[object, object],
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()
    created = _append(factory, evidence=evidence)

    with factory() as store:
        replay = store.append_evidence_atomic(
            expected_case_revision=invalid_revisions[0],
            expected_evidence_revision=invalid_revisions[1],
            evidence=evidence,
            readiness=_empty_readiness(),
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=(),
        )
        with pytest.raises(EvidenceConflict):
            store.append_evidence_atomic(
                expected_case_revision=invalid_revisions[0],
                expected_evidence_revision=invalid_revisions[1],
                evidence=_evidence(evidence_id=evidence.evidence_id, value="SANDBOX"),
                readiness=_empty_readiness(),
                target_status=CaseStatus.EVIDENCE_READY,
                audit_events=(),
            )

    assert replay.outcome is WriteOutcome.REPLAY
    assert replay.case_view == created.case_view


def test_stored_sensitive_evidence_is_rejected_before_hash_conflict_without_writes(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    original = _evidence()
    _append(factory, evidence=original)
    connection = connect_sqlite(db_path)
    try:
        connection.execute(
            """
            UPDATE evidence_items
            SET source_ref = ?, content_hash = ?
            WHERE case_id = ? AND evidence_id = ?
            """,
            (
                "Authorization: Bearer STORED-CONFLICT-SENTINEL",
                "c4fdb305e8ec99b0f8ae48f043afa78fbd61e21cac2645e5a956ce85f8aa3782",
                CASE_ID,
                original.evidence_id,
            ),
        )
    finally:
        connection.close()

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=2,
            expected_evidence_revision=1,
            evidence=_evidence(evidence_id=original.evidence_id, value="SANDBOX"),
            readiness=_empty_readiness(),
            target_status=CaseStatus.NEED_INFO,
            audit_events=(),
        )

    _assert_safe_invariant(caught.value)
    assert "STORED-CONFLICT-SENTINEL" not in str(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert tuple(
            connection.execute(
                "SELECT case_revision, evidence_revision, status FROM cases"
            ).fetchone()
        ) == (2, 1, "NEED_INFO")
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 2
        assert tuple(
            connection.execute("SELECT source_ref, content_hash FROM evidence_items").fetchone()
        ) == (
            "Authorization: Bearer STORED-CONFLICT-SENTINEL",
            "c4fdb305e8ec99b0f8ae48f043afa78fbd61e21cac2645e5a956ce85f8aa3782",
        )
    finally:
        connection.close()


def test_new_evidence_requires_audit_batch_and_rolls_back(db_path: Path) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=1,
            expected_evidence_revision=0,
            evidence=evidence,
            readiness=_readiness((evidence,)),
            target_status=CaseStatus.NEED_INFO,
            audit_events=(),
        )

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 0
        assert connection.execute("SELECT case_revision FROM cases").fetchone()[0] == 1
    finally:
        connection.close()


def test_stale_revisions_win_over_invalid_target_readiness_and_empty_audit(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    first = _evidence()
    _append(factory, evidence=first)
    second = _evidence(
        evidence_id="00000000-0000-4000-8000-000000000012",
        code=EvidenceCode.TRANSACTION_REFERENCE,
        value="txn_002",
    )

    with factory() as store, pytest.raises(ConcurrentCaseWrite):
        store.append_evidence_atomic(
            expected_case_revision=1,
            expected_evidence_revision=0,
            evidence=second,
            readiness=_empty_readiness(),
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=(),
        )

    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 1
        assert tuple(
            connection.execute("SELECT case_revision, evidence_revision FROM cases").fetchone()
        ) == (2, 1)
    finally:
        connection.close()


@pytest.mark.parametrize("invalid_part", ["readiness", "target"])
def test_append_rejects_readiness_or_target_not_derived_from_evidence(
    db_path: Path,
    invalid_part: str,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()
    readiness = _readiness((evidence,))
    target = CaseStatus.NEED_INFO
    if invalid_part == "readiness":
        readiness = _empty_readiness()
    else:
        target = CaseStatus.EVIDENCE_READY
    audits = _audits(
        current_status=CaseStatus.NEED_INFO,
        target_status=target,
        case_revision=2,
        evidence_revision=1,
    )

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=1,
            expected_evidence_revision=0,
            evidence=evidence,
            readiness=readiness,
            target_status=target,
            audit_events=audits,
        )

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 0
    finally:
        connection.close()


def _duplicate_audit(events: tuple[AuditEvent, ...]) -> tuple[AuditEvent, ...]:
    duplicate = events[0].model_copy(update={"event_id": "00000000-0000-4000-8000-000000000064"})
    return (*events, duplicate)


def _mutate_audit(
    events: tuple[AuditEvent, ...],
    **changes: object,
) -> tuple[AuditEvent, ...]:
    return (events[0].model_copy(update=changes), *events[1:])


@pytest.mark.parametrize(
    "mutate",
    [
        _duplicate_audit,
        lambda events: _mutate_audit(events, case_id="00000000-0000-4000-8000-000000000099"),
        lambda events: _mutate_audit(events, case_revision=99),
        lambda events: _mutate_audit(events, evidence_revision=99),
        lambda events: _mutate_audit(events, from_status=CaseStatus.EVIDENCE_READY),
        lambda events: _mutate_audit(events, to_status=CaseStatus.EVIDENCE_READY),
        lambda events: _mutate_audit(events, event_type=AuditEventType.DIAGNOSIS_CREATED),
    ],
)
def test_append_rejects_invalid_audit_batch_before_first_mutation(
    db_path: Path,
    mutate: Callable[[tuple[AuditEvent, ...]], tuple[AuditEvent, ...]],
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()
    readiness = _readiness((evidence,))
    audits = _audits(
        current_status=CaseStatus.NEED_INFO,
        target_status=CaseStatus.NEED_INFO,
        case_revision=2,
        evidence_revision=1,
    )

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=1,
            expected_evidence_revision=0,
            evidence=evidence,
            readiness=readiness,
            target_status=CaseStatus.NEED_INFO,
            audit_events=mutate(audits),
        )

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1
    finally:
        connection.close()


@pytest.mark.parametrize("mixed_field", ["request_id", "trace_id"])
def test_append_rejects_mixed_request_or_trace_in_real_multi_event_batch(
    db_path: Path,
    mixed_field: str,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _ready_evidence()
    _persist_sequence(factory, evidence[:4])
    final_item = evidence[4]
    readiness = _readiness(evidence)
    audits = list(
        _with_unique_event_ids(
            _audits(
                current_status=CaseStatus.NEED_INFO,
                target_status=CaseStatus.EVIDENCE_READY,
                case_revision=6,
                evidence_revision=5,
            ),
            40,
        )
    )
    audits[1] = audits[1].model_copy(update={mixed_field: "00000000-0000-4000-8000-000000000099"})

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=5,
            expected_evidence_revision=4,
            evidence=final_item,
            readiness=readiness,
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=audits,
        )

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 4
        assert tuple(
            connection.execute(
                "SELECT case_revision, evidence_revision, status FROM cases"
            ).fetchone()
        ) == (5, 4, "NEED_INFO")
    finally:
        connection.close()


def test_append_audit_trigger_failure_rolls_back_every_mutation(db_path: Path) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    connection = connect_sqlite(db_path)
    try:
        connection.executescript(
            """
            CREATE TRIGGER fail_evidence_audit BEFORE INSERT ON audit_events
            WHEN NEW.event_type = 'EVIDENCE_ADDED'
            BEGIN
                SELECT RAISE(ABORT, 'forced append audit failure');
            END;
            """
        )
    finally:
        connection.close()

    with pytest.raises(PersistenceInvariantViolation) as caught:
        _append(factory, evidence=_evidence())

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 0
        assert tuple(
            connection.execute(
                """
                SELECT case_revision, evidence_revision, status,
                       current_diagnosis_id, updated_at
                FROM cases
                """
            ).fetchone()
        ) == (1, 0, "NEED_INFO", None, "2026-07-18T04:00:00.000000Z")
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1
    finally:
        connection.close()


@pytest.mark.parametrize("payload_owner", ["evidence", "readiness", "audit"])
def test_append_scans_entire_payload_before_replay_conflict_or_sql(
    db_path: Path,
    payload_owner: str,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence()
    _append(factory, evidence=evidence)
    forged = evidence.model_copy(update={"source_ref": "Authorization: Bearer APPEND-SENTINEL"})
    readiness = _readiness((evidence,))
    audit = _event(
        AuditEventType.EVIDENCE_ADDED,
        from_status=CaseStatus.NEED_INFO,
        to_status=CaseStatus.NEED_INFO,
        case_revision=2,
        evidence_revision=1,
    )
    if payload_owner == "readiness":
        readiness = readiness.model_copy(
            update={"question_reason": "Authorization: Bearer APPEND-SENTINEL"}
        )
        forged = evidence
    elif payload_owner == "audit":
        audit = audit.model_copy(
            update={"sanitized_metadata": {"nested": ["Authorization: Bearer APPEND-SENTINEL"]}}
        )
        forged = evidence
    traced: list[str] = []

    with factory() as store:
        store._connection.set_trace_callback(traced.append)
        with pytest.raises(SensitiveDataRejected):
            store.append_evidence_atomic(
                expected_case_revision=0,
                expected_evidence_revision=0,
                evidence=forged,
                readiness=readiness,
                target_status=CaseStatus.NEED_INFO,
                audit_events=(audit,),
            )

    assert traced == []
    assert b"APPEND-SENTINEL" not in db_path.read_bytes()


@pytest.mark.parametrize(
    "changes",
    [
        {"typed_value": "SANDBOX"},
        {"value_type": EvidenceValueType.DATETIME},
        {"schema_version": "2"},
        {"content_hash": "0" * 64},
        {
            "availability": EvidenceAvailability.CONFIRMED_UNAVAILABLE,
            "typed_value": "PROD",
        },
        {"evidence_id": "00000000-0000-4000-8000-0000000000AA"},
    ],
)
def test_append_recanonicalizes_incoming_evidence_before_sql(
    db_path: Path,
    changes: dict[str, object],
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    corrupt = _evidence().model_copy(update=changes)
    traced: list[str] = []

    with factory() as store:
        store._connection.set_trace_callback(traced.append)
        with pytest.raises(PersistenceInvariantViolation) as caught:
            store.append_evidence_atomic(
                expected_case_revision=1,
                expected_evidence_revision=0,
                evidence=corrupt,
                readiness=_empty_readiness(),
                target_status=CaseStatus.NEED_INFO,
                audit_events=(),
            )

    _assert_safe_invariant(caught.value)
    assert traced == []


def test_confirmed_unavailable_uses_sql_null_and_round_trips(db_path: Path) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence(
        code=EvidenceCode.INTEGRATION_TYPE,
        value=None,
        availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
    )

    result = _append(factory, evidence=evidence)

    assert result.case_view.evidence == (evidence,)
    connection = connect_sqlite(db_path)
    try:
        row = connection.execute(
            "SELECT typed_value_json, typeof(typed_value_json) FROM evidence_items"
        ).fetchone()
        assert tuple(row) == (None, "null")
    finally:
        connection.close()


def test_datetime_typed_value_and_json_booleans_round_trip(db_path: Path) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    value = datetime(2026, 7, 18, 13, 45, 6, 123456, tzinfo=UTC)
    evidence = _evidence(
        code=EvidenceCode.TRANSACTION_OCCURRED_AT,
        value=value,
    )

    result = _append(factory, evidence=evidence)

    assert result.case_view.evidence[0].typed_value == value
    assert isinstance(result.case_view.evidence[0].typed_value, datetime)
    connection = connect_sqlite(db_path)
    try:
        row = connection.execute(
            """
            SELECT typed_value_json, readiness_json
            FROM evidence_items JOIN cases USING (case_id)
            """
        ).fetchone()
        assert row[0] == '"2026-07-18T13:45:06.123456Z"'
        assert type(json.loads(row[1])["ready"]) is bool
    finally:
        connection.close()


def test_updated_at_never_moves_backwards(db_path: Path) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _evidence(collected_at=BASE_TIME - timedelta(minutes=1))

    result = _append(factory, evidence=evidence)

    assert result.case_view.case.updated_at == BASE_TIME


def test_append_to_missing_case_preserves_case_not_found(db_path: Path) -> None:
    factory = _factory(db_path)
    evidence = _evidence()
    readiness = _readiness((evidence,))

    with factory() as store, pytest.raises(CaseNotFound):
        store.append_evidence_atomic(
            expected_case_revision=1,
            expected_evidence_revision=0,
            evidence=evidence,
            readiness=readiness,
            target_status=CaseStatus.NEED_INFO,
            audit_events=_audits(
                current_status=CaseStatus.NEED_INFO,
                target_status=CaseStatus.NEED_INFO,
                case_revision=2,
                evidence_revision=1,
            ),
        )


def test_sql_injection_shaped_value_is_inert_and_tables_survive(db_path: Path) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    injection = "synthetic:x'); DROP TABLE cases;--"
    evidence = _evidence(source_ref=injection)

    result = _append(factory, evidence=evidence)

    assert result.case_view.evidence[0].source_ref == injection
    connection = connect_sqlite(db_path)
    try:
        tables = frozenset(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
        )
        assert {
            "cases",
            "evidence_items",
            "diagnosis_snapshots",
            "hypotheses",
            "hypothesis_evidence_refs",
            "audit_events",
        }.issubset(tables)
    finally:
        connection.close()


def test_public_read_hydrates_complete_diagnosis_with_deterministic_order(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _ready_evidence()
    _persist_sequence(factory, evidence)
    _seed_current_diagnosis(db_path)

    with factory() as store:
        view = store.get_case_view(CASE_ID)
        snapshot = store.load_case_snapshot(CASE_ID)

    assert view is not None
    assert snapshot is not None
    assert view.case.status is CaseStatus.DIAGNOSED
    assert tuple(item.evidence_id for item in view.evidence) == tuple(
        sorted(item.evidence_id for item in evidence)
    )
    diagnosis = view.current_diagnosis
    assert diagnosis is not None
    assert diagnosis.status is DiagnosisStatus.CURRENT
    assert diagnosis.diagnosis_id == DIAGNOSIS_ID
    assert diagnosis.evidence_revision == 5
    assert tuple(item.hypothesis_id for item in diagnosis.hypotheses) == (
        "00000000-0000-4000-8000-000000000301",
    )
    assert tuple(item.cause_code for item in diagnosis.hypotheses) == ("CAUSE_A",)
    assert diagnosis.hypotheses[0].evidence_refs == (
        "00000000-0000-4000-8000-000000000101",
        "00000000-0000-4000-8000-000000000103",
    )
    assert diagnosis.routing_decision is not None
    assert diagnosis.routing_decision.responsible_team is ResponsibleTeam.TECHNICAL_SUPPORT
    assert diagnosis.routing_decision.priority is Priority.HIGH
    assert diagnosis.routing_decision.requires_human is diagnosis.requires_human
    assert diagnosis.routing_decision.review_reasons == diagnosis.review_reasons
    assert diagnosis.ticket_draft is not None
    assert diagnosis.ticket_draft.title == "合成工单"
    assert diagnosis.ticket_draft.hypotheses[0].rule_id == "RULE_A"
    assert snapshot.current_diagnosis == diagnosis


@pytest.mark.parametrize(
    "corruption",
    [
        "non_human_reason",
        "team_mismatch",
        "unpaired_ticket",
        "ticket_mapping",
        "route_policy_gap",
        "route_conflicting_evidence",
    ],
)
def test_standalone_diagnosis_loader_rejects_snapshot_internal_invariant_breaks(
    db_path: Path,
    corruption: str,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    _persist_sequence(factory, _ready_evidence())
    _seed_current_diagnosis(db_path)
    connection = connect_sqlite(db_path)
    try:
        row = connection.execute(
            "SELECT routing_json, ticket_json FROM diagnosis_snapshots WHERE case_id = ?",
            (CASE_ID,),
        ).fetchone()
        routing = json.loads(row[0])
        ticket = json.loads(row[1])
        if corruption == "non_human_reason":
            routing["review_reasons"] = ["LOW_CONFIDENCE"]
            connection.execute(
                """
                UPDATE diagnosis_snapshots
                SET review_reasons_json = ?, routing_json = ?
                WHERE case_id = ?
                """,
                ('["LOW_CONFIDENCE"]', json.dumps(routing), CASE_ID),
            )
        elif corruption == "team_mismatch":
            ticket["responsible_team"] = "BUSINESS"
            connection.execute(
                "UPDATE diagnosis_snapshots SET ticket_json = ? WHERE case_id = ?",
                (json.dumps(ticket), CASE_ID),
            )
        elif corruption == "unpaired_ticket":
            connection.execute(
                "UPDATE diagnosis_snapshots SET ticket_json = NULL WHERE case_id = ?",
                (CASE_ID,),
            )
        elif corruption == "ticket_mapping":
            ticket["summary"] = "不匹配的解释"
            connection.execute(
                "UPDATE diagnosis_snapshots SET ticket_json = ? WHERE case_id = ?",
                (json.dumps(ticket), CASE_ID),
            )
        else:
            reason = "POLICY_GAP" if corruption == "route_policy_gap" else "CONFLICTING_EVIDENCE"
            routing["requires_human"] = True
            routing["review_reasons"] = [reason]
            connection.execute(
                """
                UPDATE diagnosis_snapshots
                SET requires_human = 1, review_reasons_json = ?, routing_json = ?
                WHERE case_id = ?
                """,
                (json.dumps([reason]), json.dumps(routing), CASE_ID),
            )
    finally:
        connection.close()

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store._load_diagnosis_snapshot_by_id(CASE_ID, DIAGNOSIS_ID)

    _assert_safe_invariant(caught.value)


@pytest.mark.parametrize(
    ("case_status", "requires_human"),
    [
        (CaseStatus.DIAGNOSED, False),
        (CaseStatus.HUMAN_REVIEW, True),
    ],
)
def test_new_evidence_reopens_diagnosis_and_clears_pointer_atomically(
    db_path: Path,
    case_status: CaseStatus,
    requires_human: bool,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    existing = _ready_evidence()
    _persist_sequence(factory, existing)
    _seed_current_diagnosis(
        db_path,
        case_status=case_status,
        requires_human=requires_human,
    )
    new_evidence = _evidence(
        evidence_id="00000000-0000-4000-8000-000000000106",
        code=EvidenceCode.PAYMENT_METHOD,
        value="CARD",
        collected_at=BASE_TIME + timedelta(hours=2),
    )
    readiness = _readiness((*existing, new_evidence))
    target = status_after_evidence(case_status, readiness)
    audits = _with_unique_event_ids(
        _audits(
            current_status=case_status,
            target_status=target,
            case_revision=8,
            evidence_revision=6,
            reopening=True,
        ),
        20,
    )

    with factory() as store:
        result = store.append_evidence_atomic(
            expected_case_revision=7,
            expected_evidence_revision=5,
            evidence=new_evidence,
            readiness=readiness,
            target_status=target,
            audit_events=audits,
        )

    assert result.outcome is WriteOutcome.CREATED
    assert result.case_view.case.status is CaseStatus.EVIDENCE_READY
    assert result.case_view.case.current_diagnosis_id is None
    assert result.case_view.current_diagnosis is None
    connection = connect_sqlite(db_path)
    try:
        row = connection.execute(
            """
            SELECT status FROM diagnosis_snapshots
            WHERE case_id = ? AND diagnosis_id = ?
            """,
            (CASE_ID, DIAGNOSIS_ID),
        ).fetchone()
        assert row[0] == "SUPERSEDED"
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 6
    finally:
        connection.close()


def test_replay_does_not_supersede_current_diagnosis_or_clear_pointer(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    existing = _ready_evidence()
    _persist_sequence(factory, existing)
    _seed_current_diagnosis(db_path)
    with factory() as store:
        before = store.get_case_view(CASE_ID)
    assert before is not None
    connection = connect_sqlite(db_path)
    try:
        before_counts = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("evidence_items", "audit_events", "diagnosis_snapshots")
        )
        before_case = tuple(
            connection.execute(
                """
                SELECT case_revision, evidence_revision, updated_at,
                       current_diagnosis_id, status
                FROM cases
                """
            ).fetchone()
        )
        before_snapshot_status = connection.execute(
            "SELECT status FROM diagnosis_snapshots WHERE diagnosis_id = ?",
            (DIAGNOSIS_ID,),
        ).fetchone()[0]
    finally:
        connection.close()

    with factory() as store:
        result = store.append_evidence_atomic(
            expected_case_revision=0,
            expected_evidence_revision=0,
            evidence=existing[0],
            readiness=_readiness(existing),
            target_status=CaseStatus.NEED_INFO,
            audit_events=(),
        )

    assert result.outcome is WriteOutcome.REPLAY
    assert result.case_view == before
    connection = connect_sqlite(db_path)
    try:
        after_counts = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("evidence_items", "audit_events", "diagnosis_snapshots")
        )
        after_case = tuple(
            connection.execute(
                """
                SELECT case_revision, evidence_revision, updated_at,
                       current_diagnosis_id, status
                FROM cases
                """
            ).fetchone()
        )
        after_snapshot_status = connection.execute(
            "SELECT status FROM diagnosis_snapshots WHERE diagnosis_id = ?",
            (DIAGNOSIS_ID,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert after_counts == before_counts
    assert after_case == before_case
    assert after_snapshot_status == before_snapshot_status == "CURRENT"


@pytest.mark.parametrize(
    "missing_type",
    [
        AuditEventType.DIAGNOSIS_SUPERSEDED,
        AuditEventType.STATE_TRANSITIONED,
    ],
)
def test_reopen_audit_batch_requires_each_lifecycle_event(
    db_path: Path,
    missing_type: AuditEventType,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    existing = _ready_evidence()
    _persist_sequence(factory, existing)
    _seed_current_diagnosis(db_path)
    new_evidence = _evidence(
        evidence_id="00000000-0000-4000-8000-000000000106",
        code=EvidenceCode.PAYMENT_METHOD,
        value="CARD",
    )
    readiness = _readiness((*existing, new_evidence))
    complete = _with_unique_event_ids(
        _audits(
            current_status=CaseStatus.DIAGNOSED,
            target_status=CaseStatus.EVIDENCE_READY,
            case_revision=8,
            evidence_revision=6,
            reopening=True,
        ),
        41,
    )
    incomplete = tuple(event for event in complete if event.event_type is not missing_type)

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=7,
            expected_evidence_revision=5,
            evidence=new_evidence,
            readiness=readiness,
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=incomplete,
        )

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 5
        assert tuple(
            connection.execute(
                """
                SELECT case_revision, evidence_revision, status,
                       current_diagnosis_id
                FROM cases
                """
            ).fetchone()
        ) == (7, 5, "DIAGNOSED", DIAGNOSIS_ID)
        assert (
            connection.execute(
                "SELECT status FROM diagnosis_snapshots WHERE diagnosis_id = ?",
                (DIAGNOSIS_ID,),
            ).fetchone()[0]
            == "CURRENT"
        )
    finally:
        connection.close()


@pytest.mark.parametrize("corruption", ["superseded", "stale", "missing", "open_pointer"])
def test_reopen_rejects_corrupt_pointer_lifecycle_without_writes(
    db_path: Path,
    corruption: str,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    existing = _ready_evidence()
    _persist_sequence(factory, existing)
    _seed_current_diagnosis(db_path)
    connection = connect_sqlite(db_path)
    try:
        if corruption == "superseded":
            connection.execute(
                "UPDATE diagnosis_snapshots SET status = 'SUPERSEDED' WHERE case_id = ?",
                (CASE_ID,),
            )
        elif corruption == "stale":
            connection.execute(
                "UPDATE diagnosis_snapshots SET evidence_revision = 4 WHERE case_id = ?",
                (CASE_ID,),
            )
        elif corruption == "missing":
            connection.execute(
                "UPDATE cases SET current_diagnosis_id = NULL WHERE case_id = ?",
                (CASE_ID,),
            )
        else:
            connection.execute(
                "UPDATE cases SET status = 'EVIDENCE_READY' WHERE case_id = ?",
                (CASE_ID,),
            )
    finally:
        connection.close()
    new_evidence = _evidence(
        evidence_id="00000000-0000-4000-8000-000000000106",
        code=EvidenceCode.PAYMENT_METHOD,
        value="CARD",
    )
    readiness = _readiness((*existing, new_evidence))
    current_status = (
        CaseStatus.EVIDENCE_READY if corruption == "open_pointer" else CaseStatus.DIAGNOSED
    )
    audits = _with_unique_event_ids(
        _audits(
            current_status=current_status,
            target_status=CaseStatus.EVIDENCE_READY,
            case_revision=8,
            evidence_revision=6,
            reopening=corruption != "open_pointer",
        ),
        21,
    )

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.append_evidence_atomic(
            expected_case_revision=7,
            expected_evidence_revision=5,
            evidence=new_evidence,
            readiness=readiness,
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=audits,
        )

    _assert_safe_invariant(caught.value)
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0] == 5
    finally:
        connection.close()


def test_plugin_after_confirmed_unavailable_regresses_ready_case_to_need_info(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    existing = _ready_evidence(integration_value=None)
    _persist_sequence(factory, existing)
    assert _readiness(existing).ready is True
    _seed_current_diagnosis(db_path)
    plugin = _evidence(
        evidence_id="00000000-0000-4000-8000-000000000106",
        code=EvidenceCode.INTEGRATION_TYPE,
        value="PLUGIN",
    )
    readiness = _readiness((*existing, plugin))
    assert readiness.ready is False
    assert readiness.missing_fields == (
        "integration.platform",
        "integration.plugin_version",
    )
    audits = _with_unique_event_ids(
        _audits(
            current_status=CaseStatus.DIAGNOSED,
            target_status=CaseStatus.NEED_INFO,
            case_revision=8,
            evidence_revision=6,
            reopening=True,
        ),
        22,
    )

    with factory() as store:
        result = store.append_evidence_atomic(
            expected_case_revision=7,
            expected_evidence_revision=5,
            evidence=plugin,
            readiness=readiness,
            target_status=CaseStatus.NEED_INFO,
            audit_events=audits,
        )

    assert result.case_view.case.status is CaseStatus.NEED_INFO
    assert result.case_view.case.current_diagnosis_id is None


def test_plugin_after_api_is_conflicting_evidence_not_need_info_regression(
    db_path: Path,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    existing = _ready_evidence(integration_value="API")
    _persist_sequence(factory, existing)
    _seed_current_diagnosis(db_path)
    plugin = _evidence(
        evidence_id="00000000-0000-4000-8000-000000000106",
        code=EvidenceCode.INTEGRATION_TYPE,
        value="PLUGIN",
    )
    readiness = _readiness((*existing, plugin))
    assert readiness.ready is True
    assert readiness.missing_fields == ()
    assert readiness.stop_reason.value == "READY"
    view = build_active_evidence_view((*existing, plugin))
    assert view.review_reasons == frozenset({ReviewReason.CONFLICTING_EVIDENCE})
    audits = _with_unique_event_ids(
        _audits(
            current_status=CaseStatus.DIAGNOSED,
            target_status=CaseStatus.EVIDENCE_READY,
            case_revision=8,
            evidence_revision=6,
            reopening=True,
        ),
        23,
    )

    with factory() as store:
        result = store.append_evidence_atomic(
            expected_case_revision=7,
            expected_evidence_revision=5,
            evidence=plugin,
            readiness=readiness,
            target_status=CaseStatus.EVIDENCE_READY,
            audit_events=audits,
        )

    assert result.case_view.case.status is CaseStatus.EVIDENCE_READY


def _corrupt_stored_row(connection: sqlite3.Connection, kind: str) -> None:
    if kind == "bad_hash":
        connection.execute(
            "UPDATE evidence_items SET content_hash = ? WHERE case_id = ?",
            ("f" * 64, CASE_ID),
        )
    elif kind == "blob_value":
        connection.execute(
            "UPDATE evidence_items SET typed_value_json = CAST(? AS BLOB) WHERE case_id = ?",
            ('"PROD"', CASE_ID),
        )
    elif kind == "malformed_value":
        connection.execute(
            "UPDATE evidence_items SET typed_value_json = '{malformed' WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "bad_schema":
        connection.execute(
            "UPDATE evidence_items SET schema_version = '2' WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "bad_availability":
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE evidence_items SET availability = 'UNKNOWN' WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "bad_value_type":
        connection.execute(
            "UPDATE evidence_items SET value_type = 'BOOLEAN' WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "bad_synthetic_storage":
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE evidence_items SET synthetic = CAST('1' AS BLOB) WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "unknown_enum":
        connection.execute(
            "UPDATE evidence_items SET evidence_code = 'unknown.code' WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "naive_time":
        connection.execute(
            "UPDATE evidence_items SET collected_at = '2026-07-18T04:00:00' WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "sensitive":
        connection.execute(
            "UPDATE evidence_items SET source_ref = ? WHERE case_id = ?",
            ("Authorization: Bearer STORED-SENTINEL", CASE_ID),
        )
    elif kind == "noncanonical_uuid":
        connection.execute(
            "UPDATE evidence_items SET evidence_id = ? WHERE case_id = ?",
            ("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", CASE_ID),
        )
    elif kind == "bad_evidence_revision":
        connection.execute(
            "UPDATE cases SET evidence_revision = 0 WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "malformed_readiness":
        connection.execute(
            "UPDATE cases SET readiness_json = '{malformed' WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "bad_case_revision":
        connection.execute(
            "UPDATE cases SET case_revision = 1 WHERE case_id = ?",
            (CASE_ID,),
        )
    elif kind == "new_status":
        connection.execute(
            "UPDATE cases SET status = 'NEW' WHERE case_id = ?",
            (CASE_ID,),
        )


@pytest.mark.parametrize(
    "kind",
    [
        "bad_hash",
        "blob_value",
        "malformed_value",
        "bad_schema",
        "bad_availability",
        "bad_value_type",
        "bad_synthetic_storage",
        "unknown_enum",
        "naive_time",
        "sensitive",
        "noncanonical_uuid",
        "bad_evidence_revision",
        "malformed_readiness",
        "bad_case_revision",
        "new_status",
    ],
)
def test_public_read_rejects_tampered_rows_without_partial_graph(
    db_path: Path,
    kind: str,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    _append(factory, evidence=_evidence())
    connection = connect_sqlite(db_path)
    try:
        _corrupt_stored_row(connection, kind)
    finally:
        connection.close()

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.get_case_view(CASE_ID)

    _assert_safe_invariant(caught.value)
    if kind == "sensitive":
        assert "STORED-SENTINEL" not in str(caught.value)


@pytest.mark.parametrize(
    "corruption",
    ["routing", "ticket", "route_requires_human", "route_review_reasons"],
)
def test_public_read_rejects_corrupt_diagnosis_json_without_partial_graph(
    db_path: Path,
    corruption: str,
) -> None:
    factory = _factory(db_path)
    _create_case(factory)
    evidence = _ready_evidence()
    _persist_sequence(factory, evidence)
    _seed_current_diagnosis(db_path)
    connection = connect_sqlite(db_path)
    try:
        if corruption == "routing":
            connection.execute(
                """
                UPDATE diagnosis_snapshots
                SET routing_json = '{malformed'
                WHERE case_id = ?
                """,
                (CASE_ID,),
            )
        elif corruption == "ticket":
            connection.execute(
                """
                UPDATE diagnosis_snapshots
                SET ticket_json = '{malformed'
                WHERE case_id = ?
                """,
                (CASE_ID,),
            )
        elif corruption == "route_requires_human":
            connection.execute(
                """
                UPDATE diagnosis_snapshots
                SET routing_json = ?
                WHERE case_id = ?
                """,
                (
                    '{"evidence_refs":[],"priority":"HIGH","reason":"合成路由",'
                    '"requires_human":true,'
                    '"responsible_team":"TECHNICAL_SUPPORT",'
                    '"review_reasons":[]}',
                    CASE_ID,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE diagnosis_snapshots
                SET routing_json = ?
                WHERE case_id = ?
                """,
                (
                    '{"evidence_refs":[],"priority":"HIGH","reason":"合成路由",'
                    '"requires_human":false,'
                    '"responsible_team":"TECHNICAL_SUPPORT",'
                    '"review_reasons":["LOW_CONFIDENCE"]}',
                    CASE_ID,
                ),
            )
    finally:
        connection.close()

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.get_case_view(CASE_ID)

    _assert_safe_invariant(caught.value)


class _FailingReadConnection:
    in_transaction = False

    def __init__(self, error: sqlite3.Error) -> None:
        self._error = error

    def execute(self, sql: str, parameters: object = ()) -> None:
        del sql, parameters
        raise self._error


@pytest.mark.parametrize(
    ("raw_error", "safe_error"),
    [
        (sqlite3.OperationalError("OPERATIONAL-SENTINEL"), DatabaseUnavailable),
        (sqlite3.InternalError("INTERNAL-SENTINEL"), DatabaseUnavailable),
        (sqlite3.DatabaseError("DATABASE-SENTINEL"), DatabaseUnavailable),
        (sqlite3.DataError("DATA-SENTINEL"), PersistenceInvariantViolation),
        (sqlite3.ProgrammingError("PROGRAMMING-SENTINEL"), PersistenceInvariantViolation),
        (sqlite3.InterfaceError("INTERFACE-SENTINEL"), PersistenceInvariantViolation),
        (
            sqlite3.NotSupportedError("NOT-SUPPORTED-SENTINEL"),
            PersistenceInvariantViolation,
        ),
        (sqlite3.Error("BASE-SENTINEL"), PersistenceInvariantViolation),
    ],
)
def test_sqlite_failures_map_to_frozen_safe_category_without_chain(
    raw_error: sqlite3.Error,
    safe_error: type[BaseException],
) -> None:
    store = sqlite_adapter.SqliteCaseStoreSession(_FailingReadConnection(raw_error))

    with pytest.raises(safe_error) as caught:
        store.get_case_view(CASE_ID)

    assert "SENTINEL" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_business_execute_calls_use_literal_sql() -> None:
    source_path = Path(sqlite_adapter.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"execute", "executemany"}
    ]

    assert calls
    for call in calls:
        assert call.args
        assert isinstance(call.args[0], ast.Constant)
        assert isinstance(call.args[0].value, str)
        assert "{" not in call.args[0].value
        has_parameter_argument = len(call.args) > 1 or any(
            keyword.arg in {"parameters", "params"} for keyword in call.keywords
        )
        if has_parameter_argument:
            assert "?" in call.args[0].value
