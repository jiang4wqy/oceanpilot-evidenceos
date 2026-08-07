from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status

from oceanpilot.api.dependencies import (
    RequestContext,
    get_case_service,
    get_request_context,
)
from oceanpilot.api.schemas import (
    CreateCaseRequest,
    DiagnoseCaseRequest,
    DiagnosisResponse,
    EvidenceCreateRequest,
)
from oceanpilot.application.case_service import CaseService
from oceanpilot.application.commands import DiagnoseCaseCommand
from oceanpilot.domain.enums import WriteOutcome
from oceanpilot.domain.models import CaseView, UUID4Str

router = APIRouter(prefix="/api/v1/cases")

PROBLEM_RESPONSE = {
    "content": {
        "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
    }
}
COMMON_PROBLEMS = {
    422: PROBLEM_RESPONSE,
    500: PROBLEM_RESPONSE,
    503: PROBLEM_RESPONSE,
}


@router.post(
    "",
    response_model=CaseView,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Case created",
            "headers": {
                "Location": {
                    "description": "Canonical case resource",
                    "required": True,
                    "schema": {"type": "string"},
                }
            },
        },
        409: PROBLEM_RESPONSE,
        **COMMON_PROBLEMS,
    },
)
def create_case(
    payload: CreateCaseRequest,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> CaseView:
    view = service.create_case(payload.to_command(context.request_id, context.trace_id))
    response.headers["Location"] = f"/api/v1/cases/{view.case.case_id}"
    return view


@router.get(
    "/{case_id}",
    response_model=CaseView,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def get_case(
    case_id: UUID4Str,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseView:
    return service.get_case(case_id)


@router.post(
    "/{case_id}/evidence",
    response_model=CaseView,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": CaseView, "description": "Evidence replayed"},
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
        **COMMON_PROBLEMS,
    },
)
def add_evidence(
    case_id: UUID4Str,
    payload: EvidenceCreateRequest,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> CaseView:
    result = service.add_evidence(payload.to_command(case_id, context.request_id, context.trace_id))
    response.status_code = (
        status.HTTP_201_CREATED if result.outcome is WriteOutcome.CREATED else status.HTTP_200_OK
    )
    return result.case_view


@router.post(
    "/{case_id}/diagnose",
    response_model=DiagnosisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": DiagnosisResponse, "description": "Diagnosis replayed"},
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
        **COMMON_PROBLEMS,
    },
)
def diagnose(
    case_id: UUID4Str,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    payload: Annotated[DiagnoseCaseRequest | None, Body()] = None,
) -> DiagnosisResponse:
    del payload
    result = service.diagnose(
        DiagnoseCaseCommand(
            case_id=case_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
        )
    )
    response.status_code = (
        status.HTTP_201_CREATED if result.outcome is WriteOutcome.CREATED else status.HTTP_200_OK
    )
    return DiagnosisResponse.from_result(result)
