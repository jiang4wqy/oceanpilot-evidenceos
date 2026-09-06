"""Immutable case Agent views and deterministic presentation helpers.

These values describe the current demonstration behavior independently of HTTP.
They deliberately preserve existing operator copy; tightening rules/material
wording is a separate business change after the structural refactor.
"""

import json
from dataclasses import dataclass
from typing import Literal

from oceanpilot.application.case_copilot import CopilotOutcome
from oceanpilot.application.case_review import ReviewDecision, ReviewStatus
from oceanpilot.application.channels import Delivery
from oceanpilot.application.knowledge_base import KnowledgeBase, RuleCatalog
from oceanpilot.domain.chargeback import (
    ChargebackEvidenceCode,
    DisputeReasonCode,
    assess_chargeback,
    required_evidence_for,
)
from oceanpilot.domain.evidence_catalog import label_of
from oceanpilot.domain.reason_catalog import reason_label


@dataclass(frozen=True, kw_only=True)
class AgentRuntime:
    mode: Literal["DEEPSEEK_LIVE", "CLAUDE_LIVE", "INJECTED_MODEL", "OFFLINE_FALLBACK"]
    provider: str
    model: str


@dataclass(frozen=True, kw_only=True)
class AgentJudgment:
    problem_type: str
    phase: str
    confirmed_facts: tuple[str, ...]
    uncertain_facts: tuple[str, ...]
    evidence_readiness: str
    responsible_team: str
    next_action: str
    human_gate: bool
    decision_summary: str
    missing_evidence_codes: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    collected_evidence_codes: tuple[str, ...]
    collected_evidence: tuple[str, ...]
    next_evidence_code: str | None
    next_evidence_label: str | None


@dataclass(frozen=True, kw_only=True)
class AgentRecommendedAction:
    kind: Literal["OPEN_EVIDENCE_MODAL", "OPEN_CASE_DETAIL", "NONE"]
    label: str
    evidence_code: str | None = None
    evidence_label: str | None = None
    requires_confirmation: bool


@dataclass(frozen=True, kw_only=True)
class AgentTraceStep:
    step: int
    actor: str
    action: str
    status: Literal["COMPLETED", "WAITING", "BLOCKED"]
    source: str
    output_summary: str


@dataclass(frozen=True, kw_only=True)
class AgentMaterialContent:
    evidence_code: str
    label: str
    summary: str


@dataclass(frozen=True, kw_only=True)
class AgentCitation:
    reference_id: str
    reference_type: Literal["RULE", "TECHNICAL_CONTEXT"]
    title: str
    claim: str
    source_document: str
    source_section: str | None = None
    source_url: str
    verification_status: str
    limitation: str


@dataclass(frozen=True, kw_only=True)
class AgentReviewProposal:
    status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    summary: str
    confirmed_materials: tuple[str, ...]
    conflicts: tuple[str, ...]
    next_action: str
    why: str
    requires_confirmation: Literal[True]


@dataclass(frozen=True, kw_only=True)
class AgentReviewDecision:
    decision_id: str
    status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    revision: int
    confirmed_by: str
    confirmed_at: str
    audit_event_id: str


@dataclass(frozen=True, kw_only=True)
class AgentTurn:
    synthetic: Literal[True]
    result: Literal["CREATED", "REPLAYED"] = "CREATED"
    turn_kind: Literal["CASE_CREATED", "CASE_ANALYZED"]
    source_turn_id: str
    case_id: str
    card_network: Literal["VISA", "MASTERCARD", "AMEX"] | None = None
    case_revision: int
    trigger: str
    intent: str
    assistant_message: str
    analysis_summary: str
    review_status: str
    material_contents: tuple[AgentMaterialContent, ...]
    decision_reason: str
    citations: tuple[AgentCitation, ...]
    review_proposal: AgentReviewProposal | None = None
    review_decision: AgentReviewDecision | None = None
    human_boundary: str
    runtime: AgentRuntime
    judgment: AgentJudgment
    recommended_action: AgentRecommendedAction
    agent_trace: tuple[AgentTraceStep, ...]


def _saved_array(value: object) -> list[object]:
    # Unlike tuple(value), this must not coerce a malformed saved string or
    # mapping into a valid-looking response array before HTTP validation.
    if not isinstance(value, list):
        raise ValueError("Malformed saved Agent turn: expected JSON array")
    return value


