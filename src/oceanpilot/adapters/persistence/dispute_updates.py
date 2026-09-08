"""Read-only SQLite change positions; no in-memory bus or write-side bookkeeping.

Case audits, Agent runs and conversations are append-only durable records. Their
row positions are compared only inside the authenticated case and audience scope.
Every response is computed in one short read transaction, released before waiting.
"""

import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from time import monotonic

from oceanpilot.domain.dispute import DisputeError, require


class SQLiteDisputeUpdateReader:
    def __init__(self, db_path: str | Path) -> None:
        location = str(db_path)
        self.database = (
            location
            if location.startswith("file:")
            else Path(location).expanduser().resolve().as_uri() + "?mode=ro"
        )

    def read(self, identity: dict, case_id: str | None, position: dict | None) -> dict:
        try:
            with closing(sqlite3.connect(self.database, uri=True, timeout=0.2)) as connection:
                connection.row_factory = sqlite3.Row
                # Bound DB work separately from the HTTP wait, including lock contention.
                deadline = monotonic() + 1.5
                connection.set_progress_handler(lambda: int(monotonic() > deadline), 1000)
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
                clauses, parameters = [], []
                if identity["role"] == "MERCHANT":
                    clauses.append("c.merchant_id=?")
                    parameters.append(identity["merchant_id"])
                if case_id is not None:
                    clauses.append("c.case_id=?")
                    parameters.append(case_id)
                scope = " AND ".join(clauses) or "1=1"
                cases = connection.execute(
                    "SELECT c.case_id,c.revision FROM v2_dispute_cases c WHERE " + scope,
                    parameters,
                ).fetchall()
                require(case_id is None or bool(cases), "NOT_FOUND", "Case not found", 404)
                revisions = {row["case_id"]: row["revision"] for row in cases}

                # A DB awaiting the audience migration uses that migration's exact legacy rule.
                columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(v2_dispute_agent_conversations)"
                    )
                }
                audience_expression = (
                    "e.audience"
                    if "audience" in columns
                    else (
                        "CASE WHEN json_extract(e.snapshot,'$.trigger') LIKE 'AUTO_EVENT:%' "
                        "THEN 'OPERATIONS' WHEN json_extract(e.snapshot,'$.actor_role')='MERCHANT' "
                        "THEN 'MERCHANT' ELSE 'OPERATIONS' END"
                    )
                )
                audience = "MERCHANT" if identity["role"] == "MERCHANT" else "OPERATIONS"
                per_case = {}
                for kind, table in (
                    ("case", "v2_dispute_audit"),
                    ("agent", "v2_dispute_agent_runs"),
                    ("conversation", "v2_dispute_agent_conversations"),
                ):
                    predicate = scope
                    values = list(parameters)
                    if kind == "conversation":
                        predicate += f" AND {audience_expression}=?"
                        values.append(audience)
                    # Table names are fixed constants above, never supplied by an HTTP caller.
                    rows = connection.execute(
                        f"SELECT e.case_id,MAX(e.rowid) AS position FROM {table} e "
                        f"JOIN v2_dispute_cases c ON c.case_id=e.case_id WHERE {predicate} "
                        "GROUP BY e.case_id",
                        values,
                    )
                    per_case[kind] = {row["case_id"]: row["position"] for row in rows}
                first = connection.execute(
                    "SELECT e.command_id FROM v2_dispute_audit e "
                    "JOIN v2_dispute_cases c ON c.case_id=e.case_id "
                    f"WHERE {scope} ORDER BY e.rowid LIMIT 1",
                    parameters,
                ).fetchone()
                epoch = sha256(
                    ("dispute-updates-v1:" + (first[0] if first else "EMPTY")).encode()
                ).hexdigest()
                positions = {
                    kind: max(values.values(), default=0) for kind, values in per_case.items()
                }
                reset = (
                    position is None
                    or position["epoch"] != epoch
                    or any(position["positions"][kind] > value for kind, value in positions.items())
                )
                changes = []
                for identifier, revision in sorted(revisions.items()):
                    flags = {
                        kind: (
                            (kind == "case" or identifier in per_case[kind])
                            if reset
                            else per_case[kind].get(identifier, 0) > position["positions"][kind]
                        )
                        for kind in per_case
                    }
                    if any(flags.values()):
                        changes.append(
                            {
                                "case_id": identifier,
                                "revision": revision,
                                "case_changed": flags["case"],
                                "agent_changed": flags["agent"],
                                "conversation_changed": flags["conversation"],
                            }
                        )
                connection.rollback()
                return {"epoch": epoch, "positions": positions, "reset": reset, "changes": changes}
        except sqlite3.Error as exc:
            raise DisputeError(
                "UPDATES_UNAVAILABLE", "Dispute updates are temporarily unavailable", 503
            ) from exc
