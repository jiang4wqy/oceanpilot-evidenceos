from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.chargeback_schemas import (
    ChargebackAssessmentDTO,
    ChargebackCaseResponse,
    CreateChargebackRequest,
    SubmitEvidenceRequest,
)
from oceanpilot.application.chargeback_ports import ChargebackCaseStore
from oceanpilot.application.chargeback_supervisor import (
    ChargebackCaseState,
    ChargebackSupervisor,
    SupervisorPhase,
    SupervisorStep,
)
from oceanpilot.application.errors import CaseNotFound

router = APIRouter(prefix="/api/v1/chargeback")


def get_supervisor(request: Request) -> ChargebackSupervisor:
    return request.app.state.chargeback_supervisor


def get_store(request: Request) -> ChargebackCaseStore:
    return request.app.state.chargeback_store


def _response(
    case_id: str, state: ChargebackCaseState, step: SupervisorStep
) -> ChargebackCaseResponse:
    payload: dict[str, object] = {
        "case_id": case_id,
        "phase": step.phase.value,
        "reason_code": state.reason_code.value if state.reason_code else None,
        "collected": tuple(sorted(code.value for code in state.collected)),
    }
    if step.phase is SupervisorPhase.NEED_EVIDENCE and step.evidence_request:
        request = step.evidence_request
        payload["next_evidence"] = request.next_evidence.value if request.next_evidence else None
        payload["question"] = request.question
        payload["missing"] = tuple(code.value for code in request.missing)
    elif step.phase is SupervisorPhase.ASSESSED and step.assessment:
        assessment = step.assessment.assessment
        payload["assessment"] = ChargebackAssessmentDTO(
            win_likelihood=str(assessment.win_likelihood),
            completeness=str(assessment.completeness),
            responsible_team=assessment.responsible_team.value,
            requires_human=assessment.requires_human,
            review_reasons=tuple(r.value for r in assessment.review_reasons),
            explanation=step.assessment.explanation,
        )
    return ChargebackCaseResponse(**payload)


def _load(store: ChargebackCaseStore, case_id: str) -> ChargebackCaseState:
    state = store.load(case_id)
    if state is None:
        raise CaseNotFound()
    return state


@router.post(
    "/cases",
    response_model=ChargebackCaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**COMMON_PROBLEMS},
)
def create_case(
    payload: CreateChargebackRequest,
    supervisor: Annotated[ChargebackSupervisor, Depends(get_supervisor)],
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
) -> ChargebackCaseResponse:
    case_id = store.create()
    state = _load(store, case_id)
    supervisor.intake(state, payload.description)
    store.save(case_id, state)
    return _response(case_id, state, supervisor.advance(state))


@router.post(
    "/cases/{case_id}/evidence",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def submit_evidence(
    case_id: str,
    payload: SubmitEvidenceRequest,
    supervisor: Annotated[ChargebackSupervisor, Depends(get_supervisor)],
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
) -> ChargebackCaseResponse:
    state = _load(store, case_id)
    supervisor.submit_evidence(state, payload.evidence_code)
    store.save(case_id, state)
    return _response(case_id, state, supervisor.advance(state))


@router.get(
    "/cases/{case_id}",
    response_model=ChargebackCaseResponse,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def get_case(
    case_id: str,
    supervisor: Annotated[ChargebackSupervisor, Depends(get_supervisor)],
    store: Annotated[ChargebackCaseStore, Depends(get_store)],
) -> ChargebackCaseResponse:
    state = _load(store, case_id)
    return _response(case_id, state, supervisor.advance(state))
