from decimal import Decimal

from oceanpilot.domain.chargeback import ChargebackEvidenceCode
from oceanpilot.domain.chargeback_prevention import (
    HIGH_TICKET_AMOUNT,
    PreventionRiskFactor,
    PreventionRiskLevel,
    PreventionSignals,
    assess_chargeback_risk,
)


def test_clean_transaction_is_low_risk_with_no_recommendations():
    result = assess_chargeback_risk(PreventionSignals())
    assert result.risk_level is PreventionRiskLevel.LOW
    assert result.risk_score == Decimal("0.0000")
    assert result.factors == ()
    assert result.recommended_evidence == ()
    assert result.recommend_manual_review is False


def test_single_moderate_factor_stays_low():
    result = assess_chargeback_risk(PreventionSignals(three_ds_authenticated=False))
    assert PreventionRiskFactor.NO_3DS in result.factors
    assert result.risk_score == Decimal("0.2000")
    assert result.risk_level is PreventionRiskLevel.LOW
    assert ChargebackEvidenceCode.THREEDS_AUTHENTICATION in result.recommended_evidence


def test_two_factors_reach_medium():
    result = assess_chargeback_risk(
        PreventionSignals(three_ds_authenticated=False, avs_match=False)
    )
    assert set(result.factors) == {
        PreventionRiskFactor.NO_3DS,
        PreventionRiskFactor.AVS_MISMATCH,
    }
    assert result.risk_score == Decimal("0.3500")
    assert result.risk_level is PreventionRiskLevel.MEDIUM
    assert result.recommend_manual_review is False


def test_high_risk_recommends_manual_review_and_dedupes_evidence():
    result = assess_chargeback_risk(
        PreventionSignals(
            three_ds_authenticated=False,  # 0.20
            avs_match=False,  # 0.15
            cvv_match=False,  # 0.15
            customer_dispute_history=3,  # 0.15 (>= 2)
        )
    )
    assert result.risk_score == Decimal("0.6500")
    assert result.risk_level is PreventionRiskLevel.HIGH
    assert result.recommend_manual_review is True
    # Evidence is deduped and ordered by the ChargebackEvidenceCode enum.
    assert len(result.recommended_evidence) == len(set(result.recommended_evidence))
    order = list(ChargebackEvidenceCode)
    positions = [order.index(code) for code in result.recommended_evidence]
    assert positions == sorted(positions)


def test_score_is_capped_at_one():
    result = assess_chargeback_risk(
        PreventionSignals(
            avs_match=False,
            cvv_match=False,
            three_ds_authenticated=False,
            device_ip_match=False,
            amount=HIGH_TICKET_AMOUNT,
            high_risk_mcc=True,
            cross_border=True,
            shipping_billing_mismatch=True,
            customer_dispute_history=5,
            digital_goods=True,
        )
    )
    assert result.risk_score == Decimal("1.0000")
    assert result.risk_level is PreventionRiskLevel.HIGH


def test_high_ticket_boundary_is_inclusive():
    below = assess_chargeback_risk(PreventionSignals(amount=HIGH_TICKET_AMOUNT - Decimal("1")))
    at = assess_chargeback_risk(PreventionSignals(amount=HIGH_TICKET_AMOUNT))
    assert PreventionRiskFactor.HIGH_TICKET not in below.factors
    assert PreventionRiskFactor.HIGH_TICKET in at.factors


def test_assessment_is_deterministic():
    signals = PreventionSignals(cvv_match=False, high_risk_mcc=True)
    assert assess_chargeback_risk(signals) == assess_chargeback_risk(signals)
