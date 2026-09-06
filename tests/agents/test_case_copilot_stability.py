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


def ask_complete_case(
    model, message, *, offline=True, phase="ASSESSED", review_status="UNREVIEWED"
):
    return CaseCopilotAgent(model, offline=offline).respond(
        message,
        problem_type="合成正式争议",
        phase=phase,
        readiness="6/6 项",
        responsible_team="RISK",
        human_gate=True,
        missing_codes=(),
        missing_labels=(),
        review_status=review_status,
    )


@pytest.mark.parametrize("offline", [True, False])
def test_identity_and_complete_material_questions_get_distinct_bounded_answers(offline):
    model = ScriptedModelProvider(error=ModelProviderError(ModelFailureCode.TIMEOUT))
    identity = ask_complete_case(model, "你是谁？", offline=offline)
    materials = ask_complete_case(model, "现在还缺什么材料？", offline=offline)
    assert "我是 OceanPilot 案件助手" in identity.assistant_message
    assert (
        "本次回答未调用实时模型" in identity.assistant_message
        if offline
        else "降级说明" in identity.assistant_message
    )
    assert identity.action_kind is CopilotActionKind.NONE
    assert identity.target_evidence_code is None
    assert "清单没有缺失项" in materials.assistant_message
    assert "仍待业务人员" in materials.assistant_message
    assert identity.assistant_message != materials.assistant_message
    for result in (identity, materials):
        assert "真实文件正文" in result.assistant_message
        assert "ASSESSED" not in result.assistant_message + result.analysis_summary
        assert "RISK" not in result.assistant_message + result.analysis_summary
        assert result.requires_confirmation is True
        assert result.source == ("DETERMINISTIC" if offline else "FALLBACK")
        assert result.failure_code == (None if offline else "TIMEOUT")
    assert len(model.requests) == (0 if offline else 2)


@pytest.mark.parametrize(
    ("review_status", "expected"),
    [
        ("APPROVED", "已有人工登记复核通过记录"),
        ("NEEDS_MORE_INFO", "人工退回补充"),
        ("REJECTED", "已驳回"),
    ],
)
def test_complete_material_reply_respects_existing_human_review(review_status, expected):
    result = ask_complete_case(ScriptedModelProvider(), "还缺什么？", review_status=review_status)
    assert expected in result.assistant_message
    assert "仍待业务人员对当前版本进行人工登记复核" not in result.assistant_message
    assert "真实文件正文仍未读取或核验" in result.assistant_message
    assert result.requires_confirmation is True


@pytest.mark.parametrize(
    ("phase", "expected"),
    [("NEEDS_REVIEW", "登记疑点或来源问题"), ("NO_EXACT_RULE", "没有精确匹配")],
)
def test_full_registration_does_not_hide_another_review_blocker(phase, expected):
    result = ask_complete_case(ScriptedModelProvider(), "审核通过", phase=phase)
    assert expected in result.assistant_message
    assert "不会写入审核决定" in result.assistant_message
    assert result.requires_confirmation is True
    assert result.action_kind is CopilotActionKind.OPEN_CASE_DETAIL
    assert phase not in result.assistant_message + result.analysis_summary


def test_routing_reply_names_the_human_team_without_internal_enum():
    result = ask_complete_case(ScriptedModelProvider(), "谁负责处理？")
    assert "风控团队" in result.assistant_message
    assert "RISK" not in result.assistant_message + result.analysis_summary
    assert "人工登记复核" in result.assistant_message
