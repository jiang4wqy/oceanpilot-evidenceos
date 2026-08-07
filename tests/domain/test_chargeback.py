from decimal import Decimal

import pytest

from oceanpilot.domain.chargeback import (
    WIN_REVIEW_THRESHOLD,
    ChargebackEvidenceCode,
    ChargebackReviewReason,
    DisputeReasonCode,
    assess_chargeback,
    required_evidence_for,
)
from oceanpilot.domain.enums import ResponsibleTeam

_C = ChargebackEvidenceCode


def test_every_reason_code_has_a_policy():
    for reason in DisputeReasonCode:
        checklist = required_evidence_for(reason)
        assert checklist  # non-empty
        assert len(set(checklist)) == len(checklist)  # no duplicates


def test_full_evidence_is_ready_and_high_win():
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    result = assess_chargeback(reason, required_evidence_for(reason))
    assert result.missing_evidence == ()
    assert result.missing_critical == ()
    assert result.completeness == Decimal("1.0000")
    assert result.win_likelihood == Decimal("1.0000")
    assert result.ready_to_submit is True
    assert result.requires_human is False
    assert result.review_reasons == ()
    assert result.responsible_team is ResponsibleTeam.CUSTOMER_SUPPORT
    assert result.default_deadline_days == 15


def test_no_evidence_flags_missing_critical_and_human_review():
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    result = assess_chargeback(reason, [])
    assert result.present_evidence == ()
    assert set(result.missing_evidence) == set(required_evidence_for(reason))
    assert result.missing_critical  # tracked separately
    assert result.win_likelihood == Decimal("0.0000")
    assert result.ready_to_submit is False
    assert result.requires_human is True
    assert ChargebackReviewReason.MISSING_CRITICAL_EVIDENCE in result.review_reasons
    assert ChargebackReviewReason.LOW_WIN_LIKELIHOOD in result.review_reasons


def test_fraud_category_always_requires_human_even_when_complete():
    reason = DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    result = assess_chargeback(reason, required_evidence_for(reason))
    assert result.win_likelihood == Decimal("1.0000")
    assert result.ready_to_submit is True
    assert result.requires_human is True  # high-risk category
    assert result.review_reasons == (ChargebackReviewReason.HIGH_RISK_CATEGORY,)
    assert result.responsible_team is ResponsibleTeam.RISK


def test_partial_evidence_scores_between_zero_and_one():
    reason = DisputeReasonCode.CREDIT_NOT_PROCESSED
    # provide only the low-weight receipt; the critical refund record is missing
    result = assess_chargeback(reason, [ChargebackEvidenceCode.TRANSACTION_RECEIPT])
    assert Decimal("0") < result.win_likelihood < Decimal("1")
    assert ChargebackEvidenceCode.REFUND_RECORD in result.missing_critical
    assert result.requires_human is True
    assert result.responsible_team is ResponsibleTeam.FINANCE


def test_extra_non_required_evidence_does_not_change_score():
    reason = DisputeReasonCode.DUPLICATE_PROCESSING
    base = assess_chargeback(reason, required_evidence_for(reason))
    with_extra = assess_chargeback(
        reason,
        (*required_evidence_for(reason), ChargebackEvidenceCode.THREEDS_AUTHENTICATION),
    )
    assert with_extra.win_likelihood == base.win_likelihood == Decimal("1.0000")
    assert with_extra.ready_to_submit is True


def test_win_likelihood_is_bounded_and_quantized():
    for reason in DisputeReasonCode:
        result = assess_chargeback(reason, [ChargebackEvidenceCode.TRANSACTION_RECEIPT])
        assert Decimal("0") <= result.win_likelihood <= Decimal("1")
        assert result.win_likelihood == result.win_likelihood.quantize(Decimal("0.0001"))


def test_assessment_is_deterministic():
    reason = DisputeReasonCode.PRODUCT_NOT_AS_DESCRIBED
    present = [
        ChargebackEvidenceCode.TRANSACTION_RECEIPT,
        ChargebackEvidenceCode.PRODUCT_DESCRIPTION,
    ]
    assert assess_chargeback(reason, present) == assess_chargeback(reason, present)


