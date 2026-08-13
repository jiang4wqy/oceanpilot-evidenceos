from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from oceanpilot.domain.enums import EvidenceCode, TargetRole
from oceanpilot.domain.models import (
    DiagnosisView,
    NonEmptyText,
    ReferenceText,
    Revision,
    UUID4Str,
)

_ROLE_LABELS: Final = {
    TargetRole.MERCHANT_BUSINESS: "商户业务",
    TargetRole.MERCHANT_TECH: "商户技术",
    TargetRole.INTERNAL_OPS: "内部运营",
    TargetRole.INTERNAL_RISK: "内部风控",
    TargetRole.INTERNAL_FINANCE: "内部财务",
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
    missing_fields: Annotated[tuple[StrictStr, ...], Field(min_length=1)]
    target_role: TargetRole
    next_question: NonEmptyText
    question_reason: NonEmptyText
    synthetic_action: "SyntheticEvidenceAction | None" = None


class SyntheticEvidenceAction(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    action: Literal["submit_evidence"]
    case_id: UUID4Str
    evidence_id: UUID4Str
    evidence_code: EvidenceCode
    availability: Literal["AVAILABLE"]
    typed_value: StrictStr | StrictBool
    source_ref: ReferenceText


def render_need_info_card(card_input: NeedInfoCardInput) -> dict[str, object]:
    if type(card_input) is not NeedInfoCardInput:
        raise TypeError("card_input must be NeedInfoCardInput")
    role = _ROLE_LABELS[card_input.target_role]
    missing = "\n".join(f"- `{field}`" for field in card_input.missing_fields)
    elements: list[dict[str, object]] = [
        {
            "tag": "markdown",
            "content": (
                f"**案件** `{card_input.case_id}`  ·  "
                f"**版本** `{card_input.case_revision}`\n\n"
                f"请 **{role}** 协助补充：\n{missing}"
            ),
        },
        {
            "tag": "markdown",
            "content": (
                f"**补问**\n{card_input.next_question}\n\n**原因**\n{card_input.question_reason}"
            ),
        },
    ]
    if card_input.synthetic_action is not None:
        action = card_input.synthetic_action
        elements.append(
            {
                "tag": "markdown",
                "content": (
                    "**比赛演示（合成数据）**\n"
                    f"下一步将提交 `{action.evidence_code.value}` = "
                    f"`{action.typed_value}`"
                ),
            }
        )
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "提交当前合成示例"},
                        "value": action.model_dump(mode="json"),
                    }
                ],
            }
        )
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "OceanPilot 需要补充信息"},
        },
        "body": {"elements": elements},
    }


def _candidate_markdown(view: DiagnosisView) -> str:
    if not view.diagnosis.hypotheses:
        return "暂无确定性候选，需要人工复核。"
    candidates: list[str] = []
    for index, hypothesis in enumerate(view.diagnosis.hypotheses, start=1):
        refs = "、".join(f"`{reference}`" for reference in hypothesis.evidence_refs)
        candidates.append(
            f"**候选 {index} · {hypothesis.cause_code}**\n"
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
            "content": (f"**责任域** `{responsible_team}`\n\n**下一动作**\n{next_action}"),
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
                            "action": "confirm_review",
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
