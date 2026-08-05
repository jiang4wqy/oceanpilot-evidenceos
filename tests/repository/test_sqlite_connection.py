import sqlite3
from pathlib import Path

import pytest

import oceanpilot.adapters.persistence.sqlite as sqlite_adapter
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    connect_sqlite,
    immediate_transaction,
    initialize_schema,
)
from oceanpilot.application.errors import DatabaseUnavailable

_REQUIRED_TABLE_NAMES = (
    "audit_events",
    "cases",
    "diagnosis_snapshots",
    "evidence_items",
    "hypotheses",
    "hypothesis_evidence_refs",
)


def _assert_safe_database_error(error: DatabaseUnavailable) -> None:
    assert str(error) == "database is unavailable"
    assert error.__cause__ is None


class _ConnectProxy:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fail_on: str | None = None,
        ignore_foreign_keys_on: bool = False,
    ) -> None:
        self._connection = connection
        self._fail_on = fail_on
        self._ignore_foreign_keys_on = ignore_foreign_keys_on

    @property
    def row_factory(self):
        return self._connection.row_factory

    @row_factory.setter
    def row_factory(self, value) -> None:
        self._connection.row_factory = value

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        normalized = " ".join(sql.lower().split())
        if self._fail_on == normalized:
            raise sqlite3.OperationalError("SQLITE-PRAGMA-SENTINEL")
        if self._ignore_foreign_keys_on and normalized == "pragma foreign_keys=on":
            return self._connection.execute("PRAGMA foreign_keys=OFF")
        return self._connection.execute(sql, *args)

    def close(self) -> None:
        self._connection.close()


