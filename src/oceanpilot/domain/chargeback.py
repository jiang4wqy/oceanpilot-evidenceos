"""Deterministic chargeback (dispute) assessment.

This is the trustworthy kernel the Assess agent wraps: given a dispute reason
code and the evidence collected so far, it returns — deterministically, with no
LLM — the required-evidence checklist, what is present/missing, a synthetic
evidence-readiness score, the responsible team, the submission deadline, and whether the case
must go to human review. Agents propose; this decides.

Reason codes, evidence codes, and weights are **synthetic placeholders** modeled
on card-network dispute families. The tables are shaped so the company's real
reason codes, per-bank evidence templates, and weights can be dropped in later
without changing callers.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from types import MappingProxyType

from oceanpilot.domain.enums import ResponsibleTeam

_QUANT = Decimal("0.0001")
# Below this rule-based win likelihood, route to human review.
WIN_REVIEW_THRESHOLD = Decimal("0.60")
# Missing "critical" evidence gates the win likelihood by the fraction of
# critical evidence present: without your decisive proof you realistically
# cannot win, so a case that is weight-complete but missing a critical item
# must not read as high-confidence. Floored to a small non-zero value once any
# evidence exists (a bleak estimate, not an absolute 0%); with no evidence at
# all the likelihood stays exactly 0.
CRITICAL_MISSING_FLOOR = Decimal("0.05")


class DisputeReasonCode(StrEnum):
    FRAUD_CARD_NOT_PRESENT = "FRAUD_CARD_NOT_PRESENT"
    PRODUCT_NOT_RECEIVED = "PRODUCT_NOT_RECEIVED"
    PRODUCT_NOT_AS_DESCRIBED = "PRODUCT_NOT_AS_DESCRIBED"
    DUPLICATE_PROCESSING = "DUPLICATE_PROCESSING"
    CREDIT_NOT_PROCESSED = "CREDIT_NOT_PROCESSED"
    SUBSCRIPTION_CANCELED = "SUBSCRIPTION_CANCELED"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"


class ChargebackEvidenceCode(StrEnum):
    TRANSACTION_RECEIPT = "transaction.receipt"
    AVS_RESULT = "auth.avs_result"
    CVV_RESULT = "auth.cvv_result"
    THREEDS_AUTHENTICATION = "auth.threeds"
    DEVICE_OR_IP_MATCH = "auth.device_ip_match"
    DELIVERY_TRACKING = "fulfillment.tracking"
    PROOF_OF_DELIVERY = "fulfillment.proof_of_delivery"
    SHIPPING_ADDRESS_MATCH = "fulfillment.address_match"
    PRODUCT_DESCRIPTION = "product.description"
    REFUND_RECORD = "billing.refund_record"
    TERMS_AND_REFUND_POLICY = "policy.terms_refund"
    CUSTOMER_COMMUNICATION = "comms.customer"
    CANCELLATION_RECORD = "subscription.cancellation_record"
    PRIOR_TRANSACTION_HISTORY = "history.prior_transactions"
    DUPLICATE_CHECK = "billing.duplicate_check"


class ChargebackReviewReason(StrEnum):
    HIGH_RISK_CATEGORY = "HIGH_RISK_CATEGORY"
    MISSING_CRITICAL_EVIDENCE = "MISSING_CRITICAL_EVIDENCE"
    LOW_WIN_LIKELIHOOD = "LOW_WIN_LIKELIHOOD"


@dataclass(frozen=True)
class _Requirement:
    code: ChargebackEvidenceCode
    weight: int
    critical: bool


@dataclass(frozen=True)
class _ReasonPolicy:
    required: tuple[_Requirement, ...]
    responsible_team: ResponsibleTeam
    default_deadline_days: int
    high_risk: bool


def _req(code: ChargebackEvidenceCode, weight: int, *, critical: bool = False) -> _Requirement:
    return _Requirement(code=code, weight=weight, critical=critical)


_C = ChargebackEvidenceCode
_R = DisputeReasonCode

_POLICIES: dict[DisputeReasonCode, _ReasonPolicy] = MappingProxyType(
    {
        _R.FRAUD_CARD_NOT_PRESENT: _ReasonPolicy(
            required=(
                _req(_C.TRANSACTION_RECEIPT, 2, critical=True),
                _req(_C.THREEDS_AUTHENTICATION, 3, critical=True),
                _req(_C.AVS_RESULT, 2),
                _req(_C.CVV_RESULT, 2),
                _req(_C.DEVICE_OR_IP_MATCH, 2),
                _req(_C.PRIOR_TRANSACTION_HISTORY, 1),
            ),
            responsible_team=ResponsibleTeam.RISK,
            default_deadline_days=15,
            high_risk=True,
        ),
        _R.PRODUCT_NOT_RECEIVED: _ReasonPolicy(
            required=(
                _req(_C.TRANSACTION_RECEIPT, 1),
                _req(_C.DELIVERY_TRACKING, 3, critical=True),
                _req(_C.PROOF_OF_DELIVERY, 3, critical=True),
                _req(_C.SHIPPING_ADDRESS_MATCH, 2),
                _req(_C.CUSTOMER_COMMUNICATION, 1),
            ),
            responsible_team=ResponsibleTeam.CUSTOMER_SUPPORT,
            default_deadline_days=15,
            high_risk=False,
        ),
        _R.PRODUCT_NOT_AS_DESCRIBED: _ReasonPolicy(
            required=(
                _req(_C.TRANSACTION_RECEIPT, 1),
                _req(_C.PRODUCT_DESCRIPTION, 3, critical=True),
                _req(_C.CUSTOMER_COMMUNICATION, 2),
                _req(_C.TERMS_AND_REFUND_POLICY, 2),
                _req(_C.PROOF_OF_DELIVERY, 1),
            ),
            responsible_team=ResponsibleTeam.BUSINESS,
            default_deadline_days=15,
            high_risk=False,
        ),
        _R.DUPLICATE_PROCESSING: _ReasonPolicy(
            required=(
                _req(_C.TRANSACTION_RECEIPT, 2, critical=True),
                _req(_C.DUPLICATE_CHECK, 3, critical=True),
                _req(_C.PRIOR_TRANSACTION_HISTORY, 2),
            ),
            responsible_team=ResponsibleTeam.TECHNICAL_SUPPORT,
            default_deadline_days=15,
            high_risk=False,
        ),
        _R.CREDIT_NOT_PROCESSED: _ReasonPolicy(
            required=(
                _req(_C.TRANSACTION_RECEIPT, 1),
                _req(_C.REFUND_RECORD, 3, critical=True),
                _req(_C.TERMS_AND_REFUND_POLICY, 2),
                _req(_C.CUSTOMER_COMMUNICATION, 1),
            ),
            responsible_team=ResponsibleTeam.FINANCE,
            default_deadline_days=15,
            high_risk=False,
        ),
        _R.SUBSCRIPTION_CANCELED: _ReasonPolicy(
            required=(
                _req(_C.TRANSACTION_RECEIPT, 1),
                _req(_C.CANCELLATION_RECORD, 3, critical=True),
                _req(_C.TERMS_AND_REFUND_POLICY, 2),
                _req(_C.CUSTOMER_COMMUNICATION, 2),
            ),
            responsible_team=ResponsibleTeam.CUSTOMER_SUPPORT,
            default_deadline_days=15,
            high_risk=False,
        ),
        _R.AUTHORIZATION_ERROR: _ReasonPolicy(
            required=(
                _req(_C.TRANSACTION_RECEIPT, 2, critical=True),
                _req(_C.AVS_RESULT, 2),
                _req(_C.CVV_RESULT, 2),
                _req(_C.THREEDS_AUTHENTICATION, 2),
            ),
            responsible_team=ResponsibleTeam.PSP_SUPPORT,
            default_deadline_days=15,
            high_risk=False,
        ),
    }
)


@dataclass(frozen=True)
class EvidenceContribution:
    """One required-evidence item and its role in the win-likelihood decision."""

    code: ChargebackEvidenceCode
    weight: int
    critical: bool
    present: bool


@dataclass(frozen=True)
class ChargebackAssessment:
    reason_code: DisputeReasonCode
    required_evidence: tuple[ChargebackEvidenceCode, ...]
    present_evidence: tuple[ChargebackEvidenceCode, ...]
    missing_evidence: tuple[ChargebackEvidenceCode, ...]
    missing_critical: tuple[ChargebackEvidenceCode, ...]
    completeness: Decimal
    # Legacy name retained for compatibility. This is a synthetic rule-weight
    # readiness score and must not be presented as a real-world win probability.
    win_likelihood: Decimal
    responsible_team: ResponsibleTeam
    default_deadline_days: int
    ready_to_submit: bool
    requires_human: bool
    review_reasons: tuple[ChargebackReviewReason, ...]
    # Per-item breakdown behind win_likelihood (why the number is what it is).
    evidence_breakdown: tuple[EvidenceContribution, ...] = ()


def required_evidence_for(reason_code: DisputeReasonCode) -> tuple[ChargebackEvidenceCode, ...]:
    """The ordered required-evidence checklist for a reason code."""
    return tuple(r.code for r in _policy(reason_code).required)


def assess_chargeback(
    reason_code: DisputeReasonCode,
    present: Iterable[ChargebackEvidenceCode],
) -> ChargebackAssessment:
    policy = _policy(reason_code)
    present_set = set(present)

    total_weight = sum(r.weight for r in policy.required)
    present_weight = sum(r.weight for r in policy.required if r.code in present_set)

    present_required = tuple(r.code for r in policy.required if r.code in present_set)
    missing = tuple(r.code for r in policy.required if r.code not in present_set)
    missing_critical = tuple(
        r.code for r in policy.required if r.critical and r.code not in present_set
    )

    required_count = len(policy.required)
    completeness = (Decimal(len(present_required)) / Decimal(required_count)).quantize(
        _QUANT, rounding=ROUND_HALF_UP
    )

    # Critical-evidence gate: scale the raw weighted ratio by how much of the
    # decisive (critical) evidence is present, so a case missing a critical item
    # never reads as high-confidence even if its total weight is high.
    critical_required = [r for r in policy.required if r.critical]
    if critical_required:
        present_critical = sum(1 for r in critical_required if r.code in present_set)
        critical_ratio = Decimal(present_critical) / Decimal(len(critical_required))
    else:
        critical_ratio = Decimal(1)
    raw_ratio = Decimal(present_weight) / Decimal(total_weight)
    gated = raw_ratio * critical_ratio
    if present_weight > 0 and critical_ratio < 1:
        gated = max(gated, CRITICAL_MISSING_FLOOR)
    win_likelihood = gated.quantize(_QUANT, rounding=ROUND_HALF_UP)

    reasons: list[ChargebackReviewReason] = []
    if policy.high_risk:
        reasons.append(ChargebackReviewReason.HIGH_RISK_CATEGORY)
    if missing_critical:
        reasons.append(ChargebackReviewReason.MISSING_CRITICAL_EVIDENCE)
    if win_likelihood < WIN_REVIEW_THRESHOLD:
        reasons.append(ChargebackReviewReason.LOW_WIN_LIKELIHOOD)

    breakdown = tuple(
        EvidenceContribution(
            code=r.code,
            weight=r.weight,
            critical=r.critical,
            present=r.code in present_set,
        )
        for r in policy.required
    )

    return ChargebackAssessment(
        reason_code=reason_code,
        required_evidence=tuple(r.code for r in policy.required),
        present_evidence=present_required,
        missing_evidence=missing,
        missing_critical=missing_critical,
        completeness=completeness,
        win_likelihood=win_likelihood,
        responsible_team=policy.responsible_team,
        default_deadline_days=policy.default_deadline_days,
        ready_to_submit=not missing,
        requires_human=bool(reasons),
        review_reasons=tuple(reasons),
        evidence_breakdown=breakdown,
    )


def _policy(reason_code: DisputeReasonCode) -> _ReasonPolicy:
    if type(reason_code) is not DisputeReasonCode:
        raise TypeError("reason_code must be a DisputeReasonCode")
    return _POLICIES[reason_code]
