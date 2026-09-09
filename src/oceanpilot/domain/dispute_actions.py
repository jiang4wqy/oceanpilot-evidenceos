"""Shared, data-independent business gates for command execution and UI affordances.

The handler still validates submitted fields and source evidence inside the same
atomic transaction. A visible affordance is never an authorization capability.
"""

from datetime import UTC, datetime

from oceanpilot.domain.dispute import (
    ACTION_ROLES,
    close_blockers,
    evidence_applicable,
    missing_evidence,
    timestamp,
)

CONTEST_ACTIONS = {
    "REGISTER_EVIDENCE",
    "REVIEW_EVIDENCE_CONTENT",
    "WITHDRAW_EVIDENCE",
    "SUBMIT_EVIDENCE",
    "REVIEW",
    "BUILD_PACKAGE",
    "APPROVE_PACKAGE",
    "FINAL_REVIEW",
    "SUBMIT",
}
RULE_ACTIONS = CONTEST_ACTIONS | {"PUBLISH_TASK", "MERCHANT_DECISION", "PROCESS_ACCEPT"}
STATES = {
    "PUBLISH_TASK": {
        "TRIAGED",
        "RECEIVED",
        "MERCHANT_ACTION_REQUIRED",
        "EVIDENCE_COLLECTING",
        "MERCHANT_REVISION_REQUIRED",
    },
    "MERCHANT_DECISION": {
        "MERCHANT_ACTION_REQUIRED",
        "EVIDENCE_COLLECTING",
        "MERCHANT_REVISION_REQUIRED",
        "ACCEPT_RECOMMENDATION",
        "RESPONSE_REVIEW_REQUIRED",
    },
    "REGISTER_EVIDENCE": {
        "EVIDENCE_COLLECTING",
        "MERCHANT_REVISION_REQUIRED",
        "OP_REVIEW",
        "EVIDENCE_SUBMITTED",
        "READY_TO_SUBMIT",
        "SUBMISSION_PENDING_CONFIRMATION",
        "DOCUMENT_REVISION_REQUIRED",
    },
    "WITHDRAW_EVIDENCE": {
        "EVIDENCE_COLLECTING",
        "MERCHANT_REVISION_REQUIRED",
        "OP_REVIEW",
        "EVIDENCE_SUBMITTED",
        "READY_TO_SUBMIT",
        "SUBMISSION_PENDING_CONFIRMATION",
        "DOCUMENT_REVISION_REQUIRED",
    },
    "REVIEW_EVIDENCE_CONTENT": {
        "EVIDENCE_COLLECTING",
        "MERCHANT_REVISION_REQUIRED",
        "OP_REVIEW",
        "READY_TO_SUBMIT",
        "SUBMISSION_PENDING_CONFIRMATION",
        "DOCUMENT_REVISION_REQUIRED",
    },
    "SUBMIT_EVIDENCE": {"EVIDENCE_COLLECTING", "MERCHANT_REVISION_REQUIRED"},
    "REVIEW": {"OP_REVIEW"},
    "BUILD_PACKAGE": {"READY_TO_SUBMIT", "DOCUMENT_REVISION_REQUIRED"},
    "APPROVE_PACKAGE": {"SUBMISSION_PENDING_CONFIRMATION"},
    "FINAL_REVIEW": {"SUBMISSION_PENDING_CONFIRMATION", "ON_HOLD"},
    "SUBMIT": {"READY_TO_SUBMIT"},
    "VERIFY_OUTCOME": {"OUTCOME_VERIFICATION"},
    "PROCESS_ACCEPT": {"ACCEPT_PROCESSING"},
    "QUERY_SUBMISSION": {"SUBMISSION_UNCERTAIN"},
    "REOPEN_CASE": {"CLOSED", "FINANCIAL_RECONCILIATION"},
}


