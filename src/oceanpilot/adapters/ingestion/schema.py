"""Import schema for real chargeback reference data (T12, design §11).

The company will later supply real reason-code rules, per-bank evidence templates,
and redacted case samples. These strict, closed DTOs define exactly what a valid
import record looks like so that data can be dropped in and validated without
changing any caller. All shapes reuse the domain enums, so an unknown reason /
evidence / team is rejected at ingestion, not at runtime.

Synthetic-only is enforced for case samples (``synthetic`` must be ``True``).
"""

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

from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode
from oceanpilot.domain.enums import ResponsibleTeam


class _ImportModel(BaseModel):
    # extra="forbid" rejects unknown fields; enum fields coerce from their string
    # value (no model-level strict, which would block that coercion).
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceRequirementRecord(_ImportModel):
    evidence_code: ChargebackEvidenceCode
    weight: Annotated[StrictInt, Field(ge=1, le=10)]
    critical: StrictBool = False


class ReasonCodeMappingRecord(_ImportModel):
    """Map a card-network reason code to the kernel's closed reason family."""

    card_network: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    network_reason_code: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    reason_code: DisputeReasonCode
    notes: Annotated[StrictStr, Field(max_length=500)] = ""


class ReasonPolicyRecord(_ImportModel):
    """A reason-code rule row for the deterministic kernel table."""

    reason_code: DisputeReasonCode
    responsible_team: ResponsibleTeam
    default_deadline_days: Annotated[StrictInt, Field(ge=1, le=120)]
    high_risk: StrictBool = False
    required: Annotated[tuple[EvidenceRequirementRecord, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _no_duplicate_evidence(self) -> "ReasonPolicyRecord":
        codes = [requirement.evidence_code for requirement in self.required]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate evidence_code in required")
        return self


class BankRuleRecord(_ImportModel):
    """A per-bank / per-network evidence template for the knowledge base."""

    reason_code: DisputeReasonCode
    card_network: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    source: Literal["bank", "network"]
    bank_id: Annotated[StrictStr, Field(min_length=1, max_length=64)] | None = None
    required_evidence: Annotated[tuple[ChargebackEvidenceCode, ...], Field(min_length=1)]
    template_order: Annotated[tuple[ChargebackEvidenceCode, ...], Field(min_length=1)]
    submission_window_days: Annotated[StrictInt, Field(ge=1, le=120)]
    notes: Annotated[StrictStr, Field(max_length=500)] = ""

    @model_validator(mode="after")
    def _consistent(self) -> "BankRuleRecord":
        if len(self.template_order) != len(self.required_evidence) or set(
            self.template_order
        ) != set(self.required_evidence):
            raise ValueError("template_order must be a permutation of required_evidence")
        if self.source == "bank" and self.bank_id is None:
            raise ValueError("a 'bank' rule requires bank_id")
        if self.source == "network" and self.bank_id is not None:
            raise ValueError("a 'network' rule must not set bank_id")
        return self


class CaseSampleRecord(_ImportModel):
    """A redacted, synthetic historical case (for eval / prompt tuning)."""

    case_ref: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    reason_code: DisputeReasonCode
    present_evidence: tuple[ChargebackEvidenceCode, ...] = ()
    outcome: Literal["won", "lost", "pending"] | None = None
    synthetic: StrictBool
    notes: Annotated[StrictStr, Field(max_length=1000)] = ""

    @model_validator(mode="after")
    def _must_be_synthetic(self) -> "CaseSampleRecord":
        if self.synthetic is not True:
            raise ValueError("case samples must be synthetic")
        return self
