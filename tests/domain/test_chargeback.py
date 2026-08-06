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


def test_invalid_reason_code_type_is_rejected():
    with pytest.raises(TypeError):
        assess_chargeback("FRAUD_CARD_NOT_PRESENT", [])
