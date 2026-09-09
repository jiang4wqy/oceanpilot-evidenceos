"""Strict HTTP boundary for the synthetic OceanPayment-first V2 workflow."""

from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.dispute_commands_v21 import DATA_MODELS as V21_DATA_MODELS
from oceanpilot.domain.dispute import fingerprint, require
from oceanpilot.domain.dispute_rules import case_plan, rule_catalog

router = APIRouter(
    tags=["OceanPilot V2"],
    responses={
        **COMMON_PROBLEMS,
        403: PROBLEM_RESPONSE,
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
    },
)
ROLES = ("OPERATOR", "RISK_OFFICER", "SUPERVISOR", "ADMIN", "MERCHANT", "AGENT")


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class IntakeData(StrictDTO):
    merchant_id: StrictStr = Field(min_length=1, max_length=100)
    transaction_id: StrictStr = Field(min_length=1, max_length=100)
    scheme: StrictStr = Field(min_length=1, max_length=30)
    channel: StrictStr = Field(min_length=1, max_length=30)
    reason_code: StrictStr = Field(min_length=1, max_length=100)
    amount_minor: StrictInt = Field(gt=0, le=10**12)
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    event_id: StrictStr = Field(min_length=1, max_length=100)
    case_template_id: StrictStr | None = Field(default=None, min_length=1, max_length=100)
    upstream_case_id: StrictStr | None = Field(default=None, max_length=100)
    received_at: StrictStr | None = Field(default=None, max_length=60)


class RuleData(StrictDTO):
    allowed_actions: list[Literal["ACCEPT", "CONTEST"]] = Field(min_length=1, max_length=2)
    source_id: StrictStr = Field(min_length=1, max_length=160)
    source_locator: StrictStr = Field(min_length=1, max_length=500)
    rule_version: StrictStr = Field(min_length=1, max_length=100)
    external_deadline: StrictStr = Field(min_length=10, max_length=60)
    merchant_deadline: StrictStr | None = Field(default=None, max_length=60)
    internal_deadline: StrictStr | None = Field(default=None, max_length=60)
    required_evidence: list[StrictStr] | None = Field(default=None, min_length=1, max_length=30)
    reason: StrictStr = Field(min_length=3, max_length=1000)


class PublishData(StrictDTO):
    message: StrictStr = Field(default="请确认接受争议或继续抗辩。", max_length=1000)
    required: StrictBool = True


class DecisionData(StrictDTO):
    decision: Literal["ACCEPT", "CONTEST", "NO_RESPONSE", "AUTHORIZED_WAIVER"]
    reason: StrictStr = Field(min_length=3, max_length=1000)
    authorization_reference: StrictStr | None = Field(default=None, max_length=160)


class EvidenceData(StrictDTO):
    code: StrictStr = Field(min_length=1, max_length=100)
    title: StrictStr = Field(min_length=1, max_length=180)
    source_channel: Literal["PORTAL", "FEISHU", "EMAIL", "MOCK"] = "PORTAL"
    reference: StrictStr = Field(min_length=1, max_length=500)
    notes: StrictStr = Field(default="", max_length=2000)
    evidence_id: StrictStr | None = Field(default=None, max_length=100)


class WithdrawData(StrictDTO):
    evidence_id: StrictStr = Field(min_length=1, max_length=100)
    reason: StrictStr = Field(min_length=3, max_length=1000)


class ReviewData(StrictDTO):
    decision: Literal["PASS", "REVISION", "ACCEPT"]
    reason: StrictStr = Field(min_length=3, max_length=1000)


class DraftData(StrictDTO):
    draft: StrictStr | None = Field(default=None, max_length=10000)


class ApprovalData(StrictDTO):
    package_id: StrictStr | None = Field(default=None, max_length=100)
    reason: StrictStr = Field(min_length=3, max_length=1000)
    pii_checked: StrictBool


