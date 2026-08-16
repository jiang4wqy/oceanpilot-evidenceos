"""Natural-language agent gateway for the competition demo.

The model helps classify and phrase the next question. Deterministic chargeback
rules remain the source of evidence readiness, routing, and human-gate status.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.application.case_copilot import CaseCopilotAgent, CopilotOutcome
from oceanpilot.application.case_review import (
    AgentTurnRecord,
    CaseReviewStore,
    ReviewDecision,
    ReviewStatus,
)
from oceanpilot.application.channels import Delivery, InboundKind, NormalizedInbound
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.knowledge_base import KnowledgeBase, RuleCatalog
from oceanpilot.domain.chargeback import (
    ChargebackEvidenceCode,
    DisputeReasonCode,
    assess_chargeback,
    required_evidence_for,
)
from oceanpilot.domain.evidence_catalog import label_of
from oceanpilot.domain.reason_catalog import reason_label
from oceanpilot.domain.security import assert_no_sensitive_data

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class AgentTurnRequest(_StrictModel):
    message: StrictStr = Field(min_length=3, max_length=2_000)
    locale: Literal["zh-CN", "en-US"] = "zh-CN"
    case_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    card_network: Literal["VISA", "MASTERCARD", "AMEX"] | None = None
    trigger: Literal[
        "USER_MESSAGE",
        "CASE_OPENED",
        "REASON_CONFIRMED",
        "EVIDENCE_SUBMITTED",
        "EVIDENCE_WITHDRAWN",
        "REVIEW_CONFIRMED",
    ] = "USER_MESSAGE"


class AgentRuntimeDTO(_StrictModel):
    mode: Literal[
        "DEEPSEEK_LIVE",
        "CLAUDE_LIVE",
        "INJECTED_MODEL",
        "OFFLINE_FALLBACK",
    ]
    provider: StrictStr
    model: StrictStr


class AgentJudgmentDTO(_StrictModel):
    problem_type: StrictStr
    phase: StrictStr
    confirmed_facts: tuple[StrictStr, ...]
    uncertain_facts: tuple[StrictStr, ...]
    evidence_readiness: StrictStr
    responsible_team: StrictStr
    next_action: StrictStr
    human_gate: StrictBool
    decision_summary: StrictStr
    missing_evidence_codes: tuple[StrictStr, ...]
    missing_evidence: tuple[StrictStr, ...]
    collected_evidence_codes: tuple[StrictStr, ...]
    collected_evidence: tuple[StrictStr, ...]
    next_evidence_code: StrictStr | None
    next_evidence_label: StrictStr | None


class AgentRecommendedActionDTO(_StrictModel):
    kind: Literal["OPEN_EVIDENCE_MODAL", "OPEN_CASE_DETAIL", "NONE"]
    label: StrictStr
    evidence_code: StrictStr | None = None
    evidence_label: StrictStr | None = None
    requires_confirmation: StrictBool


class AgentTraceStepDTO(_StrictModel):
    step: int = Field(ge=1)
    actor: StrictStr
    action: StrictStr
    status: Literal["COMPLETED", "WAITING", "BLOCKED"]
    source: StrictStr
    output_summary: StrictStr


class AgentMaterialContentDTO(_StrictModel):
    evidence_code: StrictStr
    label: StrictStr
    summary: StrictStr


class AgentCitationDTO(_StrictModel):
    reference_id: StrictStr
    reference_type: Literal["RULE", "TECHNICAL_CONTEXT"]
    title: StrictStr
    claim: StrictStr
    source_document: StrictStr
    source_section: StrictStr | None = None
    source_url: StrictStr
    verification_status: StrictStr
    limitation: StrictStr


class AgentReviewProposalDTO(_StrictModel):
    status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    summary: StrictStr
    confirmed_materials: tuple[StrictStr, ...]
    conflicts: tuple[StrictStr, ...]
    next_action: StrictStr
    why: StrictStr
    requires_confirmation: Literal[True]


class AgentReviewDecisionDTO(_StrictModel):
    decision_id: StrictStr
    status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    revision: StrictInt
    confirmed_by: StrictStr
    confirmed_at: StrictStr
    audit_event_id: StrictStr


class AgentTurnResponse(_StrictModel):
    synthetic: Literal[True]
    result: Literal["CREATED", "REPLAYED"] = "CREATED"
    turn_kind: Literal["CASE_CREATED", "CASE_ANALYZED"]
    source_turn_id: StrictStr
    case_id: StrictStr
    card_network: Literal["VISA", "MASTERCARD", "AMEX"] | None = None
    case_revision: StrictInt = Field(ge=0)
    trigger: StrictStr
    intent: StrictStr
    assistant_message: StrictStr
    analysis_summary: StrictStr
    review_status: StrictStr
    material_contents: tuple[AgentMaterialContentDTO, ...]
    decision_reason: StrictStr
    citations: tuple[AgentCitationDTO, ...]
    review_proposal: AgentReviewProposalDTO | None = None
    review_decision: AgentReviewDecisionDTO | None = None
    human_boundary: StrictStr
    runtime: AgentRuntimeDTO
    judgment: AgentJudgmentDTO
    recommended_action: AgentRecommendedActionDTO
    agent_trace: tuple[AgentTraceStepDTO, ...]


class ConfirmAgentReviewRequest(_StrictModel):
    source_turn_id: StrictStr = Field(min_length=1, max_length=128)
    case_revision: StrictInt = Field(ge=0)
    confirmed_by: StrictStr = Field(min_length=1, max_length=128)


class ConfirmAgentReviewResponse(_StrictModel):
    result: Literal["CREATED", "REPLAYED"]
    decision_id: StrictStr
    case_id: StrictStr
    case_revision: StrictInt
    review_status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    audit_event_id: StrictStr
    reanalyze: Literal[True]


def get_agent_service(request: Request) -> ChargebackChannelService:
    return request.app.state.chargeback_channel_service


def get_case_copilot(request: Request) -> CaseCopilotAgent:
    return request.app.state.case_copilot


def get_review_store(request: Request) -> CaseReviewStore:
    return request.app.state.case_review_store


def get_knowledge_base(request: Request) -> KnowledgeBase:
    return request.app.state.rule_catalog


def get_rule_catalog(request: Request) -> RuleCatalog:
    return request.app.state.rule_catalog


def _runtime(request: Request) -> AgentRuntimeDTO:
    return AgentRuntimeDTO.model_validate(request.app.state.agent_runtime)


def _locale(locale: str) -> str:
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


def _assistant_message(delivery: Delivery, *, locale: str) -> str:
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


def _trace_source(source: str | None, runtime: AgentRuntimeDTO) -> str:
    if source == "MODEL":
        return runtime.provider
    if source == "FALLBACK":
        return "DETERMINISTIC_FALLBACK"
    return source or "CASE_STATE"


def _trace(delivery: Delivery, runtime: AgentRuntimeDTO) -> tuple[AgentTraceStepDTO, ...]:
    trace = [
        AgentTraceStepDTO(
            step=1,
            actor="AgentGateway",
            action="接收并规范化用户问题",
            status="COMPLETED",
            source="USER_INPUT",
            output_summary="已生成渠道无关的建案请求",
        ),
        AgentTraceStepDTO(
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
            AgentTraceStepDTO(
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


def _judgment(delivery: Delivery, *, locale: str) -> AgentJudgmentDTO:
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

    next_action = _assistant_message(delivery, locale=locale)
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
    return AgentJudgmentDTO(
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


def _created_action(judgment: AgentJudgmentDTO) -> AgentRecommendedActionDTO:
    if judgment.phase == "NEED_EVIDENCE" and judgment.next_evidence_code is not None:
        return AgentRecommendedActionDTO(
            kind="OPEN_EVIDENCE_MODAL",
            label=f"补交{judgment.next_evidence_label}",
            evidence_code=judgment.next_evidence_code,
            evidence_label=judgment.next_evidence_label,
            requires_confirmation=True,
        )
    return AgentRecommendedActionDTO(
        kind="OPEN_CASE_DETAIL",
        label="查看案件详情",
        requires_confirmation=True,
    )


def _analyzed_trace(
    delivery: Delivery,
    runtime: AgentRuntimeDTO,
    outcome: CopilotOutcome,
) -> tuple[AgentTraceStepDTO, ...]:
    source = runtime.provider if outcome.source == "MODEL" else "DETERMINISTIC_FALLBACK"
    return (
        AgentTraceStepDTO(
            step=1,
            actor="AgentGateway",
            action="接收案件上下文问题",
            status="COMPLETED",
            source="USER_INPUT",
            output_summary="已绑定现有案件，未创建重复案件",
        ),
        AgentTraceStepDTO(
            step=2,
            actor="CaseTool",
            action="读取当前案件确定性快照",
            status="COMPLETED",
            source="SQLITE_CASE_STORE",
            output_summary=f"读取阶段 {delivery.phase}，未修改案件状态",
        ),
        AgentTraceStepDTO(
            step=3,
            actor="CaseCopilot",
            action="理解问题并生成案件说明",
            status="COMPLETED",
            source=source,
            output_summary="模型说明受固定 JSON 合同和案件快照约束",
        ),
        AgentTraceStepDTO(
            step=4,
            actor="HumanGate",
            action="等待操作人员确认推荐动作",
            status="WAITING",
            source="POLICY_BOUNDARY",
            output_summary="Agent 不会直接改变案件或执行资金动作",
        ),
    )


def _analyzed_action(
    outcome: CopilotOutcome,
    judgment: AgentJudgmentDTO,
) -> AgentRecommendedActionDTO:
    evidence_code = outcome.target_evidence_code
    evidence_label = None
    if evidence_code in judgment.missing_evidence_codes:
        index = judgment.missing_evidence_codes.index(evidence_code)
        evidence_label = judgment.missing_evidence[index]
    elif evidence_code is not None:
        evidence_code = judgment.next_evidence_code
        evidence_label = judgment.next_evidence_label
    return AgentRecommendedActionDTO(
        kind=outcome.action_kind.value,
        label=outcome.action_label,
        evidence_code=evidence_code,
        evidence_label=evidence_label,
        requires_confirmation=outcome.requires_confirmation,
    )


def _material_contents(judgment: AgentJudgmentDTO) -> tuple[AgentMaterialContentDTO, ...]:
    return tuple(
        AgentMaterialContentDTO(
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


def _citations(
    reason: DisputeReasonCode | None,
    card_network: str | None,
    knowledge_base: KnowledgeBase,
    catalog: RuleCatalog,
) -> tuple[AgentCitationDTO, ...]:
    if reason is None or card_network is None:
        return ()
    entry = knowledge_base.lookup(reason, card_network=card_network)
    if entry.rule_version_id is None:
        return ()

    citation_ids = [entry.rule_version_id]
    if reason is DisputeReasonCode.FRAUD_CARD_NOT_PRESENT and card_network == "VISA":
        citation_ids.append("oceanpayment-threeds-doc")

    citations: list[AgentCitationDTO] = []
    for reference_id in citation_ids:
        detail = catalog.get_rule(reference_id)
        if detail is None:
            continue
        technical = detail.category == "TECHNICAL_CONTEXT"
        claim = (
            "3DS 文档仅解释认证结果留存的技术语境，不参与责任转移、资格或期限判断。"
            if technical
            else "本案按 Visa 10.4 Synthetic 映射准备无卡交易争议材料。"
        )
        citations.append(
            AgentCitationDTO(
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


def _review_proposal(
    message: str,
    outcome: CopilotOutcome,
    judgment: AgentJudgmentDTO,
) -> AgentReviewProposalDTO | None:
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
        summary = "操作人员确认内部材料已齐备且内容一致；等待确认写入案件。"
        next_action = "生成 Visa 10.4 Synthetic 材料包并预览"
        why = "材料审核通过后，最终 mock 发送仍需经过独立人工审批。"

    return AgentReviewProposalDTO(
        status=review_status.value,
        summary=summary,
        confirmed_materials=judgment.collected_evidence_codes,
        conflicts=conflicts,
        next_action=next_action,
        why=why,
        requires_confirmation=True,
    )


def _decision_reason(judgment: AgentJudgmentDTO, review_status: str) -> str:
    if review_status == ReviewStatus.APPROVED.value:
        return "内部材料审核已由操作人员确认通过；最终 mock 发送仍受独立人工审批闸门约束。"
    if review_status == ReviewStatus.REJECTED.value:
        return "内部材料审核已由操作人员确认驳回，案件保留审核决定与审计记录。"
    if judgment.missing_evidence:
        return f"内部清单仍缺少 {len(judgment.missing_evidence)} 项材料，暂不能形成通过结论。"
    if judgment.human_gate:
        return "内部清单已齐备；非本人交易属于强制人工复核类别，AI 不会自动判定通过。"
    return "确定性证据门槛已经满足，下一步仍需按案件流程执行人工确认。"


def _save_turn(store: CaseReviewStore, response: AgentTurnResponse) -> None:
    proposal = response.review_proposal
    proposal_json = None
    if proposal is not None:
        proposal_json = json.dumps(
            {
                "status": proposal.status,
                "summary": proposal.summary,
                "confirmed_materials": list(proposal.confirmed_materials),
                "citation_ids": [item.reference_id for item in response.citations],
            },
            ensure_ascii=False,
        )
    store.save_turn(
        AgentTurnRecord(
            turn_id=response.source_turn_id,
            case_id=response.case_id,
            case_revision=response.case_revision,
            trigger=response.trigger,
            response_json=response.model_dump_json(),
            proposal_json=proposal_json,
            created_at=datetime.now(UTC),
        )
    )


def _review_decision(decision: ReviewDecision | None) -> AgentReviewDecisionDTO | None:
    if decision is None:
        return None
    return AgentReviewDecisionDTO(
        decision_id=decision.decision_id,
        status=decision.status.value,
        revision=decision.case_revision,
        confirmed_by=decision.confirmed_by,
        confirmed_at=decision.confirmed_at.isoformat(),
        audit_event_id=decision.audit_event_id,
    )


@router.post(
    "/turns",
    response_model=AgentTurnResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**COMMON_PROBLEMS},
)
def create_agent_turn(
    payload: AgentTurnRequest,
    request: Request,
    service: Annotated[ChargebackChannelService, Depends(get_agent_service)],
    copilot: Annotated[CaseCopilotAgent, Depends(get_case_copilot)],
    review_store: Annotated[CaseReviewStore, Depends(get_review_store)],
    knowledge_base: Annotated[KnowledgeBase, Depends(get_knowledge_base)],
    rule_catalog: Annotated[RuleCatalog, Depends(get_rule_catalog)],
) -> AgentTurnResponse:
    assert_no_sensitive_data({"message": payload.message})
    runtime = _runtime(request)
    locale = _locale(payload.locale)
    if payload.case_id is None:
        delivery = service.handle(
            NormalizedInbound(
                kind=InboundKind.OPEN_CASE,
                channel="agent",
                description=payload.message,
                card_network=payload.card_network,
            )
        )
        judgment = _judgment(delivery, locale=locale)
        revision = review_store.current_revision(delivery.case_id)
        response = AgentTurnResponse(
            synthetic=True,
            turn_kind="CASE_CREATED",
            source_turn_id=str(uuid4()),
            case_id=delivery.case_id,
            card_network=delivery.card_network,
            case_revision=revision,
            trigger=payload.trigger,
            intent="OPEN_CASE",
            assistant_message=_assistant_message(delivery, locale=locale),
            analysis_summary=judgment.decision_summary,
            review_status="UNREVIEWED",
            material_contents=_material_contents(judgment),
            decision_reason=_decision_reason(judgment, "UNREVIEWED"),
            citations=_citations(
                DisputeReasonCode(delivery.reason_code) if delivery.reason_code else None,
                delivery.card_network,
                knowledge_base,
                rule_catalog,
            ),
            human_boundary="Agent 只提出建议；案件变更必须由操作人员明确确认。",
            runtime=runtime,
            judgment=judgment,
            recommended_action=_created_action(judgment),
            agent_trace=_trace(delivery, runtime),
        )
        _save_turn(review_store, response)
        return response

    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.GET_CASE,
            channel="agent",
            case_id=payload.case_id,
        )
    )
    if payload.card_network is not None and delivery.card_network != payload.card_network:
        delivery = service.handle(
            NormalizedInbound(
                kind=InboundKind.SET_CARD_NETWORK,
                channel="agent",
                case_id=delivery.case_id,
                card_network=payload.card_network,
                expected_revision=delivery.revision,
            )
        )
    judgment = _judgment(delivery, locale=locale)
    revision = delivery.revision
    if payload.trigger != "USER_MESSAGE":
        replayed = review_store.latest_turn_payload(delivery.case_id, revision)
        if replayed is not None:
            replayed_response = AgentTurnResponse.model_validate_json(replayed)
            if replayed_response.card_network == delivery.card_network:
                return replayed_response.model_copy(update={"result": "REPLAYED"})
    latest_decision = review_store.latest_decision(delivery.case_id, revision)
    review_status = (
        latest_decision.status.value if latest_decision is not None else "UNREVIEWED"
    )
    outcome = copilot.respond(
        payload.message,
        problem_type=judgment.problem_type,
        phase=judgment.phase,
        readiness=judgment.evidence_readiness,
        responsible_team=judgment.responsible_team,
        human_gate=judgment.human_gate,
        missing_codes=judgment.missing_evidence_codes,
        missing_labels=judgment.missing_evidence,
        review_status=review_status,
    )
    citations = _citations(
        DisputeReasonCode(delivery.reason_code) if delivery.reason_code else None,
        delivery.card_network,
        knowledge_base,
        rule_catalog,
    )
    response = AgentTurnResponse(
        synthetic=True,
        turn_kind="CASE_ANALYZED",
        source_turn_id=str(uuid4()),
        case_id=delivery.case_id,
        card_network=delivery.card_network,
        case_revision=revision,
        trigger=payload.trigger,
        intent=outcome.intent.value,
        assistant_message=outcome.assistant_message,
        analysis_summary=outcome.analysis_summary,
        review_status=review_status,
        material_contents=_material_contents(judgment),
        decision_reason=_decision_reason(judgment, review_status),
        citations=citations,
        review_proposal=_review_proposal(payload.message, outcome, judgment),
        review_decision=_review_decision(latest_decision),
        human_boundary="Agent 只提出建议；案件变更必须由操作人员明确确认。",
        runtime=runtime,
        judgment=judgment,
        recommended_action=_analyzed_action(outcome, judgment),
        agent_trace=_analyzed_trace(delivery, runtime, outcome),
    )
    _save_turn(review_store, response)
    return response


@router.post(
    "/cases/{case_id}/review-decisions",
    response_model=ConfirmAgentReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": ConfirmAgentReviewResponse, "description": "Review replayed"},
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
        **COMMON_PROBLEMS,
    },
)
def confirm_agent_review(
    case_id: str,
    payload: ConfirmAgentReviewRequest,
    response: Response,
    review_store: Annotated[CaseReviewStore, Depends(get_review_store)],
) -> ConfirmAgentReviewResponse:
    assert_no_sensitive_data({"confirmed_by": payload.confirmed_by})
    result = review_store.confirm_review(
        case_id=case_id,
        source_turn_id=payload.source_turn_id,
        expected_revision=payload.case_revision,
        confirmed_by=payload.confirmed_by,
    )
    response.status_code = (
        status.HTTP_201_CREATED if result.result == "CREATED" else status.HTTP_200_OK
    )
    decision = result.decision
    return ConfirmAgentReviewResponse(
        result=result.result,
        decision_id=decision.decision_id,
        case_id=decision.case_id,
        case_revision=decision.case_revision,
        review_status=decision.status.value,
        audit_event_id=decision.audit_event_id,
        reanalyze=True,
    )
