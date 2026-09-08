"""V2 JSON aggregates in additive SQLite tables, using a single command transaction.

The existing V1 database and tables remain untouched. Every accepted command writes
the aggregate, its audit row and its idempotency receipt under BEGIN IMMEDIATE.
"""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from oceanpilot.domain.dispute import DisputeError, fingerprint, require


class SQLiteDisputeStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._keeper = None
        self._uri = self.db_path == ":memory:"
        if self._uri:
            self.db_path = f"file:dispute-{uuid4().hex}?mode=memory&cache=shared"
            self._keeper = self._connect()
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS v2_dispute_cases (
                    case_id TEXT PRIMARY KEY,
                    merchant_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    snapshot TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS v2_dispute_merchant
                    ON v2_dispute_cases(merchant_id);
                CREATE TABLE IF NOT EXISTS v2_dispute_commands (
                    command_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    identity TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    receipt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v2_dispute_audit (
                    case_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    command_id TEXT NOT NULL UNIQUE,
                    event TEXT NOT NULL,
                    PRIMARY KEY(case_id, revision)
                );
                CREATE TABLE IF NOT EXISTS v2_dispute_upstream_events (
                    event_key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    receipt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v2_dispute_upstream_cases (
                    upstream_case_key TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, uri=self._uri, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def list_cases(self, merchant_id: str | None = None) -> list[dict]:
        with closing(self._connect()) as connection:
            if merchant_id is None:
                rows = connection.execute(
                    "SELECT snapshot FROM v2_dispute_cases ORDER BY rowid DESC"
                )
            else:
                rows = connection.execute(
                    "SELECT snapshot FROM v2_dispute_cases WHERE merchant_id = ? "
                    "ORDER BY rowid DESC",
                    (merchant_id,),
                )
            return [json.loads(row["snapshot"]) for row in rows]

    def get_case(self, case_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT snapshot FROM v2_dispute_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            return json.loads(row["snapshot"]) if row else None

    def execute_atomic(
        self,
        *,
        command: dict,
        identity: dict,
        mutate: Callable[[dict | None], dict],
        event_key: str | None = None,
        event_fingerprint: str | None = None,
        upstream_case_key: str | None = None,
    ) -> dict:
        digest = fingerprint(command)
        identity_digest = fingerprint(identity)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM v2_dispute_commands WHERE command_id = ?",
                (command["command_id"],),
            ).fetchone()
            if existing:
                require(
                    existing["identity"] == identity_digest,
                    "COMMAND_CONFLICT",
                    "Command identifier belongs to another actor",
                    409,
                )
                require(
                    existing["fingerprint"] == digest,
                    "COMMAND_CONFLICT",
                    "Command identifier was already used with different content",
                    409,
                )
                result = json.loads(existing["receipt"])
                result["replayed"] = True
                connection.commit()
                return result
            if event_key:
                prior_event = connection.execute(
                    "SELECT * FROM v2_dispute_upstream_events WHERE event_key = ?",
                    (event_key,),
                ).fetchone()
                if prior_event:
                    require(
                        command["action"] == "INTAKE"
                        or prior_event["case_id"] == command["case_id"],
                        "EVENT_CASE_CONFLICT",
                        "Upstream event already belongs to another case",
                    )
                    require(
                        prior_event["fingerprint"] == event_fingerprint,
                        "EVENT_CONFLICT",
                        "Upstream event identifier was reused with different content",
                    )
                    result = json.loads(prior_event["receipt"])
                    result["replayed"] = True
                    self._save_receipt(connection, command, digest, identity_digest, result)
                    connection.commit()
                    return result
            resolved_case_id = command["case_id"]
            linked_case = None
            if upstream_case_key:
                linked_case = connection.execute(
                    "SELECT case_id FROM v2_dispute_upstream_cases WHERE upstream_case_key = ?",
                    (upstream_case_key,),
                ).fetchone()
                if linked_case:
                    resolved_case_id = linked_case["case_id"]
            row = connection.execute(
                "SELECT * FROM v2_dispute_cases WHERE case_id = ?",
                (resolved_case_id,),
            ).fetchone()
            if command["action"] == "INTAKE":
                require(
                    row is None or linked_case is not None,
                    "CASE_EXISTS",
                    "Case identifier already exists",
                )
                current = json.loads(row["snapshot"]) if row else None
                revision = row["revision"] if row else 0
            else:
                require(row is not None, "NOT_FOUND", "Case not found", 404)
                current, revision = json.loads(row["snapshot"]), row["revision"]
                if identity["role"] == "MERCHANT":
                    require(
                        current["merchant_id"] == identity["merchant_id"],
                        "NOT_FOUND",
                        "Case not found",
                        404,
                    )
                require(
                    command["expected_revision"] == revision,
                    "REVISION_CONFLICT",
                    f"Case revision changed; expected {command['expected_revision']}, "
                    f"current {revision}",
                )
            case = mutate(deepcopy(current))
            case["revision"] = revision + 1
            event = case["audit"][-1]
            require(
                event["revision"] == case["revision"],
                "AUDIT_INVARIANT",
                "Audit revision must equal case revision",
                500,
            )
            encoded = json.dumps(case, ensure_ascii=False)
            if row is None:
                connection.execute(
                    "INSERT INTO v2_dispute_cases VALUES (?, ?, ?, ?)",
                    (case["id"], case["merchant_id"], case["revision"], encoded),
                )
            else:
                updated = connection.execute(
                    "UPDATE v2_dispute_cases SET revision = ?, snapshot = ? "
                    "WHERE case_id = ? AND revision = ?",
                    (case["revision"], encoded, case["id"], revision),
                )
                require(updated.rowcount == 1, "REVISION_CONFLICT", "Concurrent case write")
            connection.execute(
                "INSERT INTO v2_dispute_audit VALUES (?, ?, ?, ?)",
                (case["id"], case["revision"], command["command_id"], json.dumps(event)),
            )
            result = {
                "case": case,
                "receipt": {
                    "command_id": command["command_id"],
                    "case_id": case["id"],
                    "revision": case["revision"],
                    "action": command["action"],
                    "status": "EXECUTED",
                    "executed_at": event["at"],
                    "audit_id": event["id"],
                },
                "replayed": False,
            }
            self._save_receipt(connection, command, digest, identity_digest, result)
            if upstream_case_key and linked_case is None:
                connection.execute(
                    "INSERT INTO v2_dispute_upstream_cases VALUES (?, ?)",
                    (upstream_case_key, case["id"]),
                )
            if event_key:
                connection.execute(
                    "INSERT INTO v2_dispute_upstream_events VALUES (?, ?, ?, ?)",
                    (event_key, event_fingerprint, case["id"], json.dumps(result)),
                )
            connection.commit()
            return result
        except sqlite3.OperationalError as exc:
            connection.rollback()
            raise DisputeError(
                "STORAGE_UNAVAILABLE", "Dispute storage is unavailable", 503
            ) from exc
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _save_receipt(connection, command, digest, identity_digest, result) -> None:
        connection.execute(
            "INSERT INTO v2_dispute_commands VALUES (?, ?, ?, ?, ?)",
            (
                command["command_id"],
                digest,
                identity_digest,
                result["case"]["id"],
                json.dumps(result, ensure_ascii=False),
            ),
        )
