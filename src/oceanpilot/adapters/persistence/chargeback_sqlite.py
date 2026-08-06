"""SQLite-backed durable store for the chargeback agent cluster (T9).

Implements the ``ChargebackCaseStore`` protocol (``create`` / ``load`` /
``save``) against a real SQLite file so chargeback cases survive across requests
and restarts, and adds three storage invariants the in-memory store could not:

* **Append-only evidence + immutable reason.** Once classified, a case keeps its
  reason code; collected evidence only ever grows. Violations are rejected, not
  silently merged.
* **Monotonic revision + optimistic CAS.** Every meaningful change bumps
  ``revision``. ``save_checked`` refuses a stale write (lost-update protection);
  an unchanged save is an idempotent *replay* that neither bumps the revision nor
  writes audit rows.
* **Atomic audit trail.** Each state change and its audit rows commit together in
  one ``BEGIN IMMEDIATE`` transaction; any failure rolls the whole change back.

Every method opens and closes its own connection, so the store is safe to share
across the API's request threads. All rows are synthetic-only.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from oceanpilot.adapters.persistence.chargeback_schema import (
    CHARGEBACK_REQUIRED_TABLES,
    CHARGEBACK_SCHEMA_SQL,
)
from oceanpilot.adapters.persistence.sqlite import connect_sqlite, immediate_transaction
from oceanpilot.application.chargeback_supervisor import ChargebackCaseState
from oceanpilot.application.errors import (
    CaseNotFound,
    ConcurrentCaseWrite,
    DatabaseUnavailable,
    PersistenceInvariantViolation,
)
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class ChargebackAuditEventType(StrEnum):
    CASE_OPENED = "CASE_OPENED"
    REASON_CLASSIFIED = "REASON_CLASSIFIED"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"


@dataclass(frozen=True, slots=True)
class ChargebackAuditRecord:
    seq: int
    event_type: ChargebackAuditEventType
    detail: str | None
    case_revision: int
    occurred_at: datetime


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _encode_dt(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PersistenceInvariantViolation()
    return value.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)


def _decode_dt(raw: object) -> datetime:
    if type(raw) is not str:
        raise PersistenceInvariantViolation()
    try:
        return datetime.strptime(raw, _TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        raise PersistenceInvariantViolation() from None


def _map_db_errors[T](operation: Callable[[], T]) -> T:
    """Map raw sqlite failures to application errors; pass everything else through.

    Application errors and non-DB exceptions (e.g. an injected clock failure used
    to exercise rollback) propagate unchanged so callers see the true cause.
    """
    try:
        return operation()
    except (
        CaseNotFound,
        ConcurrentCaseWrite,
        PersistenceInvariantViolation,
        DatabaseUnavailable,
    ):
        raise
    except sqlite3.OperationalError:
        raise DatabaseUnavailable() from None
    except sqlite3.Error:
        raise PersistenceInvariantViolation() from None


def initialize_chargeback_schema(path: Path) -> None:
    connection: sqlite3.Connection | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect_sqlite(path)
        connection.executescript(f"BEGIN IMMEDIATE;\n{CHARGEBACK_SCHEMA_SQL}\nCOMMIT;")
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
        if not CHARGEBACK_REQUIRED_TABLES.issubset(table_names):
            raise DatabaseUnavailable()
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise DatabaseUnavailable()
    except (OSError, sqlite3.Error, DatabaseUnavailable):
        raise DatabaseUnavailable() from None
    finally:
        if connection is not None:
            connection.close()


class SqliteChargebackCaseStore:
    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._path = Path(path)
        self._clock = clock

    # -- ChargebackCaseStore protocol -------------------------------------

    def create(self) -> str:
        case_id = str(uuid4())

        def operation() -> str:
            moment = self._clock()
            connection = connect_sqlite(self._path)
            try:
                with immediate_transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO chargeback_cases (
                            case_id, reason_code, revision, synthetic,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (case_id, None, 0, 1, _encode_dt(moment), _encode_dt(moment)),
                    )
                    if cursor.rowcount != 1:
                        raise PersistenceInvariantViolation()
                    self._insert_audit(
                        connection,
                        case_id=case_id,
                        seq=0,
                        event_type=ChargebackAuditEventType.CASE_OPENED,
                        detail=None,
                        case_revision=0,
                        moment=moment,
                    )
            finally:
                connection.close()
            return case_id

        return _map_db_errors(operation)

    def load(self, case_id: str) -> ChargebackCaseState | None:
        def operation() -> ChargebackCaseState | None:
            connection = connect_sqlite(self._path)
            try:
                loaded = self._load_state(connection, case_id)
            finally:
                connection.close()
            return loaded[0] if loaded is not None else None

        return _map_db_errors(operation)

    def save(self, case_id: str, state: ChargebackCaseState) -> None:
        self._save(case_id, state, expected_revision=None)

    # -- richer capabilities (used by store-level tests / callers) ---------

    def load_with_revision(self, case_id: str) -> tuple[ChargebackCaseState, int] | None:
        def operation() -> tuple[ChargebackCaseState, int] | None:
            connection = connect_sqlite(self._path)
            try:
                return self._load_state(connection, case_id)
            finally:
                connection.close()

        return _map_db_errors(operation)

    def current_revision(self, case_id: str) -> int:
        loaded = self.load_with_revision(case_id)
        if loaded is None:
            raise CaseNotFound()
        return loaded[1]

    def save_checked(
        self,
        case_id: str,
        state: ChargebackCaseState,
        *,
        expected_revision: int,
    ) -> int:
        return self._save(case_id, state, expected_revision=expected_revision)

    def audit_trail(self, case_id: str) -> tuple[ChargebackAuditRecord, ...]:
        def operation() -> tuple[ChargebackAuditRecord, ...]:
            connection = connect_sqlite(self._path)
            try:
                rows = connection.execute(
                    """
                    SELECT seq, event_type, detail, case_revision, occurred_at
                    FROM chargeback_audit
                    WHERE case_id = ?
                    ORDER BY seq
                    """,
                    (case_id,),
                ).fetchall()
            finally:
                connection.close()
            return tuple(
                ChargebackAuditRecord(
                    seq=self._require_int(row["seq"]),
                    event_type=ChargebackAuditEventType(self._require_text(row["event_type"])),
                    detail=(None if row["detail"] is None else self._require_text(row["detail"])),
                    case_revision=self._require_int(row["case_revision"]),
                    occurred_at=_decode_dt(row["occurred_at"]),
                )
                for row in rows
            )

        return _map_db_errors(operation)

    # -- internals ---------------------------------------------------------

    def _save(
        self,
        case_id: str,
        state: ChargebackCaseState,
        *,
        expected_revision: int | None,
    ) -> int:
        if not isinstance(state, ChargebackCaseState):
            raise PersistenceInvariantViolation()
        incoming_reason = state.reason_code
        if incoming_reason is not None and not isinstance(incoming_reason, DisputeReasonCode):
            raise PersistenceInvariantViolation()
        incoming_codes = frozenset(state.collected)
        if any(not isinstance(code, ChargebackEvidenceCode) for code in incoming_codes):
            raise PersistenceInvariantViolation()

        def operation() -> int:
            connection = connect_sqlite(self._path)
            try:
                with immediate_transaction(connection):
                    row = connection.execute(
                        "SELECT reason_code, revision FROM chargeback_cases WHERE case_id = ?",
                        (case_id,),
                    ).fetchone()
                    if row is None:
                        raise CaseNotFound()
                    current_revision = self._require_int(row["revision"])
                    current_reason = (
                        DisputeReasonCode(self._require_text(row["reason_code"]))
                        if row["reason_code"] is not None
                        else None
                    )
                    if expected_revision is not None and current_revision != expected_revision:
                        raise ConcurrentCaseWrite()

                    stored_codes = frozenset(
                        ChargebackEvidenceCode(self._require_text(evidence_row["evidence_code"]))
                        for evidence_row in connection.execute(
                            "SELECT evidence_code FROM chargeback_evidence WHERE case_id = ?",
                            (case_id,),
                        )
                    )
                    # Evidence is append-only; reason is immutable once assigned.
                    if not stored_codes.issubset(incoming_codes):
                        raise PersistenceInvariantViolation()
                    if current_reason is not None and incoming_reason != current_reason:
                        raise PersistenceInvariantViolation()

                    reason_changed = incoming_reason is not None and current_reason is None
                    new_codes = tuple(
                        sorted(incoming_codes - stored_codes, key=lambda code: code.value)
                    )
                    if not reason_changed and not new_codes:
                        return current_revision  # idempotent replay

                    new_revision = current_revision + 1
                    cursor = connection.execute(
                        """
                        UPDATE chargeback_cases
                        SET reason_code = ?, revision = ?, updated_at = ?
                        WHERE case_id = ? AND revision = ?
                        """,
                        (
                            incoming_reason.value if incoming_reason is not None else None,
                            new_revision,
                            _encode_dt(self._clock()),
                            case_id,
                            current_revision,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ConcurrentCaseWrite()

                    seq = self._next_seq(connection, case_id)
                    if reason_changed:
                        self._insert_audit(
                            connection,
                            case_id=case_id,
                            seq=seq,
                            event_type=ChargebackAuditEventType.REASON_CLASSIFIED,
                            detail=incoming_reason.value,
                            case_revision=new_revision,
                            moment=self._clock(),
                        )
                        seq += 1
                    for code in new_codes:
                        moment = self._clock()
                        evidence_cursor = connection.execute(
                            """
                            INSERT INTO chargeback_evidence (
                                case_id, evidence_code, added_at, added_at_revision, synthetic
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (case_id, code.value, _encode_dt(moment), new_revision, 1),
                        )
                        if evidence_cursor.rowcount != 1:
                            raise PersistenceInvariantViolation()
                        self._insert_audit(
                            connection,
                            case_id=case_id,
                            seq=seq,
                            event_type=ChargebackAuditEventType.EVIDENCE_ADDED,
                            detail=code.value,
                            case_revision=new_revision,
                            moment=moment,
                        )
                        seq += 1
                    return new_revision
            finally:
                connection.close()

        return _map_db_errors(operation)

    def _load_state(
        self,
        connection: sqlite3.Connection,
        case_id: str,
    ) -> tuple[ChargebackCaseState, int] | None:
        row = connection.execute(
            "SELECT reason_code, revision FROM chargeback_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            return None
        reason = (
            DisputeReasonCode(self._require_text(row["reason_code"]))
            if row["reason_code"] is not None
            else None
        )
        codes = {
            ChargebackEvidenceCode(self._require_text(evidence_row["evidence_code"]))
            for evidence_row in connection.execute(
                "SELECT evidence_code FROM chargeback_evidence WHERE case_id = ?",
                (case_id,),
            )
        }
        state = ChargebackCaseState(reason_code=reason, collected=codes)
        return state, self._require_int(row["revision"])

    def _next_seq(self, connection: sqlite3.Connection, case_id: str) -> int:
        row = connection.execute(
            "SELECT MAX(seq) AS max_seq FROM chargeback_audit WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        highest = row["max_seq"]
        if highest is None:
            return 0
        return self._require_int(highest) + 1

    def _insert_audit(
        self,
        connection: sqlite3.Connection,
        *,
        case_id: str,
        seq: int,
        event_type: ChargebackAuditEventType,
        detail: str | None,
        case_revision: int,
        moment: datetime,
    ) -> None:
        cursor = connection.execute(
            """
            INSERT INTO chargeback_audit (
                case_id, seq, event_type, detail, case_revision, occurred_at, synthetic
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (case_id, seq, event_type.value, detail, case_revision, _encode_dt(moment), 1),
        )
        if cursor.rowcount != 1:
            raise PersistenceInvariantViolation()

    @staticmethod
    def _require_int(raw: object) -> int:
        if type(raw) is not int:
            raise PersistenceInvariantViolation()
        return raw

    @staticmethod
    def _require_text(raw: object) -> str:
        if type(raw) is not str:
            raise PersistenceInvariantViolation()
        return raw
