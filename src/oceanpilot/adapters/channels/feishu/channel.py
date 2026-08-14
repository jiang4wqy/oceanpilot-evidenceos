"""Feishu channel adapter — Feishu is *one* channel (issue #10 T1 / decision D2).

Parses two Feishu inbound shapes into a ``NormalizedInbound`` — an interactive
card action (``action.value`` carries the intent) and a received text message
(opens a case) — and renders a ``Delivery`` as a Feishu interactive card. It is
self-contained (no coupling to the legacy payment-incident Feishu orchestrator),
so swapping/adding channels never touches the application or domain layers.

Only synthetic, non-sensitive fields are placed in the card. The card offers a
button to confirm the next evidence item; it never triggers a business action.
"""

import json
from collections.abc import Mapping

from oceanpilot.application.channels import (
    Delivery,
    DeliveryDeadline,
    DeliveryEvidenceItem,
    InboundKind,
    NormalizedInbound,
)
from oceanpilot.application.chargeback_agents import CaseFacts
from oceanpilot.application.errors import InvalidInbound
from oceanpilot.domain.chargeback import DisputeReasonCode
from oceanpilot.domain.reason_catalog import reason_label

_ACTIONS = {
    "open_case": InboundKind.OPEN_CASE,
    "confirm_reason": InboundKind.CONFIRM_REASON,
    "submit_evidence": InboundKind.SUBMIT_EVIDENCE,
    "finalize_evidence": InboundKind.FINALIZE_EVIDENCE,
    "get_case": InboundKind.GET_CASE,
}


def _reason_display(code_value: str | None) -> str | None:
    """Human label for a reason code value; falls back to the raw value."""
    if code_value is None:
        return None
    try:
        return reason_label(DisputeReasonCode(code_value))
    except (ValueError, TypeError):
        return code_value


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


class FeishuChannel:
    name = "feishu"

    def parse_inbound(self, raw: Mapping[str, object]) -> NormalizedInbound:
        action = raw.get("action")
        if isinstance(action, Mapping):
            return self._parse_card_action(action)
        message_text = self._message_text(raw)
        if message_text is not None:
            return NormalizedInbound(
                kind=InboundKind.OPEN_CASE,
                channel=self.name,
                description=message_text,
                actor=self._actor(raw),
            )
        raise InvalidInbound()

    def _parse_card_action(self, action: Mapping[str, object]) -> NormalizedInbound:
        value = action.get("value")
        if not isinstance(value, Mapping):
            raise InvalidInbound()
        intent = value.get("action")
        if not isinstance(intent, str) or intent.lower() not in _ACTIONS:
            raise InvalidInbound()
        return NormalizedInbound(
            kind=_ACTIONS[intent.lower()],
            channel=self.name,
            case_id=_text(value.get("case_id")),
            description=_text(value.get("description")),
            evidence_code=(
                _text(value.get("chargeback_evidence_code")) or _text(value.get("evidence_code"))
            ),
            reason_code=_text(value.get("reason_code")),
            actor=_text(value.get("actor")),
        )

    @staticmethod
    def _message_text(raw: Mapping[str, object]) -> str | None:
        event = raw.get("event")
        if not isinstance(event, Mapping):
            return None
        message = event.get("message")
        if not isinstance(message, Mapping):
            return None
        content = message.get("content")
        if not isinstance(content, str):
            return None
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        text = parsed.get("text") if isinstance(parsed, dict) else None
        return text.strip() if isinstance(text, str) and text.strip() else None

    @staticmethod
    def _actor(raw: Mapping[str, object]) -> str | None:
        event = raw.get("event")
        if not isinstance(event, Mapping):
            return None
        sender = event.get("sender")
        if not isinstance(sender, Mapping):
            return None
        sender_id = sender.get("sender_id")
        if not isinstance(sender_id, Mapping):
            return None
        return _text(sender_id.get("open_id"))

    def render(self, delivery: Delivery) -> Mapping[str, object]:
        elements: list[dict[str, object]] = [
            _field(f"**案件**：{delivery.case_id}"),
            _field(f"**状态**：{delivery.phase}"),
        ]
        if delivery.reason_code is not None:
            confirmed_mark = "已确认" if delivery.reason_confirmed else "待确认"
            reason_text = _reason_display(delivery.reason_code)
            elements.append(_field(f"**争议原因**：{reason_text}（{confirmed_mark}）"))
        if delivery.collected:
            elements.append(_field("**已收集**：" + "、".join(delivery.collected)))
        if delivery.deadline is not None:
            elements.append(_field(_deadline_text(delivery.deadline)))
        if delivery.facts is not None:
            elements.append(_field(_facts_text(delivery.facts)))

        if delivery.phase == "REASON_PROPOSED":
            if delivery.question:
                elements.append(_field(delivery.question))
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "确认该原因"},
                            "type": "primary",
                            "value": {
                                "flow": "chargeback",
                                "action": "confirm_reason",
                                "case_id": delivery.case_id,
                            },
                        }
                    ],
                }
            )
        elif delivery.phase == "NEED_EVIDENCE" and delivery.next_evidence is not None:
            if delivery.question:
                elements.append(_field(delivery.question))
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "我已提交该证据"},
                            "type": "primary",
                            "value": {
                                "flow": "chargeback",
                                "action": "submit_evidence",
                                "case_id": delivery.case_id,
                                "chargeback_evidence_code": delivery.next_evidence,
                            },
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "无法提供更多，转人工复核"},
                            "type": "danger",
                            "value": {
                                "flow": "chargeback",
                                "action": "finalize_evidence",
                                "case_id": delivery.case_id,
                            },
                        },
                    ],
                }
            )
        elif delivery.phase == "ASSESSED" and delivery.assessment is not None:
            a = delivery.assessment
            review = "需人工复核" if a.requires_human else "可自动推进"
            elements.append(
                _field(
                    f"**规则证据就绪度**：{a.win_likelihood}｜**责任域**：{a.responsible_team}｜{review}"
                )
            )
            if a.evidence_breakdown:
                elements.append(_field("**证据构成**：" + _breakdown_text(a.evidence_breakdown)))
            source = "模型生成" if a.explanation_source == "MODEL" else "确定性兜底"
            elements.append(
                _field(
                    f"{a.explanation}\n\n_（就绪度不是胜诉概率；数字由确定性内核判定；"
                    f"说明文字：{source}）_"
                )
            )

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "跨境拒付案件"},
            },
            "elements": elements,
        }


def _field(content: str) -> dict[str, object]:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def _breakdown_text(items: tuple[DeliveryEvidenceItem, ...]) -> str:
    parts: list[str] = []
    for item in items:
        mark = "✅" if item.present else "❌"
        star = "⭐" if item.critical else ""
        parts.append(f"{mark}{star}{item.label}")
    return " ".join(parts)


def _facts_text(facts: CaseFacts) -> str:
    parts: list[str] = []
    if facts.summary:
        parts.append(facts.summary)
    meta: list[str] = []
    if facts.amount:
        amount = f"{facts.amount} {facts.currency}" if facts.currency else facts.amount
        meta.append(f"金额 {amount}")
    if facts.occurred_on:
        meta.append(f"日期 {facts.occurred_on}")
    if meta:
        parts.append("｜".join(meta))
    return "**识别要点**：" + ("；".join(parts) if parts else "—")


def _deadline_text(deadline: DeliveryDeadline) -> str:
    due = deadline.deadline_at[:10] if deadline.deadline_at else "—"
    if deadline.overdue:
        return f"**举证时限**：<font color='red'>已逾期</font>（截止 {due}）"
    if deadline.days_remaining is None:
        return f"**举证时限**：截止 {due}"
    return f"**举证时限**：还剩 {deadline.days_remaining} 天（截止 {due}）"
