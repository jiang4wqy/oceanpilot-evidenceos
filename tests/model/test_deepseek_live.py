"""Optional live integration tests against the DeepSeek API.

The module stays skipped in CI unless ``DEEPSEEK_API_KEY`` is explicitly
injected. Run it locally through the ignored ``.env`` file with::

    .venv\\Scripts\\dotenv.exe -f .env run -- \
      .venv\\Scripts\\python.exe -m pytest tests/model/test_deepseek_live.py -q
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="DEEPSEEK_API_KEY not set; live DeepSeek integration test skipped",
)


def _deepseek():
    from oceanpilot.adapters.model.deepseek import build_deepseek_model_provider_from_env

    provider = build_deepseek_model_provider_from_env()
    assert provider is not None
    return provider


def test_live_intake_classifies_a_synthetic_dispute_description():
    from oceanpilot.application.chargeback_agents import IntakeAgent
    from oceanpilot.domain.chargeback import DisputeReasonCode

    outcome = IntakeAgent(_deepseek()).classify("Synthetic 案件：客户下单后一直没收到货")

    assert isinstance(outcome.reason_code, DisputeReasonCode)


def test_live_assess_explains_without_changing_the_deterministic_decision():
    from oceanpilot.application.chargeback_agents import ChargebackAssessAgent, ExplanationSource
    from oceanpilot.domain.chargeback import (
        DisputeReasonCode,
        assess_chargeback,
        required_evidence_for,
    )

    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    present = required_evidence_for(reason)
    expected = assess_chargeback(reason, present)

    outcome = ChargebackAssessAgent(_deepseek()).assess(reason, present)

    assert outcome.assessment == expected
    assert outcome.explanation.strip()
    assert outcome.explanation_source is ExplanationSource.MODEL
