"""Shared merchant/business workspace; explicit demo roles and command receipts."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.application.workspace import WorkspaceService
from oceanpilot.application.workspace_ports import WorkspaceError
from oceanpilot.domain.chargeback import CardNetwork, ChargebackEvidenceCode, DisputeReasonCode
from oceanpilot.domain.security import assert_no_sensitive_data

router = APIRouter(
    prefix="/api/v1/workspace",
    tags=["workspace"],
    responses={
        **COMMON_PROBLEMS,
        403: PROBLEM_RESPONSE,
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
    },
)


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class CreateData(StrictDTO):
    title: StrictStr = Field(default="", max_length=100)
    description: StrictStr = Field(min_length=3, max_length=2000)
    card_network: CardNetwork | None = None
    formal_dispute: StrictBool


class SampleData(StrictDTO):
    sample: Literal["A", "B", "C"]


class ReasonData(StrictDTO):
    reason_code: DisputeReasonCode | None = None


class NetworkData(StrictDTO):
    card_network: CardNetwork


class MaterialData(StrictDTO):
    evidence_code: ChargebackEvidenceCode
    file_name: StrictStr = Field(min_length=1, max_length=180)
    source: Literal["SYNTHETIC_TEMPLATE", "SYNTHETIC_USER_METADATA", "UNKNOWN"]


class WithdrawData(StrictDTO):
    evidence_code: ChargebackEvidenceCode


class ReviewData(StrictDTO):
    expected_rule_fingerprint: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["APPROVED", "NEEDS_MORE_INFO", "REJECTED"]
    summary: StrictStr = Field(min_length=3, max_length=1200)
    scope: list[Literal["材料登记清单", "内部处理门槛", "规则引用来源"]] = Field(
        min_length=1, max_length=3
    )


class ConcernData(StrictDTO):
    kind: Literal["FACT_CONFLICT", "SOURCE_ISSUE", "RULE_CONFLICT"]
    field: StrictStr = Field(min_length=1, max_length=100)
    original_value: StrictStr = Field(max_length=500)
    proposed_value: StrictStr = Field(max_length=500)
    original_source: StrictStr = Field(min_length=1, max_length=120)
    proposed_source: StrictStr = Field(min_length=1, max_length=120)
    summary: StrictStr = Field(min_length=3, max_length=1200)


class ResolveData(StrictDTO):
    concern_id: StrictStr = Field(min_length=1, max_length=128)
    resolution: Literal["KEEP_ORIGINAL", "ACCEPT_PROPOSED", "ACKNOWLEDGE"]
    summary: StrictStr = Field(min_length=3, max_length=1200)


DATA_MODELS = {
    "CREATE_CASE": CreateData,
    "COPY_SAMPLE": SampleData,
    "CONFIRM_REASON": ReasonData,
    "SET_NETWORK": NetworkData,
    "REGISTER_MATERIAL": MaterialData,
    "WITHDRAW_MATERIAL": WithdrawData,
    "FINALIZE": StrictDTO,
    "REVIEW": ReviewData,
    "ADD_CONCERN": ConcernData,
    "RESOLVE_CONCERN": ResolveData,
}


class WorkspaceCommand(StrictDTO):
    command_id: StrictStr = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    action: Literal[
        "CREATE_CASE",
        "COPY_SAMPLE",
        "CONFIRM_REASON",
        "SET_NETWORK",
        "REGISTER_MATERIAL",
        "WITHDRAW_MATERIAL",
        "FINALIZE",
        "REVIEW",
        "ADD_CONCERN",
        "RESOLVE_CONCERN",
    ]
    case_id: StrictStr | None = Field(default=None, max_length=128)
    expected_revision: StrictInt | None = Field(default=None, ge=0)
    data: dict[str, Any]
    confirmed: StrictBool


class SummaryRequest(StrictDTO):
    expected_revision: StrictInt = Field(ge=0)


def demo_identity(
    role: Annotated[str, Header(alias="X-Demo-Role")] = "MERCHANT",
    actor: Annotated[str | None, Header(alias="X-Demo-Actor")] = None,
) -> tuple[str, str]:
    if role not in ("MERCHANT", "BUSINESS"):
        raise HTTPException(403, "只允许已声明的演示角色。")
    actor = (actor or ("演示材料提交方" if role == "MERCHANT" else "演示业务复核员")).strip()
    if not actor or len(actor) > 120:
        raise HTTPException(422, "演示操作人名称不合法。")
    assert_no_sensitive_data({"actor": actor})
    return role, actor


def business_identity(
    identity: Annotated[tuple[str, str], Depends(demo_identity)],
) -> tuple[str, str]:
    if identity[0] != "BUSINESS":
        raise HTTPException(403, "此写操作要求业务复核演示角色。")
    return identity


def get_workspace(request: Request) -> WorkspaceService:
    return request.app.state.workspace


@router.get("/cases")
def list_cases(
    service: Annotated[WorkspaceService, Depends(get_workspace)],
    identity: Annotated[tuple[str, str], Depends(demo_identity)],
) -> dict:
    return {"cases": [service.view(case_id, identity[0]) for case_id in service.store.case_ids()]}


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    service: Annotated[WorkspaceService, Depends(get_workspace)],
    identity: Annotated[tuple[str, str], Depends(demo_identity)],
) -> dict:
    return service.view(case_id, identity[0])


@router.post("/commands")
def command(
    payload: WorkspaceCommand,
    service: Annotated[WorkspaceService, Depends(get_workspace)],
    identity: Annotated[tuple[str, str], Depends(demo_identity)],
) -> dict:
    from pydantic import ValidationError

    try:
        data = DATA_MODELS[payload.action].model_validate(payload.data).model_dump(mode="json")
    except ValidationError:
        raise HTTPException(422, "操作字段不符合当前命令合同，请检查输入。") from None
    if payload.action not in ("CREATE_CASE", "COPY_SAMPLE") and (
        not payload.case_id or payload.expected_revision is None
    ):
        raise HTTPException(422, "写操作必须提供案件编号和当前版本。")
    return service.execute(payload.model_dump() | {"data": data}, *identity)


@router.get("/commands/{command_id}")
def command_status(
    command_id: str,
    service: Annotated[WorkspaceService, Depends(get_workspace)],
    identity: Annotated[tuple[str, str], Depends(demo_identity)],
) -> dict:
    result = service.store.command(command_id, *identity)
    if "receipt" in result:
        result = result | {"case": service.view(result["receipt"]["case_id"], identity[0])}
    return result


@router.post("/cases/{case_id}/summaries")
def create_summary(
    case_id: str,
    payload: SummaryRequest,
    service: Annotated[WorkspaceService, Depends(get_workspace)],
    identity: Annotated[tuple[str, str], Depends(business_identity)],
) -> dict:
    return service.generate_summary(case_id, payload.expected_revision, *identity)


@router.get("/summaries/{summary_id}")
def download_summary(
    summary_id: str,
    service: Annotated[WorkspaceService, Depends(get_workspace)],
    identity: Annotated[tuple[str, str], Depends(demo_identity)],
    format: Literal["html", "json"] = "html",
    locale: Literal["zh", "en"] = "zh",
) -> Response:
    import json

    from oceanpilot.application.workspace_summary import render_summary
    from oceanpilot.web.summary_i18n import localize_summary_html

    result = service.store.summary(summary_id)
    content = (
        localize_summary_html(render_summary(result["snapshot"]), locale)
        if format == "html" and locale == "en"
        else result["html"]
        if format == "html"
        else json.dumps(result["snapshot"], ensure_ascii=False, indent=2)
    )
    return Response(
        content,
        media_type="text/html" if format == "html" else "application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="case-review-{result["snapshot"]["summary_id"]}.{format}"'
            ),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        },
    )


async def workspace_error_handler(request: Request, exc: WorkspaceError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status,
        media_type="application/problem+json",
        content={
            "type": f"urn:oceanpilot:{exc.code}",
            "title": exc.code,
            "status": exc.status,
            "detail": exc.message,
        },
    )
