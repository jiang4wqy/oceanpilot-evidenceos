import pytest

from oceanpilot.adapters.knowledge.rule_repository import (
    SqliteRuleRepository,
    initialize_rule_database,
)
from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.agent_views import (
    AgentRuntime,
    analyzed_trace,
    citations,
    judgment,
    review_proposal,
    rule_match_notice,
)
from oceanpilot.application.case_copilot import CopilotActionKind, CopilotIntent, CopilotOutcome
from oceanpilot.application.case_snapshot import render_delivery
from oceanpilot.application.channels import Delivery
from oceanpilot.application.chargeback_agents import ChargebackAssessAgent, EvidenceAgent
from oceanpilot.application.chargeback_packager import PackagerAgent
from oceanpilot.application.chargeback_supervisor import ChargebackCaseState, ChargebackSupervisor
from oceanpilot.domain.chargeback import (
    ChargebackEvidenceCode as Code,
)
from oceanpilot.domain.chargeback import (
    DisputeReasonCode,
    MaterialGate,
    assess_chargeback,
    required_evidence_for,
)
from oceanpilot.domain.evidence_catalog import has_unsupported_material_claim


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "rules.db"
    initialize_rule_database(path)
    return SqliteRuleRepository(path)


@pytest.mark.parametrize(
    ("reason", "network", "code"),
    [
        (DisputeReasonCode.FRAUD_CARD_NOT_PRESENT, "VISA", "10.4"),
        (DisputeReasonCode.PRODUCT_NOT_RECEIVED, "VISA", "13.1"),
        (DisputeReasonCode.PRODUCT_NOT_AS_DESCRIBED, "MASTERCARD", "4853"),
    ],
)
def test_rule_claim_and_review_scope_follow_each_case(repository, reason, network, code):
    references = citations(reason, network, repository, repository)
    rule = next(reference for reference in references if reference.reference_type == "RULE")
    assert network in rule.claim and code in rule.claim
    assert not any(other in rule.claim for other in {"10.4", "13.1", "4853"} - {code})
    assert "未核验" in rule.claim
    assert "已匹配" in rule_match_notice(references)
    view = judgment(
        Delivery(
            case_id="synthetic-case",
            phase="ASSESSED",
            reason_code=reason.value,
            reason_confirmed=True,
            card_network=network,
            collected=tuple(item.value for item in required_evidence_for(reason)),
        ),
        locale="zh",
    )
    proposal = review_proposal("审核通过", _review_outcome(), view)
    assert proposal.status == "APPROVED"
    assert proposal.requires_confirmation is True
    assert "登记" in proposal.summary
    assert "正文" in proposal.why
    assert "案件复核摘要（合成示例）" in proposal.next_action
    assert not has_unsupported_material_claim(proposal.summary)
    assert all(other not in proposal.next_action for other in ("10.4", "13.1", "4853"))


def _review_outcome():
    return CopilotOutcome(
        intent=CopilotIntent.PROPOSE_REVIEW_DECISION,
        assistant_message="拟登记审核意见",
        analysis_summary="待人工确认",
        action_kind=CopilotActionKind.OPEN_CASE_DETAIL,
        action_label="人工确认",
        target_evidence_code=None,
        requires_confirmation=True,
        source="DETERMINISTIC",
    )


def test_deterministic_trace_is_distinct_from_model_failure_trace():
    delivery = Delivery(case_id="case", phase="NEED_EVIDENCE")
    runtime = AgentRuntime(mode="OFFLINE_FALLBACK", provider="DETERMINISTIC", model="offline")
    trace = analyzed_trace(delivery, runtime, _review_outcome())
    assert trace[2].source == "DETERMINISTIC_RULES"
    assert "降级" not in trace[2].output_summary


def test_limited_analysis_cannot_claim_the_registration_checklist_is_complete():
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    model = ScriptedModelProvider(["材料已齐全，可提交。"])
    result = ChargebackAssessAgent(model).assess(
        reason, [Code.DELIVERY_TRACKING, Code.PROOF_OF_DELIVERY]
    )
    assert result.explanation_source.value == "FALLBACK"
    assert "有限分析" in result.explanation


def test_no_exact_mapping_is_explicit_and_cannot_make_a_ready_package(repository):
    reason = DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    references = citations(reason, "AMEX", repository, repository)
    assert references == ()
    assert "默认模板" in rule_match_notice(references)
    model = ScriptedModelProvider(default_text="正式依据足够，可自动提交")
    package = PackagerAgent(model, repository).build(
        reason, required_evidence_for(reason), card_network="AMEX"
    )
    assert package.ready_to_submit is False
    assert package.rule_version_id is None
    assert model.requests == []
    assert "未匹配" in package.cover_note
    assert "并非官方响应期限" in package.cover_note


