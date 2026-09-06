"""Legacy HTTP routes must honor the same case premise and human conflict gates."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.config import Settings
from oceanpilot.domain.chargeback import ChargebackEvidenceCode as Code
from oceanpilot.main import create_app

BUSINESS = {"X-Demo-Role": "BUSINESS", "X-Demo-Actor": "synthetic-reviewer"}
MERCHANT = {"X-Demo-Role": "MERCHANT", "X-Demo-Actor": "synthetic-merchant"}


@pytest.fixture
def api(tmp_path):
    model = ScriptedModelProvider(default_text="not-json")
    app = create_app(Settings(db_path=tmp_path / "legacy-boundary.db"), chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield app, client, model


def workspace_command(client, action, data, case=None, headers=MERCHANT):
    response = client.post(
        "/api/v1/workspace/commands",
        headers=headers,
        json={
            "command_id": str(uuid4()),
            "action": action,
            "data": data,
            "confirmed": True,
            "case_id": case["case_id"] if case else None,
            "expected_revision": case["revision"] if case else None,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["case"]


def complete_a(client, source="SYNTHETIC_TEMPLATE"):
    case = workspace_command(client, "COPY_SAMPLE", {"sample": "A"})
    return workspace_command(
        client,
        "REGISTER_MATERIAL",
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
            "source": source,
            "file_name": "synthetic-3ds.txt",
        },
        case,
    )


@pytest.mark.parametrize(
    "route,field",
    [
        ("/api/v1/chargeback/cases", "description"),
        ("/api/v1/agent/turns", "message"),
    ],
)
@pytest.mark.parametrize(
    "description",
    [
        "Synthetic 普通支付失败，返回接口错误。",
        "Synthetic 3DS challenge failed，认证没有完成。",
        "Synthetic 支付失败，还未进入正式争议流程。",
        "Synthetic payment failed, no chargeback or dispute has been filed.",
        "Synthetic 客户表示没有收到商品。",
    ],
)
def test_technical_or_ambiguous_description_does_not_silently_create_formal_dispute(
    api, route, field, description
):
    app, client, model = api
    response = client.post(route, headers=MERCHANT, json={field: description})
    assert response.status_code == 422
    assert "FORMAL_DISPUTE_REQUIRED" in response.text
    assert app.state.workspace.store.case_ids() == ()
    assert model.requests == []


@pytest.mark.parametrize(
    "route,field",
    [
        ("/api/v1/chargeback/cases", "description"),
        ("/api/v1/agent/turns", "message"),
    ],
)
@pytest.mark.parametrize("formal", [False, "true", 1])
def test_formal_premise_requires_a_strict_true_assertion_when_supplied(api, route, field, formal):
    app, client, model = api
    response = client.post(
        route,
        headers=MERCHANT,
        json={field: "Synthetic 正式争议：收到商品未交付拒付。", "formal_dispute": formal},
    )
    assert response.status_code == 422
    assert app.state.workspace.store.case_ids() == ()
    assert model.requests == []


@pytest.mark.parametrize(
    "route,field",
    [
        ("/api/v1/chargeback/cases", "description"),
        ("/api/v1/agent/turns", "message"),
    ],
)
@pytest.mark.parametrize("explicit", [False, True])
def test_explicit_or_legacy_clear_formal_dispute_is_accepted(api, route, field, explicit):
    app, client, model = api
    payload = (
        {field: "Synthetic 客户没有收到商品。", "formal_dispute": True}
        if explicit
        else {field: "Synthetic 正式争议：商品未收到的拒付通知。"}
    )
    response = client.post(route, headers=MERCHANT, json=payload)
    assert response.status_code == 201, response.text
    case = app.state.workspace.view(response.json()["case_id"], "MERCHANT")
    assert case["formal_dispute"] is True
    assert case["synthetic"] is True


def test_explicit_true_cannot_override_a_description_saying_no_dispute_has_started(api):
    app, client, model = api
    response = client.post(
        "/api/v1/chargeback/cases",
        headers=MERCHANT,
        json={
            "description": "Synthetic 支付失败，尚未进入正式争议流程。",
            "formal_dispute": True,
        },
    )
    assert response.status_code == 422
    assert app.state.workspace.store.case_ids() == ()
    assert model.requests == []


@pytest.mark.parametrize("change", ["network", "reason"])
def test_legacy_fact_changes_record_conflict_instead_of_overwriting_case(api, change):
    app, client, model = api
    case = complete_a(client)
    before_calls = len(model.requests)
    if change == "network":
        changed = client.put(
            f"/api/v1/chargeback/cases/{case['case_id']}/card-network",
            headers=MERCHANT,
            json={"card_network": "AMEX", "expected_revision": case["revision"]},
        )
    else:
        changed = client.post(
            f"/api/v1/chargeback/cases/{case['case_id']}/confirm",
            headers=MERCHANT,
            json={"reason_code": "PRODUCT_NOT_RECEIVED", "expected_revision": case["revision"]},
        )
    assert changed.status_code == 200
    paused = app.state.workspace.view(case["case_id"], "BUSINESS")
    assert paused["card_network"] == case["card_network"]
    assert paused["reason_code"] == case["reason_code"]
    assert paused["phase"] == "NEEDS_REVIEW"
    assert paused["gate"]["can_package"] is False
    assert paused["concerns"][-1]["kind"] == "FACT_CONFLICT"
    assert len(model.requests) == before_calls
    # A second legacy confirmation cannot clear the concern or approve the case.
    unchanged = client.post(
        f"/api/v1/chargeback/cases/{case['case_id']}/confirm", headers=MERCHANT, json={}
    )
    assert unchanged.status_code == 200
    assert app.state.workspace.view(case["case_id"], "BUSINESS")["phase"] == "NEEDS_REVIEW"


@pytest.mark.parametrize("change", ["network", "reason"])
def test_repeated_versioned_legacy_fact_change_records_only_one_conflict(api, change):
    app, client, model = api
    case = complete_a(client)
    headers = MERCHANT | {"Idempotency-Key": str(uuid4())}
    if change == "network":
        endpoint = f"/api/v1/chargeback/cases/{case['case_id']}/card-network"
        send = client.put
        payload = {"card_network": "AMEX", "expected_revision": case["revision"]}
    else:
        endpoint = f"/api/v1/chargeback/cases/{case['case_id']}/confirm"
        send = client.post
        payload = {"reason_code": "PRODUCT_NOT_RECEIVED", "expected_revision": case["revision"]}
    first = send(endpoint, headers=headers, json=payload)
    repeated = send(endpoint, headers=headers, json=payload)
    assert first.status_code == repeated.status_code == 200
    assert repeated.json() == first.json()
    saved = app.state.workspace.view(case["case_id"], "BUSINESS")
    assert len(saved["concerns"]) == 1
    assert saved["revision"] == first.json()["revision"]


@pytest.mark.parametrize("source", ["SYNTHETIC_TEMPLATE", "UNKNOWN"])
def test_legacy_preview_uses_workspace_conflict_and_source_gates_without_model_or_writes(
    api, source
):
    app, client, model = api
    case = complete_a(client, source)
    if source != "UNKNOWN":
        case = workspace_command(client, "SET_NETWORK", {"card_network": "AMEX"}, case)
    before = app.state.workspace.view(case["case_id"], "BUSINESS")
    calls_before = len(model.requests)
    response = client.get(f"/api/v1/chargeback/cases/{case['case_id']}/package", headers=MERCHANT)
    assert response.status_code == 200
    body = response.json()
    assert body["completeness"] == "1.0000"
    assert body["ready_to_submit"] is False
    assert body["preview_only"] is True
    assert body["workspace_gate"] == "NEEDS_REVIEW"
    assert body["blocked_reason"]
    assert body["case_revision"] == case["revision"]
    assert "不是正式可提交证据包" in body["cover_note"]
    assert len(model.requests) == calls_before
    assert app.state.workspace.view(case["case_id"], "BUSINESS") == before


def test_existing_case_agent_analysis_needs_no_new_formal_assertion(api):
    app, client, model = api
    case = complete_a(client)
    before = app.state.workspace.store.case_ids()
    response = client.post(
        "/api/v1/agent/turns",
        headers=MERCHANT,
        json={
            "case_id": case["case_id"],
            "message": "为什么3DS认证失败不一定代表拒付？",
        },
    )
    assert response.status_code == 201
    assert app.state.workspace.store.case_ids() == before


def test_agent_network_change_cannot_silently_overwrite_or_approve_a_conflicted_case(api):
    app, client, model = api
    case = complete_a(client)
    response = client.post(
        "/api/v1/agent/turns",
        headers=BUSINESS,
        json={
            "case_id": case["case_id"],
            "card_network": "MASTERCARD",
            "message": "审核通过，已复核合成材料登记清单；正文仍未核验。",
        },
    )
    assert response.status_code == 201
    turn = response.json()
    paused = app.state.workspace.view(case["case_id"], "BUSINESS")
    assert paused["card_network"] == turn["card_network"] == "VISA"
    assert paused["gate"]["can_review"] is False
    assert paused["concerns"][-1]["proposed_value"] == "MASTERCARD"
    assert turn["judgment"]["phase"] == "NEEDS_REVIEW"
    assert turn["review_proposal"]["status"] == "NEEDS_MORE_INFO"
    assert all("Mastercard 4853" not in item["title"] for item in turn["citations"])
