from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr

from oceanpilot.domain.enums import EvidenceAvailability, EvidenceCode
from oceanpilot.domain.models import (
    AwareDateTime,
    CaseView,
    DiagnosisView,
    FrozenDomainModel,
    ReferenceText,
    SummaryText,
    SyntheticTrue,
    UUID4Str,
)

FeishuIdentifier = Annotated[StrictStr, Field(min_length=1, max_length=100)]
FeishuActorHash = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class FeishuFlowOutcome(StrEnum):
    NEED_INFO = "NEED_INFO"
    DIAGNOSIS = "DIAGNOSIS"


class FeishuIncident(FrozenDomainModel):
    binding_key: FeishuIdentifier
    event_id: FeishuIdentifier
    summary: SummaryText
    merchant_ref: ReferenceText
    occurred_at: AwareDateTime
    request_id: UUID4Str
    trace_id: UUID4Str


class FeishuEvidenceSubmission(FrozenDomainModel):
    binding_key: FeishuIdentifier
    event_id: FeishuIdentifier
    evidence_id: UUID4Str
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    typed_value: StrictStr | StrictBool | AwareDateTime | None = None
    observed_at: AwareDateTime | None = None
    request_id: UUID4Str
    trace_id: UUID4Str


class FeishuFlowResult(FrozenDomainModel):
    outcome: FeishuFlowOutcome
    case_view: CaseView | None = None
    diagnosis: DiagnosisView | None = None


class FeishuConfirmation(FrozenDomainModel):
    action_id: FeishuIdentifier
    approval_id: FeishuIdentifier
    case_id: UUID4Str
    diagnosis_id: UUID4Str
    actor_hash: FeishuActorHash
    occurred_at: AwareDateTime
    request_id: UUID4Str
    trace_id: UUID4Str


class FeishuApprovalRecord(FrozenDomainModel):
    action_id: FeishuIdentifier
    approval_id: FeishuIdentifier
    case_id: UUID4Str
    diagnosis_id: UUID4Str
    actor_hash: FeishuActorHash
    request_id: UUID4Str
    trace_id: UUID4Str
    action_kind: Literal["CONFIRM_REVIEW"] = "CONFIRM_REVIEW"
    result: Literal["CONFIRMED"] = "CONFIRMED"
    occurred_at: AwareDateTime
    synthetic: SyntheticTrue = True


class FeishuConfirmationReceipt(FrozenDomainModel):
    approval_id: FeishuIdentifier
    action_id: FeishuIdentifier
    replayed: StrictBool
