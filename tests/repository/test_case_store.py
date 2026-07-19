import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from queue import Queue
from threading import Barrier, Thread

import pytest

import oceanpilot.adapters.persistence.sqlite as sqlite_adapter
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    SqliteCaseStoreSession,
    connect_sqlite,
    initialize_schema,
)
from oceanpilot.application.errors import PersistenceInvariantViolation
from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseStatus,
    CaseType,
)
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.evidence_policy import assess_readiness, build_active_evidence_view
from oceanpilot.domain.models import AuditEvent, MerchantSuccessCase, ReadinessAssessment
from oceanpilot.domain.state_machine import status_after_creation

CASE_ID = "00000000-0000-4000-8000-000000000010"
EVENT_ID = "00000000-0000-4000-8000-000000000020"
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"
CREATED_AT = datetime(2026, 7, 18, 4, 0, tzinfo=UTC)
EMPTY_READINESS_JSON = (
    '{"completion_ratio":"0.0000","known_unknown_fields":[],'
    '"missing_fields":["context.environment","integration.type","symptom.signal",'
    '"transaction.occurred_at","transaction.reference"],'
    '"next_question":"transaction.reference","question_reason":"定位同一笔交易",'
    '"ready":false,"stop_reason":"NEED_MORE_EVIDENCE",'
    '"target_role":"MERCHANT_TECH"}'
)


def _empty_readiness() -> ReadinessAssessment:
    return assess_readiness(build_active_evidence_view(()))


def _case(**changes: object) -> MerchantSuccessCase:
    readiness = _empty_readiness()
    case = MerchantSuccessCase(
        case_id=CASE_ID,
        case_type=CaseType.PAYMENT_INCIDENT,
        status=status_after_creation(readiness),
        schema_version="1",
        case_revision=1,
        evidence_revision=0,
        synthetic=True,
        summary="合成支付异常",
        merchant_ref="merchant_demo_001",
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        current_diagnosis_id=None,
        readiness=readiness,
    )
    return case.model_copy(update=changes)


def _audit(**changes: object) -> AuditEvent:
    audit = AuditEvent(
        event_id=EVENT_ID,
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
        occurred_at=CREATED_AT,
        result="CREATED",
        reason_code=None,
        sanitized_metadata={"nested": {"flag": True}, "sequence": [1, "two"]},
        synthetic=True,
    )
    return audit.model_copy(update=changes)


def _factory(db_path: Path) -> SqliteCaseStoreFactory:
    initialize_schema(db_path)
    return SqliteCaseStoreFactory(db_path)


def _business_counts(db_path: Path) -> tuple[int, ...]:
    connection = connect_sqlite(db_path)
    try:
        return tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "cases",
                "evidence_items",
                "diagnosis_snapshots",
                "hypotheses",
                "hypothesis_evidence_refs",
                "audit_events",
            )
        )
    finally:
        connection.close()


def _assert_safe_invariant(error: PersistenceInvariantViolation) -> None:
    assert str(error) == "persistence invariant was violated"
    assert error.__cause__ is None
    assert error.__context__ is None


def _seed_empty_case(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO cases (
            case_id, case_type, status, schema_version, case_revision,
            evidence_revision, synthetic, summary, merchant_ref, created_at,
            updated_at, current_diagnosis_id, readiness_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CASE_ID,
            "PAYMENT_INCIDENT",
            "NEED_INFO",
            "1",
            1,
            0,
            1,
            "合成支付异常",
            "merchant_demo_001",
            "2026-07-18T04:00:00.000000Z",
            "2026-07-18T04:00:00.000000Z",
            None,
            EMPTY_READINESS_JSON,
        ),
    )


