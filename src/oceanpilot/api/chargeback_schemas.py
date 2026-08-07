from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode


class _StrictRequest(BaseModel):
    # extra="forbid" rejects unknown fields; per-field StrictStr enforces string
    # types. (Model-level strict=True would reject valid string->enum coercion.)
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class CreateChargebackRequest(_StrictRequest):
    description: Annotated[StrictStr, Field(min_length=1, max_length=2000)]


class SubmitEvidenceRequest(_StrictRequest):
    evidence_code: ChargebackEvidenceCode


class ConfirmReasonRequest(_StrictRequest):
    # Optional correction; when omitted the human confirms the proposed reason.
    reason_code: DisputeReasonCode | None = None


class ChargebackAssessmentDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    win_likelihood: StrictStr
    completeness: StrictStr
    responsible_team: StrictStr
    requires_human: StrictBool
    review_reasons: tuple[StrictStr, ...]
    explanation: StrictStr


class ChargebackCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: StrictStr
    phase: StrictStr
    reason_code: StrictStr | None = None
    reason_confirmed: StrictBool = False
    collected: tuple[StrictStr, ...] = ()
    next_evidence: StrictStr | None = None
    question: StrictStr | None = None
    missing: tuple[StrictStr, ...] | None = None
    assessment: ChargebackAssessmentDTO | None = None
