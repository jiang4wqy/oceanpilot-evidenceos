from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import IntakeAgent
from oceanpilot.application.model_provider import ModelProviderError


def test_extracts_facts_from_valid_json():
    model = ScriptedModelProvider(
        [
            '{"amount": "1200", "currency": "USD", '
            '"occurred_on": "2026-07-20", "summary": "客户称未收到跨境订单"}'
        ]
    )
    facts = IntakeAgent(model).extract_facts("下单后一直没收到货")
    assert facts.amount == "1200"
    assert facts.currency == "USD"
    assert facts.occurred_on == "2026-07-20"
    assert facts.summary == "客户称未收到跨境订单"
    assert facts.is_empty is False


def test_numeric_amount_is_coerced_to_string():
    facts = IntakeAgent(
        ScriptedModelProvider(['{"amount": 1200.5, "summary": "x"}'])
    ).extract_facts("...")
    assert facts.amount == "1200.5"


def test_non_json_output_yields_empty_facts():
    facts = IntakeAgent(ScriptedModelProvider(default_text="（合成模型输出）")).extract_facts("...")
    assert facts.is_empty is True


def test_model_error_yields_empty_facts():
    facts = IntakeAgent(ScriptedModelProvider(error=ModelProviderError())).extract_facts("...")
    assert facts.is_empty is True


def test_sensitive_summary_is_dropped():
    # A summary containing a Luhn-valid card number trips the guard -> empty.
    model = ScriptedModelProvider(['{"summary": "卡号 4111111111111111 未收到"}'])
    facts = IntakeAgent(model).extract_facts("...")
    assert facts.is_empty is True