def restore_turn(response_json: str) -> AgentTurn:
    """Restore an existing persisted turn, including pre-refactor records.

    JSON arrays are restored as tuples so replayed views are as immutable as
    freshly computed ones. The channel codec validates the complete contract
    before invoking this reconstruction helper.
    """
    payload = json.loads(response_json)
    payload["runtime"] = AgentRuntime(**payload["runtime"])
    judgment = payload["judgment"]
    for name in (
        "confirmed_facts",
        "uncertain_facts",
        "missing_evidence_codes",
        "missing_evidence",
        "collected_evidence_codes",
        "collected_evidence",
    ):
        judgment[name] = tuple(_saved_array(judgment[name]))
    payload["judgment"] = AgentJudgment(**judgment)
    payload["recommended_action"] = AgentRecommendedAction(**payload["recommended_action"])
    payload["material_contents"] = tuple(
        AgentMaterialContent(**item) for item in _saved_array(payload["material_contents"])
    )
    payload["citations"] = tuple(
        AgentCitation(**item) for item in _saved_array(payload["citations"])
    )
    payload["agent_trace"] = tuple(
        AgentTraceStep(**item) for item in _saved_array(payload["agent_trace"])
    )
    proposal = payload.get("review_proposal")
    if proposal is not None:
        proposal["confirmed_materials"] = tuple(_saved_array(proposal["confirmed_materials"]))
        proposal["conflicts"] = tuple(_saved_array(proposal["conflicts"]))
        payload["review_proposal"] = AgentReviewProposal(**proposal)
    decision = payload.get("review_decision")
    if decision is not None:
        payload["review_decision"] = AgentReviewDecision(**decision)
    return AgentTurn(**payload)


def view_locale(locale: str) -> str:
    return "en" if locale == "en-US" else "zh"


def _labels(codes: tuple[str, ...] | None, *, locale: str) -> tuple[str, ...]:
    return tuple(label_of(ChargebackEvidenceCode(code), locale=locale) for code in (codes or ()))


def _facts(delivery: Delivery, *, locale: str) -> tuple[str, ...]:
    facts: list[str] = []
    if delivery.facts is not None:
        if delivery.facts.amount:
            facts.append(f"amount={delivery.facts.amount}")
        if delivery.facts.currency:
            facts.append(f"currency={delivery.facts.currency}")
        if delivery.facts.occurred_on:
            facts.append(f"occurred_on={delivery.facts.occurred_on}")
        if delivery.facts.summary:
            facts.append(delivery.facts.summary)
    return tuple(facts)


def assistant_message(delivery: Delivery, *, locale: str) -> str:
    question = (delivery.question or "").strip()
    if question and "合成模型输出" not in question:
        return question
    if delivery.next_evidence is not None:
        label = label_of(ChargebackEvidenceCode(delivery.next_evidence), locale=locale)
        if locale == "en":
            return f"Please provide {label}. I will re-check the case after it is added."
        return f"请补充「{label}」。提交后我会重新校验案件状态并给出下一步。"
    return (
        "The case has been created. Please review the structured judgment below."
        if locale == "en"
        else "案件已创建，请查看下方结构化判断与下一步。"
    )


def _trace_source(source: str | None, runtime: AgentRuntime) -> str:
    if source == "MODEL":
        return runtime.provider
    if source == "FALLBACK":
        return "DETERMINISTIC_FALLBACK"
    return source or "CASE_STATE"


def trace(delivery: Delivery, runtime: AgentRuntime) -> tuple[AgentTraceStep, ...]:
    trace = [
        AgentTraceStep(
            step=1,
            actor="AgentGateway",
            action="接收并规范化用户问题",
            status="COMPLETED",
            source="USER_INPUT",
            output_summary="已生成渠道无关的建案请求",
        ),
        AgentTraceStep(
            step=2,
            actor="CaseTool",
            action="创建版本化案件并写入审计",
            status="COMPLETED",
            source="SQLITE_CASE_STORE",
            output_summary=f"案件 {delivery.case_id} 已持久化",
        ),
    ]
    for activity in delivery.agent_trace:
        waiting = activity.agent == "HumanGate"
        trace.append(
            AgentTraceStep(
                step=len(trace) + 1,
                actor=activity.agent,
                action=activity.action,
                status="WAITING" if waiting else "COMPLETED",
                source=_trace_source(activity.source, runtime),
                output_summary=(
                    "等待人工明确确认，系统不会自动执行高风险动作"
                    if waiting
                    else "阶段输出已按固定 JSON 合同解析并写入案件视图"
                ),
            )
        )
    return tuple(trace)


