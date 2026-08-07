"""Deterministic pre-dispute (chargeback-prevention) risk kernel.

Design §6 ⑦: *before* a dispute exists, score a transaction's chargeback
likelihood from synthetic signals and tell the merchant which evidence to keep
now, so the case is defensible later. Like the assessment kernel, this decides
deterministically (no LLM); the Prevention agent only phrases the advice.

It **never** blocks, holds, or captures a payment — the strongest output is
``recommend_manual_review`` (advisory). Signals here are synthetic booleans /
amounts / counts (no raw PII); the weights are placeholders shaped so the
company's real risk model can be dropped in without changing callers. Recommended
evidence reuses ``ChargebackEvidenceCode`` so pre-collected proof lines up with
what the representment packager will later need.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from oceanpilot.domain.chargeback import ChargebackEvidenceCode

_QUANT = Decimal("0.0001")
_C = ChargebackEvidenceCode

# Score thresholds (inclusive lower bounds).
MEDIUM_RISK_THRESHOLD = Decimal("0.30")
HIGH_RISK_THRESHOLD = Decimal("0.60")

# Signal thresholds.
HIGH_TICKET_AMOUNT = Decimal("1000")
REPEAT_DISPUTE_THRESHOLD = 2


class PreventionRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PreventionRiskFactor(StrEnum):
    AVS_MISMATCH = "AVS_MISMATCH"
    CVV_MISMATCH = "CVV_MISMATCH"
    NO_3DS = "NO_3DS"
    DEVICE_IP_MISMATCH = "DEVICE_IP_MISMATCH"
    HIGH_TICKET = "HIGH_TICKET"
    HIGH_RISK_MCC = "HIGH_RISK_MCC"
    CROSS_BORDER = "CROSS_BORDER"
    SHIPPING_BILLING_MISMATCH = "SHIPPING_BILLING_MISMATCH"
    REPEAT_DISPUTER = "REPEAT_DISPUTER"
    DIGITAL_GOODS = "DIGITAL_GOODS"


@dataclass(frozen=True, slots=True)
class PreventionSignals:
    """Synthetic pre-/at-transaction signals. Clean defaults => no risk factors."""

    avs_match: bool = True
    cvv_match: bool = True
    three_ds_authenticated: bool = True
    device_ip_match: bool = True
    amount: Decimal = Decimal("0")
    high_risk_mcc: bool = False
    cross_border: bool = False
    shipping_billing_mismatch: bool = False
    customer_dispute_history: int = 0
    digital_goods: bool = False


@dataclass(frozen=True)
class PreventionAssessment:
    risk_level: PreventionRiskLevel
    risk_score: Decimal
    factors: tuple[PreventionRiskFactor, ...] = ()
    recommended_evidence: tuple[ChargebackEvidenceCode, ...] = ()
    recommend_manual_review: bool = False


@dataclass(frozen=True)
class _FactorRule:
    factor: PreventionRiskFactor
    weight: Decimal
    recommends: tuple[ChargebackEvidenceCode, ...] = field(default_factory=tuple)


def _rule(
    factor: PreventionRiskFactor,
    weight: str,
    *recommends: ChargebackEvidenceCode,
) -> _FactorRule:
    return _FactorRule(factor=factor, weight=Decimal(weight), recommends=recommends)


# Ordered so a fired factor's contribution and evidence hints are deterministic.
_RULES: tuple[_FactorRule, ...] = (
    _rule(PreventionRiskFactor.NO_3DS, "0.20", _C.THREEDS_AUTHENTICATION),
    _rule(PreventionRiskFactor.AVS_MISMATCH, "0.15", _C.AVS_RESULT, _C.SHIPPING_ADDRESS_MATCH),
    _rule(PreventionRiskFactor.CVV_MISMATCH, "0.15", _C.CVV_RESULT),
    _rule(
        PreventionRiskFactor.REPEAT_DISPUTER,
        "0.15",
        _C.PRIOR_TRANSACTION_HISTORY,
        _C.CUSTOMER_COMMUNICATION,
    ),
    _rule(PreventionRiskFactor.DEVICE_IP_MISMATCH, "0.10", _C.DEVICE_OR_IP_MATCH),
    _rule(
        PreventionRiskFactor.HIGH_TICKET,
        "0.10",
        _C.TRANSACTION_RECEIPT,
        _C.CUSTOMER_COMMUNICATION,
    ),
    _rule(
        PreventionRiskFactor.HIGH_RISK_MCC,
        "0.10",
        _C.PRODUCT_DESCRIPTION,
        _C.TERMS_AND_REFUND_POLICY,
    ),
    _rule(
        PreventionRiskFactor.SHIPPING_BILLING_MISMATCH,
        "0.10",
        _C.SHIPPING_ADDRESS_MATCH,
        _C.PROOF_OF_DELIVERY,
    ),
    _rule(
        PreventionRiskFactor.DIGITAL_GOODS,
        "0.10",
        _C.CUSTOMER_COMMUNICATION,
        _C.TERMS_AND_REFUND_POLICY,
    ),
    _rule(PreventionRiskFactor.CROSS_BORDER, "0.05", _C.TRANSACTION_RECEIPT),
)


def _fires(factor: PreventionRiskFactor, signals: PreventionSignals) -> bool:
    match factor:
        case PreventionRiskFactor.NO_3DS:
            return not signals.three_ds_authenticated
        case PreventionRiskFactor.AVS_MISMATCH:
            return not signals.avs_match
        case PreventionRiskFactor.CVV_MISMATCH:
            return not signals.cvv_match
        case PreventionRiskFactor.REPEAT_DISPUTER:
            return signals.customer_dispute_history >= REPEAT_DISPUTE_THRESHOLD
        case PreventionRiskFactor.DEVICE_IP_MISMATCH:
            return not signals.device_ip_match
        case PreventionRiskFactor.HIGH_TICKET:
            return signals.amount >= HIGH_TICKET_AMOUNT
        case PreventionRiskFactor.HIGH_RISK_MCC:
            return signals.high_risk_mcc
        case PreventionRiskFactor.SHIPPING_BILLING_MISMATCH:
            return signals.shipping_billing_mismatch
        case PreventionRiskFactor.DIGITAL_GOODS:
            return signals.digital_goods
        case PreventionRiskFactor.CROSS_BORDER:
            return signals.cross_border
    return False  # pragma: no cover - exhaustive above


def _level_for(score: Decimal) -> PreventionRiskLevel:
    if score >= HIGH_RISK_THRESHOLD:
        return PreventionRiskLevel.HIGH
    if score >= MEDIUM_RISK_THRESHOLD:
        return PreventionRiskLevel.MEDIUM
    return PreventionRiskLevel.LOW


def assess_chargeback_risk(signals: PreventionSignals) -> PreventionAssessment:
    """Deterministically score chargeback risk and recommend evidence to keep."""
    fired: list[_FactorRule] = [rule for rule in _RULES if _fires(rule.factor, signals)]
    raw_score = sum((rule.weight for rule in fired), Decimal("0"))
    score = min(raw_score, Decimal("1")).quantize(_QUANT, rounding=ROUND_HALF_UP)
    level = _level_for(score)

    recommended_set = {code for rule in fired for code in rule.recommends}
    # Deterministic order: follow the ChargebackEvidenceCode enum declaration.
    recommended = tuple(code for code in ChargebackEvidenceCode if code in recommended_set)

    return PreventionAssessment(
        risk_level=level,
        risk_score=score,
        factors=tuple(rule.factor for rule in fired),
        recommended_evidence=recommended,
        recommend_manual_review=level is PreventionRiskLevel.HIGH,
    )