def test_connection_enables_required_pragmas_and_frozen_options(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_connect = sqlite3.connect
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    connection = connect_sqlite(db_path)
    try:
        assert calls == [
            (
                (str(db_path),),
                {
                    "timeout": 5.0,
                    "isolation_level": None,
                    "autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL,
                },
            )
        ]
        assert connection.row_factory is sqlite3.Row
        assert connection.isolation_level is None
        assert connection.autocommit == sqlite3.LEGACY_TRANSACTION_CONTROL
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        connection.close()


def test_connect_error_is_mapped_without_sqlite_message(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_connect(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise sqlite3.OperationalError("SQLITE-SENTINEL-DO-NOT-ECHO")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)
    with pytest.raises(DatabaseUnavailable) as caught:
        connect_sqlite(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)


def test_pragma_execution_failure_closes_obtained_connection(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_connection = sqlite3.connect(db_path)
    proxy = _ConnectProxy(raw_connection, fail_on="pragma busy_timeout=5000")
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: proxy)

    with pytest.raises(DatabaseUnavailable) as caught:
        connect_sqlite(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)
    with pytest.raises(sqlite3.ProgrammingError):
        raw_connection.execute("SELECT 1")


def test_foreign_keys_readback_zero_closes_obtained_connection(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_connection = sqlite3.connect(db_path)
    proxy = _ConnectProxy(raw_connection, ignore_foreign_keys_on=True)
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: proxy)

    with pytest.raises(DatabaseUnavailable) as caught:
        connect_sqlite(db_path)

    _assert_safe_database_error(caught.value)
    with pytest.raises(sqlite3.ProgrammingError):
        raw_connection.execute("SELECT 1")


def test_fresh_database_uses_delete_journal_and_leaves_no_helpers(db_path: Path) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    with immediate_transaction(connection):
        connection.execute("CREATE TABLE journal_write_probe (value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO journal_write_probe(value) VALUES (?)",
            ("demo",),
        )
    connection.close()

    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()


def test_preseeded_wal_mode_is_rejected_without_helper_files(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = sqlite3.connect(db_path)
    assert seed.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    seed.execute("CREATE TABLE wal_probe (value TEXT NOT NULL)")
    seed.execute("INSERT INTO wal_probe(value) VALUES ('demo')")
    seed.commit()
    seed.close()

    assert not Path(f"{db_path}-wal").exists()
    assert not Path(f"{db_path}-shm").exists()
    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    with pytest.raises(DatabaseUnavailable) as caught:
        connect_sqlite(db_path)

    _assert_safe_database_error(caught.value)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_corrupt_database_is_rejected_without_leaking(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path.write_bytes(b"SQLITE-CORRUPT-SENTINEL")
    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    with pytest.raises(DatabaseUnavailable) as caught:
        connect_sqlite(db_path)

    _assert_safe_database_error(caught.value)
    assert "SENTINEL" not in str(caught.value)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_successful_transaction_uses_begin_immediate_and_persists(db_path: Path) -> None:
    connection = connect_sqlite(db_path)
    connection.execute("CREATE TABLE tx_probe (value TEXT NOT NULL)")
    traced: list[str] = []
    connection.set_trace_callback(traced.append)
    with immediate_transaction(connection):
        connection.execute("INSERT INTO tx_probe(value) VALUES (?)", ("demo",))
    connection.close()

    reopened = connect_sqlite(db_path)
    try:
        assert reopened.execute("SELECT value FROM tx_probe").fetchone()[0] == "demo"
    finally:
        reopened.close()
    assert "BEGIN IMMEDIATE" in traced
    assert "COMMIT" in traced


def test_failed_transaction_rolls_back_every_write(db_path: Path) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    connection.execute("CREATE TABLE tx_probe (value TEXT NOT NULL)")
    traced: list[str] = []
    connection.set_trace_callback(traced.append)
    with pytest.raises(RuntimeError), immediate_transaction(connection):
        connection.execute("INSERT INTO tx_probe(value) VALUES (?)", ("demo",))
        raise RuntimeError("force rollback")
    assert connection.execute("SELECT count(*) FROM tx_probe").fetchone()[0] == 0
    assert "ROLLBACK" in traced
    connection.close()


class _SyntheticAbort(BaseException):
    pass


def test_base_exception_rolls_back_every_write(db_path: Path) -> None:
    connection = connect_sqlite(db_path)
    connection.execute("CREATE TABLE tx_probe (value TEXT NOT NULL)")
    with pytest.raises(_SyntheticAbort), immediate_transaction(connection):
        connection.execute("INSERT INTO tx_probe(value) VALUES (?)", ("demo",))
        raise _SyntheticAbort
    assert connection.execute("SELECT count(*) FROM tx_probe").fetchone()[0] == 0
    connection.close()


def test_commit_time_foreign_key_failure_rolls_back(db_path: Path) -> None:
    connection = connect_sqlite(db_path)
    connection.executescript(
        """
        CREATE TABLE parent (id TEXT PRIMARY KEY);
        CREATE TABLE child (
            parent_id TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES parent(id)
                DEFERRABLE INITIALLY DEFERRED
        );
        """
    )
    traced: list[str] = []
    connection.set_trace_callback(traced.append)
    with pytest.raises(sqlite3.IntegrityError), immediate_transaction(connection):
        connection.execute("INSERT INTO child(parent_id) VALUES (?)", ("missing",))
    assert connection.in_transaction is False
    assert connection.execute("SELECT count(*) FROM child").fetchone()[0] == 0
    assert "ROLLBACK" in traced
    connection.close()


@pytest.mark.parametrize("missing_table", _REQUIRED_TABLE_NAMES)
def test_healthcheck_rejects_each_missing_required_table(db_path: Path, missing_table: str) -> None:
    initialize_schema(db_path)
    raw_connection = sqlite3.connect(db_path)
    raw_connection.execute(f'DROP TABLE "{missing_table}"')
    raw_connection.close()

    factory = SqliteCaseStoreFactory(db_path)
    with factory() as session, pytest.raises(DatabaseUnavailable) as caught:
        session.healthcheck()

    _assert_safe_database_error(caught.value)


def test_healthcheck_rejects_foreign_key_check_violation(db_path: Path) -> None:
    initialize_schema(db_path)
    raw_connection = sqlite3.connect(db_path)
    raw_connection.execute(
        """
        INSERT INTO evidence_items (
            case_id, evidence_id, schema_version, evidence_code, availability,
            value_type, typed_value_json, source_type, source_ref,
            source_reliability, observed_at, collected_at, synthetic, content_hash
        ) VALUES ('missing-case', 'evidence', '1', 'context.environment',
                  'AVAILABLE', 'STRING', '"PROD"', 'SYNTHETIC_ADAPTER',
                  'synthetic:fixture', 'SYNTHETIC_TEST', NULL,
                  '2026-07-18T04:00:00Z', 1, ?)
        """,
        ("0" * 64,),
    )
    raw_connection.commit()
    raw_connection.close()

    factory = SqliteCaseStoreFactory(db_path)
    with factory() as session, pytest.raises(DatabaseUnavailable) as caught:
        session.healthcheck()

    _assert_safe_database_error(caught.value)


def test_healthcheck_executes_cases_column_probe(db_path: Path) -> None:
    raw_connection = sqlite3.connect(db_path)
    for table in _REQUIRED_TABLE_NAMES:
        raw_connection.execute(f'CREATE TABLE "{table}" (wrong_column TEXT)')
    raw_connection.close()

    factory = SqliteCaseStoreFactory(db_path)
    with factory() as session, pytest.raises(DatabaseUnavailable) as caught:
        session.healthcheck()

    _assert_safe_database_error(caught.value)


def test_healthcheck_allows_extra_non_business_table(db_path: Path) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    connection.execute("CREATE TABLE local_probe (value TEXT)")
    connection.close()

    factory = SqliteCaseStoreFactory(db_path)
    with factory() as session:
        assert session.healthcheck() is None


def test_factory_opens_distinct_connections_and_closes_every_exit(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_schema(db_path)
    real_connect = sqlite_adapter.connect_sqlite
    opened: list[sqlite3.Connection] = []

    def recording_connect(path: Path) -> sqlite3.Connection:
        connection = real_connect(path)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite_adapter, "connect_sqlite", recording_connect)
    factory = SqliteCaseStoreFactory(db_path)

    with factory() as first_session:
        first_session.healthcheck()

    with pytest.raises(RuntimeError), factory() as second_session:
        second_session.healthcheck()
        raise RuntimeError("context failure")

    assert first_session is not second_session
    assert len(opened) == 2
    assert opened[0] is not opened[1]
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
