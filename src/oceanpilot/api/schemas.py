import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from oceanpilot.application.commands import AddEvidenceCommand, CreateCaseCommand
from oceanpilot.domain.enums import (
    CaseType,
    EvidenceAvailability,
    EvidenceCode,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import (
    EvidenceCreate,
    EvidenceOrigin,
    SyntheticTrue,
    UUID4Str,
)

_RFC3339_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)


def _parse_rfc3339(value: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("invalid RFC3339 timestamp")
    return parsed


class FoundationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )


class CreateCaseRequest(FoundationRequest):
    case_type: CaseType
    summary: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    merchant_ref: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    synthetic: SyntheticTrue

    def to_command(
        self,
        request_id: UUID4Str,
        trace_id: UUID4Str,
    ) -> CreateCaseCommand:
        return CreateCaseCommand(
            case_type=self.case_type,
            summary=self.summary,
            merchant_ref=self.merchant_ref,
            synthetic=self.synthetic,
            request_id=request_id,
            trace_id=trace_id,
        )


class EvidenceCreateRequest(FoundationRequest):
    evidence_id: UUID4Str
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    typed_value: StrictStr | StrictBool | None = None
    observed_at: StrictStr | None = None
    source_ref: Annotated[StrictStr, Field(min_length=1, max_length=128)]

    def to_command(
        self,
        case_id: UUID4Str,
        request_id: UUID4Str,
        trace_id: UUID4Str,
    ) -> AddEvidenceCommand:
        observed_at = _parse_rfc3339(self.observed_at) if self.observed_at is not None else None
        typed_value: str | bool | datetime | None = self.typed_value
        if self.evidence_code is EvidenceCode.TRANSACTION_OCCURRED_AT:
            if not isinstance(self.typed_value, str):
                raise ValueError("invalid RFC3339 timestamp")
            typed_value = _parse_rfc3339(self.typed_value)

        return AddEvidenceCommand(
            case_id=case_id,
            evidence=EvidenceCreate(
                evidence_id=self.evidence_id,
                evidence_code=self.evidence_code,
                availability=self.availability,
                typed_value=typed_value,
                observed_at=observed_at,
                source_ref=self.source_ref,
            ),
            origin=EvidenceOrigin(
                source_type=SourceType.MERCHANT,
                source_reliability=SourceReliability.USER_REPORTED,
                synthetic=True,
            ),
            request_id=request_id,
            trace_id=trace_id,
        )
