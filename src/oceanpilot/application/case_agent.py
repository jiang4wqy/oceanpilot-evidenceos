"""Case Agent turn orchestration, independent of HTTP and persistence adapters.

The channel service owns versioned case changes; the review store owns turn
persistence and review compare-and-swap. This service composes those operations
with model-authored guidance and deterministic case presentation.
"""

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from oceanpilot.application import agent_views as views
from oceanpilot.application.case_copilot import CaseCopilotAgent
from oceanpilot.application.case_review import (
    AgentTurnRecord,
    CaseReviewStore,
    ReviewConfirmationResult,
)
from oceanpilot.application.channels import InboundKind, NormalizedInbound
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.knowledge_base import KnowledgeBase, RuleCatalog
from oceanpilot.domain.chargeback import DisputeReasonCode
from oceanpilot.domain.security import assert_no_sensitive_data


class AgentTurnCodec(Protocol):
    """Validate and serialize persisted turns using the channel's strict contract.

    Encoding happens before saving; decoding must reject invalid stored shapes.
    A caller must provide a codec so persistence can never bypass its contract.
    """

    def encode(self, turn: views.AgentTurn) -> str: ...

    def decode(self, response_json: str) -> views.AgentTurn: ...


@dataclass(frozen=True)
class AgentTurnCommand:
    message: str
    locale: str = "zh-CN"
    case_id: str | None = None
    card_network: str | None = None
    trigger: str = "USER_MESSAGE"


