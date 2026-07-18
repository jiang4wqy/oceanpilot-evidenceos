from decimal import Decimal
from types import MappingProxyType

import pytest

from oceanpilot.domain.diagnosis import SOURCE_QUALITY, calculate_confidence
from oceanpilot.domain.enums import ReviewReason, SourceReliability

EXPECTED_SOURCE_QUALITY = {
    SourceReliability.SYSTEM_OF_RECORD: Decimal("1.00"),
    SourceReliability.VERIFIED_DOCUMENT: Decimal("0.90"),
    SourceReliability.SYNTHETIC_TEST: Decimal("0.80"),
    SourceReliability.OPERATOR_CONFIRMED: Decimal("0.75"),
    SourceReliability.USER_REPORTED: Decimal("0.55"),
}


def test_source_quality_map_is_exact_and_externally_immutable() -> None:
    assert isinstance(SOURCE_QUALITY, MappingProxyType)
    assert dict(SOURCE_QUALITY) == EXPECTED_SOURCE_QUALITY

    with pytest.raises(TypeError):
        SOURCE_QUALITY[SourceReliability.USER_REPORTED] = Decimal("1")
    with pytest.raises(TypeError):
        del SOURCE_QUALITY[SourceReliability.SYSTEM_OF_RECORD]


@pytest.mark.parametrize(
    ("reliability", "raw", "display", "reasons"),
    (
        (SourceReliability.SYSTEM_OF_RECORD, "1.000", "1.00", frozenset()),
        (SourceReliability.VERIFIED_DOCUMENT, "0.970", "0.97", frozenset()),
        (SourceReliability.SYNTHETIC_TEST, "0.940", "0.94", frozenset()),
        (SourceReliability.OPERATOR_CONFIRMED, "0.925", "0.93", frozenset()),
        (
            SourceReliability.USER_REPORTED,
            "0.865",
            "0.87",
            frozenset({
                ReviewReason.LOW_CONFIDENCE,
                ReviewReason.INSUFFICIENT_SOURCE_QUALITY,
            }),
        ),
    ),
)
def test_all_five_full_coverage_scores_are_exact(
    evidence_factory,
    reliability: SourceReliability,
    raw: str,
    display: str,
    reasons: frozenset[ReviewReason],
) -> None:
    result = calculate_confidence(
        [evidence_factory(reliability=reliability)],
        required_coverage=Decimal("1"),
        consistency=Decimal("1"),
    )
    assert result.raw_score == Decimal(raw)
    assert result.display_score == Decimal(display)
    assert result.review_reasons == reasons


def test_mixed_sources_use_the_minimum_independent_of_order(evidence_factory) -> None:
    high = evidence_factory(
        reliability=SourceReliability.SYSTEM_OF_RECORD,
        evidence_id="00000000-0000-4000-8000-000000000001",
    )
    low = evidence_factory(
        reliability=SourceReliability.USER_REPORTED,
        evidence_id="00000000-0000-4000-8000-000000000002",
    )

    first = calculate_confidence(
        [high, low], required_coverage=Decimal("1"), consistency=Decimal("1")
    )
    second = calculate_confidence(
        [low, high], required_coverage=Decimal("1"), consistency=Decimal("1")
    )
    assert first == second
    assert first.raw_score == Decimal("0.865")


@pytest.mark.parametrize(
    "coverage",
    (
        True,
        1,
        1.0,
        "1",
        None,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-0.01"),
        Decimal("1.01"),
    ),
)
def test_invalid_coverage_uses_one_safe_error(evidence_factory, coverage: object) -> None:
    with pytest.raises(ValueError) as caught:
        calculate_confidence(
            [evidence_factory()],
            required_coverage=coverage,
            consistency=Decimal("1"),
        )
    assert str(caught.value) == "invalid confidence inputs"
    assert repr(coverage) not in str(caught.value)


@pytest.mark.parametrize(
    "consistency",
    (
        True,
        1,
        1.0,
        "1",
        None,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-1"),
        Decimal("0.5"),
        Decimal("2"),
    ),
)
def test_invalid_consistency_uses_one_safe_error(
    evidence_factory,
    consistency: object,
) -> None:
    with pytest.raises(ValueError) as caught:
        calculate_confidence(
            [evidence_factory()],
            required_coverage=Decimal("1"),
            consistency=consistency,
        )
    assert str(caught.value) == "invalid confidence inputs"
    assert repr(consistency) not in str(caught.value)


def test_empty_decisive_evidence_uses_the_same_safe_error() -> None:
    with pytest.raises(ValueError, match="^invalid confidence inputs$"):
        calculate_confidence(
            [],
            required_coverage=Decimal("1"),
            consistency=Decimal("1"),
        )


def test_unrounded_score_controls_low_confidence_gate(evidence_factory) -> None:
    evidence = [evidence_factory(reliability=SourceReliability.SYNTHETIC_TEST)]
    threshold = calculate_confidence(
        evidence,
        required_coverage=Decimal("0.92"),
        consistency=Decimal("1"),
    )
    below = calculate_confidence(
        evidence,
        required_coverage=Decimal("0.91"),
        consistency=Decimal("1"),
    )

    assert threshold.raw_score == Decimal("0.900")
    assert ReviewReason.LOW_CONFIDENCE not in threshold.review_reasons
    assert below.raw_score == Decimal("0.895")
    assert below.display_score == Decimal("0.90")
    assert ReviewReason.LOW_CONFIDENCE in below.review_reasons


def test_source_quality_point_75_is_not_insufficient(evidence_factory) -> None:
    result = calculate_confidence(
        [evidence_factory(reliability=SourceReliability.OPERATOR_CONFIRMED)],
        required_coverage=Decimal("1"),
        consistency=Decimal("1"),
    )
    assert result.raw_score == Decimal("0.925")
    assert ReviewReason.INSUFFICIENT_SOURCE_QUALITY not in result.review_reasons


def test_consistency_zero_is_valid_and_uses_the_formula(evidence_factory) -> None:
    result = calculate_confidence(
        [evidence_factory(reliability=SourceReliability.SYNTHETIC_TEST)],
        required_coverage=Decimal("1"),
        consistency=Decimal("0"),
    )
    assert result.raw_score == Decimal("0.740")
    assert result.display_score == Decimal("0.74")
    assert result.review_reasons == frozenset({ReviewReason.LOW_CONFIDENCE})
