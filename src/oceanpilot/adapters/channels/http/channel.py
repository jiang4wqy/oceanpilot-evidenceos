"""HTTP (pure JSON) channel adapter — the reference ``Channel`` (issue #10 T1).

Parses a plain JSON body into a ``NormalizedInbound`` and renders a ``Delivery``
back as a JSON-serialisable dict. This is the simplest possible channel and the
one the HTTP API uses; a new channel is added by writing another adapter with the
same ``Channel`` shape — the application and domain layers do not change.
"""

from collections.abc import Mapping

from oceanpilot.application.channels import (
    Delivery,
    InboundKind,
    NormalizedInbound,
)
from oceanpilot.application.errors import InvalidInbound

_ACTIONS = {
    "open_case": InboundKind.OPEN_CASE,
    "confirm_reason": InboundKind.CONFIRM_REASON,
    "submit_evidence": InboundKind.SUBMIT_EVIDENCE,
    "finalize_evidence": InboundKind.FINALIZE_EVIDENCE,
    "get_case": InboundKind.GET_CASE,
}


def _text_or_none(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


class HttpChannel:
    name = "http"

    def parse_inbound(self, raw: Mapping[str, object]) -> NormalizedInbound:
        action = raw.get("action")
        if not isinstance(action, str) or action.lower() not in _ACTIONS:
            raise InvalidInbound()
        return NormalizedInbound(
            kind=_ACTIONS[action.lower()],
            channel=self.name,
            case_id=_text_or_none(raw, "case_id"),
            description=_text_or_none(raw, "description"),
            evidence_code=_text_or_none(raw, "evidence_code"),
            reason_code=_text_or_none(raw, "reason_code"),
            actor=_text_or_none(raw, "actor"),
        )

    def render(self, delivery: Delivery) -> Mapping[str, object]:
        assessment: dict[str, object] | None = None
        if delivery.assessment is not None:
            a = delivery.assessment
            assessment = {
                "win_likelihood": a.win_likelihood,
                "completeness": a.completeness,
                "responsible_team": a.responsible_team,
                "requires_human": a.requires_human,
                "review_reasons": list(a.review_reasons),
                "explanation": a.explanation,
                "explanation_source": a.explanation_source,
                "evidence_breakdown": [
                    {
                        "code": item.code,
                        "label": item.label,
                        "weight": item.weight,
                        "critical": item.critical,
                        "present": item.present,
                    }
                    for item in a.evidence_breakdown
                ],
            }
        deadline: dict[str, object] | None = None
        if delivery.deadline is not None:
            d = delivery.deadline
            deadline = {
                "phase": d.phase,
                "days_remaining": d.days_remaining,
                "deadline_at": d.deadline_at,
                "overdue": d.overdue,
            }
        facts: dict[str, object] | None = None
        if delivery.facts is not None:
            f = delivery.facts
            facts = {
                "amount": f.amount,
                "currency": f.currency,
                "occurred_on": f.occurred_on,
                "summary": f.summary,
            }
        return {
            "channel": self.name,
            "case_id": delivery.case_id,
            "phase": delivery.phase,
            "reason_code": delivery.reason_code,
            "reason_confirmed": delivery.reason_confirmed,
            "collection_finalized": delivery.collection_finalized,
            "collected": list(delivery.collected),
            "next_evidence": delivery.next_evidence,
            "question": delivery.question,
            "missing": list(delivery.missing) if delivery.missing is not None else None,
            "assessment": assessment,
            "deadline": deadline,
            "facts": facts,
            "agent_trace": [
                {"agent": a.agent, "action": a.action, "source": a.source}
                for a in delivery.agent_trace
            ],
        }
