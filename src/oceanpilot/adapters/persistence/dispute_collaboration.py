"""Append-only shared collaboration journal and private synthetic evidence objects."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from oceanpilot.domain.dispute import require


class SQLiteDisputeCollaborationStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._uri = self.db_path == ":memory:" or self.db_path.startswith("file:")
        self._keeper = None
        if self.db_path == ":memory:":
            self.db_path = f"file:collaboration-{uuid4().hex}?mode=memory&cache=shared"
            self._keeper = self.connect()
        elif not self._uri:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS v21_collaboration_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL, scope TEXT NOT NULL, kind TEXT NOT NULL,
                    actor_id TEXT NOT NULL, snapshot TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS v21_collaboration_scope
                    ON v21_collaboration_events(case_id, scope, seq);
                CREATE TABLE IF NOT EXISTS v21_collaboration_commands (
                    command_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v21_evidence_objects (
                    object_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
                    snapshot TEXT NOT NULL, content BLOB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS v21_evidence_case ON v21_evidence_objects(case_id);
                CREATE TABLE IF NOT EXISTS v21_collaboration_reads (
                    case_id TEXT NOT NULL, scope TEXT NOT NULL, actor_id TEXT NOT NULL,
                    cursor INTEGER NOT NULL, PRIMARY KEY(case_id, scope, actor_id)
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.db_path, uri=self._uri, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def execute(self, command_id, fingerprint, mutate):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT fingerprint,result FROM v21_collaboration_commands WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if previous:
                require(
                    previous["fingerprint"] == fingerprint,
                    "IDEMPOTENCY_CONFLICT",
                    "Command identity or payload changed",
                )
                return json.loads(previous["result"]) | {"replayed": True}
            result = mutate(db)
            db.execute(
                "INSERT INTO v21_collaboration_commands VALUES (?,?,?)",
                (command_id, fingerprint, json.dumps(result, ensure_ascii=False)),
            )
            return result | {"replayed": False}

    @staticmethod
    def append(db, event):
        cursor = db.execute(
            "INSERT INTO v21_collaboration_events(case_id,scope,kind,actor_id,snapshot) "
            "VALUES (?,?,?,?,?)",
            (
                event["case_id"],
                event["scope"],
                event["kind"],
                event["actor_id"],
                json.dumps(event, ensure_ascii=False),
            ),
        ).lastrowid
        return event | {"cursor": cursor}

    def events(self, case_id, scope, after=0, limit=200):
        with closing(self.connect()) as db:
            return self.read_events(db, case_id, scope, after, limit)

    @staticmethod
    def read_events(db, case_id, scope, after=0, limit=200):
        rows = db.execute(
            "SELECT seq,snapshot FROM v21_collaboration_events "
            "WHERE case_id=? AND scope=? AND seq>? ORDER BY seq LIMIT ?",
            (case_id, scope, after, limit),
        )
        return [json.loads(r["snapshot"]) | {"cursor": r["seq"]} for r in rows]

    def cursor(self, case_id, scope):
        with closing(self.connect()) as db:
            return db.execute(
                "SELECT COALESCE(MAX(seq),0) FROM v21_collaboration_events "
                "WHERE case_id=? AND scope=?",
                (case_id, scope),
            ).fetchone()[0]

    def read_cursor(self, case_id, scope, actor_id):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT cursor FROM v21_collaboration_reads "
                "WHERE case_id=? AND scope=? AND actor_id=?",
                (case_id, scope, actor_id),
            ).fetchone()
            return row[0] if row else 0

    def read_receipts(self, case_id, scope):
        with closing(self.connect()) as db:
            return [
                {"actor_id": r["actor_id"], "cursor": r["cursor"]}
                for r in db.execute(
                    "SELECT actor_id,cursor FROM v21_collaboration_reads "
                    "WHERE case_id=? AND scope=?",
                    (case_id, scope),
                )
            ]

    def mark_read(self, case_id, scope, actor_id, cursor):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            maximum = db.execute(
                "SELECT COALESCE(MAX(seq),0) FROM v21_collaboration_events "
                "WHERE case_id=? AND scope=?",
                (case_id, scope),
            ).fetchone()[0]
            require(0 <= cursor <= maximum, "INVALID_CURSOR", "Read cursor exceeds thread", 422)
            # Reading a read-receipt does not recursively generate another receipt.
            visible = db.execute(
                "SELECT COALESCE(MAX(seq),0) FROM v21_collaboration_events "
                "WHERE case_id=? AND scope=? AND seq<=? AND kind!='READ'",
                (case_id, scope, cursor),
            ).fetchone()[0]
            prior = db.execute(
                "SELECT cursor FROM v21_collaboration_reads "
                "WHERE case_id=? AND scope=? AND actor_id=?",
                (case_id, scope, actor_id),
            ).fetchone()
            if visible > (prior[0] if prior else 0):
                db.execute(
                    "INSERT INTO v21_collaboration_reads VALUES (?,?,?,?) "
                    "ON CONFLICT(case_id,scope,actor_id) DO UPDATE SET cursor=excluded.cursor",
                    (case_id, scope, actor_id, visible),
                )
                self.append(
                    db,
                    {
                        "case_id": case_id,
                        "scope": scope,
                        "kind": "READ",
                        "actor_id": actor_id,
                        "read_cursor": visible,
                    },
                )
        return self.read_cursor(case_id, scope, actor_id)

    def get_object(self, object_id, *, include_content=False):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT snapshot,content FROM v21_evidence_objects WHERE object_id=?", (object_id,)
            ).fetchone()
            if row is None:
                return None
            result = json.loads(row["snapshot"])
            if include_content:
                result["content"] = bytes(row["content"])
            return result

    def objects(self, case_id):
        with closing(self.connect()) as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT snapshot FROM v21_evidence_objects WHERE case_id=?", (case_id,)
                )
            ]

    def handoffs(self, case_id, scope, db=None):
        if db is None:
            with closing(self.connect()) as conn:
                return self.handoffs(case_id, scope, conn)
        rows = db.execute(
            "SELECT seq,snapshot FROM v21_collaboration_events "
            "WHERE case_id=? AND scope=? AND kind='HANDOFF' ORDER BY seq",
            (case_id, scope),
        )
        latest = {}
        for row in rows:
            value = json.loads(row["snapshot"]) | {"cursor": row["seq"]}
            latest[value["id"]] = value
        return list(latest.values())
