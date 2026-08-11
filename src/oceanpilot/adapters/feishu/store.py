import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from oceanpilot.application.feishu_models import (
    FeishuApprovalRecord,
    FeishuConfirmationReceipt,
)

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS feishu_event_receipts (
        event_id TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK (status IN ('CLAIMED', 'COMPLETED')),
        response_json TEXT,
        case_id TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        CHECK (
            (status = 'CLAIMED' AND response_json IS NULL AND completed_at IS NULL)
            OR
            (status = 'COMPLETED' AND response_json IS NOT NULL
                AND case_id IS NOT NULL AND completed_at IS NOT NULL)
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_chat_cases (
        chat_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_action_receipts (
        action_id TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK (status IN ('CLAIMED', 'COMPLETED')),
        response_json TEXT,
        case_id TEXT,
        diagnosis_id TEXT,
        actor_id TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        CHECK (
            (status = 'CLAIMED' AND response_json IS NULL AND completed_at IS NULL)
            OR
            (status = 'COMPLETED' AND response_json IS NOT NULL
                AND case_id IS NOT NULL AND diagnosis_id IS NOT NULL
                AND actor_id IS NOT NULL AND completed_at IS NOT NULL)
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feishu_approval_audits (
        approval_id TEXT PRIMARY KEY,
        action_id TEXT NOT NULL UNIQUE,
        case_id TEXT NOT NULL,
        diagnosis_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        action_kind TEXT NOT NULL DEFAULT 'CONFIRM_REVIEW',
        result TEXT NOT NULL,
        request_id TEXT,
        trace_id TEXT,
        occurred_at TEXT NOT NULL,
        synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
    )
    """,
)

_SEMANTIC_APPROVAL_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_feishu_approval_semantic_action
ON feishu_approval_audits (case_id, diagnosis_id, action_kind)
WHERE request_id IS NOT NULL
"""

_FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "authorization",
        "body",
        "credential",
        "credentials",
        "secret",
        "token",
    }
)


class ReceiptOutcome(StrEnum):
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REPLAY = "REPLAY"


class ReceiptConflict(RuntimeError):
    pass


class ReceiptNotClaimed(RuntimeError):
    pass


@dataclass(frozen=True)
class ReceiptResult:
    outcome: ReceiptOutcome
    response: dict[str, object] | None = None


@dataclass(frozen=True)
class ApprovalAudit:
    approval_id: str
    action_id: str
    case_id: str
    diagnosis_id: str
    actor_hash: str
    action_kind: str
    result: str
    request_id: str | None
    trace_id: str | None
    occurred_at: str
    synthetic: bool


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be non-empty text")
    return value


def _actor_hash(actor_id: str) -> str:
    actor_id = _require_text("actor_id", actor_id)
    if len(actor_id) == 64 and all(character in "0123456789abcdef" for character in actor_id):
        return actor_id
    return hashlib.sha256(actor_id.encode("utf-8")).hexdigest()


def _reject_sensitive_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("response keys must be text")
            if key.casefold() in _FORBIDDEN_RESPONSE_KEYS:
                raise ValueError("response contains a forbidden key")
            _reject_sensitive_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_sensitive_keys(nested)


def _encode_response(response: Mapping[str, object]) -> str:
    if not isinstance(response, Mapping):
        raise ValueError("response must be an object")
    _reject_sensitive_keys(response)
    try:
        return json.dumps(
            dict(response),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        raise ValueError("response must contain JSON values") from None


def _decode_response(encoded: str) -> dict[str, object]:
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise RuntimeError("stored response is not an object")
    return decoded


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(path),
        timeout=5.0,
        isolation_level=None,
        autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


@contextmanager
def _immediate_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _add_column_if_missing(
    connection: sqlite3.Connection,
    *,
    table: str,
    column: str,
    declaration: str,
) -> None:
    columns = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _hash_existing_actor_ids(connection: sqlite3.Connection, *, table: str) -> None:
    rows = connection.execute(
        f"SELECT rowid, actor_id FROM {table} WHERE actor_id IS NOT NULL"
    ).fetchall()
    for row in rows:
        actor_hash = _actor_hash(row["actor_id"])
        if actor_hash != row["actor_id"]:
            connection.execute(
                f"UPDATE {table} SET actor_id = ? WHERE rowid = ?",
                (actor_hash, row["rowid"]),
            )


def _initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path)
    try:
        with _immediate_transaction(connection):
            for statement in _SCHEMA:
                connection.execute(statement)
            _add_column_if_missing(
                connection,
                table="feishu_approval_audits",
                column="request_id",
                declaration="TEXT",
            )
            _add_column_if_missing(
                connection,
                table="feishu_approval_audits",
                column="trace_id",
                declaration="TEXT",
            )
            _add_column_if_missing(
                connection,
                table="feishu_approval_audits",
                column="action_kind",
                declaration="TEXT NOT NULL DEFAULT 'CONFIRM_REVIEW'",
            )
            _hash_existing_actor_ids(connection, table="feishu_action_receipts")
            _hash_existing_actor_ids(connection, table="feishu_approval_audits")
            connection.execute(_SEMANTIC_APPROVAL_INDEX)
    finally:
        connection.close()


class FeishuCallbackStoreSession:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def _claim(
        self,
        *,
        table: str,
        key_column: str,
        receipt_id: str,
        created_at: str,
    ) -> ReceiptResult:
        _require_text(key_column, receipt_id)
        _require_text("created_at", created_at)
        with _immediate_transaction(self._connection):
            row = self._connection.execute(
                f"SELECT status, response_json FROM {table} WHERE {key_column} = ?",
                (receipt_id,),
            ).fetchone()
            if row is None:
                self._connection.execute(
                    f"INSERT INTO {table} ({key_column}, status, created_at) "
                    "VALUES (?, 'CLAIMED', ?)",
                    (receipt_id, created_at),
                )
                return ReceiptResult(ReceiptOutcome.CLAIMED)
            if row["status"] == "CLAIMED":
                return ReceiptResult(ReceiptOutcome.IN_PROGRESS)
            return ReceiptResult(
                ReceiptOutcome.REPLAY,
                _decode_response(row["response_json"]),
            )

    def claim_event(self, event_id: str, *, created_at: str) -> ReceiptResult:
        return self._claim(
            table="feishu_event_receipts",
            key_column="event_id",
            receipt_id=event_id,
            created_at=created_at,
        )

    def claim_action(self, action_id: str, *, created_at: str) -> ReceiptResult:
        return self._claim(
            table="feishu_action_receipts",
            key_column="action_id",
            receipt_id=action_id,
            created_at=created_at,
        )

    def complete_event(
        self,
        event_id: str,
        *,
        response: Mapping[str, object],
        case_id: str,
        completed_at: str,
    ) -> ReceiptResult:
        event_id = _require_text("event_id", event_id)
        encoded = _encode_response(response)
        metadata = {"case_id": _require_text("case_id", case_id)}
        completed_at = _require_text("completed_at", completed_at)
        with _immediate_transaction(self._connection):
            return self._complete_in_transaction(
                table="feishu_event_receipts",
                key_column="event_id",
                receipt_id=event_id,
                encoded=encoded,
                metadata=metadata,
                completed_at=completed_at,
            )

    def complete_action(
        self,
        action_id: str,
        *,
        response: Mapping[str, object],
        case_id: str,
        diagnosis_id: str,
        actor_id: str,
        completed_at: str,
    ) -> ReceiptResult:
        action_id, encoded, metadata, completed_at = self._action_completion_values(
            action_id=action_id,
            response=response,
            case_id=case_id,
            diagnosis_id=diagnosis_id,
            actor_id=actor_id,
            completed_at=completed_at,
        )
        with _immediate_transaction(self._connection):
            return self._complete_in_transaction(
                table="feishu_action_receipts",
                key_column="action_id",
                receipt_id=action_id,
                encoded=encoded,
                metadata=metadata,
                completed_at=completed_at,
            )

    def _action_completion_values(
        self,
        *,
        action_id: str,
        response: Mapping[str, object],
        case_id: str,
        diagnosis_id: str,
        actor_id: str,
        completed_at: str,
    ) -> tuple[str, str, dict[str, str], str]:
        return (
            _require_text("action_id", action_id),
            _encode_response(response),
            {
                "case_id": _require_text("case_id", case_id),
                "diagnosis_id": _require_text("diagnosis_id", diagnosis_id),
                "actor_id": _actor_hash(actor_id),
            },
            _require_text("completed_at", completed_at),
        )

    def _complete_in_transaction(
        self,
        *,
        table: str,
        key_column: str,
        receipt_id: str,
        encoded: str,
        metadata: Mapping[str, str],
        completed_at: str,
    ) -> ReceiptResult:
        metadata_columns = tuple(metadata)
        selected_columns = ", ".join(("status", "response_json", *metadata_columns))
        row = self._connection.execute(
            f"SELECT {selected_columns} FROM {table} WHERE {key_column} = ?",
            (receipt_id,),
        ).fetchone()
        if row is None:
            raise ReceiptNotClaimed(receipt_id)
        if row["status"] == "COMPLETED":
            expected = (encoded, *metadata.values())
            actual = (row["response_json"], *(row[column] for column in metadata_columns))
            if actual != expected:
                raise ReceiptConflict(receipt_id)
            return ReceiptResult(ReceiptOutcome.REPLAY, _decode_response(encoded))
        assignments = ", ".join(f"{column} = ?" for column in metadata_columns)
        self._connection.execute(
            f"UPDATE {table} SET status = 'COMPLETED', response_json = ?, "
            f"{assignments}, completed_at = ? "
            f"WHERE {key_column} = ? AND status = 'CLAIMED'",
            (encoded, *metadata.values(), completed_at, receipt_id),
        )
        return ReceiptResult(ReceiptOutcome.COMPLETED, _decode_response(encoded))

    def bind_chat_case(self, chat_id: str, case_id: str, *, updated_at: str) -> None:
        _require_text("chat_id", chat_id)
        _require_text("case_id", case_id)
        _require_text("updated_at", updated_at)
        with _immediate_transaction(self._connection):
            row = self._connection.execute(
                "SELECT case_id FROM feishu_chat_cases WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if row is None:
                self._connection.execute(
                    """
                    INSERT INTO feishu_chat_cases (chat_id, case_id, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (chat_id, case_id, updated_at),
                )
            elif row["case_id"] == case_id:
                self._connection.execute(
                    "UPDATE feishu_chat_cases SET updated_at = ? WHERE chat_id = ?",
                    (updated_at, chat_id),
                )
            else:
                raise ReceiptConflict(chat_id)

    def get_chat_case(self, chat_id: str) -> str | None:
        _require_text("chat_id", chat_id)
        row = self._connection.execute(
            "SELECT case_id FROM feishu_chat_cases WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return None if row is None else row["case_id"]

    def bind_case(self, binding_key: str, case_id: str, *, updated_at: str) -> None:
        self.bind_chat_case(binding_key, case_id, updated_at=updated_at)

    def get_case_id(self, binding_key: str) -> str | None:
        return self.get_chat_case(binding_key)

    def commit_confirmation(
        self,
        *,
        action_id: str,
        approval_id: str,
        response: Mapping[str, object],
        case_id: str,
        diagnosis_id: str,
        actor_id: str,
        result: str,
        action_kind: str = "CONFIRM_REVIEW",
        request_id: str,
        trace_id: str,
        occurred_at: str,
    ) -> ReceiptResult:
        action_id, encoded, metadata, occurred_at = self._action_completion_values(
            action_id=action_id,
            response=response,
            case_id=case_id,
            diagnosis_id=diagnosis_id,
            actor_id=actor_id,
            completed_at=occurred_at,
        )
        _require_text("approval_id", approval_id)
        _require_text("result", result)
        action_kind = _require_text("action_kind", action_kind)
        request_id = _require_text("request_id", request_id)
        trace_id = _require_text("trace_id", trace_id)
        try:
            with _immediate_transaction(self._connection):
                receipt = self._complete_in_transaction(
                    table="feishu_action_receipts",
                    key_column="action_id",
                    receipt_id=action_id,
                    encoded=encoded,
                    metadata=metadata,
                    completed_at=occurred_at,
                )
                existing = self._connection.execute(
                    """
                    SELECT approval_id, action_id, case_id, diagnosis_id, actor_id,
                           action_kind, result, request_id, trace_id, occurred_at
                    FROM feishu_approval_audits
                    WHERE action_id = ?
                       OR (case_id = ? AND diagnosis_id = ? AND action_kind = ?)
                    """,
                    (action_id, case_id, diagnosis_id, action_kind),
                ).fetchone()
                if existing is not None:
                    if existing["action_id"] == action_id and (
                        existing["case_id"],
                        existing["diagnosis_id"],
                        existing["action_kind"],
                        existing["result"],
                    ) != (case_id, diagnosis_id, action_kind, result):
                        raise ReceiptConflict(action_id)
                    return ReceiptResult(ReceiptOutcome.REPLAY, receipt.response)
                if receipt.outcome is ReceiptOutcome.REPLAY:
                    raise ReceiptConflict(action_id)
                self._connection.execute(
                    """
                    INSERT INTO feishu_approval_audits (
                        approval_id, action_id, case_id, diagnosis_id, actor_id,
                        action_kind, result, request_id, trace_id, occurred_at, synthetic
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        approval_id,
                        action_id,
                        case_id,
                        diagnosis_id,
                        metadata["actor_id"],
                        action_kind,
                        result,
                        request_id,
                        trace_id,
                        occurred_at,
                    ),
                )
                return receipt
        except sqlite3.IntegrityError:
            raise ReceiptConflict(action_id) from None

    def get_approval_audit(self, action_id: str) -> ApprovalAudit | None:
        _require_text("action_id", action_id)
        row = self._connection.execute(
            """
            SELECT approval_id, action_id, case_id, diagnosis_id, actor_id,
                   action_kind, result, request_id, trace_id, occurred_at, synthetic
            FROM feishu_approval_audits
            WHERE action_id = ?
            """,
            (action_id,),
        ).fetchone()
        if row is None:
            return None
        return ApprovalAudit(
            approval_id=row["approval_id"],
            action_id=row["action_id"],
            case_id=row["case_id"],
            diagnosis_id=row["diagnosis_id"],
            actor_hash=row["actor_id"],
            action_kind=row["action_kind"],
            result=row["result"],
            request_id=row["request_id"],
            trace_id=row["trace_id"],
            occurred_at=row["occurred_at"],
            synthetic=bool(row["synthetic"]),
        )

    def find_approval_audit(
        self,
        *,
        case_id: str,
        diagnosis_id: str,
        action_kind: str,
    ) -> ApprovalAudit | None:
        _require_text("case_id", case_id)
        _require_text("diagnosis_id", diagnosis_id)
        _require_text("action_kind", action_kind)
        row = self._connection.execute(
            """
            SELECT approval_id, action_id, case_id, diagnosis_id, actor_id,
                   action_kind, result, request_id, trace_id, occurred_at, synthetic
            FROM feishu_approval_audits
            WHERE case_id = ? AND diagnosis_id = ? AND action_kind = ?
            """,
            (case_id, diagnosis_id, action_kind),
        ).fetchone()
        if row is None:
            return None
        return ApprovalAudit(
            approval_id=row["approval_id"],
            action_id=row["action_id"],
            case_id=row["case_id"],
            diagnosis_id=row["diagnosis_id"],
            actor_hash=row["actor_id"],
            action_kind=row["action_kind"],
            result=row["result"],
            request_id=row["request_id"],
            trace_id=row["trace_id"],
            occurred_at=row["occurred_at"],
            synthetic=bool(row["synthetic"]),
        )


class FeishuCallbackStoreFactory:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        _initialize(self.db_path)

    @contextmanager
    def session(self) -> Iterator[FeishuCallbackStoreSession]:
        connection = _connect(self.db_path)
        try:
            yield FeishuCallbackStoreSession(connection)
        finally:
            connection.close()

    def get_case_id(self, binding_key: str) -> str | None:
        with self.session() as store:
            return store.get_case_id(binding_key)

    def bind_case(
        self,
        binding_key: str,
        case_id: str,
        *,
        updated_at: datetime,
    ) -> None:
        if not isinstance(updated_at, datetime) or updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        with self.session() as store:
            store.bind_case(
                binding_key,
                case_id,
                updated_at=updated_at.isoformat(),
            )

    def record_confirmation(
        self,
        record: FeishuApprovalRecord,
    ) -> FeishuConfirmationReceipt:
        if type(record) is not FeishuApprovalRecord:
            raise TypeError("record must be FeishuApprovalRecord")
        response = {"ok": True, "result": "confirmed"}
        with self.session() as store:
            result = store.commit_confirmation(
                action_id=record.action_id,
                approval_id=record.approval_id,
                response=response,
                case_id=record.case_id,
                diagnosis_id=record.diagnosis_id,
                actor_id=record.actor_hash,
                action_kind=record.action_kind,
                result=record.result,
                request_id=record.request_id,
                trace_id=record.trace_id,
                occurred_at=record.occurred_at.isoformat(),
            )
            audit = store.find_approval_audit(
                case_id=record.case_id,
                diagnosis_id=record.diagnosis_id,
                action_kind=record.action_kind,
            )
        if audit is None:
            raise ReceiptConflict(record.action_id)
        return FeishuConfirmationReceipt(
            approval_id=audit.approval_id,
            action_id=audit.action_id,
            replayed=result.outcome is ReceiptOutcome.REPLAY,
        )
