"""Persisted case-analysis turns and human-confirmed review decisions."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ReviewStatus(StrEnum):
    NEEDS_MORE_INFO = "NEEDS_MORE_INFO"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class AgentTurnRecord:
    turn_id: str
    case_id: str
    case_revision: int
    trigger: str
    response_json: str
    proposal_json: str | None
    created_at: datetime


@dataclass(frozen=True)
class ReviewDecision:
    decision_id: str
    case_id: str
    source_turn_id: str
    status: ReviewStatus
    summary: str
    confirmed_materials: tuple[str, ...]
    citation_ids: tuple[str, ...]
    case_revision: int
    confirmed_by: str
    confirmed_at: datetime
    audit_event_id: str


@dataclass(frozen=True)
class ReviewAuditEvent:
    audit_event_id: str
    case_id: str
    event_type: str
    decision_id: str
    case_revision: int
    occurred_at: datetime


@dataclass(frozen=True)
class ReviewConfirmationResult:
    result: str
    decision: ReviewDecision


class CaseReviewStore(Protocol):
    def current_revision(self, case_id: str) -> int: ...

    def save_turn(self, turn: AgentTurnRecord) -> None: ...

    def latest_turn_payload(self, case_id: str, case_revision: int) -> str | None: ...

    def latest_decision(self, case_id: str) -> ReviewDecision | None: ...

    def confirm_review(
        self,
        *,
        case_id: str,
        source_turn_id: str,
        expected_revision: int,
        confirmed_by: str,
    ) -> ReviewConfirmationResult: ...

    def audit_trail(self, case_id: str) -> tuple[ReviewAuditEvent, ...]: ...
