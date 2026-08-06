from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import (
    ChargebackAssessAgent,
    ExplanationSource,
)
from oceanpilot.application.model_provider import ModelProviderError
from oceanpilot.domain.chargeback import (
    ChargebackEvidenceCode,
    DisputeReasonCode,
    assess_chargeback,
    required_evidence_for,
)

_REASON = DisputeReasonCode.PRODUCT_NOT_RECEIVED


def test_agent_uses_model_explanation_but_keeps_deterministic_decision():
    model = ScriptedModelProvider(["因为关键证据齐备，建议提交。"])
    agent = ChargebackAssessAgent(model)
    present = required_evidence_for(_REASON)

    outcome = agent.assess(_REASON, present)

    # The model only explains; the decision is exactly the deterministic kernel's.
    assert outcome.assessment == assess_chargeback(_REASON, present)
    assert outcome.explanation == "因为关键证据齐备，建议提交。"
    assert outcome.explanation_source is ExplanationSource.MODEL
    # the model was handed the deterministic facts + a guardrail system prompt
    request = model.requests[0]
    assert request.system is not None
    assert "win_likelihood" in request.messages[0].content
    assert _REASON.value in request.messages[0].content


def test_model_failure_falls_back_to_deterministic_explanation():
    model = ScriptedModelProvider(error=ModelProviderError())
    agent = ChargebackAssessAgent(model)

    outcome = agent.assess(_REASON, [])

    assert outcome.explanation_source is ExplanationSource.FALLBACK
    assert outcome.explanation  # non-empty
    assert outcome.assessment == assess_chargeback(_REASON, [])
    assert outcome.assessment.requires_human is True


def test_empty_model_text_falls_back():
    model = ScriptedModelProvider([""])
    agent = ChargebackAssessAgent(model)
    outcome = agent.assess(_REASON, required_evidence_for(_REASON))
    assert outcome.explanation_source is ExplanationSource.FALLBACK
    assert outcome.explanation


def test_agent_never_changes_win_likelihood_or_routing():
    # even if the model "claims" something else, decision fields come from kernel
    model = ScriptedModelProvider(["胜诉率 100%，无需人工。"])
    agent = ChargebackAssessAgent(model)
    outcome = agent.assess(DisputeReasonCode.FRAUD_CARD_NOT_PRESENT, [])
    kernel = assess_chargeback(DisputeReasonCode.FRAUD_CARD_NOT_PRESENT, [])
    assert outcome.assessment.win_likelihood == kernel.win_likelihood
    assert outcome.assessment.requires_human is True
    assert outcome.assessment.responsible_team == kernel.responsible_team


def test_fallback_runs_without_any_model_calls_on_error():
    model = ScriptedModelProvider(error=ModelProviderError())
    agent = ChargebackAssessAgent(model)
    agent.assess(_REASON, [ChargebackEvidenceCode.TRANSACTION_RECEIPT])
    # one attempt was made, and it failed safely
    assert len(model.requests) == 1
