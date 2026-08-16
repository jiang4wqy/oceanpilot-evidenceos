from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.adapters.signals.synthetic import InMemorySignalSource
from oceanpilot.application.chargeback_agents import (
    ExplanationSource,
    PreventionAgent,
)
from oceanpilot.application.model_provider import ModelProviderError
from oceanpilot.domain.chargeback_prevention import (
    PreventionRiskLevel,
    PreventionSignals,
)

_HIGH_RISK = PreventionSignals(
    three_ds_authenticated=False,
    avs_match=False,
    cvv_match=False,
    customer_dispute_history=3,
)


def test_kernel_decides_and_model_only_phrases_the_tip():
    model = ScriptedModelProvider(default_text="请保存 3DS 验证与地址核验记录以备申诉。")
    outcome = PreventionAgent(model).assess(_HIGH_RISK)
    assert outcome.assessment.risk_level is PreventionRiskLevel.HIGH
    assert outcome.assessment.recommend_manual_review is True
    assert outcome.advice == "请保存 3DS 验证与地址核验记录以备申诉。"
    assert outcome.advice_source is ExplanationSource.MODEL


def test_prevention_parses_the_json_advice_contract():
    model = ScriptedModelProvider(
        [
            '{"advice":"请保存 3DS 验证记录。","risk_factors":["3DS 未认证"],'
            '"evidence_to_retain":["3DS 记录"],"manual_review_note":"建议人工复核"}'
        ]
    )

    outcome = PreventionAgent(model).assess(_HIGH_RISK)

    assert outcome.advice == "请保存 3DS 验证记录。"
    assert "evidence_to_retain" in (model.requests[0].system or "")
    assert "ONLY valid JSON" in (model.requests[0].system or "")


def test_falls_back_to_deterministic_advice_when_model_unavailable():
    model = ScriptedModelProvider(error=ModelProviderError())
    outcome = PreventionAgent(model).assess(_HIGH_RISK)
    assert outcome.advice_source is ExplanationSource.FALLBACK
    assert "拒付风险高" in outcome.advice
    assert "建议人工复核" in outcome.advice
    # Every recommended evidence code is named in the fallback tip.
    for code in outcome.assessment.recommended_evidence:
        assert code.value in outcome.advice


def test_empty_model_output_falls_back():
    model = ScriptedModelProvider(default_text="   ")
    outcome = PreventionAgent(model).assess(_HIGH_RISK)
    assert outcome.advice_source is ExplanationSource.FALLBACK


def test_low_risk_advice_needs_no_extra_evidence():
    model = ScriptedModelProvider(error=ModelProviderError())
    outcome = PreventionAgent(model).assess(PreventionSignals())
    assert outcome.assessment.risk_level is PreventionRiskLevel.LOW
    assert outcome.advice_source is ExplanationSource.FALLBACK
    assert "暂无需额外留证" in outcome.advice


def test_agent_sends_low_security_prevention_task_to_the_model():
    model = ScriptedModelProvider(default_text="ok")
    PreventionAgent(model).assess(_HIGH_RISK)
    assert len(model.requests) == 1
    task = model.requests[0].task
    assert task.kind == "chargeback_prevention_advice"
    assert task.security_tier.value == "LOW"


def test_synthetic_signal_source_round_trip():
    source = InMemorySignalSource()
    assert source.get_signals("txn-1") is None
    source.put("txn-1", _HIGH_RISK)
    assert source.get_signals("txn-1") == _HIGH_RISK

    seeded = InMemorySignalSource({"txn-2": PreventionSignals()})
    assert seeded.get_signals("txn-2") == PreventionSignals()
