"""Representment packager agent (internal A2A step).

Looks up the target bank/network rule in the KnowledgeBase and assembles the
representment package deterministically — which evidence is included, in the
bank's template order, what's still missing, completeness, and the submission
window. The model only writes a cover note; it cannot change what is included or
its order. Application layer: depends on the KB + ModelProvider protocols only.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from oceanpilot.application.chargeback_agents import ExplanationSource
from oceanpilot.application.knowledge_base import BankRuleEntry, KnowledgeBase
from oceanpilot.application.model_provider import (
    Effort,
    ModelMessage,
    ModelProvider,
    ModelProviderError,
    ModelRole,
    SecurityTier,
    TaskSpec,
)
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode
from oceanpilot.domain.evidence_catalog import label_of
from oceanpilot.domain.reason_catalog import reason_label

_QUANT = Decimal("0.0001")
_PACKAGER_SYSTEM = (
    "You write a one-paragraph cover note for a chargeback representment "
    "package. Do NOT change which evidence is included or its order; only "
    "summarize what is enclosed and what is missing, using the human labels "
    "provided (never a raw code token). Be concise. Synthetic data; never claim "
    "any business action was taken."
)


def _labels(codes: tuple[ChargebackEvidenceCode, ...]) -> str:
    return "、".join(label_of(code) for code in codes) or "（无）"


@dataclass(frozen=True)
class RepresentmentPackage:
    reason_code: DisputeReasonCode
    bank_id: str | None
    card_network: str | None
    ordered_evidence: tuple[ChargebackEvidenceCode, ...]
    missing_evidence: tuple[ChargebackEvidenceCode, ...]
    submission_window_days: int
    completeness: Decimal
    ready_to_submit: bool
    rule_source: str
    cover_note: str
    cover_note_source: ExplanationSource
    scheme_reason_code: str | None = None
    rule_version: str | None = None
    source_document: str | None = None
    source_section: str | None = None
    required_assertions: tuple[str, ...] = ()
    rule_limitation: str | None = None
    rule_version_id: str | None = None
    verification_status: str | None = None
    submission_window_basis: str | None = None


class PackagerAgent:
    def __init__(
        self,
        model: ModelProvider,
        knowledge_base: KnowledgeBase,
        *,
        security_tier: SecurityTier = SecurityTier.LOW,
        effort: Effort = Effort.LOW,
    ) -> None:
        self._model = model
        self._kb = knowledge_base
        self._security_tier = security_tier
        self._effort = effort

    def build(
        self,
        reason_code: DisputeReasonCode,
        present: Iterable[ChargebackEvidenceCode],
        *,
        bank_id: str | None = None,
        card_network: str | None = None,
    ) -> RepresentmentPackage:
        entry = self._kb.lookup(reason_code, bank_id=bank_id, card_network=card_network)
        present_set = set(present)
        ordered = tuple(c for c in entry.template_order if c in present_set)
        missing = tuple(c for c in entry.required_evidence if c not in present_set)

        total = len(entry.required_evidence)
        have = sum(1 for c in entry.required_evidence if c in present_set)
        completeness = (
            (Decimal(have) / Decimal(total)).quantize(_QUANT, rounding=ROUND_HALF_UP)
            if total
            else Decimal("1.0000")
        )

        note, source = self._cover_note(entry, ordered, missing)
        return RepresentmentPackage(
            reason_code=reason_code,
            bank_id=bank_id,
            card_network=card_network,
            ordered_evidence=ordered,
            missing_evidence=missing,
            submission_window_days=entry.submission_window_days,
            completeness=completeness,
            ready_to_submit=not missing,
            rule_source=entry.source,
            scheme_reason_code=entry.scheme_reason_code,
            rule_version=entry.rule_version,
            source_document=entry.source_document,
            source_section=entry.source_section,
            required_assertions=entry.required_assertions,
            rule_limitation=entry.limitation,
            rule_version_id=entry.rule_version_id,
            verification_status=entry.verification_status,
            submission_window_basis=entry.submission_window_basis,
            cover_note=note,
            cover_note_source=source,
        )

    def _cover_note(
        self,
        entry: BankRuleEntry,
        ordered: tuple[ChargebackEvidenceCode, ...],
        missing: tuple[ChargebackEvidenceCode, ...],
    ) -> tuple[str, ExplanationSource]:
        prompt = (
            f"reason={reason_label(entry.reason_code)}\n"
            f"rule_source={entry.source}\n"
            f"included={_labels(ordered)}\n"
            f"missing={_labels(missing)}\n"
            f"window_days={entry.submission_window_days}"
        )
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="chargeback_packager_cover",
                    security_tier=self._security_tier,
                    effort=self._effort,
                ),
                [ModelMessage(role=ModelRole.USER, content=prompt)],
                system=_PACKAGER_SYSTEM,
            )
        except ModelProviderError:
            return _fallback_note(entry, ordered, missing), ExplanationSource.FALLBACK
        text = result.text.strip()
        if not text:
            return _fallback_note(entry, ordered, missing), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL


def _fallback_note(
    entry: BankRuleEntry,
    ordered: tuple[ChargebackEvidenceCode, ...],
    missing: tuple[ChargebackEvidenceCode, ...],
) -> str:
    reason = reason_label(entry.reason_code)
    if missing:
        return (
            f"合成打包（{entry.source} 规则，{reason}）：已含 {len(ordered)} 项证据"
            f"（{_labels(ordered)}），仍缺 {len(missing)} 项（{_labels(missing)}）；"
            f"补齐后在 {entry.submission_window_days} 天窗口内提交。"
        )
    return (
        f"合成打包（{entry.source} 规则，{reason}）：{len(ordered)} 项证据已按模板顺序就绪"
        f"（{_labels(ordered)}），可在 {entry.submission_window_days} 天窗口内提交"
        "（需人工确认，不执行业务动作）。"
    )
