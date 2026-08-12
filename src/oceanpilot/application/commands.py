from typing import Annotated

from pydantic import Field

from oceanpilot.domain.enums import CaseType
from oceanpilot.domain.models import (
    EvidenceCreate,
    EvidenceOrigin,
    FrozenDomainModel,
    SyntheticTrue,
    UUID4Str,
)


class CreateCaseCommand(FrozenDomainModel):
    case_id: UUID4Str | None = None
    case_type: CaseType
    summary: Annotated[str, Field(strict=True, min_length=1, max_length=500)]
    merchant_ref: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    synthetic: SyntheticTrue
    request_id: UUID4Str
    trace_id: UUID4Str


class AddEvidenceCommand(FrozenDomainModel):
    case_id: UUID4Str
    evidence: EvidenceCreate
    origin: EvidenceOrigin
    request_id: UUID4Str
    trace_id: UUID4Str


class DiagnoseCaseCommand(FrozenDomainModel):
    case_id: UUID4Str
    request_id: UUID4Str
    trace_id: UUID4Str
