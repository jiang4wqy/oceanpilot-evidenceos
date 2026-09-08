"""Additive SQLite storage; one immutable agent observation per case revision."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from oceanpilot.application.dispute_agent_ports import AUDIENCES, conversation_audience
from oceanpilot.domain.dispute import DisputeError, require


class SQLiteDisputeAgentStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._uri = self.db_path == ":memory:"
        self._keeper = None
        if self._uri:
            self.db_path = f"file:dispute-agent-{uuid4().hex}?mode=memory&cache=shared"
            self._keeper = self._connect()
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS v2_dispute_agent_runs (
                    run_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    case_revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    UNIQUE(case_id, case_revision)
                );
                CREATE TABLE IF NOT EXISTS v2_dispute_agent_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    case_revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    audience TEXT NOT NULL DEFAULT 'OPERATIONS'
                );
                CREATE INDEX IF NOT EXISTS v2_agent_conversation_case
                    ON v2_dispute_agent_conversations(case_id, created_at);
            """)
            # Existing conversations predate audience isolation. Migrate explicitly
            # before any reader can query the new column; old AUTO_EVENT is internal.
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(v2_dispute_agent_conversations)"
                    )
                }
                if "audience" not in columns:
                    connection.execute(
                        "ALTER TABLE v2_dispute_agent_conversations "
                        "ADD COLUMN audience TEXT NOT NULL DEFAULT 'OPERATIONS'"
                    )
                for row in connection.execute(
                    "SELECT conversation_id, case_id, snapshot, audience "
                    "FROM v2_dispute_agent_conversations"
                ).fetchall():
                    snapshot = json.loads(row["snapshot"])
                    normalized = self._scoped_conversation(snapshot)
                    if normalized != snapshot or row["audience"] != normalized["audience"]:
                        connection.execute(
                            "UPDATE v2_dispute_agent_conversations SET audience=?, snapshot=? "
                            "WHERE conversation_id=?",
                            (
                                normalized["audience"],
                                json.dumps(normalized, ensure_ascii=False),
                                row["conversation_id"],
                            ),
                        )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS v2_agent_conversation_audience "
                    "ON v2_dispute_agent_conversations(case_id, audience, created_at)"
                )

    def _connect(self):
        connection = sqlite3.connect(self.db_path, uri=self._uri, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def get_run(self, case_id: str, revision: int) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT snapshot FROM v2_dispute_agent_runs WHERE case_id=? AND case_revision=?",
                (case_id, revision),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def list_runs(self, case_id: str, limit: int = 100) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT snapshot FROM v2_dispute_agent_runs WHERE case_id=? "
                "ORDER BY case_revision DESC LIMIT ?",
                (case_id, limit),
            )
            return [json.loads(row[0]) for row in rows]

    def save_run(self, run: dict) -> dict:
        with closing(self._connect()) as connection:
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO v2_dispute_agent_runs VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(case_id, case_revision) DO NOTHING",
                        (
                            run["id"],
                            run["case_id"],
                            run["case_revision"],
                            run["created_at"],
                            json.dumps(run, ensure_ascii=False),
                        ),
                    )
                    row = connection.execute(
                        "SELECT snapshot FROM v2_dispute_agent_runs "
                        "WHERE case_id=? AND case_revision=?",
                        (run["case_id"], run["case_revision"]),
                    ).fetchone()
                    return json.loads(row[0])
            except sqlite3.Error as exc:
                raise DisputeError(
                    "AGENT_STORAGE_UNAVAILABLE", "Agent activity storage is unavailable", 503
                ) from exc

    def get_proposal(self, case_id: str, proposal_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT snapshot FROM v2_dispute_agent_runs WHERE case_id=? "
                "ORDER BY case_revision DESC",
                (case_id,),
            )
            for row in rows:
                for proposal in json.loads(row[0])["proposals"]:
                    if proposal["id"] == proposal_id:
                        return proposal
        return None

    def list_conversations(
        self, case_id: str, limit: int = 100, *, audience: str = "OPERATIONS"
    ) -> list[dict]:
        require(audience in AUDIENCES, "INVALID_AUDIENCE", "Unknown conversation audience", 422)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT snapshot FROM v2_dispute_agent_conversations "
                "WHERE case_id=? AND audience=? "
                "ORDER BY rowid DESC LIMIT ?",
                (case_id, audience, limit),
            )
            return list(reversed([json.loads(row[0]) for row in rows]))

    @staticmethod
    def _scoped_conversation(conversation: dict) -> dict:
        audience = conversation_audience(conversation)
        return {
            **conversation,
            "audience": audience,
            "scope": {"case_id": conversation["case_id"], "audience": audience},
            "source": conversation.get("source") or "LEGACY",
        }

    def save_conversation(self, conversation: dict) -> dict:
        conversation = self._scoped_conversation(conversation)
        with closing(self._connect()) as connection:
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO v2_dispute_agent_conversations "
                        "(conversation_id, case_id, case_revision, created_at, snapshot, audience) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            conversation["id"],
                            conversation["case_id"],
                            conversation["case_revision"],
                            conversation["created_at"],
                            json.dumps(conversation, ensure_ascii=False),
                            conversation["audience"],
                        ),
                    )
            except sqlite3.Error as exc:
                raise DisputeError(
                    "AGENT_STORAGE_UNAVAILABLE", "Agent conversation storage is unavailable", 503
                ) from exc
        return conversation
