"""Optional live integration test against the real Claude API (T10).

Runs only when ``ANTHROPIC_API_KEY`` is set; otherwise the whole module is
skipped, so no-key CI stays green. When a key is present (local / controlled
environment) it drives the chargeback agents end-to-end through a real
``ClaudeProvider`` and asserts the deterministic kernel decision is preserved and
the model produced a non-empty explanation — i.e. the model explains, it never
decides.

Run just this file with a key:
    ANTHROPIC_API_KEY=sk-ant-... \
      /root/autodl-tmp/oceanpilot-venv/bin/python -m pytest tests/model/test_claude_live.py -q
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; live Claude integration test skipped",
)


def _claude():
    from oceanpilot.adapters.model.claude import ClaudeProvider

    return ClaudeProvider()


def test_live_intake_classifies_a_dispute_description():
    from oceanpilot.application.chargeback_agents import IntakeAgent
    from oceanpilot.domain.chargeback import DisputeReasonCode

    outcome = IntakeAgent(_claude()).classify("客户下单后一直没收到货，要求拒付")
    # The label may come from the model or the heuristic fallback, but it must be
    # a valid reason code — most plausibly PRODUCT_NOT_RECEIVED.
    assert isinstance(outcome.reason_code, DisputeReasonCode)


def test_live_assess_explains_without_changing_the_decision():
    from oceanpilot.application.chargeback_agents import ChargebackAssessAgent, ExplanationSource
    from oceanpilot.domain.chargeback import (
        DisputeReasonCode,
        assess_chargeback,
        required_evidence_for,
    )

    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    present = required_evidence_for(reason)
    expected = assess_chargeback(reason, present)

    outcome = ChargebackAssessAgent(_claude()).assess(reason, present)

    # Deterministic decision is untouched; only the prose comes from the model.
    assert outcome.assessment == expected
    assert outcome.explanation.strip()
    assert outcome.explanation_source is ExplanationSource.MODEL
