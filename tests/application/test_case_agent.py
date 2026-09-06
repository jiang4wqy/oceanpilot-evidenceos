"""Application-level Agent regressions, without constructing an HTTP app."""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from unittest.mock import Mock, sentinel

import pytest
from pydantic import ValidationError

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.api.agent_schemas import StrictAgentTurnCodec
from oceanpilot.application.agent_views import AgentRuntime
from oceanpilot.application.case_agent import AgentTurnCommand, CaseAgentService
from oceanpilot.application.case_copilot import CaseCopilotAgent
from oceanpilot.application.case_review import CaseReviewStore, ReviewDecision, ReviewStatus
from oceanpilot.application.channels import Delivery, InboundKind, NormalizedInbound
from oceanpilot.application.errors import ConcurrentCaseWrite
from oceanpilot.application.knowledge_base import BankRuleEntry, KnowledgeBase, RuleCatalog
from oceanpilot.domain.chargeback import DisputeReasonCode, required_evidence_for
from oceanpilot.domain.errors import SensitiveDataRejected

RUNTIME = AgentRuntime(mode="OFFLINE_FALLBACK", provider="SCRIPTED", model="synthetic")
REASON = DisputeReasonCode.PRODUCT_NOT_RECEIVED


@pytest.fixture
def agent_setup():
    delivery = Delivery(
        case_id="case-synthetic",
        phase="NEED_EVIDENCE",
        revision=7,
        reason_code=REASON.value,
        reason_confirmed=True,
    )
    cases = Mock(spec=["get_case", "handle"])
    cases.get_case.return_value = delivery
    cases.handle.return_value = delivery
    reviews = Mock(spec=CaseReviewStore)
    reviews.latest_turn_payload.return_value = None
    reviews.latest_decision.return_value = None
    # A concurrent write may have happened after the delivery was produced.
    reviews.current_revision.return_value = delivery.revision + 1
    model = ScriptedModelProvider(default_text="not-json")
    knowledge = Mock(spec=KnowledgeBase)
    knowledge.lookup.return_value = BankRuleEntry(
        reason_code=REASON,
        required_evidence=required_evidence_for(REASON),
        template_order=required_evidence_for(REASON),
        submission_window_days=30,
        notes="Synthetic fixture",
        source="default",
    )
    catalog = Mock(spec=RuleCatalog)
    service = CaseAgentService(
        cases,
        CaseCopilotAgent(model),
        reviews,
        knowledge,
        catalog,
        turn_codec=StrictAgentTurnCodec(),
    )
    return service, cases, reviews, model


def test_existing_case_analysis_is_an_explicit_read_and_one_copilot_call(agent_setup):
    agent, cases, reviews, model = agent_setup

    result = agent.create_turn(
        AgentTurnCommand(message="为什么这个案件还不能提交？", case_id="case-synthetic"),
        RUNTIME,
    )

    cases.get_case.assert_called_once_with("case-synthetic")
    cases.handle.assert_not_called()
    assert len(model.requests) == 1
    assert result.case_revision == 7
    assert result.judgment.evidence_readiness == "0/5 项"
    assert result.review_status == "UNREVIEWED"
    assert result.review_proposal is None
    reviews.confirm_review.assert_not_called()
    saved = reviews.save_turn.call_args.args[0]
    assert StrictAgentTurnCodec().decode(saved.response_json) == result


def test_reopen_replays_saved_view_without_model_or_persistence_side_effects(agent_setup):
    agent, cases, reviews, model = agent_setup
    command = AgentTurnCommand(
        message="打开案件并恢复当前状态", case_id="case-synthetic", trigger="CASE_OPENED"
    )
    original = agent.create_turn(command, RUNTIME)
    saved = reviews.save_turn.call_args.args[0]
    reviews.latest_turn_payload.return_value = saved.response_json
    reviews.save_turn.reset_mock()
    reviews.latest_decision.reset_mock()
    new_runtime = AgentRuntime(mode="INJECTED_MODEL", provider="TEST", model="other")

    replayed = agent.create_turn(command, new_runtime)

    assert replayed == replace(original, result="REPLAYED")
    assert isinstance(replayed.judgment.missing_evidence, tuple)
    assert len(model.requests) == 1
    cases.handle.assert_not_called()
    reviews.save_turn.assert_not_called()
    reviews.latest_decision.assert_not_called()
    reviews.latest_turn_payload.assert_called_with("case-synthetic", 7)