class SubmitData(StrictDTO):
    package_id: StrictStr | None = Field(default=None, max_length=100)


class OutcomeData(StrictDTO):
    event_id: StrictStr = Field(min_length=1, max_length=100)
    outcome: Literal[
        "UNKNOWN", "WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN", "OTHER"
    ]
    final: StrictBool
    source: StrictStr = Field(min_length=1, max_length=160)
    reason: StrictStr = Field(default="", max_length=1000)
    next_stage: Literal["REPRESENTMENT", "PRE_ARBITRATION", "ARBITRATION", "OTHER"] | None = None


class StageData(StrictDTO):
    stage: Literal["REPRESENTMENT", "PRE_ARBITRATION", "ARBITRATION", "OTHER"]
    event_id: StrictStr = Field(min_length=1, max_length=100)
    source: StrictStr = Field(min_length=1, max_length=160)


class FinancialData(StrictDTO):
    event_id: StrictStr = Field(min_length=1, max_length=100)
    kind: Literal["DEBIT", "CREDIT", "REFUND", "FEE", "ADJUSTMENT"]
    amount_minor: StrictInt = Field(ge=-(10**12), le=10**12)
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    source: StrictStr = Field(min_length=1, max_length=160)
    reference: StrictStr = Field(min_length=1, max_length=500)


class ReconcileData(StrictDTO):
    status: Literal["RECONCILED", "DISCREPANCY", "NOT_APPLICABLE"]
    expected_net_minor: StrictInt = Field(ge=-(10**12), le=10**12)
    reason: StrictStr = Field(min_length=3, max_length=1000)
    reference: StrictStr = Field(min_length=1, max_length=500)


class NotifyData(StrictDTO):
    message: StrictStr = Field(default="案件结果与资金核对已完成，请查看 Portal。", max_length=1000)
    channel: Literal["PORTAL"] = "PORTAL"
    reference: StrictStr | None = Field(default=None, max_length=500)


class CommentData(StrictDTO):
    message: StrictStr = Field(min_length=1, max_length=2000)
    channel: Literal["PORTAL"] = "PORTAL"


class KnowledgeData(StrictDTO):
    summary: StrictStr = Field(min_length=3, max_length=2000)
    pattern: StrictStr = Field(min_length=3, max_length=2000)


class KnowledgeReviewData(StrictDTO):
    candidate_id: StrictStr = Field(min_length=1, max_length=100)
    decision: Literal["APPROVE", "REJECT"]
    reason: StrictStr = Field(min_length=3, max_length=1000)


DATA_MODELS = {
    "INTAKE": IntakeData,
    "CONFIRM_RULE": RuleData,
    "PUBLISH_TASK": PublishData,
    "MERCHANT_DECISION": DecisionData,
    "REGISTER_EVIDENCE": EvidenceData,
    "WITHDRAW_EVIDENCE": WithdrawData,
    "SUBMIT_EVIDENCE": StrictDTO,
    "REVIEW": ReviewData,
    "BUILD_PACKAGE": DraftData,
    "APPROVE_PACKAGE": ApprovalData,
    "SUBMIT": SubmitData,
    "RECORD_OUTCOME": OutcomeData,
    "NEXT_STAGE": StageData,
    "RECORD_FINANCIAL": FinancialData,
    "RECONCILE": ReconcileData,
    "NOTIFY_MERCHANT": NotifyData,
    "CLOSE": StrictDTO,
    "COMMENT": CommentData,
    "MONITOR_SLA": StrictDTO,
    "KNOWLEDGE_CANDIDATE": KnowledgeData,
    "APPROVE_KNOWLEDGE": KnowledgeReviewData,
    **V21_DATA_MODELS,
}


class ProposalOrigin(StrictDTO):
    run_id: StrictStr = Field(min_length=1, max_length=200)
    proposal_id: StrictStr = Field(min_length=1, max_length=200)
    scope: Literal["SHARED", "OP_INTERNAL", "MERCHANT", "OPERATIONS"]
    original_revision: StrictInt = Field(ge=1)


