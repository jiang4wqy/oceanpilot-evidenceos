from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import (
    ClassificationSource,
    IntakeAgent,
)
from oceanpilot.application.model_provider import ModelProviderError, SecurityTier
from oceanpilot.domain.chargeback import DisputeReasonCode


def test_model_label_is_used_when_valid():
    agent = IntakeAgent(ScriptedModelProvider(["PRODUCT_NOT_RECEIVED"]))
    outcome = agent.classify("下单后一直没消息")
    assert outcome.reason_code is DisputeReasonCode.PRODUCT_NOT_RECEIVED
    assert outcome.confident is True
    assert outcome.source is ClassificationSource.MODEL


def test_model_parses_the_json_intake_contract():
    model = ScriptedModelProvider(
        [
            '{"reason_code":"PRODUCT_NOT_RECEIVED","confidence":0.94,'
            '"case_summary":"客户未收到商品","needs_human_confirmation":false}'
        ]
    )

    outcome = IntakeAgent(model).classify("客户下单后一直没收到货")

    assert outcome.reason_code is DisputeReasonCode.PRODUCT_NOT_RECEIVED
    assert outcome.confident is True
    assert "needs_human_confirmation" in (model.requests[0].system or "")
    assert "ONLY valid JSON" in (model.requests[0].system or "")


def test_intake_uses_medium_tier_by_default():
    model = ScriptedModelProvider(["DUPLICATE_PROCESSING"])
    IntakeAgent(model).classify("被扣了两次")
    assert model.requests[0].task.security_tier is SecurityTier.MEDIUM


def test_model_failure_falls_back_to_chinese_keyword_heuristic():
    agent = IntakeAgent(ScriptedModelProvider(error=ModelProviderError()))
    outcome = agent.classify("我下单后一直没收到货")
    assert outcome.reason_code is DisputeReasonCode.PRODUCT_NOT_RECEIVED
    assert outcome.confident is True
    assert outcome.source is ClassificationSource.HEURISTIC


def test_unparseable_model_output_falls_back_to_heuristic():
    agent = IntakeAgent(ScriptedModelProvider(["不知道呀"]))
    outcome = agent.classify("这笔是盗刷，不是我买的")
    assert outcome.reason_code is DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    assert outcome.source is ClassificationSource.HEURISTIC


def test_no_signal_defaults_and_flags_not_confident():
    agent = IntakeAgent(ScriptedModelProvider(["???"]))
    outcome = agent.classify("你好在吗")
    assert outcome.confident is False
    assert outcome.source is ClassificationSource.HEURISTIC
    assert isinstance(outcome.reason_code, DisputeReasonCode)
