"""Normalized synthetic source event endpoints, using trusted account sessions."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from oceanpilot.adapters.persistence.dispute_intake import SQLiteDisputeIntakeStore
from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.dispute_identity import _director
from oceanpilot.api.disputes import Identity
from oceanpilot.application.dispute_intake import DisputeIntakeService

router = APIRouter(
    tags=["V2.1 Normalized Synthetic Intake"],
    responses={
        **COMMON_PROBLEMS,
        403: PROBLEM_RESPONSE,
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
    },
)


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class TransactionData(StrictDTO):
    transaction_id: StrictStr = Field(min_length=1, max_length=100)
    merchant_id: StrictStr = Field(min_length=1, max_length=100)
    channel: StrictStr = Field(min_length=1, max_length=30)
    scheme: StrictStr = Field(min_length=1, max_length=30)
    amount_minor: StrictInt = Field(gt=0, le=10**12)
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    reference: StrictStr = Field(min_length=1, max_length=500)


class NormalizedEvent(StrictDTO):
    event_type: Literal["FORMAL_DISPUTE", "ALERT", "INQUIRY", "WITHDRAWAL", "CORRECTION"]
    source_event_id: StrictStr = Field(min_length=1, max_length=100)
    channel: StrictStr = Field(min_length=1, max_length=30)
    received_at: StrictStr = Field(min_length=10, max_length=60)
    occurred_at: StrictStr = Field(min_length=10, max_length=60)
    merchant_id: StrictStr = Field(min_length=1, max_length=100)
    transaction_id: StrictStr = Field(min_length=1, max_length=100)
    scheme: StrictStr = Field(min_length=1, max_length=30)
    amount_minor: StrictInt = Field(gt=0, le=10**12)
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    reason_code: StrictStr = Field(min_length=1, max_length=100)
    upstream_case_id: StrictStr | None = Field(default=None, max_length=100)
    target_case_id: StrictStr | None = Field(default=None, max_length=100)
    case_template_id: StrictStr | None = Field(default=None, max_length=100)
    stage_number: StrictInt | None = Field(default=None, ge=1)
    outcome: (
        Literal[
            "UNKNOWN", "WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN", "OTHER"
        ]
        | None
    ) = None
    final: StrictBool | None = Field(
        default=None, json_schema_extra={"required_when": {"event_type": "WITHDRAWAL"}}
    )
    corrects_event_id: StrictStr | None = Field(
        default=None,
        max_length=100,
        json_schema_extra={"required_when": {"event_type": "CORRECTION"}},
    )
    basis_reference: StrictStr | None = Field(
        default=None,
        max_length=500,
        json_schema_extra={"required_when_all": {"outcome": "OTHER", "final": True}},
    )
    reason: StrictStr | None = Field(default=None, max_length=1000)
    supported_minor: StrictInt | None = Field(
        default=None,
        ge=0,
        le=10**12,
        json_schema_extra={"required_when": {"outcome": "PARTIAL", "mapped_outcome": "PARTIAL"}},
    )
    liable_minor: StrictInt | None = Field(
        default=None,
        ge=0,
        le=10**12,
        json_schema_extra={"required_when": {"outcome": "PARTIAL", "mapped_outcome": "PARTIAL"}},
    )
    mapped_outcome: (
        Literal["WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN"] | None
    ) = Field(
        default=None,
        json_schema_extra={"required_when_all": {"outcome": "OTHER", "final": True}},
    )
    authorization_reference: StrictStr | None = Field(
        default=None,
        max_length=500,
        json_schema_extra={"required_when_all": {"outcome": "OTHER", "final": True}},
    )


class EventData(StrictDTO):
    event: NormalizedEvent
    confirmed: StrictBool


class RetryData(StrictDTO):
    confirmed: StrictBool
    reason: StrictStr = Field(min_length=3, max_length=1000)


def initialize_dispute_intake(app, db_path):
    service = DisputeIntakeService(SQLiteDisputeIntakeStore(db_path), app.state.disputes)
    app.state.dispute_intake = service
    return service


@router.get("/api/v2/intake/events")
def events(
    request: Request,
    identity: Identity,
    status: Literal["RECEIVED", "PROCESSING", "QUARANTINED", "RECORDED", "PROCESSED"] | None = None,
):
    from oceanpilot.api.dispute_presenter import command_schema

    return {
        "events": request.app.state.dispute_intake.list_events(identity, status),
        "production_eligible": False,
        "form_schemas": {
            "event": command_schema(NormalizedEvent),
            "retry": command_schema(RetryData),
        },
    }


@router.post("/api/v2/intake/events")
def receive_event(payload: EventData, request: Request, identity: Identity):
    result = request.app.state.dispute_intake.receive(
        payload.event.model_dump(exclude_none=True), identity, confirmed=payload.confirmed
    )
    return _present_result(result, request, identity)


@router.post("/api/v2/intake/events/{event_id}/retry")
def retry_event(event_id: str, payload: RetryData, request: Request, identity: Identity):
    result = request.app.state.dispute_intake.retry_event(
        event_id, identity, **payload.model_dump()
    )
    return _present_result(result, request, identity)


def _present_result(result, request, identity):
    if result.get("case_id") and result["event"]["status"] == "PROCESSED":
        from oceanpilot.api.dispute_presenter import present_case

        service = request.app.state.disputes
        case = service.get_case(result["case_id"], identity)
        result = result | {
            "case": present_case(case, identity, service),
            "receipt": result["command_receipt"],
        }
    return result


@router.get("/api/v2/director/transactions")
def transactions(request: Request):
    return {
        "transactions": request.app.state.dispute_intake.list_transactions(_director(request)),
        "production_eligible": False,
    }


@router.post("/api/v2/director/transactions")
def register_transaction(payload: TransactionData, request: Request):
    return request.app.state.dispute_intake.register_transaction(
        payload.model_dump(), _director(request)
    )