class DisputeCommand(StrictDTO):
    command_id: StrictStr = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    action: StrictStr = Field(min_length=1, max_length=50)
    case_id: StrictStr | None = Field(default=None, max_length=100)
    expected_revision: StrictInt | None = Field(default=None, ge=0)
    confirmed: StrictBool
    data: dict[str, Any]
    proposal_origin: ProposalOrigin | None = None


def v2_identity(request: Request) -> dict:
    from oceanpilot.api.dispute_identity import session_identity

    identity = session_identity(request)
    require(identity["role"] in ROLES, "FORBIDDEN", "此账号不能执行业务操作。", 403)
    return identity


Identity = Annotated[dict[str, str], Depends(v2_identity)]


async def dispute_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "status": exc.status,
            "title": exc.code,
            "code": exc.code,
            "detail": exc.message,
        },
    )


@router.get("/api/v2/cases")
def list_cases(
    request: Request,
    identity: Identity,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
    q: Annotated[str, Query(max_length=100)] = "",
    queue: Literal[
        "ALL",
        "URGENT",
        "MERCHANT",
        "EVIDENCE",
        "REVIEW",
        "SUBMISSION",
        "FINANCIAL",
        "PROCESSING",
        "CLOSED",
    ] = "ALL",
    assigned_to: Annotated[str, Query(max_length=100)] = "",
) -> dict:
    from oceanpilot.adapters.persistence.dispute_queue import DisputeQueueReader

    service = request.app.state.disputes
    return DisputeQueueReader(service.store, service.access_policy).read(
        identity,
        limit=limit,
        offset=offset,
        query=q,
        queue=queue,
        assigned_to=assigned_to,
        now=service.clock(),
    )


@router.get("/api/v2/cases/{case_id}")
def get_case(case_id: str, request: Request, identity: Identity) -> dict:
    from oceanpilot.api.dispute_presenter import present_case

    service = request.app.state.disputes
    return present_case(service.get_case(case_id, identity), identity, service)


@router.post("/api/v2/commands", responses={410: PROBLEM_RESPONSE})
def command(payload: DisputeCommand, request: Request, identity: Identity) -> dict:
    if payload.action == "INTAKE":
        require(
            identity["role"] == "OPERATOR",
            "FORBIDDEN",
            "Only an authorized Operator can receive source events",
            403,
        )
        require(
            False,
            "NORMALIZED_INTAKE_REQUIRED",
            "Use /api/v2/intake/events with source times and a registered synthetic transaction",
            410,
        )
    model = DATA_MODELS.get(payload.action)
    if model is None:
        raise HTTPException(422, "不支持的 V2 命令。")
    try:
        data = model.model_validate(payload.data).model_dump(exclude_none=True)
    except ValidationError as exc:
        errors = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors(include_input=False, include_context=False)
        ]
        raise HTTPException(422, {"message": "请核对标出的操作字段。", "fields": errors}) from None
    if payload.action != "INTAKE" and (not payload.case_id or payload.expected_revision is None):
        raise HTTPException(422, "命令必须绑定案件及当前版本。")
    from oceanpilot.api.dispute_presenter import present_result

    service = request.app.state.disputes
    normalized = payload.model_dump(exclude={"proposal_origin"}) | {"data": data}
    if payload.proposal_origin is not None:
        normalized["proposal_origin"] = payload.proposal_origin.model_dump()
    return present_result(service.execute(normalized, identity), identity, service)


