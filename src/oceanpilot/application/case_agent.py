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
from oceanpilot.application.errors import ConcurrentCaseWrite
from oceanpilot.application.knowledge_base import KnowledgeBase, RuleCatalog
from oceanpilot.application.workspace import WorkspaceService
from oceanpilot.application.workspace_ports import WorkspaceError
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
    command_id: str | None = None


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
        workspace: WorkspaceService | None = None,
        role: str = "BUSINESS",
        actor: str = "synthetic-business",
    ) -> None:
        self._cases = cases
        self._copilot = copilot
        self._reviews = reviews
        self._knowledge_base = knowledge_base
        self._rule_catalog = rule_catalog
        self._turn_codec = turn_codec
        self._workspace = workspace
        self._role = role
        self._actor = actor

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
        if self._workspace is not None:
            result = self._workspace.execute(
                {
                    "command_id": command.command_id or str(uuid4()),
                    "action": "CREATE_CASE",
                    "case_id": None,
                    "expected_revision": None,
                    "confirmed": True,
                    "data": {
                        "title": "",
                        "description": command.message,
                        "card_network": command.card_network,
                        "formal_dispute": True,
                    },
                },
                self._role,
                self._actor,
            )
            delivery = self._cases.get_case(result["receipt"]["case_id"])
        else:
            delivery = self._cases.handle(
                NormalizedInbound(
                    kind=InboundKind.OPEN_CASE,
                    channel="agent",
                    description=command.message,
                    card_network=command.card_network,
                )
            )
        locale = views.view_locale(command.locale)
        rule_digest = self._current_rule_fingerprint(delivery.case_id, delivery.revision)
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
            rule_fingerprint=rule_digest,
        )
        self._save_turn(turn)
        return turn

    def _analyze_case_turn(
        self, command: AgentTurnCommand, runtime: views.AgentRuntime
    ) -> views.AgentTurn:
        assert command.case_id is not None
        delivery = self._cases.get_case(command.case_id)
        if command.card_network is not None and delivery.card_network != command.card_network:
            if self._workspace is not None:
                self._workspace.execute(
                    {
                        "command_id": command.command_id or str(uuid4()),
                        "action": "SET_NETWORK",
                        "case_id": delivery.case_id,
                        "expected_revision": delivery.revision,
                        "confirmed": True,
                        "data": {"card_network": command.card_network},
                    },
                    self._role,
                    self._actor,
                )
                delivery = self._cases.get_case(command.case_id)
            else:
                delivery = self._cases.handle(
                    NormalizedInbound(
                        kind=InboundKind.SET_CARD_NETWORK,
                        channel="agent",
                        case_id=delivery.case_id,
                        card_network=command.card_network,
                        expected_revision=delivery.revision,
                    )
                )
        rule_digest = self._current_rule_fingerprint(delivery.case_id, delivery.revision)
        if command.trigger != "USER_MESSAGE":
            saved = self._reviews.latest_turn_payload(delivery.case_id, delivery.revision)
            if saved is not None:
                replayed = self._turn_codec.decode(saved)
                if (
                    replayed.case_id == delivery.case_id
                    and replayed.case_revision == delivery.revision
                    and replayed.card_network == delivery.card_network
                    and replayed.rule_fingerprint == rule_digest
                ):
                    self._validate_turn_rules(replayed)
                    return replace(replayed, result="REPLAYED")

        judgment = views.judgment(delivery, locale=views.view_locale(command.locale))
        workspace_view = (
            self._workspace.view(delivery.case_id, self._role) if self._workspace else None
        )
        if workspace_view is not None:
            gate = workspace_view["gate"]
            notice = workspace_view["rule_reference"]["limitation"]
            judgment = replace(
                judgment,
                human_gate=True,
                next_action=gate["reason"],
                decision_summary=judgment.decision_summary + " " + gate["reason"] + " " + notice,
            )
            if gate["status"] in ("NEEDS_REVIEW", "NO_EXACT_RULE"):
                judgment = replace(judgment, phase=gate["status"])
        latest_decision = self._reviews.latest_decision(delivery.case_id, delivery.revision)
        if workspace_view is not None:
            current_review = workspace_view["review"]["current_record"]
            if current_review is None or (
                latest_decision is not None
                and latest_decision.decision_id != current_review["decision_id"]
            ):
                latest_decision = None
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
            review_proposal=(
                views.review_proposal(command.message, outcome, judgment)
                if self._role == "BUSINESS"
                else None
            ),
            review_decision=views.review_decision(latest_decision),
            human_boundary="Agent 只提出建议；案件变更必须由操作人员明确确认。",
            runtime=runtime,
            judgment=judgment,
            recommended_action=views.analyzed_action(outcome, judgment),
            agent_trace=views.analyzed_trace(delivery, runtime, outcome),
            output_source=outcome.source,
            failure_code=outcome.failure_code,
            rule_fingerprint=rule_digest,
        )
        self._save_turn(turn)
        return turn

    def _current_rule_fingerprint(self, case_id: str, revision: int) -> str | None:
        if self._workspace is None:
            return None
        bundle = self._workspace.store.read(case_id)
        if bundle.state.revision != revision:
            raise ConcurrentCaseWrite()
        return self._workspace.rule_fingerprint(bundle)

    def _validate_turn_rules(self, turn: views.AgentTurn) -> None:
        if self._workspace is not None and (
            turn.rule_fingerprint is None
            or self._current_rule_fingerprint(turn.case_id, turn.case_revision)
            != turn.rule_fingerprint
        ):
            raise WorkspaceError("RULE_CHANGED", "规则在分析期间变化，请重新分析当前案件。")

    def _save_turn(self, turn: views.AgentTurn) -> None:
        # Validate the complete response before any turn/proposal is persisted,
        # including outcomes supplied by injected Copilot implementations.
        response_json = self._turn_codec.encode(turn)
        self._validate_turn_rules(turn)
        proposal = turn.review_proposal
        proposal_json = None
        if proposal is not None:
            proposal_json = json.dumps(
                {
                    "status": proposal.status,
                    "summary": proposal.summary,
                    "confirmed_materials": list(proposal.confirmed_materials),
                    "citation_ids": [item.reference_id for item in turn.citations],
                    "rule_fingerprint": turn.rule_fingerprint,
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
        self._validate_turn_rules(turn)

    def confirm_review(
        self,
        *,
        case_id: str,
        source_turn_id: str,
        case_revision: int,
        confirmed_by: str,
    ) -> ReviewConfirmationResult:
        assert_no_sensitive_data({"confirmed_by": confirmed_by})
        if self._workspace is not None:
            if self._role != "BUSINESS":
                raise WorkspaceError("BUSINESS_ROLE_REQUIRED", "此操作需要业务复核演示角色。", 403)
            view = self._workspace.view(case_id, self._role)
            historical = any(
                item["source_turn_id"] == source_turn_id for item in view["review"]["history"]
            )
            if not historical:
                bundle = self._workspace.store.read(case_id)
                turn = next(
                    (item for item in bundle.turns if item.get("source_turn_id") == source_turn_id),
                    None,
                )
                proposal = turn.get("review_proposal") if turn else None
                if turn and turn.get("rule_fingerprint") != self._workspace.rule_fingerprint(
                    bundle
                ):
                    raise WorkspaceError(
                        "RULE_CHANGED", "该审核提案的规则已变化，请重新分析并确认。"
                    )
                if (
                    proposal
                    and proposal.get("status") == "APPROVED"
                    and not view["gate"]["can_review"]
                ):
                    raise WorkspaceError("REVIEW_BLOCKED", view["gate"]["reason"])
        return self._reviews.confirm_review(
            case_id=case_id,
            source_turn_id=source_turn_id,
            expected_revision=case_revision,
            confirmed_by=confirmed_by,
        )
