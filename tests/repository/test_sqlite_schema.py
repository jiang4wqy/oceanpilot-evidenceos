import sqlite3
from pathlib import Path

import pytest

import oceanpilot.adapters.persistence.sqlite as sqlite_adapter
from oceanpilot.adapters.persistence.sqlite import (
    connect_sqlite,
    immediate_transaction,
    initialize_schema,
)
from oceanpilot.application.errors import DatabaseUnavailable

_EXPECTED_TABLES = frozenset(
    {
        "audit_events",
        "cases",
        "diagnosis_snapshots",
        "evidence_items",
        "hypotheses",
        "hypothesis_evidence_refs",
    }
)

_EXPECTED_COLUMNS = {
    "cases": (
        ("case_id", "TEXT", 1, 1),
        ("case_type", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0),
        ("schema_version", "TEXT", 1, 0),
        ("case_revision", "INTEGER", 1, 0),
        ("evidence_revision", "INTEGER", 1, 0),
        ("synthetic", "INTEGER", 1, 0),
        ("summary", "TEXT", 1, 0),
        ("merchant_ref", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0),
        ("updated_at", "TEXT", 1, 0),
        ("current_diagnosis_id", "TEXT", 0, 0),
        ("readiness_json", "TEXT", 1, 0),
    ),
    "evidence_items": (
        ("case_id", "TEXT", 1, 1),
        ("evidence_id", "TEXT", 1, 2),
        ("schema_version", "TEXT", 1, 0),
        ("evidence_code", "TEXT", 1, 0),
        ("availability", "TEXT", 1, 0),
        ("value_type", "TEXT", 1, 0),
        ("typed_value_json", "TEXT", 0, 0),
        ("source_type", "TEXT", 1, 0),
        ("source_ref", "TEXT", 1, 0),
        ("source_reliability", "TEXT", 1, 0),
        ("observed_at", "TEXT", 0, 0),
        ("collected_at", "TEXT", 1, 0),
        ("synthetic", "INTEGER", 1, 0),
        ("content_hash", "TEXT", 1, 0),
    ),
    "diagnosis_snapshots": (
        ("case_id", "TEXT", 1, 1),
        ("diagnosis_id", "TEXT", 1, 2),
        ("evidence_revision", "INTEGER", 1, 0),
        ("policy_version", "TEXT", 1, 0),
        ("engine_version", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0),
        ("routing_json", "TEXT", 0, 0),
        ("ticket_json", "TEXT", 0, 0),
        ("requires_human", "INTEGER", 1, 0),
        ("review_reasons_json", "TEXT", 1, 0),
        ("synthetic", "INTEGER", 1, 0),
        ("created_at", "TEXT", 1, 0),
    ),
    "hypotheses": (
        ("case_id", "TEXT", 1, 1),
        ("hypothesis_id", "TEXT", 1, 2),
        ("diagnosis_id", "TEXT", 1, 0),
        ("cause_code", "TEXT", 1, 0),
        ("explanation", "TEXT", 1, 0),
        ("confidence_score", "REAL", 1, 0),
        ("confidence_method", "TEXT", 1, 0),
        ("next_verification_action", "TEXT", 1, 0),
        ("rule_id", "TEXT", 1, 0),
    ),
    "hypothesis_evidence_refs": (
        ("case_id", "TEXT", 1, 1),
        ("hypothesis_id", "TEXT", 1, 2),
        ("evidence_id", "TEXT", 1, 3),
    ),
    "audit_events": (
        ("case_id", "TEXT", 1, 1),
        ("event_id", "TEXT", 1, 2),
        ("event_type", "TEXT", 1, 0),
        ("event_version", "TEXT", 1, 0),
        ("request_id", "TEXT", 1, 0),
        ("trace_id", "TEXT", 1, 0),
        ("actor_type", "TEXT", 1, 0),
        ("action", "TEXT", 1, 0),
        ("from_status", "TEXT", 0, 0),
        ("to_status", "TEXT", 0, 0),
        ("case_revision", "INTEGER", 1, 0),
        ("evidence_revision", "INTEGER", 1, 0),
        ("occurred_at", "TEXT", 1, 0),
        ("result", "TEXT", 1, 0),
        ("reason_code", "TEXT", 0, 0),
        ("sanitized_metadata_json", "TEXT", 1, 0),
        ("synthetic", "INTEGER", 1, 0),
    ),
}

