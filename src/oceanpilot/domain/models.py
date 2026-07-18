from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    StrictStr,
)

from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    Priority,
    ResponsibleTeam,
    ReviewReason,
    SourceReliability,
    SourceType,
    StopReason,
    TargetRole,
    WriteOutcome,
)


def normalize_uuid4(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("must be a UUID") from exc
    if parsed.version != 4:
        raise ValueError("must be UUIDv4")
    return str(parsed)


def require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone is required")
    return value


def require_true(value: bool) -> bool:
    if value is not True:
        raise ValueError("synthetic must be true")
    return value


UUID4Str = Annotated[str, Field(strict=True), AfterValidator(normalize_uuid4)]
AwareDateTime = Annotated[
    datetime,
    Field(strict=True),
    AfterValidator(require_timezone),
]
SyntheticTrue = Annotated[StrictBool, AfterValidator(require_true)]
Revision = Annotated[StrictInt, Field(ge=0)]
ConfidenceScore = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("1"), allow_inf_nan=False),
]
NonEmptyText = Annotated[StrictStr, Field(min_length=1)]
SchemaVersion = Annotated[StrictStr, Field(min_length=1, max_length=32)]
ReferenceText = Annotated[StrictStr, Field(min_length=1, max_length=128)]
SummaryText = Annotated[StrictStr, Field(min_length=1, max_length=500)]
ContentHash = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )


class FrozenDomainModel(DomainModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        hide_input_in_errors=True,
        frozen=True,
    )


class EvidenceCreate(FrozenDomainModel):
    evidence_id: UUID4Str
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    typed_value: StrictStr | StrictBool | AwareDateTime | None = None
    observed_at: AwareDateTime | None = None
    source_ref: ReferenceText


class EvidenceOrigin(FrozenDomainModel):
    source_type: SourceType
    source_reliability: SourceReliability
    synthetic: SyntheticTrue = True


class ConfidenceResult(FrozenDomainModel):
    raw_score: ConfidenceScore
    display_score: ConfidenceScore
    review_reasons: frozenset[ReviewReason]


class ReadinessAssessment(DomainModel):
    ready: StrictBool
    missing_fields: tuple[StrictStr, ...]
    known_unknown_fields: tuple[StrictStr, ...]
    next_question: StrictStr | None = None
    question_reason: StrictStr | None = None
    target_role: TargetRole | None = None
    completion_ratio: ConfidenceScore
    stop_reason: StopReason


class MerchantSuccessCase(DomainModel):
    case_id: UUID4Str
    case_type: CaseType
    status: CaseStatus
    schema_version: SchemaVersion
    case_revision: Revision
    evidence_revision: Revision
    synthetic: SyntheticTrue
    summary: SummaryText
    merchant_ref: ReferenceText
    created_at: AwareDateTime
    updated_at: AwareDateTime
    current_diagnosis_id: UUID4Str | None = None
    readiness: ReadinessAssessment


class EvidenceItem(FrozenDomainModel):
    case_id: UUID4Str
    evidence_id: UUID4Str
    schema_version: SchemaVersion
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    value_type: EvidenceValueType
    typed_value: StrictStr | StrictBool | AwareDateTime | None = None
    source_type: SourceType
    source_ref: ReferenceText
    source_reliability: SourceReliability
    observed_at: AwareDateTime | None = None
    collected_at: AwareDateTime
    synthetic: SyntheticTrue
    content_hash: ContentHash


class ActiveEvidenceSlot(FrozenDomainModel):
    evidence_code: EvidenceCode
    selected_evidence: EvidenceItem | None = None
    known_unknown: StrictBool
    conflicting: StrictBool


class ActiveEvidenceView(FrozenDomainModel):
    slots: dict[EvidenceCode, ActiveEvidenceSlot]
    review_reasons: frozenset[ReviewReason]


class HypothesisDraft(FrozenDomainModel):
    cause_code: NonEmptyText
    explanation: NonEmptyText
    evidence_refs: tuple[UUID4Str, ...]
    confidence_score: ConfidenceScore
    confidence_method: Literal["HEURISTIC_V1"]
    next_verification_action: NonEmptyText
    rule_id: NonEmptyText


class RoutingDecision(FrozenDomainModel):
    responsible_team: ResponsibleTeam
    priority: Priority
    reason: NonEmptyText
    evidence_refs: tuple[UUID4Str, ...]
    requires_human: StrictBool
    review_reasons: frozenset[ReviewReason]


class TicketDraft(FrozenDomainModel):
    title: NonEmptyText
    summary: NonEmptyText
    evidence_summary: tuple[StrictStr, ...]
    missing_material: tuple[StrictStr, ...]
    hypotheses: tuple[HypothesisDraft, ...]
    next_action: NonEmptyText
    responsible_team: ResponsibleTeam
    synthetic: SyntheticTrue


class DiagnosisDraft(FrozenDomainModel):
    hypotheses: tuple[HypothesisDraft, ...]
    routing_decision: RoutingDecision | None = None
    ticket_draft: TicketDraft | None = None
    requires_human: StrictBool
    review_reasons: frozenset[ReviewReason]


class Hypothesis(FrozenDomainModel):
    hypothesis_id: UUID4Str
    cause_code: NonEmptyText
    explanation: NonEmptyText
    evidence_refs: tuple[UUID4Str, ...]
    confidence_score: ConfidenceScore
    confidence_method: Literal["HEURISTIC_V1"]
    next_verification_action: NonEmptyText
    rule_id: NonEmptyText


class DiagnosisSnapshot(FrozenDomainModel):
    diagnosis_id: UUID4Str
    case_id: UUID4Str
    evidence_revision: Revision
    policy_version: NonEmptyText
    engine_version: NonEmptyText
    status: DiagnosisStatus
    hypotheses: tuple[Hypothesis, ...]
    routing_decision: RoutingDecision | None = None
    ticket_draft: TicketDraft | None = None
    requires_human: StrictBool
    review_reasons: frozenset[ReviewReason]
    synthetic: SyntheticTrue
    created_at: AwareDateTime


class AuditEvent(FrozenDomainModel):
    event_id: UUID4Str
    event_type: AuditEventType
    event_version: SchemaVersion
    case_id: UUID4Str
    request_id: UUID4Str
    trace_id: UUID4Str
    actor_type: AuditActorType
    action: NonEmptyText
    from_status: CaseStatus | None = None
    to_status: CaseStatus | None = None
    case_revision: Revision
    evidence_revision: Revision
    occurred_at: AwareDateTime
    result: NonEmptyText
    reason_code: StrictStr | None = None
    sanitized_metadata: dict[str, JsonValue]
    synthetic: SyntheticTrue


class CaseInputSnapshot(DomainModel):
    case: MerchantSuccessCase
    evidence: tuple[EvidenceItem, ...]
    current_diagnosis: DiagnosisSnapshot | None = None


class CaseView(DomainModel):
    case: MerchantSuccessCase
    evidence: tuple[EvidenceItem, ...]
    current_diagnosis: DiagnosisSnapshot | None = None


class DiagnosisView(DomainModel):
    case_id: UUID4Str
    case_status: CaseStatus
    case_revision: Revision
    evidence_revision: Revision
    diagnosis: DiagnosisSnapshot


class CommandResult[T](DomainModel):
    outcome: WriteOutcome
    value: T


class AppendEvidenceResult(DomainModel):
    outcome: WriteOutcome
    case_view: CaseView


class CommitDiagnosisResult(DomainModel):
    outcome: WriteOutcome
    case_view: CaseView
    diagnosis: DiagnosisSnapshot
