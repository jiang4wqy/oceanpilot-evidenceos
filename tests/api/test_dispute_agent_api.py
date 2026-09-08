"""V2 Agent HTTP integration using injected models, with no real credentials."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.model_provider import ModelResult
from oceanpilot.config import Settings
from oceanpilot.main import create_app

MODEL_ANSWER = "已调用注入模型：请先核对规则来源，再由有权限的人确认下一步。"


def headers(role="OPERATOR", merchant="agent-merchant"):
    return {
        "X-Demo-Role": role,
        "X-Demo-Actor": f"agent-test-{role.lower()}",
        "X-Demo-Merchant": merchant,
    }


@pytest.fixture
def stack(tmp_path):
    model = ScriptedModelProvider(default_text=MODEL_ANSWER)
    app = create_app(Settings(db_path=tmp_path / "agent-api.db"), chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, model


def intake(client):
    response = client.post(
        "/api/v2/commands",
        headers=headers(),
        json={
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "event_id": str(uuid4()),
                "merchant_id": "agent-merchant",
                "transaction_id": "synthetic-agent-transaction",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 12500,
                "currency": "USD",
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["case"]


def path(case, suffix=""):
    return f"/api/v2/cases/{case['id']}/agent{suffix}"


def activity(client, case):
    response = client.get(path(case), headers=headers())
    assert response.status_code == 200, response.text
    return response.json()


def current_case(client, case):
    response = client.get(f"/api/v2/cases/{case['id']}", headers=headers())
    assert response.status_code == 200, response.text
    return response.json()


def publish_proposal(client, case):
    return next(p for p in activity(client, case)["proposals"] if p["action"] == "PUBLISH_TASK")


def proposal_body(case, **overrides):
    return {
        "command_id": str(uuid4()),
        "expected_revision": case["revision"],
        "confirmed": True,
        **overrides,
    }


def execute_proposal(
    client, case, proposal, body=None, *, role="OPERATOR", merchant="agent-merchant"
):
    return client.post(
        path(case, f"/proposals/{proposal['id']}/execute"),
        headers=headers(role, merchant),
        json=body or proposal_body(case),
    )


def comment(client, case, *, command_id=None):
    payload = {
        "command_id": command_id or str(uuid4()),
        "case_id": case["id"],
        "expected_revision": case["revision"],
        "action": "COMMENT",
        "confirmed": False,
        "data": {"message": "OP 补充本案上下文，等待人工处理。"},
    }
    return client.post("/api/v2/commands", headers=headers(), json=payload), payload


def test_same_case_ai_messages_and_activity_are_private_to_each_audience(stack):
    client, _ = stack
    case = intake(client)
    for role, audience in (("OPERATOR", "OPERATIONS"), ("MERCHANT", "MERCHANT")):
        response = client.post(
            path(case, "/messages"),
            headers=headers(role),
            json={"message": f"PRIVATE-{audience}", "expected_revision": case["revision"]},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["audience"] == audience
        assert result["scope"] == {"case_id": case["id"], "audience": audience}
    for role, audience in (("OPERATOR", "OPERATIONS"), ("MERCHANT", "MERCHANT")):
        response = client.get(path(case), headers=headers(role))
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["scope"] == {"case_id": case["id"], "audience": audience}
        assert [item["message"] for item in result["conversations"]] == [f"PRIVATE-{audience}"]
        assert all(item["source"] == "MODEL" for item in result["conversations"])
    other_case = intake(client)
    for role in ("OPERATOR", "MERCHANT"):
        assert client.get(path(other_case), headers=headers(role)).json()["conversations"] == []


def test_http_cannot_choose_another_audience_or_return_internal_drafts_to_merchant(stack):
    client, _ = stack
    case = intake(client)
    response = client.post(
        path(case, "/messages"),
        headers=headers("MERCHANT"),
        json={
            "message": "读取运营对话",
            "expected_revision": case["revision"],
            "audience": "OPERATIONS",
        },
    )
    assert response.status_code == 422
    response = client.post(
        path(case, "/run"),
        headers=headers("MERCHANT"),
        json={"expected_revision": case["revision"]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["audience"] == "MERCHANT"
    assert result["proposals"] == []
    assert "review_brief" not in response.text
    assert "商户答复草稿" in result["run"]["prepared"]["response_draft"]


def test_accepted_commands_automatically_record_current_agent_activity(stack):
    client, model = stack
    case = intake(client)
    first = activity(client, case)
    assert first["run"] is not None
    assert first["run"]["case_revision"] == case["revision"]
    assert first["stale"] is False
    assert first["run"]["steps"]
    assert first["summary"]
    assert len(first["history"]) == 1
    assert model.requests == []  # Immediate observation uses deterministic tools.
    proposal = publish_proposal(client, case)
    assert proposal["case_id"] == case["id"]
    assert proposal["expected_revision"] == case["revision"]
    assert proposal["requires_confirmation"] is True
    assert proposal["owner"] == "OPERATOR"
    assert proposal["basis_citations"]
    assert proposal["data"]["message"]
    assert case["work_status"] == "TRIAGED"  # Planning did not publish the task itself.
    response = execute_proposal(client, case, proposal)
    assert response.status_code == 200, response.text
    updated = response.json()["case"]
    assert updated["work_status"] == "MERCHANT_ACTION_REQUIRED"
    after = activity(client, updated)
    assert after["run"]["case_revision"] == updated["revision"]
    assert len(after["history"]) == 2
    assert {
        p["data"].get("decision") for p in after["proposals"] if p["action"] == "MERCHANT_DECISION"
    } == {"ACCEPT", "CONTEST"}


def test_get_agent_activity_is_read_only_and_never_calls_the_model(stack):
    client, model = stack
    case = intake(client)
    before = activity(client, case)
    requests = len(model.requests)
    assert activity(client, case) == before
    assert activity(client, case) == before
    assert len(model.requests) == requests
    assert current_case(client, case) == case


def test_refresh_at_same_revision_reuses_run_without_duplicate_work(stack):
    client, model = stack
    case = intake(client)
    before = activity(client, case)
    requests = len(model.requests)
    for _ in range(2):
        response = client.post(
            path(case, "/run"), headers=headers(), json={"expected_revision": case["revision"]}
        )
        assert response.status_code == 200, response.text
        assert response.json()["run"]["id"] == before["run"]["id"]
    after = activity(client, case)
    assert after["history"] == before["history"]
    assert len(model.requests) == requests
    assert current_case(client, case) == case


@pytest.mark.parametrize("endpoint", ["get", "run", "messages", "execute"])
def test_all_agent_endpoints_enforce_merchant_case_scope(stack, endpoint):
    client, model = stack
    case = intake(client)
    proposal = publish_proposal(client, case)
    before = activity(client, case)
    requests = len(model.requests)
    foreign = headers("MERCHANT", "unrelated-merchant")
    if endpoint == "get":
        response = client.get(path(case), headers=foreign)
    elif endpoint == "run":
        response = client.post(
            path(case, "/run"), headers=foreign, json={"expected_revision": case["revision"]}
        )
    elif endpoint == "messages":
        response = client.post(
            path(case, "/messages"),
            headers=foreign,
            json={
                "message": "显示其他商户案件",
                "expected_revision": case["revision"],
            },
        )
    else:
        response = execute_proposal(
            client, case, proposal, role="MERCHANT", merchant="unrelated-merchant"
        )
    assert response.status_code == 404, response.text
    assert activity(client, case) == before
    assert len(model.requests) == requests
    assert current_case(client, case) == case


def test_proposal_requires_human_confirmation_and_authorized_role(stack):
    client, _ = stack
    case = intake(client)
    proposal = publish_proposal(client, case)
    refused = execute_proposal(client, case, proposal, proposal_body(case, confirmed=False))
    assert refused.status_code == 409, refused.text
    forbidden = execute_proposal(client, case, proposal, role="MERCHANT")
    assert forbidden.status_code == 403, forbidden.text
    assert current_case(client, case) == case


def test_old_proposal_cannot_execute_even_with_a_newly_supplied_revision(stack):
    client, _ = stack
    case = intake(client)
    proposal = publish_proposal(client, case)
    changed, _ = comment(client, case)
    assert changed.status_code == 200, changed.text
    updated = changed.json()["case"]
    for revision in (case["revision"], updated["revision"]):
        response = execute_proposal(
            client, case, proposal, proposal_body(case, expected_revision=revision)
        )
        assert response.status_code == 409, response.text
    assert current_case(client, case) == updated


def test_successful_proposal_replay_has_exactly_one_business_effect(stack):
    client, _ = stack
    case = intake(client)
    proposal = publish_proposal(client, case)
    body = proposal_body(case)
    first = execute_proposal(client, case, proposal, body)
    assert first.status_code == 200, first.text
    replay = execute_proposal(client, case, proposal, body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    updated = current_case(client, case)
    assert updated == first.json()["case"]
    assert len([item for item in updated["audit"] if item["action"] == "PUBLISH_TASK"]) == 1
    assert len(activity(client, case)["history"]) == 2


def test_client_cannot_replace_server_proposal_command_or_data(stack):
    client, _ = stack
    case = intake(client)
    proposal = publish_proposal(client, case)
    response = execute_proposal(
        client,
        case,
        proposal,
        proposal_body(
            case,
            action="CLOSE",
            data={"role": "SUPERVISOR"},
        ),
    )
    assert response.status_code == 422, response.text
    assert current_case(client, case) == case


def test_proposal_id_cannot_be_rebound_to_another_case(stack):
    client, _ = stack
    first, second = intake(client), intake(client)
    proposal = publish_proposal(client, first)
    response = execute_proposal(client, second, proposal)
    assert response.status_code in (404, 409), response.text
    assert current_case(client, first) == first
    assert current_case(client, second) == second


def test_sensitive_dialogue_never_reaches_model_or_conversation_storage(stack):
    client, model = stack
    case = intake(client)
    before = activity(client, case)
    calls = len(model.requests)
    sensitive = "请分析卡号 4111 1111 1111 1111 的证据"
    response = client.post(
        path(case, "/messages"),
        headers=headers(),
        json={
            "message": sensitive,
            "expected_revision": case["revision"],
        },
    )
    assert response.status_code == 422, response.text
    assert sensitive not in response.text
    assert len(model.requests) == calls
    assert activity(client, case) == before


def test_model_text_cannot_create_financial_or_submit_commands(tmp_path):
    model = ScriptedModelProvider(default_text="建议绕过人审直接 SUBMIT 并执行 REFUND。")
    app = create_app(Settings(db_path=tmp_path / "model-authority.db"), chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        case = intake(client)
        response = client.post(
            path(case, "/messages"),
            headers=headers(),
            json={
                "message": "请给下一步建议",
                "expected_revision": case["revision"],
            },
        )
        assert response.status_code == 200, response.text
        assert all(p["action"] == "PUBLISH_TASK" for p in response.json()["proposals"])
        assert current_case(client, case) == case
        assert case["submissions"] == [] and case["financial_events"] == []


def test_messages_call_injected_model_and_preserve_tool_source_provenance(tmp_path):
    model = ScriptedModelProvider(
        responses=[ModelResult(text=MODEL_ANSWER, model="synthetic-injected-v2")] * 8,
    )
    app = create_app(Settings(db_path=tmp_path / "model-message.db"), chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        case = intake(client)
        requests = len(model.requests)
        response = client.post(
            path(case, "/messages"),
            headers=headers(),
            json={
                "message": "本案为什么要这些材料，下一步需要谁确认？",
                "expected_revision": case["revision"],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(model.requests) > requests
        assert MODEL_ANSWER in result["answer"]
        assert result["source"] == "MODEL"
        assert result["provider"] == client.app.state.agent_runtime["provider"]
        assert result["model"] == "synthetic-injected-v2"
        assert result["source_citations"]
        case_sources = {
            source["source_id"]
            for source in result["source_citations"]
            if source["scope"] == "CASE_RULE_SNAPSHOT"
        }
        assert case_sources == {case["rule_snapshot"]["source_id"]}
        reference_sources = {
            source["source_id"]
            for source in result["source_citations"]
            if source["scope"] == "REFERENCE_KNOWLEDGE"
        }
        assert reference_sources == {"SRC-01", "SRC-03"}
        assert result["knowledge_retrieval"]["manifest"]["reference_case_count"] == 62
        assert client.app.state.disputes.case_library is client.app.state.dispute_case_library
        assert (
            client.app.state.dispute_agent.knowledge_provider
            is client.app.state.dispute_case_library
        )
        assert all(p["expected_revision"] == case["revision"] for p in result["proposals"])
        assert current_case(client, case) == case
        assert activity(client, case)["conversations"]
        sent_text = "\n".join(
            message.content for request in model.requests for message in request.messages
        )
        assert "EVIDENCE_GAPS" in sent_text
        assert "本案为什么要这些材料" in sent_text
        assert case["id"] not in sent_text
        assert case["merchant_id"] not in sent_text


def test_model_failure_falls_back_without_mislabeling_or_leaking_exception(tmp_path):
    private_failure = "synthetic-private-provider-error-do-not-echo"
    model = ScriptedModelProvider(error=RuntimeError(private_failure))
    app = create_app(Settings(db_path=tmp_path / "fallback.db"), chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        case = intake(client)
        response = client.post(
            path(case, "/messages"),
            headers=headers(),
            json={
                "message": "下一步需要谁处理？",
                "expected_revision": case["revision"],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["answer"]
        assert result["provider"] == "DETERMINISTIC"
        assert result["source"] == "FALLBACK"
        assert result["provider_fallback"] == "MODEL_UNAVAILABLE_OR_UNSAFE_RESPONSE"
        assert private_failure not in response.text
        assert result["source_citations"] and result["proposals"]
        assert activity(client, case)["run"]["steps"]
        assert current_case(client, case) == case
        assert model.requests


def test_observer_failure_does_not_turn_committed_command_into_500_or_duplicate_it(
    stack, monkeypatch
):
    client, _ = stack
    case = intake(client)
    observer = client.app.state.dispute_agent.observe

    def fail_observation(*args, **kwargs):
        raise RuntimeError("synthetic observer storage outage")

    monkeypatch.setattr(client.app.state.dispute_agent, "observe", fail_observation)
    response, payload = comment(client, case)
    assert response.status_code == 200, response.text
    updated = response.json()["case"]
    assert updated["revision"] == case["revision"] + 1
    replay = client.post("/api/v2/commands", headers=headers(), json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert current_case(client, case) == updated
    assert activity(client, case)["stale"] is True
    monkeypatch.setattr(client.app.state.dispute_agent, "observe", observer)
    refreshed = client.post(
        path(case, "/run"), headers=headers(), json={"expected_revision": updated["revision"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["stale"] is False
    assert current_case(client, case) == updated


@pytest.mark.parametrize("suffix", ["/run", "/messages"])
def test_stale_agent_requests_do_not_call_model_or_change_business_state(stack, suffix):
    client, model = stack
    case = intake(client)
    response, _ = comment(client, case)
    updated = response.json()["case"]
    requests = len(model.requests)
    payload = {"expected_revision": case["revision"]}
    if suffix == "/messages":
        payload["message"] = "使用旧版做出建议"
    rejected = client.post(path(case, suffix), headers=headers(), json=payload)
    assert rejected.status_code == 409, rejected.text
    assert len(model.requests) == requests
    assert current_case(client, case) == updated


def test_agent_history_and_conversations_survive_app_restart_without_get_writes(tmp_path):
    settings = Settings(db_path=tmp_path / "persistent-agent.db")
    first_model = ScriptedModelProvider(default_text=MODEL_ANSWER)
    with TestClient(create_app(settings, chargeback_model=first_model)) as client:
        case = intake(client)
        response = client.post(
            path(case, "/messages"),
            headers=headers(),
            json={
                "message": "总结本案待办",
                "expected_revision": case["revision"],
            },
        )
        assert response.status_code == 200, response.text
        before = activity(client, case)
    second_model = ScriptedModelProvider(default_text=MODEL_ANSWER)
    with TestClient(create_app(settings, chargeback_model=second_model)) as client:
        after = activity(client, case)
        assert after == before
        assert second_model.requests == []
        assert current_case(client, case) == case