def test_create_writes_case_readiness_and_audit_then_returns_persisted_graph(
    db_path: Path,
) -> None:
    factory = _factory(db_path)

    with factory() as store:
        view = store.create_case_atomic(case=_case(), audit=_audit())

    assert view.case == _case()
    assert view.evidence == ()
    assert view.current_diagnosis is None

    connection = connect_sqlite(db_path)
    try:
        case_row = connection.execute(
            """
            SELECT case_id, case_type, status, schema_version, case_revision,
                   evidence_revision, synthetic, typeof(synthetic), summary,
                   merchant_ref, created_at, updated_at, current_diagnosis_id,
                   readiness_json
            FROM cases
            """
        ).fetchone()
        audit_row = connection.execute(
            """
            SELECT event_type, request_id, trace_id, from_status, to_status,
                   case_revision, evidence_revision, sanitized_metadata_json,
                   synthetic, typeof(synthetic)
            FROM audit_events
            """
        ).fetchone()
    finally:
        connection.close()

    assert tuple(case_row) == (
        CASE_ID,
        "PAYMENT_INCIDENT",
        "NEED_INFO",
        "1",
        1,
        0,
        1,
        "integer",
        "合成支付异常",
        "merchant_demo_001",
        "2026-07-18T04:00:00.000000Z",
        "2026-07-18T04:00:00.000000Z",
        None,
        EMPTY_READINESS_JSON,
    )
    assert tuple(audit_row) == (
        "CASE_CREATED",
        REQUEST_ID,
        TRACE_ID,
        None,
        "NEED_INFO",
        1,
        0,
        '{"nested":{"flag":true},"sequence":[1,"two"]}',
        1,
        "integer",
    )
    assert json.loads(audit_row[7]) == _audit().sanitized_metadata


@pytest.mark.parametrize(
    ("case_changes", "audit_changes"),
    [
        ({"case_type": CaseType.ONBOARDING_RECOMMENDATION}, {}),
        ({"case_revision": 2}, {}),
        ({"evidence_revision": 1}, {}),
        ({"current_diagnosis_id": "00000000-0000-4000-8000-000000000099"}, {}),
        ({"updated_at": CREATED_AT + timedelta(seconds=1)}, {}),
        ({"status": CaseStatus.EVIDENCE_READY}, {}),
        (
            {
                "readiness": _empty_readiness().model_copy(
                    update={"completion_ratio": Decimal("0.1000")}
                )
            },
            {},
        ),
        ({}, {"case_id": "00000000-0000-4000-8000-000000000099"}),
        ({}, {"event_type": AuditEventType.EVIDENCE_ADDED}),
        ({}, {"case_revision": 2}),
        ({}, {"evidence_revision": 1}),
        ({}, {"from_status": CaseStatus.NEW}),
        ({}, {"to_status": CaseStatus.EVIDENCE_READY}),
    ],
)
def test_create_rejects_invalid_aggregate_or_audit_without_rows(
    db_path: Path,
    case_changes: dict[str, object],
    audit_changes: dict[str, object],
) -> None:
    factory = _factory(db_path)

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.create_case_atomic(
            case=_case(**case_changes),
            audit=_audit(**audit_changes),
        )

    _assert_safe_invariant(caught.value)
    assert _business_counts(db_path) == (0, 0, 0, 0, 0, 0)


