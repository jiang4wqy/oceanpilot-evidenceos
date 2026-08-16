from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from oceanpilot.domain.chargeback import CardNetwork, ChargebackEvidenceCode, DisputeReasonCode


class _StrictRequest(BaseModel):
    # extra="forbid" rejects unknown fields; per-field StrictStr enforces string
    # types. (Model-level strict=True would reject valid string->enum coercion.)
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class CreateChargebackRequest(_StrictRequest):
    description: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    card_network: CardNetwork | None = None


class SetCardNetworkRequest(_StrictRequest):
    card_network: CardNetwork
    expected_revision: Annotated[StrictInt, Field(ge=0)]


class SubmitEvidenceRequest(_StrictRequest):
    evidence_code: ChargebackEvidenceCode


class WithdrawLatestEvidenceRequest(_StrictRequest):
    evidence_code: ChargebackEvidenceCode


class ConfirmReasonRequest(_StrictRequest):
    # Optional correction; when omitted the human confirms the proposed reason.
    reason_code: DisputeReasonCode | None = None


class ChargebackEvidenceItemDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: StrictStr
    label: StrictStr
    weight: StrictInt
    critical: StrictBool
    present: StrictBool


class ChargebackAssessmentDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    win_likelihood: Annotated[
        StrictStr,
        Field(
            deprecated=True,
            description=(
                "Deprecated compatibility alias for evidence_readiness. This deterministic "
                "value measures evidence readiness, not predicted chargeback win probability."
            ),
        ),
    ]
    evidence_readiness: StrictStr
    completeness: StrictStr
    responsible_team: StrictStr
    requires_human: StrictBool
    review_reasons: tuple[StrictStr, ...]
    explanation: StrictStr
    explanation_source: StrictStr = "FALLBACK"
    evidence_breakdown: tuple[ChargebackEvidenceItemDTO, ...] = ()


class ChargebackDeadlineDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: StrictStr
    days_remaining: StrictInt | None = None
    deadline_at: StrictStr | None = None
    overdue: StrictBool


class ChargebackFactsDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: StrictStr | None = None
    currency: StrictStr | None = None
    occurred_on: StrictStr | None = None
    summary: StrictStr | None = None


class ChargebackAuditEventDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: StrictInt
    event_type: StrictStr
    detail: StrictStr | None = None
    case_revision: StrictInt
    occurred_at: StrictStr


class ChargebackAuditResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: StrictStr
    events: tuple[ChargebackAuditEventDTO, ...] = ()


class LabeledEvidenceDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: StrictStr
    label: StrictStr


class ChargebackPackageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: StrictStr
    reason_code: StrictStr
    reason_label: StrictStr
    bank_id: StrictStr | None = None
    card_network: StrictStr | None = None
    rule_source: StrictStr
    scheme_reason_code: StrictStr | None = None
    rule_version: StrictStr | None = None
    source_document: StrictStr | None = None
    source_section: StrictStr | None = None
    required_assertions: tuple[StrictStr, ...] = ()
    rule_limitation: StrictStr | None = None
    rule_version_id: StrictStr | None = None
    verification_status: StrictStr | None = None
    submission_window_basis: StrictStr | None = None
    submission_window_days: StrictInt
    completeness: StrictStr
    ready_to_submit: StrictBool
    ordered_evidence: tuple[LabeledEvidenceDTO, ...] = ()
    missing_evidence: tuple[LabeledEvidenceDTO, ...] = ()
    cover_note: StrictStr
    cover_note_source: StrictStr


class RuleSummaryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version_id: StrictStr
    document_id: StrictStr
    scheme: StrictStr
    scheme_reason_code: StrictStr
    display_name: StrictStr
    category: StrictStr
    region: StrictStr
    version_label: StrictStr | None = None
    demo_role: StrictStr
    verification_status: StrictStr
    source_document: StrictStr
    source_url: StrictStr


class RuleCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[RuleSummaryDTO, ...] = ()
    total: StrictInt
    demo_mapped: StrictInt
    scheme_count: StrictInt
    source_document_count: StrictInt
    disclaimer: StrictStr


class RuleRequirementDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: StrictStr
    requirement_type: StrictStr
    necessity: StrictStr
    sequence: StrictInt
    description_zh: StrictStr
    internal_evidence_code: StrictStr | None = None


class RuleDocumentDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: StrictStr
    scheme: StrictStr
    title: StrictStr
    publisher: StrictStr
    source_url: StrictStr
    source_version: StrictStr | None = None


class RuleDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version_id: StrictStr
    scheme: StrictStr
    scheme_reason_code: StrictStr
    display_name: StrictStr
    category: StrictStr
    region: StrictStr
    version_label: StrictStr | None = None
    source_section: StrictStr | None = None
    effective_date: StrictStr | None = None
    internal_reason_code: StrictStr | None = None
    demo_role: StrictStr
    internal_window_days: StrictInt | None = None
    verification_status: StrictStr
    limitation: StrictStr
    document: RuleDocumentDTO
    assertions: tuple[RuleRequirementDTO, ...] = ()
    evidence: tuple[RuleRequirementDTO, ...] = ()
    disclaimer: StrictStr


class RuleReferenceDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version_id: StrictStr
    scheme_reason_code: StrictStr
    rule_version: StrictStr | None = None
    source_document: StrictStr | None = None
    source_section: StrictStr | None = None
    verification_status: StrictStr
    submission_window_basis: StrictStr
    limitation: StrictStr


class CaseRuleReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: StrictStr
    card_network: StrictStr
    match_status: Literal["EXACT_MATCH", "NO_EXACT_MAPPING"]
    rule_reference: RuleReferenceDTO | None = None


class AppealRequest(_StrictRequest):
    bank_id: StrictStr | None = None
    card_network: CardNetwork | None = None
    human_approved: StrictBool = False
    actor_id: StrictStr | None = None

    @model_validator(mode="after")
    def _actor_required_when_approved(self) -> "AppealRequest":
        if self.human_approved and not (self.actor_id and self.actor_id.strip()):
            raise ValueError("actor_id is required when human_approved is true")
        return self


class ChargebackAppealResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthetic: Literal[True]
    connector_kind: Literal["IN_PROCESS_MOCK"]
    draft: StrictStr
    draft_source: StrictStr
    submitted: StrictBool
    submission_id: StrictStr | None = None
    status: StrictStr | None = None
    blocked_reason: StrictStr | None = None


class PreventionRequest(_StrictRequest):
    # Synthetic pre-/at-transaction signals; clean defaults => no risk factors.
    avs_match: StrictBool = True
    cvv_match: StrictBool = True
    three_ds_authenticated: StrictBool = True
    device_ip_match: StrictBool = True
    amount: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    high_risk_mcc: StrictBool = False
    cross_border: StrictBool = False
    shipping_billing_mismatch: StrictBool = False
    customer_dispute_history: Annotated[StrictInt, Field(ge=0)] = 0
    digital_goods: StrictBool = False


class PreventionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: StrictStr
    risk_score: StrictStr
    factors: tuple[StrictStr, ...] = ()
    recommended_evidence: tuple[LabeledEvidenceDTO, ...] = ()
    recommend_manual_review: StrictBool
    advice: StrictStr
    advice_source: StrictStr


class MetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts: dict[StrictStr, StrictInt] = {}


class CatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: StrictStr
    reasons: tuple[LabeledEvidenceDTO, ...] = ()
    evidence: tuple[LabeledEvidenceDTO, ...] = ()


class SafetyScanRequest(_StrictRequest):
    text: Annotated[StrictStr, Field(min_length=1, max_length=4000)]


class SafetyScanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: StrictBool
    detail: StrictStr


class AgentActivityDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: StrictStr
    action: StrictStr
    source: StrictStr | None = None


class ChargebackCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: StrictStr
    phase: StrictStr
    revision: StrictInt
    card_network: CardNetwork | None = None
    reason_code: StrictStr | None = None
    reason_confirmed: StrictBool = False
    collection_finalized: StrictBool = False
    collected: tuple[StrictStr, ...] = ()
    next_evidence: StrictStr | None = None
    next_evidence_label: StrictStr | None = None
    question: StrictStr | None = None
    missing: tuple[StrictStr, ...] | None = None
    missing_labels: tuple[StrictStr, ...] = ()
    assessment: ChargebackAssessmentDTO | None = None
    deadline: ChargebackDeadlineDTO | None = None
    facts: ChargebackFactsDTO | None = None
    agent_trace: tuple[AgentActivityDTO, ...] = ()
