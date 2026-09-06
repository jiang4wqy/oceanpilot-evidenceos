import json

import pytest

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.case_copilot import CaseCopilotAgent, CopilotActionKind
from oceanpilot.application.model_provider import ModelFailureCode, ModelProviderError

PAYLOAD = {
    "intent": "PROPOSE_EVIDENCE_SUBMISSION",
    "assistant_message": "请先登记 Synthetic 交易收据；登记不代表正文已经核验。",
    "analysis_summary": "当前仍缺少交易收据。",
    "recommended_action_kind": "OPEN_EVIDENCE_MODAL",
    "recommended_action_label": "登记交易收据",
    "target_evidence_code": "TRANSACTION_RECEIPT",
    "requires_confirmation": True,
}


def respond(model, *, offline=False, phase="NEED_EVIDENCE"):
    return CaseCopilotAgent(model, offline=offline).respond(
        "为什么仍然缺少材料？",
        problem_type="合成争议",
        phase=phase,
        readiness="0/1 项",
        responsible_team="CUSTOMER_SUPPORT",
        human_gate=True,
        missing_codes=("TRANSACTION_RECEIPT",),
        missing_labels=("交易收据",),
    )


def test_valid_model_result_has_actual_model_source_and_keeps_human_gate():
    outcome = respond(ScriptedModelProvider(default_text=json.dumps(PAYLOAD)))
    assert outcome.source == "MODEL"
    assert outcome.offline is False
    assert outcome.failure_code is None
    assert outcome.requires_confirmation is True


def test_offline_output_is_deterministic_and_makes_no_model_request():
    model = ScriptedModelProvider(default_text=json.dumps(PAYLOAD))
    outcome = respond(model, offline=True)
    assert outcome.source == "DETERMINISTIC"
    assert outcome.offline is True
    assert outcome.failure_code is None
    assert model.requests == []


@pytest.mark.parametrize("code", list(ModelFailureCode))
def test_provider_failure_is_distinct_from_offline_mode(code):
    outcome = respond(ScriptedModelProvider(error=ModelProviderError(code)))
    assert outcome.source == "FALLBACK"
    assert outcome.offline is False
    assert outcome.failure_code == code.value
    assert outcome.requires_confirmation is True


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"requires_confirmation": False}, "INVALID_ACTION"),
        ({"requires_confirmation": 1}, "INVALID_ACTION"),
        ({"recommended_action_kind": "SEND_APPEAL"}, "INVALID_ACTION"),
        ({"intent": "APPROVE_CASE"}, "INVALID_ACTION"),
        ({"target_evidence_code": "UNREGISTERED"}, "INVALID_ACTION"),
        ({"target_evidence_code": None}, "INVALID_ACTION"),
        ({"recommended_action_label": ""}, "INVALID_ACTION"),
        ({"extra_field": True}, "INVALID_RESPONSE"),
        ({"assistant_message": ""}, "INVALID_RESPONSE"),
        ({"analysis_summary": 123}, "INVALID_RESPONSE"),
        ({"recommended_action_label": "4111 1111 1111 1111"}, "UNSAFE_OUTPUT"),
    ],
)
def test_invalid_model_contract_and_actions_degrade_safely(changes, code):
    outcome = respond(ScriptedModelProvider(default_text=json.dumps(PAYLOAD | changes)))
    assert outcome.source == "FALLBACK"
    assert outcome.failure_code == code
    assert outcome.requires_confirmation is True
    assert outcome.target_evidence_code == "TRANSACTION_RECEIPT"
    assert "4111" not in outcome.action_label


@pytest.mark.parametrize(
    "text",
    [
        "not-json",
        "[]",
        json.dumps(PAYLOAD)[:-1] + ',"requires_confirmation":false}',
        json.dumps(PAYLOAD)[:-1] + ',"extra":NaN}',
        "```json\n" + json.dumps(PAYLOAD) + "\n```",
    ],
)
def test_malformed_json_is_an_explicit_fallback(text):
    outcome = respond(ScriptedModelProvider(default_text=text))
    assert outcome.source == "FALLBACK"
    assert outcome.failure_code == "INVALID_RESPONSE"
    assert outcome.requires_confirmation is True


def test_model_cannot_open_evidence_submission_before_reason_confirmation():
    outcome = respond(
        ScriptedModelProvider(default_text=json.dumps(PAYLOAD)), phase="REASON_PROPOSED"
    )
    assert outcome.source == "FALLBACK"
    assert outcome.failure_code == "INVALID_ACTION"
    assert outcome.action_kind is CopilotActionKind.OPEN_CASE_DETAIL
    assert "人工确认" in outcome.assistant_message


@pytest.mark.parametrize(
    "field", ["assistant_message", "analysis_summary", "recommended_action_label"]
)
@pytest.mark.parametrize(
    "claim",
    [
        "登记齐全，材料内容一致。",
        "因此交易真实。",
        "胜诉概率为90%。",
        "胜率90%。",
        "已经读取文件正文。",
    ],
)
def test_valid_json_cannot_turn_registered_metadata_into_verified_content(field, claim):
    outcome = respond(ScriptedModelProvider(default_text=json.dumps(PAYLOAD | {field: claim})))
    assert outcome.source == "FALLBACK"
    assert outcome.failure_code == "UNSUPPORTED_CLAIM"
    assert outcome.requires_confirmation is True
    assert claim not in outcome.assistant_message
    assert claim not in outcome.analysis_summary
    assert claim not in outcome.action_label