class CaseAgentService:
    def __init__(
        self,
        cases: ChargebackChannelService,
        copilot: CaseCopilotAgent,
        reviews: CaseReviewStore,
        knowledge_base: KnowledgeBase,
        rule_catalog: RuleCatalog,
        *,
        turn_codec: AgentTurnCodec,
    ) -> None:
        self._cases = cases
        self._copilot = copilot
        self._reviews = reviews
        self._knowledge_base = knowledge_base
        self._rule_catalog = rule_catalog
        self._turn_codec = turn_codec

    def create_turn(
        self, command: AgentTurnCommand, runtime: views.AgentRuntime
    ) -> views.AgentTurn:
        assert_no_sensitive_data({"message": command.message})
        if command.case_id is None:
            return self._create_case_turn(command, runtime)
        return self._analyze_case_turn(command, runtime)

    def _create_case_turn(
        self, command: AgentTurnCommand, runtime: views.AgentRuntime
    ) -> views.AgentTurn:
        delivery = self._cases.handle(
            NormalizedInbound(
                kind=InboundKind.OPEN_CASE,
                channel="agent",
                description=command.message,
                card_network=command.card_network,
            )
        )
        locale = views.view_locale(command.locale)
        judgment = views.judgment(delivery, locale=locale)
        turn = views.AgentTurn(
            synthetic=True,
            turn_kind="CASE_CREATED",
            source_turn_id=str(uuid4()),
            case_id=delivery.case_id,
            card_network=delivery.card_network,
            # The saved judgment must describe this delivery, never a later
            # revision fetched independently while the turn was being built.
            case_revision=delivery.revision,
            trigger=command.trigger,
            intent="OPEN_CASE",
            assistant_message=views.assistant_message(delivery, locale=locale),
            analysis_summary=judgment.decision_summary,
            review_status="UNREVIEWED",
            material_contents=views.material_contents(judgment),
            decision_reason=views.decision_reason(judgment, "UNREVIEWED"),
            citations=views.citations(
                DisputeReasonCode(delivery.reason_code) if delivery.reason_code else None,
                delivery.card_network,
                self._knowledge_base,
                self._rule_catalog,
            ),
            human_boundary="Agent 只提出建议；案件变更必须由操作人员明确确认。",
            runtime=runtime,
            judgment=judgment,
            recommended_action=views.created_action(judgment),
            agent_trace=views.trace(delivery, runtime),
        )
        self._save_turn(turn)
        return turn

    def _analyze_case_turn(
        self, command: AgentTurnCommand, runtime: views.AgentRuntime
    ) -> views.AgentTurn:
        assert command.case_id is not None
        delivery = self._cases.get_case(command.case_id)
        if command.card_network is not None and delivery.card_network != command.card_network:
            delivery = self._cases.handle(
                NormalizedInbound(
                    kind=InboundKind.SET_CARD_NETWORK,
                    channel="agent",
                    case_id=delivery.case_id,
                    card_network=command.card_network,
                    expected_revision=delivery.revision,
                )
            )
        if command.trigger != "USER_MESSAGE":
            saved = self._reviews.latest_turn_payload(delivery.case_id, delivery.revision)
            if saved is not None:
                replayed = self._turn_codec.decode(saved)
                if (
                    replayed.case_id == delivery.case_id
                    and replayed.case_revision == delivery.revision
                    and replayed.card_network == delivery.card_network
                ):
                    return replace(replayed, result="REPLAYED")

        judgment = views.judgment(delivery, locale=views.view_locale(command.locale))
        latest_decision = self._reviews.latest_decision(delivery.case_id, delivery.revision)
        review_status = (
            latest_decision.status.value if latest_decision is not None else "UNREVIEWED"
        )
        outcome = self._copilot.respond(
            command.message,
            problem_type=judgment.problem_type,
            phase=judgment.phase,
            readiness=judgment.evidence_readiness,
            responsible_team=judgment.responsible_team,
            human_gate=judgment.human_gate,
            missing_codes=judgment.missing_evidence_codes,
            missing_labels=judgment.missing_evidence,
            review_status=review_status,
        )
        turn = views.AgentTurn(
            synthetic=True,
            turn_kind="CASE_ANALYZED",
            source_turn_id=str(uuid4()),
            case_id=delivery.case_id,
            card_network=delivery.card_network,
            case_revision=delivery.revision,
            trigger=command.trigger,
            intent=outcome.intent.value,
            assistant_message=outcome.assistant_message,
            analysis_summary=outcome.analysis_summary,
            review_status=review_status,
            material_contents=views.material_contents(judgment),
            decision_reason=views.decision_reason(judgment, review_status),
            citations=views.citations(
                DisputeReasonCode(delivery.reason_code) if delivery.reason_code else None,
                delivery.card_network,
                self._knowledge_base,
                self._rule_catalog,
            ),
            review_proposal=views.review_proposal(command.message, outcome, judgment),
            review_decision=views.review_decision(latest_decision),
            human_boundary="Agent 只提出建议；案件变更必须由操作人员明确确认。",
            runtime=runtime,
            judgment=judgment,
            recommended_action=views.analyzed_action(outcome, judgment),
            agent_trace=views.analyzed_trace(delivery, runtime, outcome),
        )
        self._save_turn(turn)
        return turn

    def _save_turn(self, turn: views.AgentTurn) -> None:
        # Validate the complete response before any turn/proposal is persisted,
        # including outcomes supplied by injected Copilot implementations.
        response_json = self._turn_codec.encode(turn)
        proposal = turn.review_proposal
        proposal_json = None
        if proposal is not None:
            proposal_json = json.dumps(
                {
                    "status": proposal.status,
                    "summary": proposal.summary,
                    "confirmed_materials": list(proposal.confirmed_materials),
                    "citation_ids": [item.reference_id for item in turn.citations],
                },
                ensure_ascii=False,
            )
        self._reviews.save_turn(
            AgentTurnRecord(
                turn_id=turn.source_turn_id,
                case_id=turn.case_id,
                case_revision=turn.case_revision,
                trigger=turn.trigger,
                response_json=response_json,
                proposal_json=proposal_json,
                created_at=datetime.now(UTC),
            )
        )

    def confirm_review(
        self,
        *,
        case_id: str,
        source_turn_id: str,
        case_revision: int,
        confirmed_by: str,
    ) -> ReviewConfirmationResult:
        assert_no_sensitive_data({"confirmed_by": confirmed_by})
        return self._reviews.confirm_review(
            case_id=case_id,
            source_turn_id=source_turn_id,
            expected_revision=case_revision,
            confirmed_by=confirmed_by,
        )