@router.get("/api/v2/cases/{case_id}/plan")
def plan(case_id: str, request: Request, identity: Identity) -> dict:
    case = request.app.state.disputes.get_case(case_id, identity)
    result = case_plan(case)
    # Only approved, redacted patterns are eligible for reuse. Do not return
    # merchant identifiers, evidence references or free-form conversation history.
    if identity["role"] != "MERCHANT":
        for item in request.app.state.disputes.list_cases(identity):
            if item.get("scheme") != case.get("scheme") or item.get("reason_code") != case.get(
                "reason_code"
            ):
                continue
            for candidate in item.get("knowledge_candidates", []):
                if candidate.get("status") == "APPROVED":
                    result["similar_cases"].append(
                        {k: candidate.get(k) for k in ("id", "summary", "pattern", "status")}
                    )
    from oceanpilot.api.dispute_presenter import present_plan

    return present_plan(result, identity, case, request.app.state.disputes)


@router.get("/api/v2/rules")
def rules(identity: Identity) -> dict:
    return {"rules": rule_catalog(), "production_eligible": False}


class AgentRunRequest(StrictDTO):
    expected_revision: StrictInt = Field(ge=1)


class AgentMessageRequest(AgentRunRequest):
    message: StrictStr = Field(min_length=1, max_length=6000)


class AgentProposalRequest(AgentRunRequest):
    command_id: StrictStr = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    confirmed: StrictBool


def _activity(case_id: str, request: Request, identity: dict) -> dict:
    result = request.app.state.dispute_agent.get_activity(case_id, identity)
    result["runtime"] = {
        **request.app.state.agent_runtime,
        "analysis_pending": request.app.state.dispute_agent_events.is_pending(case_id),
    }
    return result


@router.get("/api/v2/cases/{case_id}/agent")
def agent_activity(case_id: str, request: Request, identity: Identity) -> dict:
    return _activity(case_id, request, identity)


@router.post("/api/v2/cases/{case_id}/agent/run")
def agent_run(case_id: str, payload: AgentRunRequest, request: Request, identity: Identity) -> dict:
    case = request.app.state.disputes.get_case(case_id, identity)
    require(
        case["revision"] == payload.expected_revision,
        "REVISION_CONFLICT",
        "Refresh the case before requesting Agent analysis",
    )
    request.app.state.dispute_agent.observe(case, "USER_RUN")
    request.app.state.dispute_agent_events.schedule(case, "USER_RUN")
    return _activity(case_id, request, identity)


@router.post("/api/v2/cases/{case_id}/agent/messages", deprecated=True)
def agent_message(
    case_id: str, payload: AgentMessageRequest, request: Request, identity: Identity
) -> dict:
    case = request.app.state.disputes.get_case(case_id, identity)
    require(
        case["revision"] == payload.expected_revision,
        "REVISION_CONFLICT",
        "案件已变化，请刷新后提问。",
    )
    # Compatibility transport now joins the same public journal as the main UI.
    # Previously saved private conversations remain available only as history.
    result = request.app.state.dispute_collaboration.post_message(
        case_id,
        identity,
        "compat-message-" + str(uuid4()),
        payload.message,
        scope="SHARED",
        ask_agent=True,
    )
    require(
        result.get("agent_status") != "CASE_CHANGED",
        "REVISION_CONFLICT",
        "问题已保留；案件在分析期间发生变化，请重新请求分析。",
    )
    reply = result["agent_reply"]
    conversation = next(
        item
        for item in request.app.state.dispute_agent.store.list_conversations(
            case_id, audience="SHARED"
        )
        if item["id"] == reply["conversation_id"]
    )
    response = {
        key: conversation.get(key)
        for key in (
            "answer",
            "model_analysis",
            "provider",
            "source",
            "model",
            "provider_fallback",
            "reference_notice",
            "trigger",
            "source_citations",
            "intent",
            "audience",
            "scope",
            "knowledge_retrieval",
            "tool_steps",
        )
    }
    current = _activity(case_id, request, identity)
    return response | {
        "run": current["run"],
        "proposals": current["proposals"],
        "conversation_id": conversation["id"],
        "message_id": result["message"]["id"],
    }


