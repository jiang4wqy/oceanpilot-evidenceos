"""Strict HTTP boundary for the synthetic OceanPayment-first V2 workflow."""

from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.domain.dispute_rules import case_plan, rule_catalog
from oceanpilot.domain.security import assert_no_sensitive_data

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
}


class DisputeCommand(StrictDTO):
    command_id: StrictStr = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    action: StrictStr = Field(min_length=1, max_length=50)
    case_id: StrictStr | None = Field(default=None, max_length=100)
    expected_revision: StrictInt | None = Field(default=None, ge=0)
    confirmed: StrictBool
    data: dict[str, Any]


def v2_identity(
    role: Annotated[str, Header(alias="X-Demo-Role")] = "MERCHANT",
    actor: Annotated[str, Header(alias="X-Demo-Actor")] = "synthetic-user",
    merchant: Annotated[str, Header(alias="X-Demo-Merchant")] = "synthetic-merchant-001",
) -> dict[str, str]:
    if role not in ROLES:
        raise HTTPException(403, "未识别的演示角色。")
    if any(not text.strip() or len(text) > 100 for text in (actor, merchant)):
        raise HTTPException(422, "身份标识不合法。")
    assert_no_sensitive_data({"actor": actor, "merchant": merchant})
    return {"role": role, "actor_id": actor, "merchant_id": merchant}


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
def list_cases(request: Request, identity: Identity) -> dict:
    return {"cases": request.app.state.disputes.list_cases(identity)}


@router.get("/api/v2/cases/{case_id}")
def get_case(case_id: str, request: Request, identity: Identity) -> dict:
    return request.app.state.disputes.get_case(case_id, identity)


@router.post("/api/v2/commands")
def command(payload: DisputeCommand, request: Request, identity: Identity) -> dict:
    model = DATA_MODELS.get(payload.action)
    if model is None:
        raise HTTPException(422, "不支持的 V2 命令。")
    try:
        data = model.model_validate(payload.data).model_dump(exclude_none=True)
    except ValidationError:
        raise HTTPException(422, "操作字段不符合 V2 命令合同。") from None
    if payload.action != "INTAKE" and (not payload.case_id or payload.expected_revision is None):
        raise HTTPException(422, "命令必须绑定案件及当前版本。")
    return request.app.state.disputes.execute(payload.model_dump() | {"data": data}, identity)


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
    return result


@router.get("/api/v2/rules")
def rules(identity: Identity) -> dict:
    return {"rules": rule_catalog(), "production_eligible": False}


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
            "model": "DETERMINISTIC_WORKFLOW_AGENT",
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
        "boundary": "全部案例为合成演示；Header 角色仅用于本地演示，未接生产身份认证。",
    }


class DemoData(StrictDTO):
    scenario: Literal["A", "B", "C", "D"]


@router.get("/api/v2/capabilities")
def capabilities(identity: Identity) -> dict:
    from oceanpilot.domain.dispute import ACTION_ROLES

    return {
        "role": identity["role"],
        "actions": sorted(a for a, roles in ACTION_ROLES.items() if identity["role"] in roles),
    }


@router.post("/api/v2/demo")
def demo(payload: DemoData, request: Request, identity: Identity) -> dict:
    if identity["role"] != "OPERATOR":
        raise HTTPException(403, "只有 OP 运营角色可以接收合成演示案件。")
    from oceanpilot.application.dispute_demo import create_demo

    return create_demo(request.app.state.disputes, payload.scenario, identity, str(uuid4()))


@router.get("/v2/operations", response_class=HTMLResponse, include_in_schema=False)
def operations_page() -> HTMLResponse:
    from oceanpilot.web.v2.rendering import render_v2_page

    return HTMLResponse(render_v2_page("OPERATOR"))


@router.get("/v2/merchant", response_class=HTMLResponse, include_in_schema=False)
def merchant_page() -> HTMLResponse:
    from oceanpilot.web.v2.rendering import render_v2_page

    return HTMLResponse(render_v2_page("MERCHANT"))


@router.get("/v2/governance", response_class=HTMLResponse, include_in_schema=False)
def governance_page() -> HTMLResponse:
    from oceanpilot.web.v2.rendering import render_v2_page

    return HTMLResponse(render_v2_page("ADMIN"))
