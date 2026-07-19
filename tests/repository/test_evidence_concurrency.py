from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Queue
from threading import Barrier, Thread

import pytest

from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    connect_sqlite,
    initialize_schema,
)
from oceanpilot.application.errors import ConcurrentCaseWrite
from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseStatus,
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
from oceanpilot.domain.models import AuditEvent, EvidenceCreate, EvidenceItem, EvidenceOrigin

CASE_ID = "00000000-0000-4000-8000-000000000010"
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"
BASE_TIME = datetime(2026, 7, 18, 4, 0, tzinfo=UTC)
EMPTY_READINESS_JSON = (
    '{"completion_ratio":"0.0000","known_unknown_fields":[],'
    '"missing_fields":["context.environment","integration.type","symptom.signal",'
    '"transaction.occurred_at","transaction.reference"],'
    '"next_question":"transaction.reference","question_reason":"定位同一笔交易",'
    '"ready":false,"stop_reason":"NEED_MORE_EVIDENCE",'
    '"target_role":"MERCHANT_TECH"}'
)
PARTIAL_READINESS_JSON = (
    '{"completion_ratio":"0.2000","known_unknown_fields":[],'
    '"missing_fields":["integration.type","symptom.signal",'
    '"transaction.occurred_at","transaction.reference"],'
    '"next_question":"transaction.reference","question_reason":"定位同一笔交易",'
    '"ready":false,"stop_reason":"NEED_MORE_EVIDENCE",'
    '"target_role":"MERCHANT_TECH"}'
)


def _seed_case(db_path: Path) -> SqliteCaseStoreFactory:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        connection.execute(
            """
            INSERT INTO cases (
                case_id, case_type, status, schema_version, case_revision,
                evidence_revision, synthetic, summary, merchant_ref, created_at,
                updated_at, current_diagnosis_id, readiness_json
            ) VALUES (?, 'PAYMENT_INCIDENT', 'NEED_INFO', '1', 1, 0, 1,
                      '合成支付异常', 'merchant_demo_001',
                      '2026-07-18T04:00:00.000000Z',
                      '2026-07-18T04:00:00.000000Z', NULL, ?)
            """,
            (CASE_ID, EMPTY_READINESS_JSON),
        )
    finally:
        connection.close()
    return SqliteCaseStoreFactory(db_path)


def _evidence(evidence_id: str, value: str = "PROD") -> EvidenceItem:
    request = EvidenceCreate(
        evidence_id=evidence_id,
        evidence_code=EvidenceCode.CONTEXT_ENVIRONMENT,
        availability=EvidenceAvailability.AVAILABLE,
        typed_value=value,
        observed_at=BASE_TIME + timedelta(minutes=1),
        source_ref="synthetic:concurrency",
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
        collected_at=BASE_TIME + timedelta(minutes=2),
    )


def _audit(event_id: str) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        event_type=AuditEventType.EVIDENCE_ADDED,
        event_version="1",
        case_id=CASE_ID,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        actor_type=AuditActorType.SYNTHETIC_ADAPTER,
        action="append_evidence",
        from_status=CaseStatus.NEED_INFO,
        to_status=CaseStatus.NEED_INFO,
        case_revision=2,
        evidence_revision=1,
        occurred_at=BASE_TIME + timedelta(minutes=3),
        result="CREATED",
        reason_code=None,
        sanitized_metadata={},
        synthetic=True,
    )


def _race(
    factory: SqliteCaseStoreFactory,
    evidence: tuple[EvidenceItem, EvidenceItem],
) -> list[object]:
    barrier = Barrier(3)
    outcomes: Queue[object] = Queue()

    def worker(index: int) -> None:
        item = evidence[index]
        readiness = assess_readiness(build_active_evidence_view((item,)))
        try:
            with factory() as store:
                barrier.wait(timeout=5)
                result = store.append_evidence_atomic(
                    expected_case_revision=1,
                    expected_evidence_revision=0,
                    evidence=item,
                    readiness=readiness,
                    target_status=CaseStatus.NEED_INFO,
                    audit_events=(_audit(f"00000000-0000-4000-8000-{70 + index:012d}"),),
                )
            outcomes.put(result.outcome)
        except BaseException as error:  # test thread must report every failure
            outcomes.put(error)

    threads = [Thread(target=worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    return [outcomes.get_nowait(), outcomes.get_nowait()]


def _assert_single_winner_terminal_state(db_path: Path) -> None:
    connection = connect_sqlite(db_path)
    try:
        case_row = tuple(
            connection.execute(
                """
                SELECT case_revision, evidence_revision, status, readiness_json,
                       updated_at, current_diagnosis_id
                FROM cases
                """
            ).fetchone()
        )
        evidence_count = connection.execute("SELECT count(*) FROM evidence_items").fetchone()[0]
        audit_count = connection.execute("SELECT count(*) FROM audit_events").fetchone()[0]
    finally:
        connection.close()
    assert case_row == (
        2,
        1,
        "NEED_INFO",
        PARTIAL_READINESS_JSON,
        "2026-07-18T04:02:00.000000Z",
        None,
    )
    assert evidence_count == 1
    assert audit_count == 1


@pytest.mark.parametrize("attempt", range(3))
def test_two_connections_same_evidence_yield_created_and_replay(
    db_path: Path,
    attempt: int,
) -> None:
    del attempt
    factory = _seed_case(db_path)
    item = _evidence("00000000-0000-4000-8000-000000000011")

    outcomes = _race(factory, (item, item))

    assert Counter(outcomes) == Counter({WriteOutcome.CREATED: 1, WriteOutcome.REPLAY: 1})
    _assert_single_winner_terminal_state(db_path)


@pytest.mark.parametrize("attempt", range(3))
def test_two_connections_different_evidence_yield_created_and_concurrent_write(
    db_path: Path,
    attempt: int,
) -> None:
    del attempt
    factory = _seed_case(db_path)
    first = _evidence("00000000-0000-4000-8000-000000000011")
    second = _evidence("00000000-0000-4000-8000-000000000012")

    outcomes = _race(factory, (first, second))

    assert sum(outcome is WriteOutcome.CREATED for outcome in outcomes) == 1
    errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(errors) == 1
    assert type(errors[0]) is ConcurrentCaseWrite
    _assert_single_winner_terminal_state(db_path)