def test_create_business_validation_runs_inside_transaction_before_first_insert(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _factory(db_path)
    case = _case()
    audit = _audit()
    real_assess = sqlite_adapter.assess_readiness
    real_validate = sqlite_adapter._validate_audit_batch
    checkpoints: list[tuple[str, bool, tuple[int, int]]] = []

    with factory() as store:

        def counts() -> tuple[int, int]:
            return (
                store._connection.execute("SELECT count(*) FROM cases").fetchone()[0],
                store._connection.execute("SELECT count(*) FROM audit_events").fetchone()[0],
            )

        def assess_spy(view: object) -> ReadinessAssessment:
            checkpoints.append(("readiness", store._connection.in_transaction, counts()))
            return real_assess(view)

        def audit_spy(*args: object, **kwargs: object) -> tuple[AuditEvent, ...]:
            checkpoints.append(("audit", store._connection.in_transaction, counts()))
            return real_validate(*args, **kwargs)

        monkeypatch.setattr(sqlite_adapter, "assess_readiness", assess_spy)
        monkeypatch.setattr(sqlite_adapter, "_validate_audit_batch", audit_spy)
        store.create_case_atomic(case=case, audit=audit)

    assert checkpoints[:2] == [
        ("readiness", True, (0, 0)),
        ("audit", True, (0, 0)),
    ]


def test_duplicate_case_id_is_not_replay_and_preserves_original_rows(db_path: Path) -> None:
    factory = _factory(db_path)
    with factory() as store:
        original = store.create_case_atomic(case=_case(), audit=_audit())
    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.create_case_atomic(
            case=_case(summary="不同的合成描述"),
            audit=_audit(event_id="00000000-0000-4000-8000-000000000021"),
        )

    _assert_safe_invariant(caught.value)
    with factory() as store:
        assert store.get_case_view(CASE_ID) == original
    assert _business_counts(db_path) == (1, 0, 0, 0, 0, 1)


def test_create_audit_trigger_failure_rolls_back_case_and_audit(db_path: Path) -> None:
    factory = _factory(db_path)
    connection = connect_sqlite(db_path)
    try:
        connection.executescript(
            """
            CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'forced audit failure');
            END;
            """
        )
    finally:
        connection.close()

    with factory() as store, pytest.raises(PersistenceInvariantViolation) as caught:
        store.create_case_atomic(case=_case(), audit=_audit())

    _assert_safe_invariant(caught.value)
    assert _business_counts(db_path) == (0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("payload_owner", ["case", "audit"])
def test_create_scans_all_caller_payload_before_sql(
    db_path: Path,
    payload_owner: str,
) -> None:
    factory = _factory(db_path)
    case = (
        _case(summary="Authorization: Bearer CREATE-SENTINEL")
        if payload_owner == "case"
        else _case()
    )
    audit = (
        _audit(sanitized_metadata={"nested": ["Authorization: Bearer CREATE-SENTINEL"]})
        if payload_owner == "audit"
        else _audit()
    )
    traced: list[str] = []

    with factory() as store:
        store._connection.set_trace_callback(traced.append)
        with pytest.raises(SensitiveDataRejected):
            store.create_case_atomic(case=case, audit=audit)

    assert traced == []
    assert _business_counts(db_path) == (0, 0, 0, 0, 0, 0)
    assert b"CREATE-SENTINEL" not in db_path.read_bytes()


def test_public_reads_use_deferred_transactions_and_return_none_when_absent(
    db_path: Path,
) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    _seed_empty_case(connection)
    store = SqliteCaseStoreSession(connection)
    traced: list[str] = []
    connection.set_trace_callback(traced.append)
    try:
        view = store.get_case_view(CASE_ID)
        snapshot = store.load_case_snapshot(CASE_ID)
        assert store.get_case_view("00000000-0000-4000-8000-000000000099") is None
        assert store.load_case_snapshot("00000000-0000-4000-8000-000000000099") is None
    finally:
        connection.close()

    assert view is not None
    assert snapshot is not None
    assert view.case == _case()
    assert snapshot.case == view.case
    assert snapshot.evidence == view.evidence == ()
    assert snapshot.current_diagnosis is view.current_diagnosis is None
    assert traced.count("BEGIN") == 4
    assert traced.count("COMMIT") == 4
    assert "BEGIN IMMEDIATE" not in traced


def test_failed_public_read_rolls_back_and_session_is_reusable(db_path: Path) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    _seed_empty_case(connection)
    store = SqliteCaseStoreSession(connection)
    traced: list[str] = []
    connection.execute(
        "UPDATE cases SET readiness_json = ? WHERE case_id = ?",
        ("{malformed", CASE_ID),
    )
    connection.set_trace_callback(traced.append)
    try:
        with pytest.raises(PersistenceInvariantViolation) as caught:
            store.get_case_view(CASE_ID)
        _assert_safe_invariant(caught.value)
        assert connection.in_transaction is False
        assert "ROLLBACK" in traced

        connection.execute(
            "UPDATE cases SET readiness_json = ? WHERE case_id = ?",
            (EMPTY_READINESS_JSON, CASE_ID),
        )
        assert store.get_case_view(CASE_ID) is not None
        assert connection.in_transaction is False
    finally:
        connection.close()


@pytest.mark.parametrize("raw", [2, "1", None, True, False, 1.0, b"1"])
def test_decode_sqlite_bool_rejects_every_non_exact_integer(raw: object) -> None:
    decode = sqlite_adapter.decode_sqlite_bool

    with pytest.raises(PersistenceInvariantViolation) as caught:
        decode("synthetic", raw)

    _assert_safe_invariant(caught.value)


@pytest.mark.parametrize(("raw", "expected"), [(0, False), (1, True)])
def test_decode_sqlite_bool_accepts_only_exact_integer_zero_or_one(
    raw: object,
    expected: bool,
) -> None:
    decode = sqlite_adapter.decode_sqlite_bool

    assert decode("synthetic", raw) is expected


def test_public_reader_hydrates_test_owned_raw_evidence_without_writer_codec(
    db_path: Path,
) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        _seed_empty_case(connection)
        connection.execute(
            """
            INSERT INTO evidence_items (
                case_id, evidence_id, schema_version, evidence_code, availability,
                value_type, typed_value_json, source_type, source_ref,
                source_reliability, observed_at, collected_at, synthetic, content_hash
            ) VALUES (?, '00000000-0000-4000-8000-000000000012', '1',
                      'context.environment', 'AVAILABLE', 'STRING', '"PROD"',
                      'SYNTHETIC_ADAPTER', 'synthetic:fixture', 'SYNTHETIC_TEST',
                      '2026-07-18T04:05:00.000000Z',
                      '2026-07-18T04:10:00.000000Z', 1, ?)
            """,
            (
                CASE_ID,
                "4b3cc03a6921e929be93e9b987d879f2a3603af03288b95cd63c19967c68924a",
            ),
        )
        connection.execute(
            """
            INSERT INTO evidence_items (
                case_id, evidence_id, schema_version, evidence_code, availability,
                value_type, typed_value_json, source_type, source_ref,
                source_reliability, observed_at, collected_at, synthetic, content_hash
            ) VALUES (?, '00000000-0000-4000-8000-000000000011', '1',
                      'context.environment', 'AVAILABLE', 'STRING', '"PROD"',
                      'SYNTHETIC_ADAPTER', 'synthetic:fixture', 'SYNTHETIC_TEST',
                      '2026-07-18T04:05:00.000000Z',
                      '2026-07-18T04:10:00.000000Z', 1, ?)
            """,
            (
                CASE_ID,
                "e7ece8a666bf0e272b106ce7c23cdf38458faea14f08c3cd20cd140548fe85d5",
            ),
        )
        connection.execute(
            """
            UPDATE cases
            SET case_revision = 3, evidence_revision = 2,
                updated_at = '2026-07-18T04:10:00.000000Z', readiness_json = ?
            WHERE case_id = ?
            """,
            (
                '{"completion_ratio":"0.2000","known_unknown_fields":[],'
                '"missing_fields":["integration.type","symptom.signal",'
                '"transaction.occurred_at","transaction.reference"],'
                '"next_question":"transaction.reference",'
                '"question_reason":"定位同一笔交易","ready":false,'
                '"stop_reason":"NEED_MORE_EVIDENCE",'
                '"target_role":"MERCHANT_TECH"}',
                CASE_ID,
            ),
        )
    finally:
        connection.close()

    with SqliteCaseStoreFactory(db_path)() as store:
        view = store.get_case_view(CASE_ID)
        snapshot = store.load_case_snapshot(CASE_ID)

    assert view is not None
    assert snapshot is not None
    assert snapshot.case == view.case
    assert snapshot.evidence == view.evidence
    assert tuple(item.evidence_id for item in view.evidence) == (
        "00000000-0000-4000-8000-000000000011",
        "00000000-0000-4000-8000-000000000012",
    )
    item = view.evidence[0]
    assert item.evidence_id == "00000000-0000-4000-8000-000000000011"
    assert item.evidence_code.value == "context.environment"
    assert item.value_type.value == "STRING"
    assert item.typed_value == "PROD"
    assert item.observed_at == datetime(2026, 7, 18, 4, 5, tzinfo=UTC)
    assert item.collected_at == datetime(2026, 7, 18, 4, 10, tzinfo=UTC)


def test_public_read_transaction_cannot_mix_case_and_evidence_versions(
    db_path: Path,
) -> None:
    initialize_schema(db_path)
    seed = connect_sqlite(db_path)
    try:
        _seed_empty_case(seed)
    finally:
        seed.close()
    case_row_seen = Barrier(2)
    writer_mutated = Barrier(2)
    outcomes: Queue[tuple[str, object]] = Queue()

    def reader() -> None:
        connection = connect_sqlite(db_path)
        blocked = False

        def blocking_row_factory(
            cursor: sqlite3.Cursor,
            row: tuple[object, ...],
        ) -> sqlite3.Row:
            nonlocal blocked
            columns = tuple(description[0] for description in cursor.description)
            if not blocked and "readiness_json" in columns and "case_revision" in columns:
                blocked = True
                case_row_seen.wait(timeout=5)
                writer_mutated.wait(timeout=5)
            return sqlite3.Row(cursor, row)

        connection.row_factory = blocking_row_factory
        try:
            view = SqliteCaseStoreSession(connection).get_case_view(CASE_ID)
            outcomes.put(("reader", view))
        except BaseException as error:
            outcomes.put(("reader_error", error))
        finally:
            connection.close()

    def writer() -> None:
        connection = connect_sqlite(db_path)
        try:
            case_row_seen.wait(timeout=5)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO evidence_items (
                    case_id, evidence_id, schema_version, evidence_code, availability,
                    value_type, typed_value_json, source_type, source_ref,
                    source_reliability, observed_at, collected_at, synthetic,
                    content_hash
                ) VALUES (?, '00000000-0000-4000-8000-000000000011', '1',
                          'context.environment', 'AVAILABLE', 'STRING', '"PROD"',
                          'SYNTHETIC_ADAPTER', 'synthetic:fixture', 'SYNTHETIC_TEST',
                          '2026-07-18T04:05:00.000000Z',
                          '2026-07-18T04:10:00.000000Z', 1, ?)
                """,
                (
                    CASE_ID,
                    "e7ece8a666bf0e272b106ce7c23cdf38458faea14f08c3cd20cd140548fe85d5",
                ),
            )
            connection.execute(
                """
                UPDATE cases
                SET case_revision = 2, evidence_revision = 1,
                    updated_at = '2026-07-18T04:10:00.000000Z', readiness_json = ?
                WHERE case_id = ?
                """,
                (
                    '{"completion_ratio":"0.2000","known_unknown_fields":[],'
                    '"missing_fields":["integration.type","symptom.signal",'
                    '"transaction.occurred_at","transaction.reference"],'
                    '"next_question":"transaction.reference",'
                    '"question_reason":"定位同一笔交易","ready":false,'
                    '"stop_reason":"NEED_MORE_EVIDENCE",'
                    '"target_role":"MERCHANT_TECH"}',
                    CASE_ID,
                ),
            )
            writer_mutated.wait(timeout=5)
            connection.execute("COMMIT")
            outcomes.put(("writer", "committed"))
        except BaseException as error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            outcomes.put(("writer_error", error))
        finally:
            connection.close()

    threads = [Thread(target=reader), Thread(target=writer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    results = dict(outcomes.get_nowait() for _ in range(2))
    assert results["writer"] == "committed"
    old_view = results["reader"]
    assert old_view is not None
    assert old_view.case.case_revision == 1
    assert old_view.case.evidence_revision == 0
    assert old_view.evidence == ()
    with SqliteCaseStoreFactory(db_path)() as store:
        new_view = store.get_case_view(CASE_ID)
    assert new_view is not None
    assert new_view.case.case_revision == 2
    assert new_view.case.evidence_revision == 1
    assert len(new_view.evidence) == 1