@router.post("/api/v2/cases/{case_id}/agent/proposals/{proposal_id}/execute")
def agent_proposal(
    case_id: str,
    proposal_id: str,
    payload: AgentProposalRequest,
    request: Request,
    identity: Identity,
) -> dict:
    proposal = request.app.state.dispute_agent.get_proposal(case_id, proposal_id, identity)
    require(
        payload.confirmed is True,
        "CONFIRMATION_REQUIRED",
        "Review the prepared action and explicitly confirm it",
    )
    require(
        payload.expected_revision == proposal["expected_revision"],
        "REVISION_CONFLICT",
        "The request must use the proposal's case revision",
    )
    require(
        not proposal.get("required_inputs"),
        "PROPOSAL_INPUT_REQUIRED",
        "Complete the required fields in the reviewed command form",
        422,
    )
    require(
        identity["role"] == proposal["owner"],
        "FORBIDDEN",
        "This proposal requires its assigned decision maker",
        403,
    )
    # The persisted kernel proposal is the only source of the action and payload.
    # The command store checks actor-bound idempotency before current-revision CAS,
    # allowing an exact retry after success while rejecting a new stale command.
    command_payload = DisputeCommand(
        command_id=payload.command_id,
        case_id=case_id,
        expected_revision=payload.expected_revision,
        confirmed=True,
        action=proposal["action"],
        data=proposal["data"],
    )
    legacy_command = command_payload.model_dump(exclude={"proposal_origin"}) | {
        "data": DATA_MODELS[proposal["action"]]
        .model_validate(proposal["data"])
        .model_dump(exclude_none=True)
    }
    saved_fingerprint = request.app.state.disputes.store.get_command_fingerprint(payload.command_id)
    # Keep exact historical retries byte-compatible; the atomic store still
    # enforces the original actor. Every new confirmation gets trusted lineage.
    if saved_fingerprint != fingerprint(legacy_command):
        run = request.app.state.dispute_agent.store.get_run(case_id, proposal["expected_revision"])
        require(
            run is not None and any(p["id"] == proposal_id for p in run["proposals"]),
            "PROPOSAL_NOT_FOUND",
            "Proposal run not found",
            404,
        )
        command_payload.proposal_origin = ProposalOrigin(
            run_id=run["id"],
            proposal_id=proposal_id,
            scope=proposal.get("scope", "SHARED"),
            original_revision=proposal["expected_revision"],
        )
    return command(command_payload, request, identity)


@router.get("/api/v2/governance")
def governance(request: Request, identity: Identity) -> dict:
    if identity["role"] not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(403, "治理页面需要管理员或主管演示角色。")
    cases = request.app.state.disputes.list_cases(identity)
    from oceanpilot.domain.dispute import ACTION_ROLES

    return {
        "integrations": {
            "upstream": "MOCK / DISABLED — 无生产发送",
            "feishu": "SIGNED_CALLBACK_READY"
            if getattr(request.app.state, "dispute_feishu", None)
            else "UNCONFIGURED",
            "email": "PORT_DEFINED_ONLY",
            "portal": "LOCAL_SYNTHETIC",
            "model": request.app.state.agent_runtime["mode"],
        },
        "rules": rule_catalog(),
        "knowledge": [
            k | {"case_id": c["id"]} for c in cases for k in c.get("knowledge_candidates", [])
        ],
        "metrics": {
            "cases": len(cases),
            "closed": sum(c["work_status"] == "CLOSED" for c in cases),
            "pending_financial": sum(
                c["financial_status"] in ("PENDING", "DISCREPANCY") for c in cases
            ),
        },
        "permissions": {
            role: sorted(a for a, roles in ACTION_ROLES.items() if role in roles) for role in ROLES
        },
        "open_confirmation_points": [
            "各渠道 OP 法律与清算角色",
            "真实上游事件字段",
            "商户授权与未响应处置",
            "正式规则和 SLA",
            "提交回执及结果语义",
            "财务核对字段与费用规则",
        ],
        "boundary": "本地合成案例；身份来自服务端账号会话及案件授权。尚未接入生产 SSO 与真实上游。",
    }