def test_low_win_likelihood_drives_review_reason():
    # AUTHORIZATION_ERROR: only the 2-weight receipt out of total 8 -> 0.25 < 0.60
    result = assess_chargeback(
        DisputeReasonCode.AUTHORIZATION_ERROR,
        [ChargebackEvidenceCode.TRANSACTION_RECEIPT],
    )
    assert result.win_likelihood < WIN_REVIEW_THRESHOLD
    assert ChargebackReviewReason.LOW_WIN_LIKELIHOOD in result.review_reasons


def test_missing_one_critical_gates_win_below_the_raw_ratio():
    # FRAUD: everything present except the critical 3DS. Raw weighted ratio is
    # 9/12 = 0.75, but with 1 of 2 critical items present the gate halves it to
    # 0.375 — a weight-complete case missing decisive proof must not read high.
    reason = DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    present = [c for c in required_evidence_for(reason) if c is not _C.THREEDS_AUTHENTICATION]
    result = assess_chargeback(reason, present)
    assert result.win_likelihood == Decimal("0.3750")
    assert result.win_likelihood < WIN_REVIEW_THRESHOLD
    assert _C.THREEDS_AUTHENTICATION in result.missing_critical
    assert result.requires_human is True
    assert ChargebackReviewReason.MISSING_CRITICAL_EVIDENCE in result.review_reasons
    assert ChargebackReviewReason.LOW_WIN_LIKELIHOOD in result.review_reasons


def test_missing_all_criticals_with_some_evidence_floors_low_but_nonzero():
    # FRAUD: only non-critical AVS + CVV present; both critical items missing.
    # The gate zeroes the product, then the floor lifts it to 0.05 — bleak, not 0.
    reason = DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    result = assess_chargeback(reason, [_C.AVS_RESULT, _C.CVV_RESULT])
    assert result.win_likelihood == Decimal("0.0500")
    assert result.win_likelihood > Decimal("0")


def test_all_criticals_present_incurs_no_gate_penalty():
    # PRODUCT_NOT_RECEIVED: both critical items present, only non-critical missing.
    # Win equals the raw weighted ratio (7/10) with no gate reduction.
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    present = [_C.TRANSACTION_RECEIPT, _C.DELIVERY_TRACKING, _C.PROOF_OF_DELIVERY]
    result = assess_chargeback(reason, present)
    assert result.win_likelihood == Decimal("0.7000")
    assert result.missing_critical == ()
    assert result.requires_human is False


def test_dropping_any_required_item_never_raises_the_win():
    # Monotonicity property: removing any single required item can only lower
    # (or hold) the win likelihood — the gate never makes a weaker case score
    # higher than the complete one.
    for reason in DisputeReasonCode:
        full = required_evidence_for(reason)
        result_full = assess_chargeback(reason, full)
        for dropped_code in full:
            weaker = assess_chargeback(reason, [c for c in full if c is not dropped_code])
            assert weaker.win_likelihood <= result_full.win_likelihood


def test_assessment_exposes_per_evidence_breakdown():
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    result = assess_chargeback(reason, [_C.TRANSACTION_RECEIPT, _C.DELIVERY_TRACKING])
    # Breakdown covers exactly the required checklist, in order.
    assert tuple(item.code for item in result.evidence_breakdown) == result.required_evidence
    by_code = {item.code: item for item in result.evidence_breakdown}
    assert by_code[_C.TRANSACTION_RECEIPT].present is True
    assert by_code[_C.PROOF_OF_DELIVERY].present is False
    assert by_code[_C.PROOF_OF_DELIVERY].critical is True
    assert all(item.weight >= 1 for item in result.evidence_breakdown)
    # present items are exactly those in present_evidence
    present = {item.code for item in result.evidence_breakdown if item.present}
    assert present == set(result.present_evidence)


def test_invalid_reason_code_type_is_rejected():
    with pytest.raises(TypeError):
        assess_chargeback("FRAUD_CARD_NOT_PRESENT", [])
