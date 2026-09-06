"""Strict HTTP request and response contracts for the case Agent gateway."""

from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from oceanpilot.application.agent_views import AgentTurn, restore_turn


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class AgentTurnRequest(_StrictModel):
    message: StrictStr = Field(min_length=3, max_length=2_000)
    locale: Literal["zh-CN", "en-US"] = "zh-CN"
    case_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    card_network: Literal["VISA", "MASTERCARD", "AMEX"] | None = None
    trigger: Literal[
        "USER_MESSAGE",
        "CASE_OPENED",
        "REASON_CONFIRMED",
        "EVIDENCE_SUBMITTED",
        "EVIDENCE_WITHDRAWN",
        "REVIEW_CONFIRMED",
    ] = "USER_MESSAGE"


class AgentRuntimeDTO(_StrictModel):
    mode: Literal[
        "DEEPSEEK_LIVE",
        "CLAUDE_LIVE",
        "INJECTED_MODEL",
        "OFFLINE_FALLBACK",
    ]
    provider: StrictStr
    model: StrictStr


class AgentJudgmentDTO(_StrictModel):
    problem_type: StrictStr
    phase: StrictStr
    confirmed_facts: tuple[StrictStr, ...]
    uncertain_facts: tuple[StrictStr, ...]
    evidence_readiness: StrictStr
    responsible_team: StrictStr
    next_action: StrictStr
    human_gate: StrictBool
    decision_summary: StrictStr
    missing_evidence_codes: tuple[StrictStr, ...]
    missing_evidence: tuple[StrictStr, ...]
    collected_evidence_codes: tuple[StrictStr, ...]
    collected_evidence: tuple[StrictStr, ...]
    next_evidence_code: StrictStr | None
    next_evidence_label: StrictStr | None


class AgentRecommendedActionDTO(_StrictModel):
    kind: Literal["OPEN_EVIDENCE_MODAL", "OPEN_CASE_DETAIL", "NONE"]
    label: StrictStr
    evidence_code: StrictStr | None = None
    evidence_label: StrictStr | None = None
    requires_confirmation: StrictBool


class AgentTraceStepDTO(_StrictModel):
    step: int = Field(ge=1)
    actor: StrictStr
    action: StrictStr
    status: Literal["COMPLETED", "WAITING", "BLOCKED"]
    source: StrictStr
    output_summary: StrictStr


class AgentMaterialContentDTO(_StrictModel):
    evidence_code: StrictStr
    label: StrictStr
    summary: StrictStr


class AgentCitationDTO(_StrictModel):
    reference_id: StrictStr
    reference_type: Literal["RULE", "TECHNICAL_CONTEXT"]
    title: StrictStr
    claim: StrictStr
    source_document: StrictStr
    source_section: StrictStr | None = None
    source_url: StrictStr
    verification_status: StrictStr
    limitation: StrictStr


class AgentReviewProposalDTO(_StrictModel):
    status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    summary: StrictStr
    confirmed_materials: tuple[StrictStr, ...]
    conflicts: tuple[StrictStr, ...]
    next_action: StrictStr
    why: StrictStr
    requires_confirmation: Literal[True]


class AgentReviewDecisionDTO(_StrictModel):
    decision_id: StrictStr
    status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    revision: StrictInt
    confirmed_by: StrictStr
    confirmed_at: StrictStr
    audit_event_id: StrictStr


class AgentTurnResponse(_StrictModel):
    synthetic: Literal[True]
    result: Literal["CREATED", "REPLAYED"] = "CREATED"
    turn_kind: Literal["CASE_CREATED", "CASE_ANALYZED"]
    source_turn_id: StrictStr
    case_id: StrictStr
    card_network: Literal["VISA", "MASTERCARD", "AMEX"] | None = None
    case_revision: StrictInt = Field(ge=0)
    trigger: StrictStr
    intent: StrictStr
    assistant_message: StrictStr
    analysis_summary: StrictStr
    review_status: StrictStr
    material_contents: tuple[AgentMaterialContentDTO, ...]
    decision_reason: StrictStr
    citations: tuple[AgentCitationDTO, ...]
    review_proposal: AgentReviewProposalDTO | None = None
    review_decision: AgentReviewDecisionDTO | None = None
    human_boundary: StrictStr
    runtime: AgentRuntimeDTO
    judgment: AgentJudgmentDTO
    recommended_action: AgentRecommendedActionDTO
    agent_trace: tuple[AgentTraceStepDTO, ...]


class ConfirmAgentReviewRequest(_StrictModel):
    source_turn_id: StrictStr = Field(min_length=1, max_length=128)
    case_revision: StrictInt = Field(ge=0)
    confirmed_by: StrictStr = Field(min_length=1, max_length=128)


class ConfirmAgentReviewResponse(_StrictModel):
    result: Literal["CREATED", "REPLAYED"]
    decision_id: StrictStr
    case_id: StrictStr
    case_revision: StrictInt
    review_status: Literal["NEEDS_MORE_INFO", "APPROVED", "REJECTED"]
    audit_event_id: StrictStr
    reanalyze: Literal[True]


class StrictAgentTurnCodec:
    """Retain the original strict wire contract for persisted turn snapshots."""

    def encode(self, turn: AgentTurn) -> str:
        return AgentTurnResponse.model_validate(asdict(turn)).model_dump_json()

    def decode(self, response_json: str) -> AgentTurn:
        response = AgentTurnResponse.model_validate_json(response_json)
        return restore_turn(response.model_dump_json())
