"""Chargeback agent cluster (application layer).

Agents wrap the deterministic kernel: the decision (win likelihood, routing,
human-review flag) always comes from ``domain.chargeback``; the model only
writes a plain-language explanation. If the model is unavailable or empty, a
deterministic fallback explanation is used, so the agent never depends on a
model being reachable. Depends only on the ``ModelProvider`` protocol — no
vendor SDK, no adapter imports (kept clean by the import-boundary test).
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from oceanpilot.application.model_output import json_object, json_text
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
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.evidence_catalog import describe, request_sentence
from oceanpilot.domain.security import assert_no_sensitive_data

_ASSESS_SYSTEM = (
    "Explain a cross-border chargeback assessment that was already decided by a "
    "deterministic rule engine. Do NOT change evidence readiness, responsible_team, "
    "or requires_human. Return ONLY valid JSON with exactly these fields: "
    '{"operator_summary":"concise Chinese explanation",'
    '"missing_evidence":["human-readable item"],'
    '"next_action":"one concrete Chinese action",'
    '"human_review_note":"Chinese review boundary"}. '
    "This is synthetic data; never claim any business action was taken."
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
        structured = json_text(text, "operator_summary")
        if structured is not None:
            return structured, ExplanationSource.MODEL
        if text.startswith("{"):
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
        f"合成评估：规则证据就绪度 {percent}%（非胜诉概率），责任域 {a.responsible_team.value}，"
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
    "Classify a merchant's free-text card dispute. Return ONLY valid JSON with "
    "exactly these fields: "
    '{"reason_code":"one valid code",'
    '"confidence":0.0,'
    '"case_summary":"one neutral Chinese sentence",'
    '"needs_human_confirmation":true}. '
    "Valid reason_code values: "
    + ", ".join(c.value for c in DisputeReasonCode)
    + ". confidence must be between 0 and 1. Synthetic data only."
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


def _parse_intake_output(text: str) -> tuple[DisputeReasonCode, bool] | None:
    data = json_object(text)
    if data is None:
        return None
    raw_code = data.get("reason_code")
    confidence = data.get("confidence")
    needs_human = data.get("needs_human_confirmation")
    if not isinstance(raw_code, str) or isinstance(confidence, bool):
        return None
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return None
    if not isinstance(needs_human, bool):
        return None
    try:
        code = DisputeReasonCode(raw_code)
    except ValueError:
        return None
    return code, confidence >= 0.7 and not needs_human


def _heuristic_reason(text: str) -> DisputeReasonCode | None:
    lowered = text.lower()
    for keywords, code in _HEURISTICS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return code
    return None


@dataclass(frozen=True)
class CaseFacts:
    """Light, non-sensitive structured facts pulled from the free-text intake."""

    amount: str | None = None
    currency: str | None = None
    occurred_on: str | None = None
    summary: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any((self.amount, self.currency, self.occurred_on, self.summary))


_EMPTY_FACTS = CaseFacts()

_INTAKE_FACTS_SYSTEM = (
    "Extract non-sensitive structured facts from a merchant's dispute "
    "description and reply with ONLY a JSON object with keys: amount (numeric "
    "string or null), currency (ISO code or null), occurred_on (YYYY-MM-DD or "
    "null), summary (one neutral Chinese sentence or null). NEVER include card "
    "numbers, names, emails, phone numbers or any other PII. Synthetic data."
)


def _facts_field(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, bool):  # avoid bool-as-int surprises
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _parse_facts(raw: str) -> CaseFacts:
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return _EMPTY_FACTS
    if not isinstance(data, dict):
        return _EMPTY_FACTS
    facts = CaseFacts(
        amount=_facts_field(data, "amount"),
        currency=_facts_field(data, "currency"),
        occurred_on=_facts_field(data, "occurred_on"),
        summary=_facts_field(data, "summary"),
    )
    # Never surface anything the sensitive-data guard would reject.
    try:
        assert_no_sensitive_data(
            {
                "amount": facts.amount or "",
                "currency": facts.currency or "",
                "occurred_on": facts.occurred_on or "",
                "summary": facts.summary or "",
            }
        )
    except SensitiveDataRejected:
        return _EMPTY_FACTS
    return facts


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

    def extract_facts(self, text: str) -> CaseFacts:
        """Best-effort structured facts from the description; empty on any failure."""
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="chargeback_intake_facts",
                    security_tier=self._security_tier,
                    effort=self._effort,
                ),
                [ModelMessage(role=ModelRole.USER, content=text)],
                system=_INTAKE_FACTS_SYSTEM,
            )
        except ModelProviderError:
            return _EMPTY_FACTS
        return _parse_facts(result.text)

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
            structured = _parse_intake_output(result.text)
            if structured is not None:
                code, confident = structured
                return IntakeOutcome(
                    reason_code=code,
                    confident=confident,
                    source=ClassificationSource.MODEL,
                )
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
    "Ask a merchant for exactly one specified piece of chargeback evidence. "
    "Never expose the raw evidence_code or invent requirements. Return ONLY valid "
    "JSON with exactly these fields: "
    '{"question":"one or two concise Chinese sentences",'
    '"why":"concise Chinese reason",'
    '"accepted_examples":["human-readable example"],'
    '"safety_note":"Chinese reminder not to submit sensitive credentials"}. '
    "Synthetic data only."
)


def _fallback_question(code: ChargebackEvidenceCode, remaining: int) -> str:
    return request_sentence(code, remaining)


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
        display = describe(code)
        prompt = (
            f"reason_code={reason_code.value}\n"
            f"evidence_code={code.value}\n"
            f"evidence_label={display.label}\n"
            f"evidence_description={display.description}\n"
            f"why_it_matters={display.why}\n"
            f"examples={', '.join(display.examples)}\n"
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
        structured = json_text(text, "question")
        if structured is not None:
            return structured, ExplanationSource.MODEL
        if text.startswith("{"):
            return _fallback_question(code, remaining), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL


# --- Prevention agent: pre-dispute risk tip (design §6 ⑦) ------------------


@dataclass(frozen=True)
class PreventionOutcome:
    assessment: PreventionAssessment
    advice: str
    advice_source: ExplanationSource


_PREVENTION_SYSTEM = (
    "Explain a chargeback prevention decision already made by a deterministic "
    "engine. Do NOT change the risk level or invent factors. Return ONLY valid "
    "JSON with exactly these fields: "
    '{"advice":"concise Chinese merchant guidance",'
    '"risk_factors":["human-readable factor"],'
    '"evidence_to_retain":["human-readable evidence"],'
    '"manual_review_note":"Chinese manual-review boundary"}. '
    "Never block, hold, capture, or refund anything. Synthetic data only."
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
        structured = json_text(text, "advice")
        if structured is not None:
            return structured, ExplanationSource.MODEL
        if text.startswith("{"):
            return _prevention_fallback(assessment), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL
