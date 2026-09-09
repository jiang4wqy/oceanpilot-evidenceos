"""Durable normalized-event inbox and immutable synthetic transaction registry."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from oceanpilot.domain.dispute import fingerprint, require


class SQLiteDisputeIntakeStore:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._uri = self.db_path == ":memory:"
        self._keeper = None
        if self._uri:
            self.db_path = f"file:intake-{uuid4().hex}?mode=memory&cache=shared"
            self._keeper = self._connect()
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS v21_synthetic_transactions (
                    channel TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    PRIMARY KEY(channel,transaction_id)
                );
                CREATE TABLE IF NOT EXISTS v21_intake_events (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    merchant_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    UNIQUE(channel,source_event_id)
                );
                CREATE INDEX IF NOT EXISTS v21_intake_merchant ON v21_intake_events(merchant_id);
            """)

    def _connect(self):
        db = sqlite3.connect(self.db_path, uri=self._uri, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def register(self, record):
        data = {k: v for k, v in record.items() if k not in {"created_at", "created_by"}}
        digest = fingerprint(data)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT fingerprint,snapshot FROM v21_synthetic_transactions "
                "WHERE channel=? AND transaction_id=?",
                (record["channel"], record["transaction_id"]),
            ).fetchone()
            if prior:
                require(
                    prior["fingerprint"] == digest,
                    "REGISTRY_CONFLICT",
                    (
                        "Synthetic transaction facts are immutable; "
                        "use a distinct transaction identity"
                    ),
                )
                return json.loads(prior["snapshot"])
            db.execute(
                "INSERT INTO v21_synthetic_transactions VALUES (?,?,?,?)",
                (record["channel"], record["transaction_id"], digest, json.dumps(record)),
            )
        return record

    def transaction(self, channel, transaction_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT snapshot FROM v21_synthetic_transactions "
                "WHERE channel=? AND transaction_id=?",
                (channel, transaction_id),
            ).fetchone()
            return json.loads(row["snapshot"]) if row else None

    def list_transactions(self):
        with closing(self._connect()) as db:
            return [
                json.loads(r["snapshot"])
                for r in db.execute(
                    "SELECT snapshot FROM v21_synthetic_transactions ORDER BY rowid DESC"
                )
            ]

    def remember(self, record):
        digest = fingerprint(record["envelope"])
        envelope = record["envelope"]
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT snapshot,fingerprint FROM v21_intake_events "
                "WHERE channel=? AND source_event_id=?",
                (envelope["channel"], envelope["source_event_id"]),
            ).fetchone()
            if row:
                require(
                    row["fingerprint"] == digest,
                    "SOURCE_EVENT_CONFLICT",
                    "A source event identity cannot be reused with different data",
                )
                return json.loads(row["snapshot"]), True
            db.execute(
                "INSERT INTO v21_intake_events VALUES (?,?,?,?,?,?)",
                (
                    record["id"],
                    envelope["channel"],
                    envelope["source_event_id"],
                    envelope["merchant_id"],
                    digest,
                    json.dumps(record),
                ),
            )
        return record, False

    def get_event(self, event_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT snapshot FROM v21_intake_events WHERE id=?", (event_id,)
            ).fetchone()
            return json.loads(row["snapshot"]) if row else None

    def list_events(self):
        with closing(self._connect()) as db:
            return [
                json.loads(r["snapshot"])
                for r in db.execute("SELECT snapshot FROM v21_intake_events ORDER BY rowid DESC")
            ]

    def prepare(self, event_id, expected_attempts, prepared):
        """First concurrent preparation wins. No business database lock is held on dispatch."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            record = json.loads(
                db.execute(
                    "SELECT snapshot FROM v21_intake_events WHERE id=?", (event_id,)
                ).fetchone()["snapshot"]
            )
            if len(record["attempts"]) != expected_attempts or record["status"] == "PROCESSED":
                return record
            record["attempts"].append(prepared)
            record.update(
                status=prepared["status"],
                reason=prepared.get("reason"),
                updated_at=prepared["created_at"],
            )
            db.execute(
                "UPDATE v21_intake_events SET snapshot=? WHERE id=?", (json.dumps(record), event_id)
            )
            return record

    def finish(self, event_id, attempt_number, *, status, reason, at, result=None):
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            record = json.loads(
                db.execute(
                    "SELECT snapshot FROM v21_intake_events WHERE id=?", (event_id,)
                ).fetchone()["snapshot"]
            )
            if len(record["attempts"]) != attempt_number or record["status"] == "PROCESSED":
                return record
            record.update(status=status, reason=reason, updated_at=at)
            record["attempts"][-1].update(status=status, reason=reason, completed_at=at)
            if result:
                record["case_id"] = result["case"]["id"]
                record["command_receipt"] = result["receipt"]
            db.execute(
                "UPDATE v21_intake_events SET snapshot=? WHERE id=?", (json.dumps(record), event_id)
            )
            return record
