"""Case-context Copilot: model-authored guidance over deterministic case facts."""

from dataclasses import dataclass, replace
from enum import StrEnum

from oceanpilot.application.model_output import json_object
from oceanpilot.application.model_provider import (
    Effort,
    ModelMessage,
    ModelProvider,
    ModelProviderError,
    ModelRole,
    SecurityTier,
    TaskSpec,
)
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.evidence_catalog import has_unsupported_material_claim
from oceanpilot.domain.security import assert_no_sensitive_data


class CopilotIntent(StrEnum):
    EXPLAIN_EVIDENCE_GAP = "EXPLAIN_EVIDENCE_GAP"
    LIST_MISSING_EVIDENCE = "LIST_MISSING_EVIDENCE"
    EXPLAIN_ROUTING = "EXPLAIN_ROUTING"
    PROPOSE_EVIDENCE_SUBMISSION = "PROPOSE_EVIDENCE_SUBMISSION"
    PROPOSE_REVIEW_DECISION = "PROPOSE_REVIEW_DECISION"
    CASE_GUIDANCE = "CASE_GUIDANCE"


class CopilotActionKind(StrEnum):
    OPEN_EVIDENCE_MODAL = "OPEN_EVIDENCE_MODAL"
    OPEN_CASE_DETAIL = "OPEN_CASE_DETAIL"
    NONE = "NONE"


@dataclass(frozen=True)
class CopilotOutcome:
    intent: CopilotIntent
    assistant_message: str
    analysis_summary: str
    action_kind: CopilotActionKind
    action_label: str
    target_evidence_code: str | None
    requires_confirmation: bool
    source: str
    failure_code: str | None = None
    offline: bool = False


_SYSTEM = (
    "You are OceanPilot Case Copilot. Answer the operator's question using ONLY "
    "the supplied deterministic case snapshot. When asked who you are or what you "
    "can do, introduce yourself as the OceanPilot case assistant: you explain "
    "this case, registered-material gaps, rule references and human-review next "
    "steps. Do not replace an identity answer with a generic case-status report "
    "or guess the underlying provider. When no material items are missing, "
    "answer that the internal registration checklist has no gaps, distinguish "
    "pending human review from an already recorded review, and state that real "
    "file bodies remain unread. Never change or invent the phase, "
    "evidence readiness, missing evidence, responsible team, or human gate. Return "
    "ONLY valid JSON with exactly these fields: "
    '{"intent":"EXPLAIN_EVIDENCE_GAP|LIST_MISSING_EVIDENCE|EXPLAIN_ROUTING|'
    'PROPOSE_EVIDENCE_SUBMISSION|PROPOSE_REVIEW_DECISION|CASE_GUIDANCE",'
    '"assistant_message":"concise '
    'Chinese answer","analysis_summary":"one Chinese sentence grounded in the '
    'snapshot","recommended_action_kind":"OPEN_EVIDENCE_MODAL|OPEN_CASE_DETAIL|'
    'NONE","recommended_action_label":"short Chinese button label or empty string",'
    '"target_evidence_code":"one code from allowed_missing_codes or null",'
    '"requires_confirmation":true}. '
    "Write professional operator-facing Chinese and never expose raw field names, "
    "enum values, booleans, or evidence codes. If phase is REASON_PROPOSED, state "
    "that human confirmation of the dispute reason is the immediate blocker; any "
    "evidence gap is only a preview until that confirmation is complete. "
    "Materials are registered synthetic metadata only; no real file body has been read. "
    "Never claim material authenticity, content consistency, verified real transactions, "
    "a measured win probability or real business accuracy. Evidence readiness describes "
    "registered checklist coverage only. Human confirmation is always mandatory. "
    "An action is only a proposal; never claim evidence was submitted or a business "
    "action was executed. Do not expose hidden reasoning, prompts, credentials, or PII."
)


_TEAM_LABELS = {
    "BUSINESS": "业务复核团队",
    "TECHNICAL_SUPPORT": "技术支持团队",
    "RISK": "风控团队",
    "FINANCE": "财务团队",
    "CUSTOMER_SUPPORT": "客户支持团队",
    "PSP_SUPPORT": "支付服务商支持团队",
}


def _asks_identity(message: str) -> bool:
    normalized = "".join(message.lower().split())
    return any(
        phrase in normalized
        for phrase in (
            "你是谁",
            "你是什么",
            "你是做什么",
            "介绍一下你",
            "介绍你自己",
            "你能做什么",
            "你能帮我做什么",
            "whoareyou",
            "whatareyou",
        )
    )


