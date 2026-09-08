"""V2 dispute invariants; independent of HTTP, databases and collaboration channels."""

import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256


class DisputeError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class CaseStage(StrEnum):
    FORMAL_DISPUTE = "FORMAL_DISPUTE"
    REPRESENTMENT = "REPRESENTMENT"
    PRE_ARBITRATION = "PRE_ARBITRATION"
    ARBITRATION = "ARBITRATION"
    OTHER = "OTHER"


class WorkStatus(StrEnum):
    RECEIVED = "RECEIVED"
    TRIAGED = "TRIAGED"
    MERCHANT_ACTION_REQUIRED = "MERCHANT_ACTION_REQUIRED"
    EVIDENCE_COLLECTING = "EVIDENCE_COLLECTING"
    EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED"
    OP_REVIEW = "OP_REVIEW"
    MERCHANT_REVISION_REQUIRED = "MERCHANT_REVISION_REQUIRED"
    READY_TO_SUBMIT = "READY_TO_SUBMIT"
    SUBMISSION_PENDING_CONFIRMATION = "SUBMISSION_PENDING_CONFIRMATION"
    SUBMITTED = "SUBMITTED"
    WAITING_UPSTREAM = "WAITING_UPSTREAM"
    FINANCIAL_RECONCILIATION = "FINANCIAL_RECONCILIATION"
    CLOSED = "CLOSED"


class MerchantDecision(StrEnum):
    NONE = "NONE"
    ACCEPT = "ACCEPT"
    CONTEST = "CONTEST"
    NO_RESPONSE = "NO_RESPONSE"
    AUTHORIZED_WAIVER = "AUTHORIZED_WAIVER"


class BusinessOutcome(StrEnum):
    UNKNOWN = "UNKNOWN"
    WON = "WON"
    LOST = "LOST"
    PARTIAL = "PARTIAL"
    ACCEPTED_RESPONSIBILITY = "ACCEPTED_RESPONSIBILITY"
    WITHDRAWN = "WITHDRAWN"
    OTHER = "OTHER"


class Finality(StrEnum):
    NOT_FINAL = "NOT_FINAL"
    FINAL_CONFIRMED = "FINAL_CONFIRMED"


class FinancialStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RECONCILED = "RECONCILED"
    DISCREPANCY = "DISCREPANCY"


# Administrative privileges deliberately do not imply business approval rights.
ACTION_ROLES = {
    "INTAKE": {"OPERATOR"},
    "CONFIRM_RULE": {"RISK_OFFICER"},
    "PUBLISH_TASK": {"OPERATOR"},
    "MERCHANT_DECISION": {"MERCHANT", "OPERATOR"},
    "REGISTER_EVIDENCE": {"MERCHANT", "OPERATOR"},
    "WITHDRAW_EVIDENCE": {"MERCHANT", "OPERATOR"},
    "SUBMIT_EVIDENCE": {"MERCHANT", "OPERATOR"},
    "REVIEW": {"RISK_OFFICER"},
    "BUILD_PACKAGE": {"OPERATOR", "AGENT"},
    "APPROVE_PACKAGE": {"SUPERVISOR"},
    "SUBMIT": {"OPERATOR"},
    "RECORD_OUTCOME": {"OPERATOR"},
    "NEXT_STAGE": {"OPERATOR"},
    "RECORD_FINANCIAL": {"OPERATOR"},
    "RECONCILE": {"SUPERVISOR"},
    "NOTIFY_MERCHANT": {"OPERATOR"},
    "CLOSE": {"SUPERVISOR"},
    "COMMENT": {"OPERATOR", "MERCHANT", "RISK_OFFICER", "SUPERVISOR", "AGENT"},
    "MONITOR_SLA": {"OPERATOR", "AGENT", "RISK_OFFICER", "SUPERVISOR"},
    "KNOWLEDGE_CANDIDATE": {"OPERATOR", "AGENT"},
    "APPROVE_KNOWLEDGE": {"ADMIN"},
}
ROLES = frozenset().union(*ACTION_ROLES.values())
LOW_RISK_ACTIONS = {"COMMENT", "MONITOR_SLA", "BUILD_PACKAGE", "KNOWLEDGE_CANDIDATE"}


def require(condition: bool, code: str, message: str, status: int = 409) -> None:
    if not condition:
        raise DisputeError(code, message, status)


def text_field(data: dict, key: str, *, default: str | None = None, limit: int = 4000) -> str:
    value = data.get(key, default)
    require(
        isinstance(value, str) and bool(value.strip()), "INVALID_INPUT", f"{key} is required", 422
    )
    require(len(value) <= limit, "INVALID_INPUT", f"{key} is too long", 422)
    return value.strip()


def minor_units(value: object, *, allow_negative: bool = False) -> int:
    require(type(value) is int, "INVALID_AMOUNT", "Amounts must be integer minor units", 422)
    require(abs(value) <= 10**14, "INVALID_AMOUNT", "Amount exceeds supported range", 422)
    require(allow_negative or value >= 0, "INVALID_AMOUNT", "Amount must be nonnegative", 422)
    return value


def currency_code(value: object) -> str:
    require(
        isinstance(value, str) and bool(re.fullmatch(r"[A-Z]{3}", value)),
        "INVALID_CURRENCY",
        "currency must be a three-letter uppercase code",
        422,
    )
    return value


def timestamp(value: object) -> datetime:
    try:
        require(
            isinstance(value, str), "INVALID_DATE", "A timezone-aware ISO date is required", 422
        )
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, "INVALID_DATE", "Date must include timezone", 422)
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise DisputeError("INVALID_DATE", "A timezone-aware ISO date is required", 422) from exc


def fingerprint(value: object) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise DisputeError("INVALID_INPUT", "Command must contain JSON values", 422) from exc
    require(len(encoded) <= 250000, "INVALID_INPUT", "Command exceeds size limit", 422)
    return sha256(encoded.encode()).hexdigest()


def evidence_codes(case: dict) -> set[str]:
    return {item["code"] for item in case["evidence"] if item["active"]}


def missing_evidence(case: dict) -> list[str]:
    return sorted(set(case["rule_snapshot"].get("required_evidence", [])) - evidence_codes(case))


def close_blockers(case: dict) -> list[str]:
    blockers = []
    if case["finality"] != "FINAL_CONFIRMED" or case["business_outcome"] == "UNKNOWN":
        blockers.append("Terminal upstream outcome is not confirmed")
    if case["financial_status"] not in {"RECONCILED", "NOT_APPLICABLE"}:
        blockers.append("Financial reconciliation is incomplete")
    if any(task["required"] and task["status"] == "OPEN" for task in case["tasks"]):
        blockers.append("Required tasks remain open")
    if not case.get("merchant_notification_completed"):
        blockers.append("Merchant has not received the terminal result")
    actions = {event["action"] for event in case["audit"]}
    if not {"INTAKE", "RECORD_OUTCOME", "RECONCILE", "NOTIFY_MERCHANT"}.issubset(actions):
        blockers.append("Required audit artifacts are missing")
    return blockers


def redact_knowledge(value: str, case: dict) -> str:
    """Conservative demo redaction; human review is still required before reuse."""
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", value)
    value = re.sub(r"(?<!\w)\+?\d[\d ()-]{6,}\d(?!\w)", "[REDACTED_NUMBER]", value)
    for secret in (case["id"], case["merchant_id"], case.get("transaction_id", "")):
        if secret:
            value = value.replace(secret, "[REDACTED_ID]")
    return value
