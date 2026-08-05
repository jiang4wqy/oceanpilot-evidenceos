from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from oceanpilot.domain.enums import EvidenceAvailability, EvidenceCode
from oceanpilot.domain.models import CaseView, DiagnosisView


class FeishuOrchestrationError(Exception):
    pass


class UnboundChat(FeishuOrchestrationError):
    pass


class CaseBindingMismatch(FeishuOrchestrationError):
    pass


class FeishuOutcomeKind(StrEnum):
    IGNORED = "IGNORED"
    NEED_INFO = "NEED_INFO"
    DIAGNOSED = "DIAGNOSED"
    ALREADY_DIAGNOSED = "ALREADY_DIAGNOSED"
    CONFIRMED = "CONFIRMED"
    DIAGNOSIS_NOT_CONFIRMABLE = "DIAGNOSIS_NOT_CONFIRMABLE"


@dataclass(frozen=True, slots=True)
class MessageEvent:
    chat_id: str
    text: str
    from_bot: bool = False


@dataclass(frozen=True, slots=True)
class EvidenceAnswer:
    chat_id: str
    case_id: str
    actor_id: str
    evidence_id: str
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    source_ref: str
    typed_value: str | bool | datetime | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    chat_id: str
    case_id: str
    diagnosis_id: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class OrchestrationOutcome:
    kind: FeishuOutcomeKind
    case_view: CaseView | None = None
    diagnosis_view: DiagnosisView | None = None