_EXPECTED_UNIQUE_INDEXES = {
    "cases": frozenset({("case_id",)}),
    "evidence_items": frozenset({("case_id", "evidence_id")}),
    "diagnosis_snapshots": frozenset(
        {
            ("case_id", "diagnosis_id"),
            ("case_id", "evidence_revision", "policy_version"),
        }
    ),
    "hypotheses": frozenset(
        {
            ("case_id", "hypothesis_id"),
            ("case_id", "diagnosis_id", "rule_id"),
        }
    ),
    "hypothesis_evidence_refs": frozenset(
        {("case_id", "hypothesis_id", "evidence_id")}
    ),
    "audit_events": frozenset({("case_id", "event_id")}),
}

_EXPECTED_FOREIGN_KEYS = {
    "cases": frozenset(
        {
            (
                "diagnosis_snapshots",
                (("case_id", "case_id"), ("current_diagnosis_id", "diagnosis_id")),
                "NO ACTION",
                "NO ACTION",
                "NONE",
            )
        }
    ),
    "evidence_items": frozenset(
        {("cases", (("case_id", "case_id"),), "NO ACTION", "NO ACTION", "NONE")}
    ),
    "diagnosis_snapshots": frozenset(
        {("cases", (("case_id", "case_id"),), "NO ACTION", "NO ACTION", "NONE")}
    ),
    "hypotheses": frozenset(
        {
            (
                "diagnosis_snapshots",
                (("case_id", "case_id"), ("diagnosis_id", "diagnosis_id")),
                "NO ACTION",
                "NO ACTION",
                "NONE",
            )
        }
    ),
    "hypothesis_evidence_refs": frozenset(
        {
            (
                "evidence_items",
                (("case_id", "case_id"), ("evidence_id", "evidence_id")),
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
            (
                "hypotheses",
                (("case_id", "case_id"), ("hypothesis_id", "hypothesis_id")),
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
        }
    ),
    "audit_events": frozenset(
        {("cases", (("case_id", "case_id"),), "NO ACTION", "NO ACTION", "NONE")}
    ),
}


def _table_columns(
    connection: sqlite3.Connection, table: str
) -> tuple[tuple[str, str, int, int], ...]:
    return tuple(
        (row["name"], row["type"], row["notnull"], row["pk"])
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    )


def _unique_indexes(
    connection: sqlite3.Connection, table: str
) -> frozenset[tuple[str, ...]]:
    unique_indexes: set[tuple[str, ...]] = set()
    for index in connection.execute(f'PRAGMA index_list("{table}")'):
        if index["unique"] != 1:
            continue
        index_name = index["name"]
        columns = tuple(
            row["name"]
            for row in connection.execute(f'PRAGMA index_info("{index_name}")')
        )
        unique_indexes.add(columns)
    return frozenset(unique_indexes)


def _foreign_keys(
    connection: sqlite3.Connection, table: str
) -> frozenset[tuple[str, tuple[tuple[str, str], ...], str, str, str]]:
    grouped: dict[
        tuple[int, str, str, str, str], list[tuple[int, str, str]]
    ] = {}
    for row in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
        key = (
            row["id"],
            row["table"],
            row["on_update"],
            row["on_delete"],
            row["match"],
        )
        grouped.setdefault(key, []).append((row["seq"], row["from"], row["to"]))

    return frozenset(
        (
            target,
            tuple((source, destination) for _, source, destination in sorted(columns)),
            on_update,
            on_delete,
            match,
        )
        for (_, target, on_update, on_delete, match), columns in grouped.items()
    )


def _insert_case(
    connection: sqlite3.Connection,
    *,
    case_id: str = "00000000-0000-4000-8000-000000000100",
    case_type: str = "PAYMENT_INCIDENT",
    status: str = "NEED_INFO",
    case_revision: int = 0,
    evidence_revision: int = 0,
    synthetic: int = 1,
    summary: str = "synthetic incident",
    merchant_ref: str = "merchant_demo",
    current_diagnosis_id: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO cases (
            case_id, case_type, status, schema_version, case_revision,
            evidence_revision, synthetic, summary, merchant_ref, created_at,
            updated_at, current_diagnosis_id, readiness_json
        ) VALUES (?, ?, ?, '1', ?, ?, ?, ?, ?, ?, ?, ?, '{}')
        """,
        (
            case_id,
            case_type,
            status,
            case_revision,
            evidence_revision,
            synthetic,
            summary,
            merchant_ref,
            "2026-07-18T04:00:00Z",
            "2026-07-18T04:00:00Z",
            current_diagnosis_id,
        ),
    )


def _insert_evidence(
    connection: sqlite3.Connection,
    *,
    case_id: str = "00000000-0000-4000-8000-000000000100",
    evidence_id: str = "00000000-0000-4000-8000-000000000200",
    availability: str = "AVAILABLE",
    synthetic: int = 1,
    content_hash: str = "0" * 64,
) -> None:
    connection.execute(
        """
        INSERT INTO evidence_items (
            case_id, evidence_id, schema_version, evidence_code, availability,
            value_type, typed_value_json, source_type, source_ref,
            source_reliability, observed_at, collected_at, synthetic, content_hash
        ) VALUES (?, ?, '1', 'context.environment', ?, 'STRING', '"PROD"',
                  'SYNTHETIC_ADAPTER', 'synthetic:fixture', 'SYNTHETIC_TEST',
                  NULL, '2026-07-18T04:00:00Z', ?, ?)
        """,
        (case_id, evidence_id, availability, synthetic, content_hash),
    )


def _insert_diagnosis(
    connection: sqlite3.Connection,
    *,
    case_id: str = "00000000-0000-4000-8000-000000000100",
    diagnosis_id: str = "00000000-0000-4000-8000-000000000300",
    evidence_revision: int = 0,
    policy_version: str = "POLICY_V1",
    status: str = "CURRENT",
    requires_human: int = 0,
    synthetic: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO diagnosis_snapshots (
            case_id, diagnosis_id, evidence_revision, policy_version,
            engine_version, status, routing_json, ticket_json, requires_human,
            review_reasons_json, synthetic, created_at
        ) VALUES (?, ?, ?, ?, 'ENGINE_V1', ?, NULL, NULL, ?, '[]', ?, ?)
        """,
        (
            case_id,
            diagnosis_id,
            evidence_revision,
            policy_version,
            status,
            requires_human,
            synthetic,
            "2026-07-18T04:00:00Z",
        ),
    )


def _insert_hypothesis(
    connection: sqlite3.Connection,
    *,
    case_id: str = "00000000-0000-4000-8000-000000000100",
    hypothesis_id: str = "00000000-0000-4000-8000-000000000400",
    diagnosis_id: str = "00000000-0000-4000-8000-000000000300",
    confidence_score: float = 0.94,
    confidence_method: str = "HEURISTIC_V1",
    rule_id: str = "RULE_V1",
) -> None:
    connection.execute(
        """
        INSERT INTO hypotheses (
            case_id, hypothesis_id, diagnosis_id, cause_code, explanation,
            confidence_score, confidence_method, next_verification_action, rule_id
        ) VALUES (?, ?, ?, 'CAUSE', 'safe explanation', ?, ?, 'verify', ?)
        """,
        (
            case_id,
            hypothesis_id,
            diagnosis_id,
            confidence_score,
            confidence_method,
            rule_id,
        ),
    )


def _insert_audit(
    connection: sqlite3.Connection,
    *,
    case_id: str = "00000000-0000-4000-8000-000000000100",
    event_id: str = "00000000-0000-4000-8000-000000000500",
    case_revision: int = 0,
    evidence_revision: int = 0,
    synthetic: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_events (
            case_id, event_id, event_type, event_version, request_id, trace_id,
            actor_type, action, from_status, to_status, case_revision,
            evidence_revision, occurred_at, result, reason_code,
            sanitized_metadata_json, synthetic
        ) VALUES (?, ?, 'CASE_EVENT', '1', 'request', 'trace', 'SYSTEM',
                  'TEST', NULL, 'NEED_INFO', ?, ?, ?, 'SUCCESS', NULL, '{}', ?)
        """,
        (
            case_id,
            event_id,
            case_revision,
            evidence_revision,
            "2026-07-18T04:00:00Z",
            synthetic,
        ),
    )


def _assert_safe_database_error(error: DatabaseUnavailable) -> None:
    assert str(error) == "database is unavailable"
    assert error.__cause__ is None


def test_initialize_schema_creates_exact_metadata_on_real_file(db_path: Path) -> None:
    initialize_schema(db_path)

    assert db_path.is_file()
    connection = connect_sqlite(db_path)
    try:
        main_database = next(
            row for row in connection.execute("PRAGMA database_list") if row["name"] == "main"
        )
        assert Path(main_database["file"]).resolve() == db_path.resolve()

        table_names = frozenset(
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        )
        assert table_names == _EXPECTED_TABLES

        for table in _EXPECTED_TABLES:
            assert _table_columns(connection, table) == _EXPECTED_COLUMNS[table]
            assert _unique_indexes(connection, table) == _EXPECTED_UNIQUE_INDEXES[table]
            assert _foreign_keys(connection, table) == _EXPECTED_FOREIGN_KEYS[table]

        normalized_sql = {
            row["name"]: " ".join(row["sql"].lower().split())
            for row in connection.execute(
                """
                SELECT name, sql
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        assert (
            "foreign key (case_id, current_diagnosis_id) references "
            "diagnosis_snapshots(case_id, diagnosis_id) deferrable initially deferred"
            in normalized_sql["cases"]
        )
        assert sum(
            sql.count("deferrable initially deferred") for sql in normalized_sql.values()
        ) == 1
    finally:
        connection.close()


def test_cases_primary_key_rejects_null(db_path: Path) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO cases (
                    case_id, case_type, status, schema_version, case_revision,
                    evidence_revision, synthetic, summary, merchant_ref, created_at,
                    updated_at, current_diagnosis_id, readiness_json
                ) VALUES (NULL, 'PAYMENT_INCIDENT', 'NEED_INFO', '1', 0, 0, 1,
                          'synthetic incident', 'merchant_demo',
                          '2026-07-18T04:00:00Z', '2026-07-18T04:00:00Z', NULL, '{}')
                """
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("overrides"),
    [
        {"case_type": "OTHER"},
        {"status": "ASSIGNED"},
        {"case_revision": -1},
        {"evidence_revision": -1},
        {"synthetic": 0},
        {"summary": ""},
        {"summary": "x" * 501},
        {"merchant_ref": ""},
        {"merchant_ref": "x" * 129},
    ],
)
def test_cases_check_constraints_reject_invalid_rows(
    db_path: Path, overrides: dict[str, object]
) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_case(connection, **overrides)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("overrides"),
    [
        {"availability": "UNKNOWN"},
        {"synthetic": 0},
        {"content_hash": "0" * 63},
    ],
)
def test_evidence_check_constraints_reject_invalid_rows(
    db_path: Path, overrides: dict[str, object]
) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        _insert_case(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_evidence(connection, **overrides)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("overrides"),
    [
        {"evidence_revision": -1},
        {"status": "ARCHIVED"},
        {"requires_human": 2},
        {"synthetic": 0},
    ],
)
def test_diagnosis_check_constraints_reject_invalid_rows(
    db_path: Path, overrides: dict[str, object]
) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        _insert_case(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_diagnosis(connection, **overrides)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("overrides"),
    [
        {"confidence_score": -0.01},
        {"confidence_score": 1.01},
        {"confidence_method": "MODEL_PROBABILITY"},
    ],
)
def test_hypothesis_check_constraints_reject_invalid_rows(
    db_path: Path, overrides: dict[str, object]
) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        _insert_case(connection)
        _insert_diagnosis(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_hypothesis(connection, **overrides)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("overrides"),
    [
        {"case_revision": -1},
        {"evidence_revision": -1},
        {"synthetic": 0},
    ],
)
def test_audit_check_constraints_reject_invalid_rows(
    db_path: Path, overrides: dict[str, object]
) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        _insert_case(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_audit(connection, **overrides)
    finally:
        connection.close()


def test_primary_and_unique_constraints_reject_duplicates(db_path: Path) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        _insert_case(connection)

        _insert_evidence(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_evidence(connection)

        _insert_diagnosis(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_diagnosis(
                connection,
                diagnosis_id="00000000-0000-4000-8000-000000000301",
            )

        _insert_hypothesis(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_hypothesis(
                connection,
                hypothesis_id="00000000-0000-4000-8000-000000000401",
            )

        _insert_audit(connection)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_audit(connection)
    finally:
        connection.close()


def test_composite_foreign_keys_reject_cross_case_references(db_path: Path) -> None:
    case_a = "00000000-0000-4000-8000-000000000100"
    case_b = "00000000-0000-4000-8000-000000000101"
    diagnosis_a = "00000000-0000-4000-8000-000000000300"
    hypothesis_a = "00000000-0000-4000-8000-000000000400"
    evidence_a = "00000000-0000-4000-8000-000000000200"
    evidence_b = "00000000-0000-4000-8000-000000000201"

    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        _insert_case(connection, case_id=case_a)
        _insert_case(connection, case_id=case_b)
        _insert_diagnosis(connection, case_id=case_a, diagnosis_id=diagnosis_a)
        _insert_hypothesis(
            connection,
            case_id=case_a,
            hypothesis_id=hypothesis_a,
            diagnosis_id=diagnosis_a,
        )
        _insert_evidence(connection, case_id=case_b, evidence_id=evidence_b)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO hypothesis_evidence_refs (
                    case_id, hypothesis_id, evidence_id
                ) VALUES (?, ?, ?)
                """,
                (case_a, hypothesis_a, evidence_b),
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_hypothesis(
                connection,
                case_id=case_b,
                hypothesis_id="00000000-0000-4000-8000-000000000401",
                diagnosis_id=diagnosis_a,
            )

        _insert_evidence(connection, case_id=case_a, evidence_id=evidence_a)
        connection.execute(
            """
            INSERT INTO hypothesis_evidence_refs (case_id, hypothesis_id, evidence_id)
            VALUES (?, ?, ?)
            """,
            (case_a, hypothesis_a, evidence_a),
        )
        assert connection.execute(
            "SELECT count(*) FROM hypothesis_evidence_refs"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_deferred_current_diagnosis_reference_supports_cycle_and_rolls_back_cross_case(
    db_path: Path,
) -> None:
    case_a = "00000000-0000-4000-8000-000000000100"
    case_b = "00000000-0000-4000-8000-000000000101"
    diagnosis_a = "00000000-0000-4000-8000-000000000300"
    diagnosis_b = "00000000-0000-4000-8000-000000000301"

    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    try:
        with immediate_transaction(connection):
            _insert_case(
                connection,
                case_id=case_a,
                current_diagnosis_id=diagnosis_a,
            )
            _insert_diagnosis(connection, case_id=case_a, diagnosis_id=diagnosis_a)

        _insert_case(connection, case_id=case_b)
        _insert_diagnosis(connection, case_id=case_b, diagnosis_id=diagnosis_b)

        with pytest.raises(sqlite3.IntegrityError), immediate_transaction(connection):
            connection.execute(
                "UPDATE cases SET current_diagnosis_id = ? WHERE case_id = ?",
                (diagnosis_b, case_a),
            )

        assert connection.execute(
            "SELECT current_diagnosis_id FROM cases WHERE case_id = ?",
            (case_a,),
        ).fetchone()[0] == diagnosis_a
    finally:
        connection.close()


def test_initialize_schema_creates_parent_and_closes_its_single_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "nested" / "oceanpilot.db"
    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    initialize_schema(db_path)

    assert db_path.is_file()
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


class _FailingSchemaConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def executescript(self, sql: str) -> None:
        del sql
        raise sqlite3.OperationalError("SQLITE-SCHEMA-SENTINEL")

    def execute(self, sql: str) -> sqlite3.Cursor:
        return self._connection.execute(sql)

    def close(self) -> None:
        self._connection.close()


def test_initialize_schema_closes_connection_after_ddl_failure(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_connection = sqlite3.connect(db_path)
    failing_connection = _FailingSchemaConnection(raw_connection)
    monkeypatch.setattr(
        sqlite_adapter,
        "connect_sqlite",
        lambda path: failing_connection,
    )

    with pytest.raises(DatabaseUnavailable) as caught:
        initialize_schema(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)
    with pytest.raises(sqlite3.ProgrammingError):
        raw_connection.execute("SELECT 1")


def test_initialize_schema_rolls_back_partial_ddl_after_script_error(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    monkeypatch.setattr(
        sqlite_adapter,
        "SCHEMA_SQL",
        """
        CREATE TABLE cases (case_id TEXT NOT NULL PRIMARY KEY);
        DDL-SENTINEL IS NOT VALID SQL;
        """,
    )

    with pytest.raises(DatabaseUnavailable) as caught:
        initialize_schema(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")

    reopened = real_connect(db_path)
    try:
        business_tables = frozenset(
            row[0]
            for row in reopened.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        ).intersection(_EXPECTED_TABLES)
        assert business_tables == frozenset()
        reopened.execute("BEGIN IMMEDIATE")
        assert reopened.in_transaction is True
        reopened.execute("ROLLBACK")
        assert reopened.in_transaction is False
    finally:
        reopened.close()


def test_initialize_schema_closes_connection_after_table_set_self_check_failure(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = sqlite3.connect(db_path)
    seed.execute("CREATE TABLE unexpected_table (value TEXT)")
    seed.close()

    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    with pytest.raises(DatabaseUnavailable) as caught:
        initialize_schema(db_path)

    _assert_safe_database_error(caught.value)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_initialize_schema_rejects_foreign_key_check_violation_and_closes(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_schema(db_path)
    seed = sqlite3.connect(db_path)
    seed.execute(
        """
        INSERT INTO evidence_items (
            case_id, evidence_id, schema_version, evidence_code, availability,
            value_type, typed_value_json, source_type, source_ref,
            source_reliability, observed_at, collected_at, synthetic, content_hash
        ) VALUES ('missing-case', 'evidence', '1', 'context.environment',
                  'AVAILABLE', 'STRING', '"PROD"', 'SYNTHETIC_ADAPTER',
                  'FK-SELF-CHECK-SENTINEL', 'SYNTHETIC_TEST', NULL,
                  '2026-07-18T04:00:00Z', 1, ?)
        """,
        ("0" * 64,),
    )
    seed.commit()
    assert seed.execute("PRAGMA foreign_key_check").fetchone() is not None
    seed.close()

    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    with pytest.raises(DatabaseUnavailable) as caught:
        initialize_schema(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_initialize_schema_maps_parent_creation_failure_without_leaking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "blocked" / "oceanpilot.db"

    def fail_mkdir(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PermissionError("PATH-SENTINEL")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with pytest.raises(DatabaseUnavailable) as caught:
        initialize_schema(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)


def test_initialize_schema_maps_corrupt_file_without_leaking(db_path: Path) -> None:
    db_path.write_bytes(b"SQLITE-CORRUPT-SENTINEL")

    with pytest.raises(DatabaseUnavailable) as caught:
        initialize_schema(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)
