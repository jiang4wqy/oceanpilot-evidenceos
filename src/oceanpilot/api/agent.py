"""HTTP boundary for case Agent turns and human review confirmation."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from oceanpilot.api.agent_schemas import (
    AgentRuntimeDTO,
    AgentTurnRequest,
    AgentTurnResponse,
    ConfirmAgentReviewRequest,
    ConfirmAgentReviewResponse,
    StrictAgentTurnCodec,
)
from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.application.agent_views import AgentRuntime
from oceanpilot.application.case_agent import AgentTurnCommand, CaseAgentService
from oceanpilot.application.case_copilot import CaseCopilotAgent
from oceanpilot.application.case_review import CaseReviewStore
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.knowledge_base import KnowledgeBase, RuleCatalog

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


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


def get_case_agent_service(
    service: Annotated[ChargebackChannelService, Depends(get_agent_service)],
    copilot: Annotated[CaseCopilotAgent, Depends(get_case_copilot)],
    review_store: Annotated[CaseReviewStore, Depends(get_review_store)],
    knowledge_base: Annotated[KnowledgeBase, Depends(get_knowledge_base)],
    rule_catalog: Annotated[RuleCatalog, Depends(get_rule_catalog)],
) -> CaseAgentService:
    return CaseAgentService(
        service,
        copilot,
        review_store,
        knowledge_base,
        rule_catalog,
        turn_codec=StrictAgentTurnCodec(),
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
    agent: Annotated[CaseAgentService, Depends(get_case_agent_service)],
) -> AgentTurnResponse:
    runtime = AgentRuntimeDTO.model_validate(request.app.state.agent_runtime)
    turn = agent.create_turn(
        AgentTurnCommand(**payload.model_dump()),
        AgentRuntime(**runtime.model_dump()),
    )
    return AgentTurnResponse.model_validate(asdict(turn))


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
    agent: Annotated[CaseAgentService, Depends(get_case_agent_service)],
) -> ConfirmAgentReviewResponse:
    result = agent.confirm_review(case_id=case_id, **payload.model_dump())
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
