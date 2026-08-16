from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import EvidenceAgent, ExplanationSource
from oceanpilot.application.model_provider import ModelProviderError
from oceanpilot.domain.chargeback import (
    DisputeReasonCode,
    required_evidence_for,
)
from oceanpilot.domain.evidence_catalog import label_of

_REASON = DisputeReasonCode.PRODUCT_NOT_RECEIVED


def test_partial_evidence_asks_for_a_missing_critical_item():
    agent = EvidenceAgent(ScriptedModelProvider(default_text="请提供物流签收证明。"))
    request = agent.next_request(_REASON, [])
    assert request.complete is False
    assert request.next_evidence in request.missing
    assert request.next_evidence is not None
    assert request.question == "请提供物流签收证明。"
    assert request.question_source is ExplanationSource.MODEL


def test_agent_parses_the_json_evidence_question_contract():
    model = ScriptedModelProvider(
        [
            '{"question":"请提供物流签收证明。","why":"用于证明履约",'
            '"accepted_examples":["签收记录"],"safety_note":"请勿提供卡号"}'
        ]
    )

    request = EvidenceAgent(model).next_request(_REASON, [])

    assert request.question == "请提供物流签收证明。"
    assert "accepted_examples" in (model.requests[0].system or "")
    assert "ONLY valid JSON" in (model.requests[0].system or "")


def test_complete_evidence_needs_no_question():
    agent = EvidenceAgent(ScriptedModelProvider())
    request = agent.next_request(_REASON, required_evidence_for(_REASON))
    assert request.complete is True
    assert request.next_evidence is None
    assert request.missing == ()


def test_model_failure_falls_back_to_deterministic_question():
    agent = EvidenceAgent(ScriptedModelProvider(error=ModelProviderError()))
    request = agent.next_request(_REASON, [])
    assert request.complete is False
    assert request.question_source is ExplanationSource.FALLBACK
    # The fallback speaks plain language and never leaks the raw code token.
    assert label_of(request.next_evidence) in request.question
    assert request.next_evidence.value not in request.question
