from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Response, status

from oceanpilot.api.dependencies import get_case_service
from oceanpilot.api.errors import FeatureDeferred
from oceanpilot.api.schemas import CreateCaseRequest, EvidenceCreateRequest
from oceanpilot.application.case_service import CaseService
from oceanpilot.domain.enums import WriteOutcome
from oceanpilot.domain.models import CaseView, UUID4Str

router = APIRouter(prefix="/api/v1/cases")


@router.post("", response_model=CaseView, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CreateCaseRequest,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseView:
    view = service.create_case(payload.to_command(str(uuid4()), str(uuid4())))
    response.headers["Location"] = f"/api/v1/cases/{view.case.case_id}"
    return view


@router.get("/{case_id}", response_model=CaseView)
def get_case(
    case_id: UUID4Str,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseView:
    return service.get_case(case_id)


@router.post(
    "/{case_id}/evidence",
    response_model=CaseView,
    status_code=status.HTTP_201_CREATED,
)
def add_evidence(
    case_id: UUID4Str,
    payload: EvidenceCreateRequest,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseView:
    result = service.add_evidence(payload.to_command(case_id, str(uuid4()), str(uuid4())))
    response.status_code = (
        status.HTTP_201_CREATED if result.outcome is WriteOutcome.CREATED else status.HTTP_200_OK
    )
    return result.case_view


@router.post("/{case_id}/diagnose", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def diagnose(case_id: UUID4Str) -> None:
    del case_id
    raise FeatureDeferred()
