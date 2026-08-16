"""SQLite persistence for case-analysis turns and confirmed review decisions."""

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from oceanpilot.adapters.persistence.sqlite import connect_sqlite, immediate_transaction
from oceanpilot.application.case_review import (
    AgentTurnRecord,
    ReviewAuditEvent,
    ReviewConfirmationResult,
    ReviewDecision,
    ReviewStatus,
)
from oceanpilot.application.errors import (
    CaseNotFound,
    ConcurrentCaseWrite,
    DatabaseUnavailable,
    PersistenceInvariantViolation,
)
from oceanpilot.domain.security import assert_no_sensitive_data

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _now() -> datetime:
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


def _text(raw: object) -> str:
    if type(raw) is not str or not raw:
        raise PersistenceInvariantViolation()
    return raw


def _integer(raw: object) -> int:
    if type(raw) is not int or raw < 0:
        raise PersistenceInvariantViolation()
    return raw


def _json_object(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise PersistenceInvariantViolation() from None
    if not isinstance(value, dict):
        raise PersistenceInvariantViolation()
    assert_no_sensitive_data(value)
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
        raise PersistenceInvariantViolation()
    return tuple(value)


def _database_call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (
        CaseNotFound,
        ConcurrentCaseWrite,
        PersistenceInvariantViolation,
        DatabaseUnavailable,
        ValueError,
    ):
        raise
    except sqlite3.OperationalError:
        raise DatabaseUnavailable() from None
    except sqlite3.Error:
        raise PersistenceInvariantViolation() from None


class SqliteCaseReviewStore:
    def __init__(self, path: Path, *, clock: Callable[[], datetime] = _now) -> None:
        self._path = Path(path)
        self._clock = clock

    def current_revision(self, case_id: str) -> int:
        def operation() -> int:
            connection = connect_sqlite(self._path)
            try:
                row = connection.execute(
                    "SELECT revision FROM chargeback_cases WHERE case_id = ?",
                    (case_id,),
                ).fetchone()
            finally:
                connection.close()
            if row is None:
                raise CaseNotFound()
            return _integer(row["revision"])

        return _database_call(operation)

    def save_turn(self, turn: AgentTurnRecord) -> None:
        _json_object(turn.response_json)
        if turn.proposal_json is not None:
            _json_object(turn.proposal_json)

        def operation() -> None:
            connection = connect_sqlite(self._path)
            try:
                with immediate_transaction(connection):
                    row = connection.execute(
                        "SELECT revision FROM chargeback_cases WHERE case_id = ?",
                        (turn.case_id,),
                    ).fetchone()
                    if row is None:
                        raise CaseNotFound()
                    if _integer(row["revision"]) != turn.case_revision:
                        raise ConcurrentCaseWrite()
                    connection.execute(
                        """
                        INSERT INTO chargeback_agent_turns (
                            turn_id, case_id, case_revision, trigger,
                            response_json, proposal_json, created_at, synthetic
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            turn.turn_id,
                            turn.case_id,
                            turn.case_revision,
                            turn.trigger,
                            turn.response_json,
                            turn.proposal_json,
                            _encode_dt(turn.created_at),
                        ),
                    )
            finally:
                connection.close()

        _database_call(operation)

    def latest_turn_payload(self, case_id: str, case_revision: int) -> str | None:
        def operation() -> str | None:
            connection = connect_sqlite(self._path)
            try:
                row = connection.execute(
                    """
                    SELECT response_json
                    FROM chargeback_agent_turns
                    WHERE case_id = ? AND case_revision = ?
                      AND proposal_json IS NULL AND trigger <> 'USER_MESSAGE'
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (case_id, case_revision),
                ).fetchone()
            finally:
                connection.close()
            return None if row is None else _text(row["response_json"])

        return _database_call(operation)

    def latest_decision(self, case_id: str) -> ReviewDecision | None:
        def operation() -> ReviewDecision | None:
            connection = connect_sqlite(self._path)
            try:
                row = connection.execute(
                    """
                    SELECT decision_id, case_id, source_turn_id, status, summary,
                           confirmed_materials_json, citation_ids_json, case_revision,
                           confirmed_by, confirmed_at, audit_event_id
                    FROM chargeback_review_decisions
                    WHERE case_id = ?
                    ORDER BY confirmed_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (case_id,),
                ).fetchone()
            finally:
                connection.close()
            return None if row is None else self._decision(row)

        return _database_call(operation)

    def confirm_review(
        self,
        *,
        case_id: str,
        source_turn_id: str,
        expected_revision: int,
        confirmed_by: str,
    ) -> ReviewConfirmationResult:
        actor = confirmed_by.strip()
        if not actor:
            raise ValueError("confirmed_by is required")

        def operation() -> ReviewConfirmationResult:
            connection = connect_sqlite(self._path)
            try:
                with immediate_transaction(connection):
                    existing = connection.execute(
                        """
                        SELECT decision_id, case_id, source_turn_id, status, summary,
                               confirmed_materials_json, citation_ids_json, case_revision,
                               confirmed_by, confirmed_at, audit_event_id
                        FROM chargeback_review_decisions
                        WHERE source_turn_id = ?
                        """,
                        (source_turn_id,),
                    ).fetchone()
                    if existing is not None:
                        decision = self._decision(existing)
                        if decision.case_id != case_id:
                            raise ValueError("review turn belongs to another case")
                        return ReviewConfirmationResult(result="REPLAYED", decision=decision)

                    turn = connection.execute(
                        """
                        SELECT case_id, case_revision, proposal_json
                        FROM chargeback_agent_turns WHERE turn_id = ?
                        """,
                        (source_turn_id,),
                    ).fetchone()
                    if turn is None or turn["proposal_json"] is None:
                        raise ValueError("review proposal was not found")
                    if _text(turn["case_id"]) != case_id:
                        raise ValueError("review turn belongs to another case")
                    if _integer(turn["case_revision"]) != expected_revision:
                        raise ConcurrentCaseWrite()

                    case_row = connection.execute(
                        "SELECT revision FROM chargeback_cases WHERE case_id = ?",
                        (case_id,),
                    ).fetchone()
                    if case_row is None:
                        raise CaseNotFound()
                    current_revision = _integer(case_row["revision"])
                    if current_revision != expected_revision:
                        raise ConcurrentCaseWrite()

                    proposal = _json_object(_text(turn["proposal_json"]))
                    try:
                        status = ReviewStatus(_text(proposal.get("status")))
                    except ValueError:
                        raise PersistenceInvariantViolation() from None
                    summary = _text(proposal.get("summary"))
                    materials = _string_tuple(proposal.get("confirmed_materials"))
                    citations = _string_tuple(proposal.get("citation_ids"))
                    moment = self._clock()
                    new_revision = current_revision + 1
                    decision_id = str(uuid4())
                    audit_event_id = str(uuid4())
                    cursor = connection.execute(
                        """
                        UPDATE chargeback_cases
                        SET revision = ?, updated_at = ?
                        WHERE case_id = ? AND revision = ?
                        """,
                        (new_revision, _encode_dt(moment), case_id, current_revision),
                    )
                    if cursor.rowcount != 1:
                        raise ConcurrentCaseWrite()
                    connection.execute(
                        """
                        INSERT INTO chargeback_review_decisions (
                            decision_id, case_id, source_turn_id, status, summary,
                            confirmed_materials_json, citation_ids_json, case_revision,
                            confirmed_by, confirmed_at, audit_event_id, synthetic
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            decision_id,
                            case_id,
                            source_turn_id,
                            status.value,
                            summary,
                            json.dumps(materials, ensure_ascii=False),
                            json.dumps(citations, ensure_ascii=False),
                            new_revision,
                            actor,
                            _encode_dt(moment),
                            audit_event_id,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO chargeback_review_audit (
                            audit_event_id, case_id, event_type, decision_id,
                            case_revision, occurred_at, synthetic
                        ) VALUES (?, ?, 'REVIEW_DECISION_CONFIRMED', ?, ?, ?, 1)
                        """,
                        (
                            audit_event_id,
                            case_id,
                            decision_id,
                            new_revision,
                            _encode_dt(moment),
                        ),
                    )
                    decision = ReviewDecision(
                        decision_id=decision_id,
                        case_id=case_id,
                        source_turn_id=source_turn_id,
                        status=status,
                        summary=summary,
                        confirmed_materials=materials,
                        citation_ids=citations,
                        case_revision=new_revision,
                        confirmed_by=actor,
                        confirmed_at=moment,
                        audit_event_id=audit_event_id,
                    )
                    return ReviewConfirmationResult(result="CREATED", decision=decision)
            finally:
                connection.close()

        return _database_call(operation)

    def audit_trail(self, case_id: str) -> tuple[ReviewAuditEvent, ...]:
        def operation() -> tuple[ReviewAuditEvent, ...]:
            connection = connect_sqlite(self._path)
            try:
                rows = connection.execute(
                    """
                    SELECT audit_event_id, case_id, event_type, decision_id,
                           case_revision, occurred_at
                    FROM chargeback_review_audit
                    WHERE case_id = ?
                    ORDER BY occurred_at, rowid
                    """,
                    (case_id,),
                ).fetchall()
            finally:
                connection.close()
            return tuple(
                ReviewAuditEvent(
                    audit_event_id=_text(row["audit_event_id"]),
                    case_id=_text(row["case_id"]),
                    event_type=_text(row["event_type"]),
                    decision_id=_text(row["decision_id"]),
                    case_revision=_integer(row["case_revision"]),
                    occurred_at=_decode_dt(row["occurred_at"]),
                )
                for row in rows
            )

        return _database_call(operation)

    @staticmethod
    def _decision(row: sqlite3.Row) -> ReviewDecision:
        try:
            status = ReviewStatus(_text(row["status"]))
        except ValueError:
            raise PersistenceInvariantViolation() from None
        materials = _string_tuple(json.loads(_text(row["confirmed_materials_json"])))
        citations = _string_tuple(json.loads(_text(row["citation_ids_json"])))
        return ReviewDecision(
            decision_id=_text(row["decision_id"]),
            case_id=_text(row["case_id"]),
            source_turn_id=_text(row["source_turn_id"]),
            status=status,
            summary=_text(row["summary"]),
            confirmed_materials=materials,
            citation_ids=citations,
            case_revision=_integer(row["case_revision"]),
            confirmed_by=_text(row["confirmed_by"]),
            confirmed_at=_decode_dt(row["confirmed_at"]),
            audit_event_id=_text(row["audit_event_id"]),
        )
