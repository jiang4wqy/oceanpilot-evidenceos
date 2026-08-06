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

_APPEAL_SYSTEM = (
    "You draft a concise Chinese chargeback representment appeal letter from the "
    "enclosed package. Use only the listed evidence; invent nothing. Synthetic "
    "data; never claim any business action was taken."
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
        prompt = (
            f"reason={package.reason_code.value}\n"
            f"bank_id={package.bank_id or '(any)'}\n"
            f"card_network={package.card_network or '(any)'}\n"
            f"included={', '.join(c.value for c in package.ordered_evidence) or '(none)'}\n"
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
    count = len(package.ordered_evidence)
    return (
        f"申诉说明（合成）：针对 {package.reason_code.value} 争议，随附 {count} 项证据，"
        f"请在 {package.submission_window_days} 天窗口内受理。（合成数据，不执行任何业务动作）"
    )
