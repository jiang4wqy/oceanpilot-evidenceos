"""Chargeback agent cluster (application layer).

Agents wrap the deterministic kernel: the decision (win likelihood, routing,
human-review flag) always comes from ``domain.chargeback``; the model only
writes a plain-language explanation. If the model is unavailable or empty, a
deterministic fallback explanation is used, so the agent never depends on a
model being reachable. Depends only on the ``ModelProvider`` protocol — no
vendor SDK, no adapter imports (kept clean by the import-boundary test).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from oceanpilot.application.model_provider import (
    Effort,
    ModelMessage,
    ModelProvider,
    ModelProviderError,
    ModelRole,
    SecurityTier,
    TaskSpec,
)
from oceanpilot.domain.chargeback import (
    ChargebackAssessment,
    ChargebackEvidenceCode,
    DisputeReasonCode,
    assess_chargeback,
)
from oceanpilot.domain.chargeback_prevention import (
    PreventionAssessment,
    PreventionRiskLevel,
    PreventionSignals,
    assess_chargeback_risk,
)

_ASSESS_SYSTEM = (
    "You explain a cross-border chargeback representment assessment to an "
    "operator, in plain language. You are given a decision that was already made "
    "by a deterministic rule engine. Do NOT change the win likelihood, the "
    "responsible team, or whether human review is required — only explain them, "
    "state which evidence is still missing, and give the single next step. Be "
    "concise. This is synthetic data; never claim any business action was taken."
)


class ExplanationSource(StrEnum):
    MODEL = "MODEL"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True)
class AssessOutcome:
    assessment: ChargebackAssessment
    explanation: str
    explanation_source: ExplanationSource


class ChargebackAssessAgent:
    def __init__(
        self,
        model: ModelProvider,
        *,
        security_tier: SecurityTier = SecurityTier.LOW,
        effort: Effort = Effort.MEDIUM,
    ) -> None:
        self._model = model
        self._security_tier = security_tier
        self._effort = effort

    def assess(
        self,
        reason_code: DisputeReasonCode,
        present_evidence: Iterable[ChargebackEvidenceCode],
    ) -> AssessOutcome:
        # Deterministic kernel decides; the model never overrides it.
        assessment = assess_chargeback(reason_code, present_evidence)
        explanation, source = self._explain(assessment)
        return AssessOutcome(
            assessment=assessment,
            explanation=explanation,
            explanation_source=source,
        )

    def _explain(self, assessment: ChargebackAssessment) -> tuple[str, ExplanationSource]:
        facts = _facts(assessment)
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="chargeback_assess_explanation",
                    security_tier=self._security_tier,
                    effort=self._effort,
                ),
                [ModelMessage(role=ModelRole.USER, content=facts)],
                system=_ASSESS_SYSTEM,
            )
        except ModelProviderError:
            return _fallback(assessment), ExplanationSource.FALLBACK
        text = result.text.strip()
        if not text:
            return _fallback(assessment), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL


def _facts(a: ChargebackAssessment) -> str:
    def codes(items: Sequence[ChargebackEvidenceCode]) -> str:
        return ", ".join(c.value for c in items) or "(none)"

    return (
        f"reason_code={a.reason_code.value}\n"
        f"win_likelihood={a.win_likelihood}\n"
        f"completeness={a.completeness}\n"
        f"responsible_team={a.responsible_team.value}\n"
        f"deadline_days={a.default_deadline_days}\n"
        f"ready_to_submit={a.ready_to_submit}\n"
        f"requires_human={a.requires_human}\n"
        f"present_evidence={codes(a.present_evidence)}\n"
        f"missing_evidence={codes(a.missing_evidence)}\n"
        f"missing_critical={codes(a.missing_critical)}\n"
        f"review_reasons={', '.join(r.value for r in a.review_reasons) or '(none)'}"
    )


def _fallback(a: ChargebackAssessment) -> str:
    percent = int(a.win_likelihood * 100)
    if a.missing_critical:
        missing = "、".join(c.value for c in a.missing_critical)
        nxt = f"补齐关键证据：{missing}"
    elif not a.ready_to_submit:
        missing = "、".join(c.value for c in a.missing_evidence)
        nxt = f"补齐证据：{missing}"
    else:
        nxt = "证据齐备，等待人工确认后打包提交" if a.requires_human else "证据齐备，可进入打包"
    review = "需人工复核" if a.requires_human else "可自动推进"
    return (
        f"合成评估：预计胜诉可能性约 {percent}%，责任域 {a.responsible_team.value}，"
        f"{review}。下一步：{nxt}。（{a.default_deadline_days} 天举证时限）"
    )


# --- Intake agent: free-text description -> dispute reason code -------------


class ClassificationSource(StrEnum):
    MODEL = "MODEL"
    HEURISTIC = "HEURISTIC"


@dataclass(frozen=True)
class IntakeOutcome:
    reason_code: DisputeReasonCode
    confident: bool
    source: ClassificationSource


_INTAKE_SYSTEM = (
    "You classify a merchant's free-text description of a card dispute into "
    "exactly one reason code. Reply with ONLY the code token, nothing else. "
    "Valid codes: " + ", ".join(c.value for c in DisputeReasonCode) + ". "
    "This is synthetic data."
)

# ordered keyword heuristics (Chinese + English); first match wins.
_HEURISTICS: tuple[tuple[tuple[str, ...], DisputeReasonCode], ...] = (
    (
        ("未收到", "没收到", "没到", "未送达", "not received", "never arrived"),
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
    ),
    (
        ("不对板", "不符", "描述不符", "假货", "not as described", "wrong item"),
        DisputeReasonCode.PRODUCT_NOT_AS_DESCRIBED,
    ),
    (
        ("重复", "扣了两次", "两笔", "duplicate", "charged twice"),
        DisputeReasonCode.DUPLICATE_PROCESSING,
    ),
    (
        ("退款", "没退", "未退", "refund", "credit not"),
        DisputeReasonCode.CREDIT_NOT_PROCESSED,
    ),
    (
        ("订阅", "会员", "recurring", "subscription", "cancel"),
        DisputeReasonCode.SUBSCRIPTION_CANCELED,
    ),
    (
        ("欺诈", "盗刷", "未授权", "不是我", "fraud", "unauthorized"),
        DisputeReasonCode.FRAUD_CARD_NOT_PRESENT,
    ),
    (
        ("授权", "处理错误", "authorization", "processing error"),
        DisputeReasonCode.AUTHORIZATION_ERROR,
    ),
)

_DEFAULT_REASON = DisputeReasonCode.AUTHORIZATION_ERROR


def _parse_reason(text: str) -> DisputeReasonCode | None:
    upper = text.upper()
    for code in DisputeReasonCode:
        if code.value in upper:
            return code
    return None


def _heuristic_reason(text: str) -> DisputeReasonCode | None:
    lowered = text.lower()
    for keywords, code in _HEURISTICS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return code
    return None


class IntakeAgent:
    def __init__(
        self,
        model: ModelProvider,
        *,
        security_tier: SecurityTier = SecurityTier.MEDIUM,
        effort: Effort = Effort.LOW,
    ) -> None:
        self._model = model
        self._security_tier = security_tier
        self._effort = effort

    def classify(self, text: str) -> IntakeOutcome:
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="chargeback_intake",
                    security_tier=self._security_tier,
                    effort=self._effort,
                ),
                [ModelMessage(role=ModelRole.USER, content=text)],
                system=_INTAKE_SYSTEM,
            )
        except ModelProviderError:
            result = None
        if result is not None:
            code = _parse_reason(result.text)
            if code is not None:
                return IntakeOutcome(
                    reason_code=code, confident=True, source=ClassificationSource.MODEL
                )
        heuristic = _heuristic_reason(text)
        if heuristic is not None:
            return IntakeOutcome(
                reason_code=heuristic,
                confident=True,
                source=ClassificationSource.HEURISTIC,
            )
        return IntakeOutcome(
            reason_code=_DEFAULT_REASON,
            confident=False,
            source=ClassificationSource.HEURISTIC,
        )


# --- Evidence agent: next missing-evidence question ------------------------


@dataclass(frozen=True)
class EvidenceRequest:
    reason_code: DisputeReasonCode
    complete: bool
    next_evidence: ChargebackEvidenceCode | None
    missing: tuple[ChargebackEvidenceCode, ...]
    question: str
    question_source: ExplanationSource


_EVIDENCE_SYSTEM = (
    "You ask a merchant, in one concise Chinese sentence, to provide exactly "
    "one specified piece of chargeback evidence. Ask only for the given "
    "evidence code; do not invent new requirements. Synthetic data."
)


def _fallback_question(code: ChargebackEvidenceCode, remaining: int) -> str:
    return f"请补充证据：{code.value}（还差 {remaining} 项）。"


class EvidenceAgent:
    def __init__(
        self,
        model: ModelProvider,
        *,
        security_tier: SecurityTier = SecurityTier.LOW,
        effort: Effort = Effort.LOW,
    ) -> None:
        self._model = model
        self._security_tier = security_tier
        self._effort = effort

    def next_request(
        self,
        reason_code: DisputeReasonCode,
        present: Iterable[ChargebackEvidenceCode],
    ) -> EvidenceRequest:
        assessment = assess_chargeback(reason_code, present)
        if assessment.ready_to_submit:
            return EvidenceRequest(
                reason_code=reason_code,
                complete=True,
                next_evidence=None,
                missing=(),
                question="证据已齐备，可进入胜诉评估。",
                question_source=ExplanationSource.FALLBACK,
            )
        next_code = (
            assessment.missing_critical[0]
            if assessment.missing_critical
            else assessment.missing_evidence[0]
        )
        question, source = self._ask(reason_code, next_code, len(assessment.missing_evidence))
        return EvidenceRequest(
            reason_code=reason_code,
            complete=False,
            next_evidence=next_code,
            missing=assessment.missing_evidence,
            question=question,
            question_source=source,
        )

    def _ask(
        self,
        reason_code: DisputeReasonCode,
        code: ChargebackEvidenceCode,
        remaining: int,
    ) -> tuple[str, ExplanationSource]:
        prompt = (
            f"reason_code={reason_code.value}\n"
            f"evidence_code={code.value}\n"
            f"remaining_missing={remaining}"
        )
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="chargeback_evidence_question",
                    security_tier=self._security_tier,
                    effort=self._effort,
                ),
                [ModelMessage(role=ModelRole.USER, content=prompt)],
                system=_EVIDENCE_SYSTEM,
            )
        except ModelProviderError:
            return _fallback_question(code, remaining), ExplanationSource.FALLBACK
        text = result.text.strip()
        if not text:
            return _fallback_question(code, remaining), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL


# --- Prevention agent: pre-dispute risk tip (design §6 ⑦) ------------------


@dataclass(frozen=True)
class PreventionOutcome:
    assessment: PreventionAssessment
    advice: str
    advice_source: ExplanationSource


_PREVENTION_SYSTEM = (
    "You warn a merchant, in plain Chinese, that a transaction has an elevated "
    "chargeback risk and tell them which evidence to keep now so they can win a "
    "future dispute. You are given a risk decision already made by a "
    "deterministic engine — do NOT change the risk level or invent new factors, "
    "only explain them and list the evidence to retain. You never block, hold, "
    "capture, or refund anything; the strongest action is advising a manual "
    "review. Be concise. Synthetic data; never claim any action was executed."
)

_RISK_LABELS = {
    PreventionRiskLevel.LOW: "低",
    PreventionRiskLevel.MEDIUM: "中",
    PreventionRiskLevel.HIGH: "高",
}


def _prevention_facts(a: PreventionAssessment) -> str:
    factors = ", ".join(f.value for f in a.factors) or "(none)"
    evidence = ", ".join(c.value for c in a.recommended_evidence) or "(none)"
    return (
        f"risk_level={a.risk_level.value}\n"
        f"risk_score={a.risk_score}\n"
        f"risk_factors={factors}\n"
        f"recommend_manual_review={a.recommend_manual_review}\n"
        f"recommended_evidence={evidence}"
    )


def _prevention_fallback(a: PreventionAssessment) -> str:
    label = _RISK_LABELS[a.risk_level]
    if a.risk_level is PreventionRiskLevel.LOW or not a.recommended_evidence:
        return f"合成风险提示：拒付风险{label}，暂无需额外留证。"
    evidence = "、".join(c.value for c in a.recommended_evidence)
    review = "，建议人工复核后再放行" if a.recommend_manual_review else ""
    return f"合成风险提示：拒付风险{label}{review}。建议现在留存证据：{evidence}。"


class PreventionAgent:
    """Pre-dispute risk assistant: deterministic kernel decides, model advises.

    Takes synthetic transaction signals directly (the channel/composition layer
    fetches them via a ``SignalSource``); the kernel decides the risk level and
    which evidence to keep, and the model only phrases the merchant-facing tip
    with a deterministic fallback. Purely advisory — it never acts on a payment.
    """

    def __init__(
        self,
        model: ModelProvider,
        *,
        security_tier: SecurityTier = SecurityTier.LOW,
        effort: Effort = Effort.LOW,
    ) -> None:
        self._model = model
        self._security_tier = security_tier
        self._effort = effort

    def assess(self, signals: PreventionSignals) -> PreventionOutcome:
        assessment = assess_chargeback_risk(signals)
        advice, source = self._advise(assessment)
        return PreventionOutcome(
            assessment=assessment,
            advice=advice,
            advice_source=source,
        )

    def _advise(self, assessment: PreventionAssessment) -> tuple[str, ExplanationSource]:
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="chargeback_prevention_advice",
                    security_tier=self._security_tier,
                    effort=self._effort,
                ),
                [ModelMessage(role=ModelRole.USER, content=_prevention_facts(assessment))],
                system=_PREVENTION_SYSTEM,
            )
        except ModelProviderError:
            return _prevention_fallback(assessment), ExplanationSource.FALLBACK
        text = result.text.strip()
        if not text:
            return _prevention_fallback(assessment), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL
