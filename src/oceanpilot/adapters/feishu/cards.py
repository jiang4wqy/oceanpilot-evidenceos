from decimal import Decimal
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from oceanpilot.application.feishu_orchestrator import feishu_evidence_values
from oceanpilot.domain.enums import EvidenceCode, TargetRole
from oceanpilot.domain.models import DiagnosisView, NonEmptyText, Revision, UUID4Str

_ROLE_LABELS: Final = {
    TargetRole.MERCHANT_BUSINESS: "商户业务",
    TargetRole.MERCHANT_TECH: "商户技术",
    TargetRole.INTERNAL_OPS: "内部运营",
    TargetRole.INTERNAL_RISK: "内部风控",
    TargetRole.INTERNAL_FINANCE: "内部财务",
}

_EVIDENCE_ACTION_LABELS: Final = {
    EvidenceCode.TRANSACTION_REFERENCE: ("使用演示交易号",),
    EvidenceCode.TRANSACTION_OCCURRED_AT: ("使用演示发生时间",),
    EvidenceCode.CONTEXT_ENVIRONMENT: ("生产环境",),
    EvidenceCode.SYMPTOM_STATUS: ("交易处理中", "交易已拒绝"),
    EvidenceCode.AUTHENTICATION_STATUS: ("需要 3DS 认证",),
    EvidenceCode.CALLBACK_DELIVERY_STATUS: ("未收到回调",),
    EvidenceCode.RISK_DECISION_CODE: ("风控拒绝",),
    EvidenceCode.INTEGRATION_TYPE: ("API 接入",),
}


class NeedInfoCardInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    case_id: UUID4Str
    case_revision: Revision
    evidence_code: EvidenceCode
    missing_fields: Annotated[tuple[StrictStr, ...], Field(min_length=1)]
    target_role: TargetRole
    completion_ratio: Annotated[Decimal, Field(ge=0, le=1)]
    next_question: NonEmptyText
    question_reason: NonEmptyText


def render_need_info_card(card_input: NeedInfoCardInput) -> dict[str, object]:
    if type(card_input) is not NeedInfoCardInput:
        raise TypeError("card_input must be NeedInfoCardInput")
    role = _ROLE_LABELS[card_input.target_role]
    missing = "\n".join(f"- `{field}`" for field in card_input.missing_fields)
    completion = f"{card_input.completion_ratio * 100:.0f}%"
    try:
        labels = _EVIDENCE_ACTION_LABELS[card_input.evidence_code]
    except KeyError:
        raise ValueError("unsupported evidence action") from None
    evidence_actions = zip(
        labels,
        feishu_evidence_values(card_input.evidence_code),
        strict=True,
    )
    actions = [
        {
            "tag": "button",
            "type": "primary",
            "text": {"tag": "plain_text", "content": label},
            "value": {
                "action_kind": "submit_evidence",
                "case_id": card_input.case_id,
                "case_revision": card_input.case_revision,
                "evidence_code": card_input.evidence_code.value,
                "availability": "AVAILABLE",
                "typed_value": typed_value,
            },
        }
        for label, typed_value in evidence_actions
    ]
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "OceanPilot 需要补充信息"},
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**案件** `{card_input.case_id}`  ·  "
                        f"**版本** `{card_input.case_revision}`  ·  "
                        f"**证据完成度** `{completion}`\n\n"
                        f"请 **{role}** 协助补充：\n{missing}"
                    ),
                },
                {
                    "tag": "markdown",
                    "content": (
                        f"**补问**\n{card_input.next_question}\n\n"
                        f"**原因**\n{card_input.question_reason}"
                    ),
                },
                {"tag": "action", "actions": actions},
            ]
        },
    }


def _candidate_markdown(view: DiagnosisView) -> str:
    if not view.diagnosis.hypotheses:
        return "暂无确定性候选，需要人工复核。"
    candidates: list[str] = []
    for index, hypothesis in enumerate(view.diagnosis.hypotheses, start=1):
        refs = "、".join(f"`{reference}`" for reference in hypothesis.evidence_refs)
        candidates.append(
            f"**候选 {index} · {hypothesis.cause_code}**\n"
            f"规则：`{hypothesis.rule_id}`\n"
            f"{hypothesis.explanation}\n"
            f"置信度：`{hypothesis.confidence_score:.2f}`\n"
            f"证据引用：{refs}"
        )
    return "\n\n".join(candidates)


def render_diagnosis_card(view: DiagnosisView) -> dict[str, object]:
    if type(view) is not DiagnosisView:
        raise TypeError("view must be DiagnosisView")
    diagnosis = view.diagnosis
    route = diagnosis.routing_decision
    ticket = diagnosis.ticket_draft
    responsible_team = route.responsible_team.value if route is not None else "待人工分配"
    priority = route.priority.value if route is not None else "待人工判定"
    review_reasons = "、".join(f"`{reason.value}`" for reason in sorted(diagnosis.review_reasons))
    if not review_reasons:
        review_reasons = "无"
    if ticket is not None:
        next_action = ticket.next_action
    elif diagnosis.hypotheses:
        next_action = diagnosis.hypotheses[0].next_verification_action
    else:
        next_action = "补充证据后人工复核"

    elements: list[dict[str, object]] = [
        {
            "tag": "markdown",
            "content": (
                f"**案件** `{view.case_id}`  ·  **案件版本** `{view.case_revision}`\n"
                f"**诊断** `{diagnosis.diagnosis_id}`  ·  "
                f"**证据版本** `{view.evidence_revision}`"
            ),
        },
        {"tag": "markdown", "content": _candidate_markdown(view)},
        {
            "tag": "markdown",
            "content": (
                f"**责任域** `{responsible_team}`  ·  **优先级** `{priority}`\n"
                f"**人工复核原因** {review_reasons}\n\n"
                f"**下一动作**\n{next_action}"
            ),
        },
        {
            "tag": "markdown",
            "content": (
                "**安全边界**：仅限 synthetic 演示；未执行支付、退款、风控放行或生产配置变更。"
            ),
        },
    ]
    if diagnosis.requires_human:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "确认人工复核"},
                        "value": {
                            "action_kind": "confirm_review",
                            "case_id": view.case_id,
                            "diagnosis_id": diagnosis.diagnosis_id,
                        },
                    }
                ],
            }
        )
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "template": "orange" if diagnosis.requires_human else "green",
            "title": {"tag": "plain_text", "content": "OceanPilot 诊断结果"},
        },
        "body": {"elements": elements},
    }