def judgment(delivery: Delivery, *, locale: str) -> AgentJudgment:
    reason = DisputeReasonCode(delivery.reason_code) if delivery.reason_code else None
    extracted_facts = _facts(delivery, locale=locale)
    confirmed: tuple[str, ...] = ()

    if reason is None:
        missing_codes: tuple[str, ...] = ()
        responsible_team = "UNASSIGNED"
        human_gate = True
        readiness = "0/0 项"
    else:
        assessment = assess_chargeback(
            reason,
            (ChargebackEvidenceCode(code) for code in delivery.collected),
        )
        missing_codes = (
            delivery.missing
            if delivery.missing is not None
            else tuple(code.value for code in assessment.missing_evidence)
        )
        required = required_evidence_for(reason)
        present_required = sum(
            ChargebackEvidenceCode(code) in required for code in delivery.collected
        )
        readiness = f"{present_required}/{len(required)} 项"
        responsible_team = assessment.responsible_team.value
        human_gate = not delivery.reason_confirmed or assessment.requires_human
        if delivery.reason_confirmed:
            confirmed = (reason_label(reason, locale=locale),)

    missing = _labels(missing_codes, locale=locale)
    collected_codes = tuple(delivery.collected)
    collected = _labels(collected_codes, locale=locale)
    uncertain = list(extracted_facts) + list(missing)
    if reason is not None and not delivery.reason_confirmed:
        uncertain.insert(0, reason_label(reason, locale=locale))

    next_action = assistant_message(delivery, locale=locale)
    problem_type = reason_label(reason, locale=locale) if reason is not None else "待识别"
    if locale == "en":
        summary = (
            f"The deterministic kernel classified this as {problem_type}; evidence readiness "
            f"is {readiness}, routed to {responsible_team}."
        )
    else:
        summary = (
            f"确定性内核将问题归类为「{problem_type}」，当前证据就绪度为 {readiness}，"
            f"责任域为 {responsible_team}；AI 只负责理解问题和生成说明。"
        )
    return AgentJudgment(
        problem_type=problem_type,
        phase=delivery.phase,
        confirmed_facts=confirmed,
        uncertain_facts=tuple(uncertain),
        evidence_readiness=readiness,
        responsible_team=responsible_team,
        next_action=next_action,
        human_gate=human_gate,
        decision_summary=summary,
        missing_evidence_codes=missing_codes,
        missing_evidence=missing,
        collected_evidence_codes=collected_codes,
        collected_evidence=collected,
        next_evidence_code=(missing_codes[0] if missing_codes else None),
        next_evidence_label=(missing[0] if missing else None),
    )


def created_action(judgment: AgentJudgment) -> AgentRecommendedAction:
    if judgment.phase == "NEED_EVIDENCE" and judgment.next_evidence_code is not None:
        return AgentRecommendedAction(
            kind="OPEN_EVIDENCE_MODAL",
            label=f"补交{judgment.next_evidence_label}",
            evidence_code=judgment.next_evidence_code,
            evidence_label=judgment.next_evidence_label,
            requires_confirmation=True,
        )
    return AgentRecommendedAction(
        kind="OPEN_CASE_DETAIL",
        label="查看案件详情",
        requires_confirmation=True,
    )


def analyzed_trace(
    delivery: Delivery,
    runtime: AgentRuntime,
    outcome: CopilotOutcome,
) -> tuple[AgentTraceStep, ...]:
    source = runtime.provider if outcome.source == "MODEL" else "DETERMINISTIC_FALLBACK"
    return (
        AgentTraceStep(
            step=1,
            actor="AgentGateway",
            action="接收案件上下文问题",
            status="COMPLETED",
            source="USER_INPUT",
            output_summary="已绑定现有案件，未创建重复案件",
        ),
        AgentTraceStep(
            step=2,
            actor="CaseTool",
            action="读取当前案件确定性快照",
            status="COMPLETED",
            source="SQLITE_CASE_STORE",
            output_summary=f"读取阶段 {delivery.phase}，未修改案件状态",
        ),
        AgentTraceStep(
            step=3,
            actor="CaseCopilot",
            action="理解问题并生成案件说明",
            status="COMPLETED",
            source=source,
            output_summary="模型说明受固定 JSON 合同和案件快照约束",
        ),
        AgentTraceStep(
            step=4,
            actor="HumanGate",
            action="等待操作人员确认推荐动作",
            status="WAITING",
            source="POLICY_BOUNDARY",
            output_summary="Agent 不会直接改变案件或执行资金动作",
        ),
    )


def analyzed_action(
    outcome: CopilotOutcome,
    judgment: AgentJudgment,
) -> AgentRecommendedAction:
    evidence_code = outcome.target_evidence_code
    evidence_label = None
    if evidence_code in judgment.missing_evidence_codes:
        index = judgment.missing_evidence_codes.index(evidence_code)
        evidence_label = judgment.missing_evidence[index]
    elif evidence_code is not None:
        evidence_code = judgment.next_evidence_code
        evidence_label = judgment.next_evidence_label
    return AgentRecommendedAction(
        kind=outcome.action_kind.value,
        label=outcome.action_label,
        evidence_code=evidence_code,
        evidence_label=evidence_label,
        requires_confirmation=outcome.requires_confirmation,
    )


