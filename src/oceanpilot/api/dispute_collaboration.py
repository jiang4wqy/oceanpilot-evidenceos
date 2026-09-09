"""Trusted-session API for shared threads and real synthetic file objects."""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from oceanpilot.adapters.persistence.dispute_collaboration import SQLiteDisputeCollaborationStore
from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.disputes import Identity
from oceanpilot.application.dispute_collaboration import (
    DisputeCollaborationScheduler,
    DisputeCollaborationService,
)
from oceanpilot.application.dispute_views import case_view

router = APIRouter(
    tags=["V2.1 Case Collaboration"],
    responses={
        **COMMON_PROBLEMS,
        403: PROBLEM_RESPONSE,
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
        415: PROBLEM_RESPONSE,
    },
)
_PREFIX = "/api/v2/cases/{case_id}/collaboration"


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class MessageDTO(StrictDTO):
    command_id: StrictStr = Field(min_length=1, max_length=200)
    scope: Literal["SHARED", "OP_INTERNAL"] = "SHARED"
    message: StrictStr = Field(min_length=1, max_length=6000)
    ask_agent: StrictBool = False


class ReadDTO(StrictDTO):
    scope: Literal["SHARED", "OP_INTERNAL"] = "SHARED"
    cursor: StrictInt = Field(ge=0)


class HandoffDTO(StrictDTO):
    command_id: StrictStr = Field(min_length=1, max_length=200)
    scope: Literal["SHARED", "OP_INTERNAL"] = "SHARED"
    reason: StrictStr = Field(min_length=1, max_length=2000)
    assignee_id: StrictStr | None = Field(default=None, max_length=100)
    follow_up_at: StrictStr | None = Field(default=None, max_length=60)


class HandoffUpdateDTO(StrictDTO):
    command_id: StrictStr = Field(min_length=1, max_length=200)
    action: Literal["CLAIM", "RESOLVE"]
    reason: StrictStr = Field(min_length=1, max_length=2000)
    follow_up_at: StrictStr | None = Field(default=None, max_length=60)


class FileDTO(StrictDTO):
    command_id: StrictStr = Field(min_length=1, max_length=200)
    expected_revision: StrictInt = Field(ge=1)
    code: StrictStr = Field(min_length=1, max_length=100)
    title: StrictStr = Field(min_length=1, max_length=180)
    filename: StrictStr = Field(min_length=1, max_length=180)
    mime_type: Literal["text/plain", "application/json", "text/csv"]
    content_base64: StrictStr = Field(min_length=1, max_length=2800000)
    evidence_id: StrictStr | None = Field(default=None, max_length=100)


def initialize_dispute_collaboration(app, db_path, *, start_scheduler=True):
    """Only call inside lifespan, after disputes and dispute_agent are initialized."""
    service = DisputeCollaborationService(
        SQLiteDisputeCollaborationStore(db_path),
        app.state.disputes,
        app.state.dispute_agent,
        clock=app.state.dispute_agent.clock,
    )
    app.state.dispute_collaboration = service
    app.state.disputes.evidence_objects = service
    app.state.disputes.collaboration = service
    app.state.dispute_agent.collaboration_provider = service
    for case in app.state.disputes.list_cases(
        {"role": "AGENT", "actor_id": "oceanpilot-workflow-agent"}
    ):
        service.observe_business(case, "STARTUP_PUBLIC_HISTORY")
    app.state.dispute_collaboration_scheduler = DisputeCollaborationScheduler(service)
    if start_scheduler:
        app.state.dispute_collaboration_scheduler.start()
    return service


@router.get(_PREFIX)
def activity(
    case_id: str,
    request: Request,
    identity: Identity,
    scope: Literal["SHARED", "OP_INTERNAL"] = "SHARED",
    after: int = 0,
):
    return request.app.state.dispute_collaboration.activity(case_id, identity, scope, after)


@router.post(_PREFIX + "/messages")
def message(case_id: str, payload: MessageDTO, request: Request, identity: Identity):
    return request.app.state.dispute_collaboration.post_message(
        case_id, identity, **payload.model_dump()
    )


@router.post(_PREFIX + "/read")
def read(case_id: str, payload: ReadDTO, request: Request, identity: Identity):
    return request.app.state.dispute_collaboration.mark_read(
        case_id, identity, **payload.model_dump()
    )


@router.post(_PREFIX + "/handoffs")
def handoff(case_id: str, payload: HandoffDTO, request: Request, identity: Identity):
    return request.app.state.dispute_collaboration.create_handoff(
        case_id, identity, **payload.model_dump()
    )


@router.post(_PREFIX + "/handoffs/{handoff_id}")
def update_handoff(
    case_id: str, handoff_id: str, payload: HandoffUpdateDTO, request: Request, identity: Identity
):
    return request.app.state.dispute_collaboration.update_handoff(
        case_id, identity, handoff_id, **payload.model_dump()
    )


@router.post(_PREFIX + "/files")
def upload(case_id: str, payload: FileDTO, request: Request, identity: Identity):
    result = request.app.state.dispute_collaboration.upload_file(
        case_id, identity, **payload.model_dump()
    )
    # Root installs the same response projector used for command receipts.
    projector = getattr(request.app.state, "v21_project_result", None)
    if callable(projector):
        return projector(result, identity)
    result["case"] = case_view(result["case"], identity, request.app.state.disputes.access_policy)
    return result


@router.get(_PREFIX + "/files/{object_id}")
def download(case_id: str, object_id: str, request: Request, identity: Identity):
    obj = request.app.state.dispute_collaboration.download_file(case_id, object_id, identity)
    return Response(
        obj["content"],
        media_type=obj["mime_type"],
        headers={
            "Content-Disposition": "inline; filename*=UTF-8''" + quote(obj["filename"]),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )
