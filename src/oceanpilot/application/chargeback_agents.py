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