def material_contents(judgment: AgentJudgment) -> tuple[AgentMaterialContent, ...]:
    return tuple(
        AgentMaterialContent(
            evidence_code=code,
            label=label,
            summary=f"已登记 Synthetic「{label}」材料元数据；未读取或存储真实文件正文。",
        )
        for code, label in zip(
            judgment.collected_evidence_codes,
            judgment.collected_evidence,
            strict=True,
        )
    )


def citations(
    reason: DisputeReasonCode | None,
    card_network: str | None,
    knowledge_base: KnowledgeBase,
    catalog: RuleCatalog,
) -> tuple[AgentCitation, ...]:
    if reason is None or card_network is None:
        return ()
    entry = knowledge_base.lookup(reason, card_network=card_network)
    if entry.rule_version_id is None:
        return ()

    citation_ids = [entry.rule_version_id]
    if reason is DisputeReasonCode.FRAUD_CARD_NOT_PRESENT and card_network == "VISA":
        citation_ids.append("oceanpayment-threeds-doc")

    citations: list[AgentCitation] = []
    for reference_id in citation_ids:
        detail = catalog.get_rule(reference_id)
        if detail is None:
            continue
        technical = detail.category == "TECHNICAL_CONTEXT"
        # Existing demo wording is preserved here for the separate P0 rules fix.
        claim = (
            "3DS 文档仅解释认证结果留存的技术语境，不参与责任转移、资格或期限判断。"
            if technical
            else "本案按 Visa 10.4 Synthetic 映射准备无卡交易争议材料。"
        )
        citations.append(
            AgentCitation(
                reference_id=detail.rule_version_id,
                reference_type="TECHNICAL_CONTEXT" if technical else "RULE",
                title=f"{detail.scheme} {detail.scheme_reason_code} · {detail.display_name}",
                claim=claim,
                source_document=detail.document.title,
                source_section=detail.source_section,
                source_url=detail.document.source_url,
                verification_status=detail.verification_status,
                limitation=detail.limitation,
            )
        )
    return tuple(citations)


def review_proposal(
    message: str,
    outcome: CopilotOutcome,
    judgment: AgentJudgment,
) -> AgentReviewProposal | None:
    if outcome.intent.value != "PROPOSE_REVIEW_DECISION":
        return None

    rejected = any(word in message for word in ("审核驳回", "审核不通过", "拒绝"))
    conflicts = tuple(f"仍缺少「{label}」" for label in judgment.missing_evidence)
    if rejected:
        review_status = ReviewStatus.REJECTED
        summary = "操作人员提议驳回当前材料审核；确认后才会写入案件。"
        next_action = "确认驳回结论并保留审核审计"
        why = "驳回属于人工审核决定，必须经明确确认后才能持久化。"
    elif conflicts:
        review_status = ReviewStatus.NEEDS_MORE_INFO
        summary = "已识别审核通过意图，但内部材料清单尚未齐备。"
        next_action = f"补充{judgment.missing_evidence[0]}"
        why = "仍有缺失资料，当前不能写入审核通过结论。"
    else:
        review_status = ReviewStatus.APPROVED
        # This legacy review wording is addressed by the separate P0 scope.
        summary = "操作人员确认内部材料已齐备且内容一致；等待确认写入案件。"
        next_action = "生成 Visa 10.4 Synthetic 材料包并预览"
        why = "材料审核通过后，最终 mock 发送仍需经过独立人工审批。"

    return AgentReviewProposal(
        status=review_status.value,
        summary=summary,
        confirmed_materials=judgment.collected_evidence_codes,
        conflicts=conflicts,
        next_action=next_action,
        why=why,
        requires_confirmation=True,
    )


def decision_reason(judgment: AgentJudgment, review_status: str) -> str:
    if review_status == ReviewStatus.APPROVED.value:
        return "内部材料审核已由操作人员确认通过；最终 mock 发送仍受独立人工审批闸门约束。"
    if review_status == ReviewStatus.REJECTED.value:
        return "内部材料审核已由操作人员确认驳回，案件保留审核决定与审计记录。"
    if judgment.missing_evidence:
        return f"内部清单仍缺少 {len(judgment.missing_evidence)} 项材料，暂不能形成通过结论。"
    if judgment.human_gate:
        return "内部清单已齐备；非本人交易属于强制人工复核类别，AI 不会自动判定通过。"
    return "确定性证据门槛已经满足，下一步仍需按案件流程执行人工确认。"


def review_decision(decision: ReviewDecision | None) -> AgentReviewDecision | None:
    if decision is None:
        return None
    return AgentReviewDecision(
        decision_id=decision.decision_id,
        status=decision.status.value,
        revision=decision.case_revision,
        confirmed_by=decision.confirmed_by,
        confirmed_at=decision.confirmed_at.isoformat(),
        audit_event_id=decision.audit_event_id,
    )
