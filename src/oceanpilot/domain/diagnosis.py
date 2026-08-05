from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

from oceanpilot.domain.enums import ReviewReason, SourceReliability
from oceanpilot.domain.models import (
    ActiveEvidenceView,
    ConfidenceResult,
    DiagnosisDraft,
    EvidenceItem,
    MerchantSuccessCase,
)

HUMAN_REVIEW_SCORE_THRESHOLD = Decimal("0.90")
HUMAN_REVIEW_SOURCE_QUALITY_THRESHOLD = Decimal("0.75")

SOURCE_QUALITY: Final[Mapping[SourceReliability, Decimal]] = MappingProxyType(
    {
        SourceReliability.SYSTEM_OF_RECORD: Decimal("1.00"),
        SourceReliability.VERIFIED_DOCUMENT: Decimal("0.90"),
        SourceReliability.SYNTHETIC_TEST: Decimal("0.80"),
        SourceReliability.OPERATOR_CONFIRMED: Decimal("0.75"),
        SourceReliability.USER_REPORTED: Decimal("0.55"),
    }
)


def _valid_coverage(value: object) -> bool:
    return (
        isinstance(value, Decimal) and value.is_finite() and Decimal("0") <= value <= Decimal("1")
    )


def _valid_consistency(value: object) -> bool:
    return (
        isinstance(value, Decimal) and value.is_finite() and value in {Decimal("0"), Decimal("1")}
    )


def calculate_confidence(
    decisive_evidence: Sequence[EvidenceItem],
    *,
    required_coverage: Decimal,
    consistency: Decimal,
) -> ConfidenceResult:
    if (
        not decisive_evidence
        or not _valid_coverage(required_coverage)
        or not _valid_consistency(consistency)
    ):
        raise ValueError("invalid confidence inputs")

    minimum_source_quality = min(
        SOURCE_QUALITY[item.source_reliability] for item in decisive_evidence
    )
    raw_score = (
        Decimal("0.50") * required_coverage
        + Decimal("0.30") * minimum_source_quality
        + Decimal("0.20") * consistency
    )
    display_score = raw_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    reasons: set[ReviewReason] = set()
    if raw_score < HUMAN_REVIEW_SCORE_THRESHOLD:
        reasons.add(ReviewReason.LOW_CONFIDENCE)
    if minimum_source_quality < HUMAN_REVIEW_SOURCE_QUALITY_THRESHOLD:
        reasons.add(ReviewReason.INSUFFICIENT_SOURCE_QUALITY)
    return ConfidenceResult(
        raw_score=raw_score,
        display_score=display_score,
        review_reasons=frozenset(reasons),
    )


@runtime_checkable
class DiagnosisEngine(Protocol):
    def evaluate(
        self,
        case: MerchantSuccessCase,
        view: ActiveEvidenceView,
        *,
        policy_version: str,
    ) -> DiagnosisDraft: ...
