"""Allowlisted merchant projections, separate from the internal business aggregate."""

from copy import deepcopy

from oceanpilot.domain.dispute import close_blockers

PUBLIC_CASE_FIELDS = [
    "id",
    "revision",
    "merchant_id",
    "transaction_id",
    "scheme",
    "reason_code",
    "amount_minor",
    "currency",
    "stage",
    "stage_number",
    "work_status",
    "merchant_decision",
    "decision_response_status",
    "business_outcome",
    "current_stage_outcome",
    "last_known_outcome",
    "finality",
    "financial_status",
    "received_at",
    "created_at",
    "updated_at",
    "production_eligible",
    "assigned_op_user_id",
    "assigned_op",
    "evidence_version",
    "eligibility_status",
    "source_type",
    "library_reference",
    "merchant_notification_completed",
    "outcome_version",
    "financial_version",
]
SUMMARY_FIELDS = [
    "id",
    "revision",
    "merchant_id",
    "transaction_id",
    "scheme",
    "reason_code",
    "amount_minor",
    "currency",
    "stage",
    "stage_number",
    "work_status",
    "merchant_decision",
    "business_outcome",
    "finality",
    "financial_status",
    "received_at",
    "created_at",
    "updated_at",
    "assigned_op_user_id",
    "assigned_op",
    "source_type",
    "production_eligible",
    "decision_response_status",
    "eligibility_status",
]


def select(value: dict, names) -> dict:
    return {key: deepcopy(value[key]) for key in names if key in value}


def close_gate(case: dict) -> dict:
    blockers = close_blockers(case)
    notification = case.get("merchant_notification", {})
    reconciliation = case.get("reconciliation", {})
    outcome_version = case.get("outcome_version", 0)
    return {
        "enabled": not blockers,
        "blockers": blockers,
        "notification_current": bool(case.get("merchant_notification_completed"))
        and (
            not outcome_version
            or (
                notification.get("outcome_version") == outcome_version
                and notification.get("financial_version") == case.get("financial_version", 0)
            )
        ),
        "finality_confirmed": case.get("finality") == "FINAL_CONFIRMED"
        and not case.get("outcome_verification_required"),
        "financial_reconciled": case.get("financial_status") in {"RECONCILED", "NOT_APPLICABLE"}
        and (not outcome_version or reconciliation.get("outcome_version") == outcome_version),
        "required_tasks_resolved": not any(
            task.get("required") and task.get("status") in {"OPEN", "IN_PROGRESS"}
            for task in case.get("tasks", [])
        ),
    }


def merchant_case_view(case: dict, *, participants: list[dict] | None = None) -> dict:
    result = select(case, PUBLIC_CASE_FIELDS)
    result["view"] = "MERCHANT"
    result["participants"] = deepcopy(
        participants if participants is not None else case.get("participants", [])
    )
    result["deadlines"] = select(case.get("deadlines", {}), ("merchant", "status"))
    result["rule_snapshot"] = select(
        case.get("rule_snapshot", {}),
        (
            "allowed_actions",
            "required_evidence",
            "source_id",
            "source_locator",
            "rule_version",
            "conflict_status",
        ),
    )
    result["tasks"] = [
        select(
            task,
            (
                "id",
                "type",
                "title",
                "message",
                "status",
                "required",
                "owner",
                "assignee",
                "assignee_id",
                "deadline",
                "stage_number",
                "created_at",
                "completed_at",
                "resolution",
            ),
        )
        for task in case.get("tasks", [])
        if task.get("owner") == "MERCHANT" or task.get("assignee_role") == "MERCHANT"
    ]
    result["evidence"] = [
        select(
            item,
            (
                "id",
                "code",
                "title",
                "reference",
                "notes",
                "source_channel",
                "revision",
                "active",
                "created_at",
                "updated_at",
                "stage_number",
                "applicable_stage_numbers",
                "object_id",
                "hash",
                "content_hash",
                "filename",
                "mime_type",
                "content_assessment",
                "content_verified",
                "content_check",
                "content_status",
                "uploaded_by",
                "size",
            ),
        )
        for item in case.get("evidence", [])
        if item.get("visibility", "SHARED") == "SHARED"
    ]
    feedback = [
        item
        for item in case.get("reviews", [])
        if item.get("decision") in {"REVISION", "ACCEPT", "RECOMMEND_ACCEPT", "RETURN_MATERIALS"}
    ]
    result["public_feedback"] = [
        select(item, ("id", "decision", "reason", "created_at", "at", "valid", "evidence_version"))
        for item in feedback[-5:]
    ]
    result["financial_summary"] = select(
        case.get("financial_summary", {}),
        (
            "source_type",
            "production_eligible",
            "currency",
            "disputed_minor",
            "supported_minor",
            "liable_minor",
            "fee_minor",
            "refund_minor",
            "debit_minor",
            "credit_minor",
            "adjustment_minor",
            "net_minor",
            "net_direction",
            "outcome_version",
            "financial_version",
            "boundary",
        ),
    )
    gate = close_gate(case)
    result["close_gate"] = gate | {
        "blockers": [] if gate["enabled"] else ["OceanPayment 正在完成本案结果、资金或通知的处理。"]
    }
    return result


def case_view(case: dict, identity: dict, access_policy=None) -> dict:
    participants = (
        access_policy.case_participants(case) if access_policy else case.get("participants", [])
    )
    if identity["role"] == "MERCHANT":
        return merchant_case_view(case, participants=participants)
    return deepcopy(case) | {
        "view": "OPERATIONS",
        "participants": participants,
        "close_gate": close_gate(case),
    }


def case_summary(case: dict, identity: dict) -> dict:
    result = select(case, SUMMARY_FIELDS)
    result["view"] = "MERCHANT" if identity["role"] == "MERCHANT" else "OPERATIONS"
    result["deadlines"] = select(
        case.get("deadlines", {}),
        ("merchant", "status")
        if identity["role"] == "MERCHANT"
        else ("merchant", "internal", "external", "status"),
    )
    result["task_summary"] = {
        "open": sum(
            task.get("status") in {"OPEN", "IN_PROGRESS"} for task in case.get("tasks", [])
        ),
        "for_me": sum(
            task.get("status") in {"OPEN", "IN_PROGRESS"}
            and (
                task.get("assignee_id") == identity["actor_id"]
                or task.get("owner") == identity["role"]
            )
            for task in case.get("tasks", [])
        ),
    }
    return result


def merchant_plan_view(plan: dict) -> dict:
    result = select(
        plan,
        (
            "case_id",
            "revision",
            "summary",
            "rule_status",
            "checklist",
            "readiness",
            "missing_required",
            "missing_critical",
            "next_action",
            "current_action_blockers",
            "source_citations",
            "production_eligible",
            "allowed_actions",
            "blockers",
        ),
    )
    result["deadlines"] = select(plan.get("deadlines", {}), ("merchant", "status"))
    proposal = plan.get("proposal")
    if proposal and proposal.get("owner") == "MERCHANT":
        result["proposal"] = deepcopy(proposal)
    return result