def test_user_message_never_uses_automatic_reopen_cache(agent_setup):
    agent, cases, reviews, model = agent_setup
    original = agent.create_turn(
        AgentTurnCommand(message="打开案件并恢复当前状态", case_id="case-synthetic"), RUNTIME
    )
    reviews.latest_turn_payload.return_value = reviews.save_turn.call_args.args[0].response_json

    refreshed = agent.create_turn(
        AgentTurnCommand(message="为什么还缺资料？", case_id="case-synthetic"), RUNTIME
    )

    assert refreshed.source_turn_id != original.source_turn_id
    assert refreshed.intent == "EXPLAIN_EVIDENCE_GAP"
    assert len(model.requests) == 2
    reviews.latest_turn_payload.assert_not_called()
    cases.handle.assert_not_called()


def test_network_change_keeps_case_snapshot_compare_and_swap(agent_setup):
    agent, cases, reviews, model = agent_setup
    cases.handle.return_value = replace(
        cases.get_case.return_value, card_network="VISA", revision=8
    )

    result = agent.create_turn(
        AgentTurnCommand(
            message="读取当前案件",
            case_id="case-synthetic",
            card_network="VISA",
            trigger="CASE_OPENED",
        ),
        RUNTIME,
    )

    cases.handle.assert_called_once_with(
        NormalizedInbound(
            kind=InboundKind.SET_CARD_NETWORK,
            channel="agent",
            case_id="case-synthetic",
            card_network="VISA",
            expected_revision=7,
        )
    )
    assert result.case_revision == 8
    assert result.card_network == "VISA"
    reviews.latest_turn_payload.assert_called_once_with("case-synthetic", 8)
    assert reviews.save_turn.call_args.args[0].case_revision == 8
    assert len(model.requests) == 1


def test_create_turn_cannot_relabel_old_delivery_with_newer_store_revision(agent_setup):
    agent, cases, reviews, model = agent_setup

    result = agent.create_turn(AgentTurnCommand(message="客户一直没有收到商品"), RUNTIME)

    assert result.turn_kind == "CASE_CREATED"
    assert result.case_revision == 7
    assert reviews.save_turn.call_args.args[0].case_revision == 7
    reviews.current_revision.assert_not_called()
    cases.get_case.assert_not_called()
    assert model.requests == []


def test_concurrent_save_conflict_is_propagated_without_retrying_the_case_write(agent_setup):
    agent, cases, reviews, model = agent_setup
    reviews.save_turn.side_effect = ConcurrentCaseWrite()

    with pytest.raises(ConcurrentCaseWrite):
        agent.create_turn(AgentTurnCommand(message="客户一直没有收到商品"), RUNTIME)

    cases.handle.assert_called_once()
    reviews.save_turn.assert_called_once()
    reviews.current_revision.assert_not_called()
    assert model.requests == []


def test_review_proposal_and_record_survive_saved_json_without_auto_confirmation(agent_setup):
    agent, cases, reviews, model = agent_setup
    cases.get_case.return_value = replace(
        cases.get_case.return_value,
        collected=tuple(code.value for code in required_evidence_for(REASON)),
        phase="ASSESSED",
    )
    reviews.latest_decision.return_value = ReviewDecision(
        decision_id="decision-synthetic",
        case_id="case-synthetic",
        source_turn_id="prior-turn",
        status=ReviewStatus.NEEDS_MORE_INFO,
        summary="Synthetic review record",
        confirmed_materials=(),
        citation_ids=(),
        case_revision=7,
        confirmed_by="synthetic-reviewer",
        confirmed_at=datetime(2026, 9, 6, tzinfo=UTC),
        audit_event_id="audit-synthetic",
    )

    result = agent.create_turn(
        AgentTurnCommand(message="审核通过", case_id="case-synthetic"), RUNTIME
    )
    restored = StrictAgentTurnCodec().decode(reviews.save_turn.call_args.args[0].response_json)

    assert result.review_proposal.status == "APPROVED"
    assert result.review_proposal.requires_confirmation is True
    assert result.review_decision.decision_id == "decision-synthetic"
    assert len(result.material_contents) == 5
    assert all("未读取或存储真实文件正文" in item.summary for item in result.material_contents)
    assert asdict(restored) == asdict(result)
    assert isinstance(restored.review_proposal.confirmed_materials, tuple)
    reviews.confirm_review.assert_not_called()
    cases.handle.assert_not_called()
    assert len(model.requests) == 1