def action_gate(case, action, identity, now=None):
    role = identity.get("role")
    owners = ACTION_ROLES.get(action, set())
    result = {
        "enabled": True,
        "blocked_reason": None,
        "code": None,
        "owner": role if role in owners else sorted(owners)[0] if owners else None,
    }

    def block(code, reason):
        return result | {"enabled": False, "blocked_reason": reason, "code": code}

    if role not in owners:
        return block("FORBIDDEN", "This action requires a different business role")
    if not case or action == "INTAKE":
        return result
    status = case.get("work_status")
    if action == "CONFIRM_RULE" and status not in {
        "RECEIVED",
        "TRIAGED",
        "MERCHANT_ACTION_REQUIRED",
        "EVIDENCE_COLLECTING",
        "MERCHANT_REVISION_REQUIRED",
        "OP_REVIEW",
        "READY_TO_SUBMIT",
        "SUBMISSION_PENDING_CONFIRMATION",
        "RESPONSE_REVIEW_REQUIRED",
        "ACCEPT_RECOMMENDATION",
        "DOCUMENT_REVISION_REQUIRED",
        "ON_HOLD",
    }:
        return block(
            "INVALID_STATE", "Rules cannot be replaced after submission or a terminal outcome"
        )
    if status == "CLOSED" and action not in {
        "REOPEN_CASE",
        "COMMENT",
        "KNOWLEDGE_CANDIDATE",
        "APPROVE_KNOWLEDGE",
    }:
        return block("CASE_CLOSED", "Closed business records require authorized reopening")
    rule = case.get("rule_snapshot", {})
    if action in CONTEST_ACTIONS and (
        case.get("merchant_decision") != "CONTEST"
        or "CONTEST" not in rule.get("allowed_actions", [])
        or case.get("eligibility_status") in {"REQUIRES_RECONFIRMATION", "RIGHTS_LOST"}
    ):
        return block(
            "CONTEST_NOT_ELIGIBLE",
            "Current Contest authority must be confirmed before evidence, review or submission",
        )
    if action in RULE_ACTIONS:
        if rule.get("conflict_status") != "VERIFIED":
            return block(
                "RULE_CONFIRMATION_REQUIRED",
                "Unknown or conflicting rule requires Risk confirmation",
            )
        if case.get("deadlines", {}).get("status") != "CONFIRMED":
            return block(
                "DEADLINE_CONFIRMATION_REQUIRED",
                "An explicit source and confirmed deadline are required",
            )
        if case.get("pending_next_stage"):
            return block("NEXT_STAGE_REQUIRED", "Create the confirmed next stage before continuing")
    if action in STATES and status not in STATES[action]:
        return block("INVALID_STATE", "This action is unavailable in the current business state")
    if action == "FINAL_REVIEW" and status == "ON_HOLD":
        result["choices"] = {
            "decision": ["RETURN_EVIDENCE", "RETURN_DOCUMENT", "RECOMMEND_ACCEPT", "HOLD"]
        }
    if action == "REVIEW_EVIDENCE_CONTENT":
        candidates = [
            item
            for item in case.get("evidence", [])
            if evidence_applicable(case, item)
            and item.get("object_id")
            and item.get("content_check", {})
            .get("automatic_check", item.get("content_check", {}))
            .get("status")
            == "NEEDS_MANUAL"
            and item.get("uploaded_by", item.get("registered_by")) != identity.get("actor_id")
        ]
        if not candidates:
            return block(
                "CONTENT_REVIEW_NOT_REQUIRED", "No file requires independent manual content review"
            )
        result["choices"] = {"evidence_id": [item["id"] for item in candidates]}
    if action == "RECONCILE" and (
        case.get("finality") != "FINAL_CONFIRMED" or case.get("outcome_verification_required")
    ):
        return block(
            "FINALITY_REQUIRED",
            "Financial reconciliation requires a verified terminal upstream outcome",
        )
    if action == "RESOLVE_TASK" and not any(
        t.get("status") == "OPEN" for t in case.get("tasks", [])
    ):
        return block("TASK_NOT_FOUND", "No open business task requires resolution")
    if action == "MERCHANT_DECISION":
        choices = list(rule.get("allowed_actions", []))
        if case.get("eligibility_status") in {"REQUIRES_RECONFIRMATION", "RIGHTS_LOST"}:
            choices = [choice for choice in choices if choice != "CONTEST"]
        current = timestamp(now) if isinstance(now, str) else now or datetime.now(UTC)
        merchant_deadline = case.get("deadlines", {}).get("merchant")
        if (
            role == "OPERATOR"
            and case.get("merchant_decision") == "NONE"
            and merchant_deadline
            and current > timestamp(merchant_deadline)
        ):
            choices += ["NO_RESPONSE"]
        if role == "OPERATOR" and "ACCEPT" in choices:
            choices += ["AUTHORIZED_WAIVER"]
        result["choices"] = choices
        if not choices:
            return block("RESPONSE_REVIEW_REQUIRED", "Risk must verify remaining response rights")
    if action in {"SUBMIT_EVIDENCE", "BUILD_PACKAGE", "APPROVE_PACKAGE", "SUBMIT"} and any(
        evidence_applicable(case, e)
        and e.get("object_id")
        and e.get("content_check", {}).get("status") != "SUPPORTED"
        for e in case.get("evidence", [])
    ):
        return block(
            "CONTENT_CHECK_REQUIRED",
            "Active file content is insufficient or requires human verification",
        )
    if action in {
        "SUBMIT_EVIDENCE",
        "BUILD_PACKAGE",
        "APPROVE_PACKAGE",
        "SUBMIT",
    } and missing_evidence(case):
        return block(
            "MISSING_EVIDENCE", "Required evidence is missing or its file content needs review"
        )
    if action in {"BUILD_PACKAGE", "APPROVE_PACKAGE", "SUBMIT"}:
        review = next(
            (
                r
                for r in reversed(case.get("reviews", []))
                if r.get("type") == "EVIDENCE"
                and r.get("decision") == "PASS"
                and r.get("valid")
                and r.get("evidence_version") == case.get("evidence_version")
            ),
            None,
        )
        if not review:
            return block("REVIEW_REQUIRED", "Current evidence requires Risk review")
        if action == "APPROVE_PACKAGE" and review.get("reviewer") == identity.get("actor_id"):
            return block(
                "REVIEWER_SEPARATION_REQUIRED",
                "Evidence review and final approval require two different people",
            )
    if action == "SUBMIT":
        package = next(
            (
                p
                for p in reversed(case.get("packages", []))
                if p.get("stage_number") == case.get("stage_number")
            ),
            None,
        )
        if not package or package.get("status") != "FROZEN" or not package.get("pii_checked"):
            return block("FINAL_REVIEW_REQUIRED", "Supervisor must approve and freeze the package")
    if action in CONTEST_ACTIONS | {"PROCESS_ACCEPT"}:
        external = case.get("deadlines", {}).get("external")
        current = timestamp(now) if isinstance(now, str) else now or datetime.now(UTC)
        if external and current > timestamp(external):
            return block(
                "EXTERNAL_DEADLINE_EXPIRED",
                "Confirmed external deadline has passed; verify remaining rights",
            )
    if action == "NEXT_STAGE" and not case.get("pending_next_stage"):
        return block("NEXT_STAGE_NOT_CONFIRMED", "A confirmed next-stage event is required")
    if action == "RESOLVE_RESPONSE" and status not in {
        "RESPONSE_REVIEW_REQUIRED",
        "WAITING_UPSTREAM",
        "EVIDENCE_COLLECTING",
        "ON_HOLD",
        "UPSTREAM_ACTION_REQUIRED",
        "OP_REVIEW",
        "READY_TO_SUBMIT",
        "SUBMISSION_PENDING_CONFIRMATION",
        "MERCHANT_REVISION_REQUIRED",
    }:
        return block("INVALID_STATE", "No response or rights review is pending")
    if action == "REUSE_EVIDENCE" and (
        case.get("stage_number", 1) < 2
        or status
        not in {
            "RECEIVED",
            "TRIAGED",
            "MERCHANT_ACTION_REQUIRED",
            "EVIDENCE_COLLECTING",
            "MERCHANT_REVISION_REQUIRED",
        }
    ):
        return block(
            "INVALID_STATE", "Evidence reuse must be reviewed before this stage is submitted"
        )
    if (
        action == "RECORD_OUTCOME"
        and case.get("finality") == "FINAL_CONFIRMED"
        and not case.get("reopened_for_correction")
    ):
        # A source correction is accepted by the handler only with explicit coverage;
        # this affordance points the operator toward authorized reopening first.
        return block(
            "INVALID_STATE", "Terminal outcomes require authorized reopening before correction"
        )
    if action == "CLOSE":
        blockers = close_blockers(case)
        if blockers:
            return block("CLOSE_BLOCKED", "; ".join(blockers))
    return result
