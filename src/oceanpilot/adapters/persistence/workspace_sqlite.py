"""Workspace commands reuse case/review stores in one SQLite transaction."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from oceanpilot.adapters.persistence.chargeback_review_sqlite import SqliteCaseReviewStore
from oceanpilot.adapters.persistence.chargeback_sqlite import SqliteChargebackCaseStore
from oceanpilot.adapters.persistence.sqlite import connect_sqlite, immediate_transaction
from oceanpilot.application.errors import CaseNotFound, ConcurrentCaseWrite
from oceanpilot.application.workspace_ports import WorkspaceBundle, WorkspaceError, WorkspaceUnit
from oceanpilot.domain.chargeback import CardNetwork, DisputeReasonCode

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_case_info (
 case_id TEXT PRIMARY KEY REFERENCES chargeback_cases(case_id), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspace_materials (
 material_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES chargeback_cases(case_id),
 evidence_code TEXT NOT NULL, payload TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS workspace_concerns (
 concern_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES chargeback_cases(case_id),
 payload TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED'))
);
CREATE TABLE IF NOT EXISTS workspace_audit (
 audit_event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES chargeback_cases(case_id),
 event_type TEXT NOT NULL, detail TEXT NOT NULL, case_revision INTEGER NOT NULL,
 actor TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspace_commands (
 command_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, role TEXT NOT NULL,
 actor TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspace_summaries (
 summary_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES chargeback_cases(case_id),
 case_revision INTEGER NOT NULL, generated_at TEXT NOT NULL,
 payload TEXT NOT NULL, html TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def initialize_workspace_schema(path: Path) -> None:
    connection = connect_sqlite(path)
    try:
        connection.executescript(f"BEGIN IMMEDIATE;\n{_SCHEMA}\nCOMMIT;")
    finally:
        connection.close()


class _Unit:
    def __init__(self, path: Path, connection) -> None:
        self.connection = connection
        self.cases = SqliteChargebackCaseStore(path, connection=connection)
        self.reviews = SqliteCaseReviewStore(path, connection=connection)

    def bundle(self, case_id: str) -> WorkspaceBundle:
        state = self.cases.load(case_id)
        if state is None:
            raise CaseNotFound()
        row = self.connection.execute(
            "SELECT payload FROM workspace_case_info WHERE case_id=?", (case_id,)
        ).fetchone()
        info = json.loads(row["payload"]) if row else {}
        stamps = self.connection.execute(
            "SELECT created_at,updated_at FROM chargeback_cases WHERE case_id=?", (case_id,)
        ).fetchone()
        info.update(dict(stamps))
        materials = [
            json.loads(row["payload"])
            for row in self.connection.execute(
                "SELECT payload FROM workspace_materials WHERE case_id=? ORDER BY rowid", (case_id,)
            )
        ]
        # Older cases carry only metadata in the original registration table.
        known = {m["code"] for m in materials if m["active"]}
        active = {item.value for item in state.collected}
        for item in materials:
            if item["active"] and item["code"] not in active:
                item["active"] = False
                item["withdrawn_at"] = info["updated_at"]
        for row in self.connection.execute(
            "SELECT * FROM chargeback_evidence WHERE case_id=? ORDER BY added_at_revision",
            (case_id,),
        ):
            if row["evidence_code"] not in known:
                materials.append(
                    {
                        "code": row["evidence_code"],
                        "file_name": "合成材料元数据（旧登记）",
                        "source": "LEGACY_SYNTHETIC_METADATA",
                        "registered_at": row["added_at"],
                        "registered_by": "旧版演示操作",
                        "registered_revision": row["added_at_revision"],
                        "content_verification": "NOT_READ",
                        "active": True,
                        "withdrawn_at": None,
                    }
                )
        concerns = [
            json.loads(row["payload"])
            for row in self.connection.execute(
                "SELECT payload FROM workspace_concerns WHERE case_id=? ORDER BY rowid", (case_id,)
            )
        ]
        reviews = []
        for row in self.connection.execute(
            "SELECT d.*,t.proposal_json AS source_proposal_json "
            "FROM chargeback_review_decisions d LEFT JOIN chargeback_agent_turns t "
            "ON t.turn_id=d.source_turn_id WHERE d.case_id=? ORDER BY d.confirmed_at,d.rowid",
            (case_id,),
        ):
            record = dict(row)
            record["confirmed_materials"] = json.loads(record.pop("confirmed_materials_json"))
            record["citation_ids"] = json.loads(record.pop("citation_ids_json"))
            proposal_json = record.pop("source_proposal_json")
            proposal = json.loads(proposal_json) if proposal_json else {}
            record["rule_fingerprint"] = proposal.get("rule_fingerprint")
            record.pop("synthetic")
            reviews.append(record)
        timeline = [
            dict(row) | {"actor": "旧版演示操作"}
            for row in self.connection.execute(
                "SELECT event_type,detail,case_revision,occurred_at "
                "FROM chargeback_audit WHERE case_id=?",
                (case_id,),
            )
        ]
        timeline.extend(
            dict(row)
            for row in self.connection.execute(
                "SELECT event_type,detail,case_revision,occurred_at,actor "
                "FROM workspace_audit WHERE case_id=?",
                (case_id,),
            )
        )
        timeline.extend(
            {
                "event_type": "REVIEW_DECISION_CONFIRMED",
                "detail": item["summary"],
                "case_revision": item["case_revision"],
                "occurred_at": item["confirmed_at"],
                "actor": item["confirmed_by"],
            }
            for item in reviews
        )
        timeline.sort(key=lambda item: (item["occurred_at"], item["case_revision"]))
        turns = [
            json.loads(row["response_json"])
            for row in self.connection.execute(
                "SELECT response_json FROM chargeback_agent_turns WHERE case_id=? "
                "AND case_revision=? ORDER BY created_at DESC,rowid DESC",
                (case_id, state.revision),
            )
        ]
        summaries = [
            dict(row)
            for row in self.connection.execute(
                "SELECT summary_id,case_id,case_revision AS revision,generated_at "
                "FROM workspace_summaries WHERE case_id=? ORDER BY generated_at DESC,rowid DESC",
                (case_id,),
            )
        ]
        return WorkspaceBundle(
            state, info, materials, concerns, reviews, timeline, turns, summaries
        )

    def set_info(self, case_id: str, data: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO workspace_case_info VALUES (?,?) ON CONFLICT(case_id) "
            "DO UPDATE SET payload=excluded.payload",
            (case_id, _json(data)),
        )

    def register_material(self, case_id: str, data: dict[str, Any]) -> None:
        existing = self.connection.execute(
            "SELECT material_id FROM workspace_materials "
            "WHERE case_id=? AND evidence_code=? AND active=1",
            (case_id, data["code"]),
        ).fetchone()
        if existing:
            raise WorkspaceError("MATERIAL_ALREADY_REGISTERED", "该材料已登记，请先查看当前记录。")
        self.connection.execute(
            "INSERT INTO workspace_materials VALUES (?,?,?,?,1)",
            (str(uuid4()), case_id, data["code"], _json(data)),
        )

    def withdraw_material(self, case_id: str, code: str) -> None:
        for row in self.connection.execute(
            "SELECT material_id,payload FROM workspace_materials WHERE case_id=? "
            "AND evidence_code=? AND active=1",
            (case_id, code),
        ).fetchall():
            value = json.loads(row["payload"])
            value.update(active=False, withdrawn_at=_now())
            self.connection.execute(
                "UPDATE workspace_materials SET active=0,payload=? WHERE material_id=?",
                (_json(value), row["material_id"]),
            )

    def touch(self, case_id: str) -> None:
        self.connection.execute(
            "UPDATE chargeback_cases SET revision=revision+1,updated_at=?,collection_finalized=0 "
            "WHERE case_id=?",
            (_now(), case_id),
        )

    def correct_fact(self, case_id: str, field: str, value: str) -> None:
        # The field is selected by this fixed allowlist, never interpolated from input.
        if field == "reason_code":
            code = DisputeReasonCode(value).value
            self.connection.execute(
                "UPDATE chargeback_cases SET reason_code=?,reason_confirmed=1 WHERE case_id=?",
                (code, case_id),
            )
        elif field == "card_network":
            network = CardNetwork(value).value
            self.connection.execute(
                "UPDATE chargeback_cases SET card_network=? WHERE case_id=?", (network, case_id)
            )
        else:
            raise WorkspaceError(
                "UNSUPPORTED_CORRECTION", "此字段只能记录人工复核结论，不能自动改写。", 422
            )

    def add_concern(self, case_id: str, data: dict[str, Any]) -> str:
        concern_id = str(uuid4())
        data = data | {"concern_id": concern_id, "status": "OPEN"}
        self.connection.execute(
            "INSERT INTO workspace_concerns VALUES (?,?,?,'OPEN')",
            (concern_id, case_id, _json(data)),
        )
        return concern_id

    def resolve_concern(self, case_id: str, concern_id: str, data: dict[str, Any]) -> None:
        row = self.connection.execute(
            "SELECT payload,status FROM workspace_concerns WHERE concern_id=? AND case_id=?",
            (concern_id, case_id),
        ).fetchone()
        if row is None or row["status"] != "OPEN":
            raise WorkspaceError("CONCERN_NOT_OPEN", "该疑点不存在或已经复核，请刷新案件。")
        payload = json.loads(row["payload"]) | data | {"status": "RESOLVED"}
        self.connection.execute(
            "UPDATE workspace_concerns SET payload=?,status='RESOLVED' WHERE concern_id=?",
            (_json(payload), concern_id),
        )

    def record(self, case_id: str, event_type: str, detail: str, actor: str) -> str:
        state = self.cases.load(case_id)
        assert state is not None
        event_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO workspace_audit VALUES (?,?,?,?,?,?,?)",
            (event_id, case_id, event_type, detail, state.revision, actor, _now()),
        )
        return event_id


class SqliteWorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self, case_id: str) -> WorkspaceBundle:
        connection = connect_sqlite(self.path)
        try:
            connection.execute("BEGIN")
            return _Unit(self.path, connection).bundle(case_id)
        finally:
            connection.rollback()
            connection.close()

    def case_ids(self) -> tuple[str, ...]:
        return SqliteChargebackCaseStore(self.path).list_case_ids()

    def command(self, command_id: str, role: str, actor: str) -> dict[str, Any]:
        connection = connect_sqlite(self.path)
        try:
            row = connection.execute(
                "SELECT * FROM workspace_commands WHERE command_id=?", (command_id,)
            ).fetchone()
            if row is None:
                return {"status": "UNKNOWN"}
            if row["role"] != role or row["actor"] != actor:
                raise WorkspaceError("COMMAND_ACTOR_MISMATCH", "命令回执属于另一个演示身份。", 403)
            return json.loads(row["result_json"])
        finally:
            connection.close()

    def run(
        self,
        command: dict[str, Any],
        role: str,
        actor: str,
        apply: Callable[[WorkspaceUnit], dict[str, Any]],
    ) -> dict[str, Any]:
        fingerprint = hashlib.sha256(_json(command).encode()).hexdigest()
        connection = connect_sqlite(self.path)
        try:
            with immediate_transaction(connection):
                row = connection.execute(
                    "SELECT * FROM workspace_commands WHERE command_id=?", (command["command_id"],)
                ).fetchone()
                if row:
                    if (
                        row["request_hash"] != fingerprint
                        or row["role"] != role
                        or row["actor"] != actor
                    ):
                        raise WorkspaceError(
                            "COMMAND_REUSED", "命令编号已用于其他内容或身份，请核对原回执。"
                        )
                    return json.loads(row["result_json"]) | {"status": "REPLAYED"}
                result = apply(_Unit(self.path, connection))
                connection.execute(
                    "INSERT INTO workspace_commands VALUES (?,?,?,?,?,?)",
                    (
                        command["command_id"],
                        fingerprint,
                        role,
                        actor,
                        _json(result),
                        _now(),
                    ),
                )
                return result
        finally:
            connection.close()

    def save_summary(
        self,
        case_id: str,
        revision: int,
        summary: dict[str, Any],
        html: str,
        validate: Callable[[], None],
    ) -> dict[str, Any]:
        connection = connect_sqlite(self.path)
        try:
            with immediate_transaction(connection):
                row = connection.execute(
                    "SELECT revision FROM chargeback_cases WHERE case_id=?", (case_id,)
                ).fetchone()
                if row is None:
                    raise CaseNotFound()
                if row["revision"] != revision:
                    raise ConcurrentCaseWrite()
                validate()
                connection.execute(
                    "INSERT INTO workspace_summaries VALUES (?,?,?,?,?,?)",
                    (
                        summary["summary_id"],
                        case_id,
                        revision,
                        summary["generated_at"],
                        _json(summary),
                        html,
                    ),
                )
                validate()
            return summary
        finally:
            connection.close()

    def summary(self, summary_id: str) -> dict[str, Any]:
        connection = connect_sqlite(self.path)
        try:
            row = connection.execute(
                "SELECT payload,html FROM workspace_summaries WHERE summary_id=?", (summary_id,)
            ).fetchone()
            if row is None:
                raise CaseNotFound()
            return {"snapshot": json.loads(row["payload"]), "html": row["html"]}
        finally:
            connection.close()