def test_sensitive_message_is_rejected_before_case_or_model_access(agent_setup):
    agent, cases, reviews, model = agent_setup

    with pytest.raises(SensitiveDataRejected):
        agent.create_turn(AgentTurnCommand(message="请查询卡号 4111 1111 1111 1111"), RUNTIME)

    cases.handle.assert_not_called()
    cases.get_case.assert_not_called()
    reviews.save_turn.assert_not_called()
    assert model.requests == []


def test_review_confirmation_delegates_exact_frozen_revision_without_analysis(agent_setup):
    agent, cases, reviews, model = agent_setup
    reviews.confirm_review.return_value = sentinel.confirmation

    result = agent.confirm_review(
        case_id="case-synthetic",
        source_turn_id="turn-synthetic",
        case_revision=7,
        confirmed_by="synthetic-reviewer",
    )

    assert result is sentinel.confirmation
    reviews.confirm_review.assert_called_once_with(
        case_id="case-synthetic",
        source_turn_id="turn-synthetic",
        expected_revision=7,
        confirmed_by="synthetic-reviewer",
    )
    cases.get_case.assert_not_called()
    cases.handle.assert_not_called()
    assert model.requests == []


@pytest.mark.parametrize(
    ("section", "field", "malformed"),
    (
        ("judgment", "missing_evidence", "invalid-array"),
        (None, "citations", {}),
        (None, "agent_trace", ""),
        (None, "material_contents", None),
        ("review_proposal", "conflicts", {}),
    ),
)
def test_saved_json_arrays_are_not_coerced_from_malformed_strings_or_objects(
    agent_setup, section, field, malformed
):
    agent, cases, reviews, model = agent_setup
    agent.create_turn(AgentTurnCommand(message="审核通过", case_id="case-synthetic"), RUNTIME)
    payload = json.loads(reviews.save_turn.call_args.args[0].response_json)
    target = payload if section is None else payload[section]
    target[field] = malformed

    with pytest.raises(ValidationError):
        StrictAgentTurnCodec().decode(json.dumps(payload))

    cases.handle.assert_not_called()
    reviews.confirm_review.assert_not_called()
    assert len(model.requests) == 1


@pytest.mark.parametrize(
    "changes",
    ({"case_id": "another-case"}, {"case_revision": 6}, {"card_network": "VISA"}),
)
def test_reopen_cache_must_match_case_revision_and_network(agent_setup, changes):
    agent, cases, reviews, model = agent_setup
    command = AgentTurnCommand(
        message="打开案件并恢复当前状态", case_id="case-synthetic", trigger="CASE_OPENED"
    )
    original = agent.create_turn(command, RUNTIME)
    reviews.latest_turn_payload.return_value = StrictAgentTurnCodec().encode(
        replace(original, **changes)
    )

    refreshed = agent.create_turn(command, RUNTIME)

    assert refreshed.result == "CREATED"
    assert refreshed.source_turn_id != original.source_turn_id
    assert refreshed.case_id == "case-synthetic"
    assert refreshed.case_revision == 7
    assert refreshed.card_network is None
    assert len(model.requests) == 2
    cases.handle.assert_not_called()


def test_invalid_injected_copilot_output_cannot_be_persisted(agent_setup):
    agent, cases, reviews, model = agent_setup
    valid_outcome = agent._copilot.respond(
        "当前案件状态",
        problem_type="Synthetic",
        phase="NEED_EVIDENCE",
        readiness="0/5 项",
        responsible_team="CUSTOMER_SUPPORT",
        human_gate=True,
        missing_codes=(),
        missing_labels=(),
    )
    agent._copilot = Mock()
    agent._copilot.respond.return_value = replace(valid_outcome, assistant_message=123)

    with pytest.raises(ValidationError):
        agent.create_turn(
            AgentTurnCommand(message="当前案件状态", case_id="case-synthetic"), RUNTIME
        )

    reviews.save_turn.assert_not_called()
    reviews.confirm_review.assert_not_called()
    cases.handle.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    (
        [],
        {"unknown": True},
        {"synthetic": False},
    ),
)
def test_malformed_cached_payload_is_rejected_before_any_model_or_write(agent_setup, payload):
    agent, cases, reviews, model = agent_setup
    reviews.latest_turn_payload.return_value = json.dumps(payload)

    with pytest.raises(ValidationError):
        agent.create_turn(
            AgentTurnCommand(
                message="打开案件并恢复当前状态",
                case_id="case-synthetic",
                trigger="CASE_OPENED",
            ),
            RUNTIME,
        )

    reviews.save_turn.assert_not_called()
    reviews.confirm_review.assert_not_called()
    cases.handle.assert_not_called()
    assert model.requests == []