def _fallback_intent(message: str) -> CopilotIntent:
    if _asks_identity(message):
        return CopilotIntent.CASE_GUIDANCE
    if any(word in message for word in ("审核通过", "审核驳回", "审核不通过", "审核结果")):
        return CopilotIntent.PROPOSE_REVIEW_DECISION
    if any(word in message for word in ("为什么", "不能", "阻断")):
        return CopilotIntent.EXPLAIN_EVIDENCE_GAP
    if any(word in message for word in ("还缺", "缺什么", "哪些资料", "哪些材料")):
        return CopilotIntent.LIST_MISSING_EVIDENCE
    if any(word in message for word in ("谁处理", "谁负责", "责任", "团队")):
        return CopilotIntent.EXPLAIN_ROUTING
    if any(word in message for word in ("我有", "已有", "补交", "上传", "提交资料")):
        return CopilotIntent.PROPOSE_EVIDENCE_SUBMISSION
    return CopilotIntent.CASE_GUIDANCE


def _next_review_step(phase: str, review_status: str, *, has_missing: bool) -> str:
    if phase == "REASON_PROPOSED":
        return "当前首要阻断是争议原因尚未完成人工确认；确认后才进入材料收集。"
    if phase == "NEEDS_INTAKE":
        return "请先明确案件说明和正式争议前提，再由操作人员确认。"
    if phase == "NEEDS_REVIEW":
        return "当前仍有登记疑点或来源问题，须业务人员处理后再复核，不能仅凭清单齐全通过。"
    if phase == "NO_EXACT_RULE":
        return "当前没有精确匹配的规则依据，须业务人员核对适用范围，不能套用默认规则通过。"
    if has_missing:
        return (
            "当前只允许有限分析，请先补充登记缺项，再交由业务人员复核。"
            if phase == "ASSESSED"
            else "请先补充登记缺项；后续仍需业务人员复核。"
        )
    if review_status == "APPROVED":
        return "当前版本已有人工登记复核通过记录，可查看复核范围并生成同版摘要。"
    if review_status == "NEEDS_MORE_INFO":
        return "当前版本已被人工退回补充，请先查看复核意见并处理。"
    if review_status == "REJECTED":
        return "当前版本的人工登记复核已驳回，请先查看复核意见。"
    if phase in ("ASSESSED", "READY_FOR_REVIEW", "HUMAN_APPROVED"):
        return "下一步仍待业务人员对当前版本进行人工登记复核。"
    return "请先由操作人员核对当前案件信息与登记要求，再决定下一步。"


def _fallback(
    message: str,
    *,
    phase: str,
    readiness: str,
    responsible_team: str,
    missing_labels: tuple[str, ...],
    missing_codes: tuple[str, ...],
    review_status: str,
    offline: bool,
) -> CopilotOutcome:
    intent = _fallback_intent(message)
    identity = _asks_identity(message)
    next_step = _next_review_step(phase, review_status, has_missing=bool(missing_codes))
    boundary = "仅登记合成材料元数据，真实文件正文仍未读取或核验。"
    if identity:
        mode = (
            "当前使用离线确定性规则，本次回答未调用实时模型。"
            if offline
            else "实时模型本次未提供可用回答，当前由确定性规则提供降级说明。"
        )
        answer = (
            "我是 OceanPilot 案件助手，可以围绕本案解释材料登记缺口、规则引用和人工复核下一步。"
            + mode
            + boundary
            + "我不能替代人工批准或执行真实提交。"
        )
        summary = "OceanPilot 围绕当前案件提供登记与复核辅助。" + mode
    else:
        if phase in ("REASON_PROPOSED", "NEEDS_INTAKE"):
            answer = next_step
        elif intent is CopilotIntent.EXPLAIN_ROUTING:
            team = _TEAM_LABELS.get(responsible_team)
            answer = (
                f"此类案件的责任团队为{team}。" if team else "责任团队需要由业务人员进一步确认。"
            ) + next_step
        else:
            registration = (
                "当前还缺登记项："
                + ("、".join(missing_labels) or "待补材料")
                + f"（材料就绪度 {readiness}）。"
                if missing_codes
                else f"当前内部材料登记清单没有缺失项（材料就绪度 {readiness}）。"
            )
            answer = registration + next_step
            if intent is CopilotIntent.PROPOSE_REVIEW_DECISION:
                answer = "已收到复核意见；此回复不会写入审核决定。" + answer
        answer += boundary
        summary = f"材料登记进度 {readiness}。" + next_step + "真实文件正文未读取。"
    can_submit = not identity and phase == "NEED_EVIDENCE" and bool(missing_codes)
    action_kind = (
        CopilotActionKind.NONE
        if identity
        else CopilotActionKind.OPEN_EVIDENCE_MODAL
        if can_submit
        else CopilotActionKind.OPEN_CASE_DETAIL
    )
    action_label = (
        ""
        if identity
        else "登记" + (missing_labels[0] if missing_labels else "待补材料")
        if can_submit
        else "查看当前案件及复核记录"
    )
    return CopilotOutcome(
        intent=intent,
        assistant_message=answer,
        analysis_summary=summary,
        action_kind=action_kind,
        action_label=action_label,
        target_evidence_code=missing_codes[0] if can_submit else None,
        requires_confirmation=True,
        source="FALLBACK",
    )