class DemoData(StrictDTO):
    scenario: Literal["A", "B", "C", "D"]


@router.get("/api/v2/capabilities")
def capabilities(identity: Identity) -> dict:
    from oceanpilot.domain.dispute import ACTION_ROLES

    return {
        "role": identity["role"],
        "intake_events": identity["role"] == "OPERATOR",
        "actions": sorted(
            a for a, roles in ACTION_ROLES.items() if identity["role"] in roles and a != "INTAKE"
        ),
    }


@router.get("/api/v2/command-schemas")
def command_schemas(identity: Identity) -> dict:
    from oceanpilot.api.dispute_presenter import command_schema
    from oceanpilot.domain.dispute import ACTION_ROLES

    return {
        "commands": {
            action: command_schema(model)
            for action, model in DATA_MODELS.items()
            if identity["role"] in ACTION_ROLES.get(action, set()) and action != "INTAKE"
        }
    }


@router.post("/api/v2/demo", responses={410: PROBLEM_RESPONSE})
def demo(payload: DemoData, request: Request, identity: Identity) -> dict:
    require(
        identity["role"] == "OPERATOR", "FORBIDDEN", "此入口不能替代商户、风控或主管执行决定。", 403
    )
    require(
        False,
        "NORMALIZED_INTAKE_REQUIRED",
        "请先由独立导演登记合成交易，再经标准事件入口接收；后续由各角色本人处理。",
        410,
    )


@router.get("/api/v2/case-library")
def case_library(request: Request, identity: Identity) -> dict:
    library = request.app.state.dispute_case_library
    return {
        "manifest": library.manifest(),
        "references": library.list_references(limit=100),
        "templates": library.list_templates(),
    }


@router.get("/api/v2/case-library/{template_id}")
def case_library_reference(template_id: str, request: Request, identity: Identity) -> dict:
    library = request.app.state.dispute_case_library
    reference = library.get_reference(template_id)
    require(reference is not None, "NOT_FOUND", "Case reference not found", 404)
    return {"reference": reference, "template": library.get_template(template_id)}


@router.get("/v2/operations", response_class=HTMLResponse, include_in_schema=False)
@router.get("/v2/operations/library", response_class=HTMLResponse, include_in_schema=False)
@router.get("/v2/operations/cases/{case_id}", response_class=HTMLResponse, include_in_schema=False)
def operations_page(request: Request) -> HTMLResponse:
    from oceanpilot.api.dispute_identity import page_access
    from oceanpilot.web.v2.rendering import render_v2_page

    denied = page_access(request, {"OPERATOR", "RISK_OFFICER", "SUPERVISOR"})
    if denied is not None:
        return denied
    return HTMLResponse(render_v2_page("OPERATOR"))


@router.get("/v2/merchant", response_class=HTMLResponse, include_in_schema=False)
@router.get("/v2/merchant/cases/{case_id}", response_class=HTMLResponse, include_in_schema=False)
def merchant_page(request: Request) -> HTMLResponse:
    from oceanpilot.api.dispute_identity import page_access
    from oceanpilot.web.v2.rendering import render_v2_page

    denied = page_access(request, {"MERCHANT"})
    if denied is not None:
        return denied
    return HTMLResponse(render_v2_page("MERCHANT"))


@router.get("/v2/governance", response_class=HTMLResponse, include_in_schema=False)
def governance_page(request: Request) -> HTMLResponse:
    from oceanpilot.api.dispute_identity import page_access
    from oceanpilot.web.v2.rendering import render_v2_page

    denied = page_access(request, {"ADMIN", "SUPERVISOR"})
    if denied is not None:
        return denied
    return HTMLResponse(render_v2_page("ADMIN"))