def test_catalog_reason_or_network_mismatch_does_not_become_a_citation(repository):
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    wrong = repository.get_rule("visa-10-4-demo-v1")

    class WrongCatalog:
        def get_rule(self, rule_id):
            return wrong

    assert citations(reason, "VISA", repository, WrongCatalog()) == ()


def test_unknown_or_unconfirmed_case_cannot_propose_approval_without_a_checklist():
    view = judgment(Delivery(case_id="case", phase="NEEDS_INTAKE"), locale="zh")
    assert review_proposal("审核通过", _review_outcome(), view).status == "NEEDS_MORE_INFO"


@pytest.mark.parametrize("reason", list(DisputeReasonCode))
def test_material_gate_distinguishes_internal_missing_levels_and_human_review(reason):
    full = required_evidence_for(reason)
    assessment = assess_chargeback(reason, full)
    assert assessment.material_gate is MaterialGate.READY_FOR_REVIEW
    assert assessment.requires_human is True
    for item in assessment.evidence_breakdown:
        partial = assess_chargeback(reason, [code for code in full if code is not item.code])
        expected = MaterialGate.CRITICAL_MISSING if item.critical else MaterialGate.LIMITED
        assert partial.material_gate is expected
        assert partial.requires_human is True
        assert partial.evidence_readiness == partial.win_likelihood


def test_a_template_threeds_gap_really_is_critical_and_cannot_finalize_into_assessment(repository):
    reason = DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    present = set(required_evidence_for(reason)) - {Code.THREEDS_AUTHENTICATION}
    assert len(present) == 5
    state = ChargebackCaseState(reason_code=reason, reason_confirmed=True, collected=present)
    assert assess_chargeback(reason, present).missing_critical == (Code.THREEDS_AUTHENTICATION,)
    state.collection_finalized = True
    step = ChargebackSupervisor.snapshot(state)
    assert step.phase.value == "NEED_EVIDENCE"
    assert step.assessment is None
    model = ScriptedModelProvider(default_text="正式评估通过")
    direct = ChargebackAssessAgent(model).assess(reason, present)
    package = PackagerAgent(model, repository).build(reason, present, card_network="VISA")
    assert "正式评估已阻断" in direct.explanation
    assert not package.ready_to_submit
    assert model.requests == []


def test_missing_internal_ordinary_item_blocks_package_even_if_scheme_summary_is_complete(
    repository,
):
    reason = DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    present = set(required_evidence_for(reason)) - {Code.AVS_RESULT}
    package = PackagerAgent(ScriptedModelProvider(), repository).preview(
        reason, present, card_network="VISA"
    )
    assert package.missing_evidence == ()  # AVS is not asserted to be scheme-mandated.
    assert package.ready_to_submit is False
    assert "AVS" in package.cover_note


def test_limited_snapshot_retains_ordinary_gaps_after_collection_is_finalized():
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    state = ChargebackCaseState(
        reason_code=reason,
        reason_confirmed=True,
        collection_finalized=True,
        collected={Code.DELIVERY_TRACKING, Code.PROOF_OF_DELIVERY},
    )
    step = ChargebackSupervisor.snapshot(state)
    delivery = render_delivery("case", state, step)
    assert delivery.phase == "ASSESSED"
    assert set(delivery.missing) == {
        Code.TRANSACTION_RECEIPT.value,
        Code.SHIPPING_ADDRESS_MATCH.value,
        Code.CUSTOMER_COMMUNICATION.value,
    }
    assert delivery.next_evidence in delivery.missing
    assert "有限分析" in delivery.question
    assert "有限分析" in delivery.assessment.explanation
    assert delivery.assessment.requires_human is True


@pytest.mark.parametrize(
    "claim",
    [
        "材料内容一致，交易真实。",
        "胜诉率 100%，无需人工。",
        "已读取材料正文，证明已送达。",
        "Verified document contents are consistent.",
    ],
)
def test_model_assertions_do_not_upgrade_metadata_to_verified_content(repository, claim):
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    full = required_evidence_for(reason)
    assess = ChargebackAssessAgent(ScriptedModelProvider([claim])).assess(reason, full)
    evidence = EvidenceAgent(ScriptedModelProvider([claim])).next_request(reason, ())
    package = PackagerAgent(ScriptedModelProvider([claim]), repository).build(
        reason, full, card_network="VISA"
    )
    for text in (assess.explanation, evidence.question, package.cover_note):
        assert claim not in text
    assert assess.explanation_source.value == "FALLBACK"
    assert evidence.question_source.value == "FALLBACK"
    assert package.cover_note_source.value == "FALLBACK"