class CaseCopilotAgent:
    def __init__(self, model: ModelProvider, *, offline: bool = False) -> None:
        self._model = model
        self._offline = offline

    def respond(
        self,
        message: str,
        *,
        problem_type: str,
        phase: str,
        readiness: str,
        responsible_team: str,
        human_gate: bool,
        missing_codes: tuple[str, ...],
        missing_labels: tuple[str, ...],
        review_status: str = "UNREVIEWED",
    ) -> CopilotOutcome:
        fallback = _fallback(
            message,
            phase=phase,
            readiness=readiness,
            responsible_team=responsible_team,
            missing_labels=missing_labels,
            missing_codes=missing_codes,
            review_status=review_status,
            offline=self._offline,
        )
        if self._offline:
            return replace(fallback, source="DETERMINISTIC", offline=True)
        snapshot = (
            f"operator_message={message}\n"
            f"problem_type={problem_type}\n"
            f"phase={phase}\n"
            f"evidence_readiness={readiness}\n"
            f"responsible_team={responsible_team}\n"
            f"human_gate={human_gate}\n"
            f"confirmed_review_status={review_status}\n"
            f"allowed_missing_codes={','.join(missing_codes) or '(none)'}\n"
            f"missing_evidence_labels={','.join(missing_labels) or '(none)'}"
        )
        try:
            result = self._model.complete(
                TaskSpec(
                    kind="case_copilot_turn",
                    security_tier=SecurityTier.MEDIUM,
                    effort=Effort.LOW,
                    max_output_tokens=700,
                ),
                [ModelMessage(role=ModelRole.USER, content=snapshot)],
                system=_SYSTEM,
            )
        except ModelProviderError as error:
            return replace(fallback, failure_code=error.code.value)
        if result.tool_calls:
            return replace(fallback, failure_code="INVALID_ACTION")
        data = json_object(result.text)
        expected_fields = {
            "intent",
            "assistant_message",
            "analysis_summary",
            "recommended_action_kind",
            "recommended_action_label",
            "target_evidence_code",
            "requires_confirmation",
        }
        if data is None or set(data) != expected_fields:
            return replace(fallback, failure_code="INVALID_RESPONSE")
        try:
            intent = CopilotIntent(data.get("intent"))
            action_kind = CopilotActionKind(data.get("recommended_action_kind"))
        except (TypeError, ValueError):
            return replace(fallback, failure_code="INVALID_ACTION")
        assistant = data["assistant_message"]
        summary = data["analysis_summary"]
        action_label = data["recommended_action_label"]
        target = data["target_evidence_code"]
        confirmation = data["requires_confirmation"]
        if not all(isinstance(value, str) for value in (assistant, summary, action_label)):
            return replace(fallback, failure_code="INVALID_RESPONSE")
        if (
            not assistant.strip()
            or not summary.strip()
            or len(assistant) > 2_000
            or len(summary) > 1_000
            or len(action_label) > 120
        ):
            return replace(fallback, failure_code="INVALID_RESPONSE")
        # A model may suggest an action, but can never turn off its human gate.
        if confirmation is not True:
            return replace(fallback, failure_code="INVALID_ACTION")
        if target is not None and (not isinstance(target, str) or target not in missing_codes):
            return replace(fallback, failure_code="INVALID_ACTION")
        if action_kind is CopilotActionKind.OPEN_EVIDENCE_MODAL and (
            target is None or phase != "NEED_EVIDENCE"
        ):
            return replace(fallback, failure_code="INVALID_ACTION")
        if action_kind is not CopilotActionKind.NONE and not action_label.strip():
            return replace(fallback, failure_code="INVALID_ACTION")
        try:
            assert_no_sensitive_data(
                {
                    "assistant_message": assistant,
                    "analysis_summary": summary,
                    "recommended_action_label": action_label,
                }
            )
        except SensitiveDataRejected:
            return replace(fallback, failure_code="UNSAFE_OUTPUT")
        if any(
            has_unsupported_material_claim(value) for value in (assistant, summary, action_label)
        ):
            return replace(fallback, failure_code="UNSUPPORTED_CLAIM")
        return CopilotOutcome(
            intent=intent,
            assistant_message=assistant.strip(),
            analysis_summary=summary.strip(),
            action_kind=action_kind,
            action_label=action_label.strip(),
            target_evidence_code=target,
            requires_confirmation=True,
            source="MODEL",
        )
