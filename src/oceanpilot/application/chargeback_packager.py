"""Representment packager agent (internal A2A step).

Looks up the target bank/network rule in the KnowledgeBase and assembles the
representment package deterministically — which evidence is included, in the
bank's template order, what's still missing, completeness, and the submission
window. The model only writes a cover note; it cannot change what is included or
its order. Application layer: depends on the KB + ModelProvider protocols only.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from oceanpilot.application.chargeback_agents import ExplanationSource
from oceanpilot.application.knowledge_base import BankRuleEntry, KnowledgeBase
from oceanpilot.application.model_output import json_text
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
    ChargebackEvidenceCode,
    DisputeReasonCode,
    assess_chargeback,
)
from oceanpilot.domain.evidence_catalog import (
    MATERIAL_REGISTRATION_BOUNDARY,
    has_unsupported_material_claim,
    label_of,
)
from oceanpilot.domain.reason_catalog import reason_label

_QUANT = Decimal("0.0001")
_PACKAGER_SYSTEM = (
    "Write a concise cover note for a chargeback representment package. Do NOT "
    "change evidence inclusion or order and never expose raw code tokens. Return "
    "ONLY valid JSON with exactly these fields: "
    '{"cover_note":"one Chinese paragraph",'
    '"included_evidence":["human-readable label"],'
    '"missing_evidence":["human-readable label"],'
    '"submission_boundary":"Chinese human-approval boundary"}. '
    "Only synthetic metadata is registered, not verified document contents. Never assert "
    "transaction authenticity, content consistency, delivery, liability shift, win probability, "
    "or automatic approval. The rule is an unverified synthetic summary, not an official "
    "submission basis. The window is an internal demo value, not an official deadline. "
    "Never claim any business action was taken."
)


def _labels(codes: tuple[ChargebackEvidenceCode, ...]) -> str:
    return "、".join(label_of(code) for code in codes) or "（无）"


def has_exact_rule(entry: BankRuleEntry) -> bool:
    """Only a complete versioned provenance link qualifies as a demo mapping."""
    return bool(
        entry.source != "default"
        and entry.rule_version_id
        and entry.scheme_reason_code
        and entry.source_document
        and entry.verification_status
        and entry.limitation
        and entry.submission_window_basis
    )


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
        """Explicitly compose a package and ask the model for its cover note."""
        entry, package = self._prepare(
            reason_code, present, bank_id=bank_id, card_network=card_network
        )
        if not has_exact_rule(entry) or not package.ready_to_submit:
            # An unmatched or incomplete preparation list gets deterministic
            # guidance, never a model-written formal representment rationale.
            return package
        note, source = self._cover_note(entry, package.ordered_evidence, package.missing_evidence)
        return replace(package, cover_note=note, cover_note_source=source)

    def preview(
        self,
        reason_code: DisputeReasonCode,
        present: Iterable[ChargebackEvidenceCode],
        *,
        bank_id: str | None = None,
        card_network: str | None = None,
    ) -> RepresentmentPackage:
        """Read the deterministic package from one rule lookup, without a model."""
        _, package = self._prepare(reason_code, present, bank_id=bank_id, card_network=card_network)
        return package

    def _prepare(
        self,
        reason_code: DisputeReasonCode,
        present: Iterable[ChargebackEvidenceCode],
        *,
        bank_id: str | None = None,
        card_network: str | None = None,
    ) -> tuple[BankRuleEntry, RepresentmentPackage]:
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

        internal = assess_chargeback(reason_code, present_set)
        return entry, RepresentmentPackage(
            reason_code=reason_code,
            bank_id=bank_id,
            card_network=card_network,
            ordered_evidence=ordered,
            missing_evidence=missing,
            submission_window_days=entry.submission_window_days,
            completeness=completeness,
            ready_to_submit=not missing and internal.ready_to_submit and has_exact_rule(entry),
            rule_source=entry.source,
            scheme_reason_code=entry.scheme_reason_code,
            rule_version=entry.rule_version,
            source_document=entry.source_document,
            source_section=entry.source_section,
            required_assertions=entry.required_assertions,
            rule_limitation=(
                entry.limitation
                if has_exact_rule(entry)
                else (
                    f"{entry.limitation or ''} "
                    "没有可追溯的精确规则映射；仅供内部材料准备，不可作为正式提交依据。"
                ).strip()
            ),
            rule_version_id=entry.rule_version_id,
            verification_status=entry.verification_status,
            submission_window_basis=entry.submission_window_basis,
            cover_note=_fallback_note(entry, ordered, missing, internal.missing_evidence),
            cover_note_source=ExplanationSource.FALLBACK,
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
            f"internal_demo_window_days={entry.submission_window_days}\n"
            "material_verification=METADATA_ONLY_CONTENT_UNVERIFIED"
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
        structured = json_text(text, "cover_note")
        if structured is not None:
            if has_unsupported_material_claim(structured):
                return _fallback_note(entry, ordered, missing), ExplanationSource.FALLBACK
            return structured, ExplanationSource.MODEL
        if text.startswith("{") or has_unsupported_material_claim(text):
            return _fallback_note(entry, ordered, missing), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL


def _fallback_note(
    entry: BankRuleEntry,
    ordered: tuple[ChargebackEvidenceCode, ...],
    missing: tuple[ChargebackEvidenceCode, ...],
    internal_missing: tuple[ChargebackEvidenceCode, ...] = (),
) -> str:
    reason = reason_label(entry.reason_code)
    match = (
        f"匹配 {entry.scheme_reason_code} 合成规则摘要（{entry.rule_version_id}），规则尚待核验"
        if has_exact_rule(entry)
        else "未匹配到可追溯的精确规则；当前仅为内部准备清单，默认模板不能作为正式依据"
    )
    gaps = tuple(dict.fromkeys((*internal_missing, *missing)))
    readiness = (
        f"仍缺 {len(gaps)} 项（{_labels(gaps)}），不能形成通过结论"
        if gaps
        else "登记清单齐备，等待人工复核"
    )
    return (
        f"合成材料预览（{reason}）：{match}。已登记 {len(ordered)} 项"
        f"（{_labels(ordered)}）；{readiness}。"
        f"{entry.submission_window_days} 天仅为内部演示窗口，并非官方响应期限。"
        f"{MATERIAL_REGISTRATION_BOUNDARY}"
    )
