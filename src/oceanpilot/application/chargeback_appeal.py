"""Appeal / representment drafting agent.

Drafts the appeal letter from a packaged representment (model, with a
deterministic fallback) and submits to the upstream channel **only** behind a
hard human-approval gate and only when the package is complete. Without approval
it returns the draft and does not touch the connector. Application layer:
depends on the ModelProvider and UpstreamConnector protocols only.
"""

from dataclasses import dataclass
from enum import StrEnum

from oceanpilot.application.chargeback_agents import ExplanationSource
from oceanpilot.application.chargeback_packager import RepresentmentPackage
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
from oceanpilot.application.upstream import UpstreamConnector
from oceanpilot.domain.evidence_catalog import label_of, rebuttal_line
from oceanpilot.domain.reason_catalog import reason_label

_APPEAL_SYSTEM = (
    "Draft a structured Chinese chargeback representment letter from the enclosed "
    "package. Use only listed evidence, invent nothing, and never expose raw code "
    "tokens. Return ONLY valid JSON with exactly these fields: "
    '{"draft":"structured Chinese letter",'
    '"claims":["claim supported by the package"],'
    '"evidence_references":["human-readable evidence label"],'
    '"disclaimer":"Chinese synthetic and human-approval boundary"}. '
    "Never claim any business action was taken."
)


class AppealBlockedReason(StrEnum):
    NOT_READY = "NOT_READY"
    NOT_APPROVED = "NOT_APPROVED"


@dataclass(frozen=True)
class AppealOutcome:
    draft: str
    draft_source: ExplanationSource
    submitted: bool
    submission_id: str | None
    status: str | None
    blocked_reason: AppealBlockedReason | None


class AppealAgent:
    def __init__(
        self,
        model: ModelProvider,
        upstream: UpstreamConnector,
        *,
        security_tier: SecurityTier = SecurityTier.LOW,
        effort: Effort = Effort.MEDIUM,
    ) -> None:
        self._model = model
        self._upstream = upstream
        self._security_tier = security_tier
        self._effort = effort

    def draft(self, package: RepresentmentPackage) -> tuple[str, ExplanationSource]:
        included = "; ".join(rebuttal_line(c) for c in package.ordered_evidence) or "(none)"
        prompt = (
            f"reason={reason_label(package.reason_code)}\n"
            f"bank_id={package.bank_id or '(any)'}\n"
            f"card_network={package.card_network or '(any)'}\n"
            f"included={included}\n"
            f"window_days={package.submission_window_days}"
        )
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="chargeback_appeal_draft",
                    security_tier=self._security_tier,
                    effort=self._effort,
                ),
                [ModelMessage(role=ModelRole.USER, content=prompt)],
                system=_APPEAL_SYSTEM,
            )
        except ModelProviderError:
            return _fallback_letter(package), ExplanationSource.FALLBACK
        text = result.text.strip()
        if not text:
            return _fallback_letter(package), ExplanationSource.FALLBACK
        structured = json_text(text, "draft")
        if structured is not None:
            return structured, ExplanationSource.MODEL
        if text.startswith("{"):
            return _fallback_letter(package), ExplanationSource.FALLBACK
        return text, ExplanationSource.MODEL

    def submit(
        self,
        package: RepresentmentPackage,
        *,
        human_approved: bool,
        actor_id: str,
    ) -> AppealOutcome:
        draft, source = self.draft(package)

        if not package.ready_to_submit:
            return _blocked(draft, source, AppealBlockedReason.NOT_READY)
        if not human_approved:
            # Hard gate: no upstream call without an explicit human approval.
            return _blocked(draft, source, AppealBlockedReason.NOT_APPROVED)

        receipt = self._upstream.submit(
            reference=f"{package.reason_code.value}:{package.bank_id or 'any'}",
            payload={
                "reason_code": package.reason_code.value,
                "evidence": [c.value for c in package.ordered_evidence],
                "approved_by": actor_id,
                "synthetic": True,
            },
        )
        return AppealOutcome(
            draft=draft,
            draft_source=source,
            submitted=True,
            submission_id=receipt.submission_id,
            status=receipt.status.value,
            blocked_reason=None,
        )


def _blocked(draft: str, source: ExplanationSource, reason: AppealBlockedReason) -> AppealOutcome:
    return AppealOutcome(
        draft=draft,
        draft_source=source,
        submitted=False,
        submission_id=None,
        status=None,
        blocked_reason=reason,
    )


def _fallback_letter(package: RepresentmentPackage) -> str:
    """Deterministic, structured representment letter (used when no model runs)."""
    reason = reason_label(package.reason_code)
    recipient = package.card_network or "受理机构"
    if package.ordered_evidence:
        enclosed = "\n".join(
            f"{index}. {rebuttal_line(code)}"
            for index, code in enumerate(package.ordered_evidence, start=1)
        )
    else:
        enclosed = "（暂无随附证据）"

    sections = [
        "拒付申诉说明（合成样例，非真实提交）",
        f"争议原因：{reason}",
        f"受理方：{recipient}",
        f"举证时限：{package.submission_window_days} 天内",
        "一、申诉立场\n我方就上述争议提交举证，随附以下证据，证明交易真实且商户已依约履行：",
        f"二、随附证据（按受理方模板顺序）\n{enclosed}",
    ]
    if package.missing_evidence:
        missing = "、".join(label_of(code) for code in package.missing_evidence)
        sections.append(f"三、尚缺证据（提交前需补齐或书面说明）\n{missing}")
    sections.append("结论\n基于上述证据，恳请受理方在举证窗口内予以复核并驳回本次拒付。")
    sections.append(
        "（本内容为合成数据；系统不执行任何支付/退款/风控/提交动作，最终以人工确认为准。）"
    )
    return "\n\n".join(sections)
