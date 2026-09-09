"""Permission-scoped SQL summaries: never materialize every aggregate for a queue."""

import json
from contextlib import closing
from datetime import UTC

from oceanpilot.application.dispute_views import SUMMARY_FIELDS
from oceanpilot.domain.dispute import require


def _value(field: str) -> str:
    # Only internal field constants reach SQL; all caller values are parameters.
    return f"json_extract(c.snapshot, '$.{field}')"


def queue_predicates(role: str) -> dict[str, str]:
    status, finality, financial = map(_value, ("work_status", "finality", "financial_status"))
    deadline = _value("deadlines.merchant" if role == "MERCHANT" else "deadlines.internal")
    return {
        "ALL": "1",
        "URGENT": (
            f"({status} != 'CLOSED' AND ({_value('decision_response_status')}='NO_RESPONSE' "
            f"OR {_value('eligibility_status')}='NEEDS_CONFIRMATION' "
            f"OR ({finality} != 'FINAL_CONFIRMED' AND julianday({deadline}) "
            "<= julianday(:now,'+1 day'))))"
        ),
        "MERCHANT": f"{status}='MERCHANT_ACTION_REQUIRED'",
        "EVIDENCE": f"{status} IN ('EVIDENCE_COLLECTING','MERCHANT_REVISION_REQUIRED')",
        "REVIEW": f"{status} IN ('EVIDENCE_SUBMITTED','OP_REVIEW')",
        "SUBMISSION": f"{status} IN ('READY_TO_SUBMIT','SUBMISSION_PENDING_CONFIRMATION',"
        "'SUBMITTED','WAITING_UPSTREAM','ACCEPT_PROCESSING')",
        "FINANCIAL": f"({status} != 'CLOSED' AND ({status}='FINANCIAL_RECONCILIATION' OR "
        f"{finality}='FINAL_CONFIRMED') AND {financial} IN ('PENDING','PROCESSING','DISCREPANCY'))",
        "PROCESSING": f"{status} NOT IN ('CLOSED','MERCHANT_ACTION_REQUIRED',"
        "'EVIDENCE_COLLECTING','MERCHANT_REVISION_REQUIRED')",
        "CLOSED": f"{status}='CLOSED'",
    }


class DisputeQueueReader:
    def __init__(self, store, access_policy):
        self.store = store
        self.access_policy = access_policy

    def read(self, identity, *, limit=25, offset=0, query="", queue="ALL", assigned_to="", now):
        predicates = queue_predicates(identity["role"])
        require(queue in predicates, "INVALID_QUEUE", "未知案件队列。", 422)
        params = {"now": now.astimezone(UTC).isoformat(), "limit": limit, "offset": offset}
        if self.access_policy is None:
            # Standalone test/domain composition still retains merchant isolation.
            scope = "1"
            if identity["role"] == "MERCHANT":
                scope = "c.merchant_id=:merchant"
                params["merchant"] = identity["merchant_id"]
        else:
            user = self.access_policy._user(identity)
            require(user is not None, "UNAUTHORIZED", "登录身份已失效。", 401)
            require(user["role"] != "DIRECTOR", "FORBIDDEN", "导演账号不能读取业务案件。", 403)
            params.update(user_id=user["id"], merchants=json.dumps(user["merchant_ids"]))
            scope = (
                "c.merchant_id IN (SELECT value FROM json_each(:merchants)) AND "
                "(json_type(c.snapshot,'$.participants') IS NULL OR EXISTS "
                "(SELECT 1 FROM json_each(c.snapshot,'$.participants') p "
                "WHERE json_extract(p.value,'$.user_id')=:user_id))"
            )
        if query.strip():
            # Literal substring search, not caller-controlled SQL LIKE wildcards.
            params["query"] = query.strip().casefold()
            scope += (
                " AND ("
                + " OR ".join(
                    f"instr(lower(coalesce({_value(key)},'')),:query)>0"
                    for key in ("id", "merchant_id", "transaction_id", "reason_code")
                )
                + ")"
            )
        if assigned_to:
            params["assigned_to"] = identity["actor_id"] if assigned_to == "me" else assigned_to
            scope += f" AND {_value('assigned_op_user_id')}=:assigned_to"

        pairs = [f"'{key}',{_value(key)}" for key in SUMMARY_FIELDS]
        deadline_fields = (
            ("merchant", "status")
            if identity["role"] == "MERCHANT"
            else ("merchant", "internal", "external", "status")
        )
        pairs.append(
            "'deadlines',json_object("
            + ",".join(f"'{key}',{_value('deadlines.' + key)}" for key in deadline_fields)
            + ")"
        )
        params.update(actor=identity["actor_id"], role=identity["role"])
        tasks = "json_each(c.snapshot,'$.tasks') t"
        active = "json_extract(t.value,'$.status') IN ('OPEN','IN_PROGRESS')"
        if identity["role"] == "MERCHANT":
            active += " AND json_extract(t.value,'$.owner')='MERCHANT'"
        mine = (
            active + " AND (json_extract(t.value,'$.assignee_id')=:actor OR "
            "(json_extract(t.value,'$.assignee_id') IS NULL AND "
            "json_extract(t.value,'$.owner')=:role))"
        )
        pairs.append(
            f"'task_summary',json_object('open',(SELECT count(*) FROM {tasks} WHERE {active}),"
            f"'for_me',(SELECT count(*) FROM {tasks} WHERE {mine}))"
        )
        with closing(self.store._connect()) as connection:
            # Counts and page share one read snapshot under concurrent business writes.
            connection.execute("BEGIN")
            counts = connection.execute(
                "SELECT "
                + ",".join(
                    f'coalesce(sum(CASE WHEN {predicate} THEN 1 ELSE 0 END),0) AS "{name}"'
                    for name, predicate in predicates.items()
                )
                + f" FROM v2_dispute_cases c WHERE {scope}",
                params,
            ).fetchone()
            rows = connection.execute(
                "SELECT json_object(" + ",".join(pairs) + ") AS summary "
                f"FROM v2_dispute_cases c WHERE {scope} AND {predicates[queue]} "
                "ORDER BY c.rowid DESC LIMIT :limit OFFSET :offset",
                params,
            ).fetchall()
            connection.rollback()
        cases = [json.loads(row["summary"]) for row in rows]
        for case in cases:
            case["view"] = "MERCHANT" if identity["role"] == "MERCHANT" else "OPERATIONS"
            case["production_eligible"] = bool(case.get("production_eligible"))
        return {
            "cases": cases,
            "total": counts[queue],
            "limit": limit,
            "offset": offset,
            "queue_counts": dict(counts),
        }
