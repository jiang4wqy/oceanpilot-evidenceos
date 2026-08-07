from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.chargeback_schemas import (
    ChargebackAssessmentDTO,
    ChargebackAuditEventDTO,
    ChargebackAuditResponse,
    ChargebackCaseResponse,
    ChargebackDeadlineDTO,
    ChargebackEvidenceItemDTO,
    ChargebackFactsDTO,
    ConfirmReasonRequest,
    CreateChargebackRequest,
    SubmitEvidenceRequest,
)
from oceanpilot.application.channels import Delivery, InboundKind, NormalizedInbound
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.chargeback_deadline import DeadlineTracker
from oceanpilot.application.chargeback_ports import ChargebackCaseStore
from oceanpilot.application.chargeback_supervisor import ChargebackSupervisor
from oceanpilot.application.errors import CaseNotFound

router = APIRouter(prefix="/api/v1/chargeback")

# The HTTP API is one channel over the channel-agnostic core: it maps the request
# to a NormalizedInbound, runs the shared ChargebackChannelService, and renders
# the resulting Delivery as JSON. Feishu / other channels reuse the same core.
_CHANNEL = "http"


def get_supervisor(request: Request) -> ChargebackSupervisor:
    return request.app.state.chargeback_supervisor


def get_store(request: Request) -> ChargebackCaseStore:
    return request.app.state.chargeback_store


def get_deadline(request: Request) -> DeadlineTracker:
    return request.app.state.chargeback_deadline


def get_channel_service(
    supervisor: Annotated[ChargebackSupervisor, Depends(get_supervisor)],
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
    deadline: Annotated[DeadlineTracker, Depends(get_deadline)],
) -> ChargebackChannelService:
    return ChargebackChannelService(supervisor, store, deadline=deadline)


def _response(delivery: Delivery) -> ChargebackCaseResponse:
    assessment = None
    if delivery.assessment is not None:
        a = delivery.assessment
        assessment = ChargebackAssessmentDTO(
            win_likelihood=a.win_likelihood,
            completeness=a.completeness,
            responsible_team=a.responsible_team,
            requires_human=a.requires_human,
            review_reasons=a.review_reasons,
            explanation=a.explanation,
            explanation_source=a.explanation_source,
            evidence_breakdown=tuple(
                ChargebackEvidenceItemDTO(
                    code=item.code,
                    label=item.label,
                    weight=item.weight,
                    critical=item.critical,
                    present=item.present,
                )
                for item in a.evidence_breakdown
            ),
        )
    deadline = None
    if delivery.deadline is not None:
        d = delivery.deadline
        deadline = ChargebackDeadlineDTO(
            phase=d.phase,
            days_remaining=d.days_remaining,
            deadline_at=d.deadline_at,
            overdue=d.overdue,
        )
    facts = None
    if delivery.facts is not None:
        f = delivery.facts
        facts = ChargebackFactsDTO(
            amount=f.amount,
            currency=f.currency,
            occurred_on=f.occurred_on,
            summary=f.summary,
        )
    return ChargebackCaseResponse(
        case_id=delivery.case_id,
        phase=delivery.phase,
        reason_code=delivery.reason_code,
        reason_confirmed=delivery.reason_confirmed,
        collection_finalized=delivery.collection_finalized,
        collected=delivery.collected,
        next_evidence=delivery.next_evidence,
        question=delivery.question,
        missing=delivery.missing,
        assessment=assessment,
        deadline=deadline,
        facts=facts,
    )


@router.post(
    "/cases",
    response_model=ChargebackCaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**COMMON_PROBLEMS},
)
def create_case(
    payload: CreateChargebackRequest,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE,
            channel=_CHANNEL,
            description=payload.description,
        )
    )
    return _response(delivery)


@router.post(
    "/cases/{case_id}/confirm",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def confirm_reason(
    case_id: str,
    payload: ConfirmReasonRequest,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.CONFIRM_REASON,
            channel=_CHANNEL,
            case_id=case_id,
            reason_code=payload.reason_code.value if payload.reason_code else None,
        )
    )
    return _response(delivery)


@router.post(
    "/cases/{case_id}/evidence",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def submit_evidence(
    case_id: str,
    payload: SubmitEvidenceRequest,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.SUBMIT_EVIDENCE,
            channel=_CHANNEL,
            case_id=case_id,
            evidence_code=payload.evidence_code.value,
        )
    )
    return _response(delivery)


@router.post(
    "/cases/{case_id}/finalize",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def finalize_evidence(
    case_id: str,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.FINALIZE_EVIDENCE,
            channel=_CHANNEL,
            case_id=case_id,
        )
    )
    return _response(delivery)


@router.get(
    "/cases/{case_id}/audit",
    response_model=ChargebackAuditResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def get_audit(
    case_id: str,
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
) -> ChargebackAuditResponse:
    if store.load(case_id) is None:
        raise CaseNotFound()
    events = tuple(
        ChargebackAuditEventDTO(
            seq=event.seq,
            event_type=event.event_type,
            detail=event.detail,
            case_revision=event.case_revision,
            occurred_at=event.occurred_at.isoformat(),
        )
        for event in store.audit_trail(case_id)
    )
    return ChargebackAuditResponse(case_id=case_id, events=events)


@router.get(
    "/cases/{case_id}",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def get_case(
    case_id: str,
    service: Annotated[ChargebackChannelService, Depends(get_channel_service)],
) -> ChargebackCaseResponse:
    delivery = service.handle(
        NormalizedInbound(kind=InboundKind.GET_CASE, channel=_CHANNEL, case_id=case_id)
    )
    return _response(delivery)
