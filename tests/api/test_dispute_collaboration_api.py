import base64
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app
from tests.v21_support import normalized_intake


@pytest.fixture
def api(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "base.db", chargeback_db_path=tmp_path / "v2.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.dispute_agent.model = None
        app.state.dispute_agent_events.enabled = False
        auth = app.state.v21_auth
        credentials = {}
        for name, role, merchant in [
            ("operator", "OPERATOR", "merchant-a"),
            ("merchant", "MERCHANT", "merchant-a"),
            ("outsider", "MERCHANT", "merchant-b"),
        ]:
            auth.create_user(
                username=name,
                password="Synthetic-pass-only!",
                display_name=name,
                role=role,
                merchant_id=merchant if role == "MERCHANT" else None,
                merchant_ids=[merchant],
                user_id=name,
            )
            response = client.post(
                "/api/v2/session/login", json={"username": name, "password": "Synthetic-pass-only!"}
            )
            assert response.status_code == 200
            credentials[name] = {
                "Cookie": "oceanpilot_session=" + client.cookies.get("oceanpilot_session"),
                "X-CSRF-Token": response.json()["csrf_token"],
            }
            client.cookies.clear()
        result = normalized_intake(
            client,
            request_headers=credentials["operator"],
            payload={
                "command_id": str(uuid4()),
                "action": "INTAKE",
                "confirmed": True,
                "data": {
                    "merchant_id": "merchant-a",
                    "transaction_id": "synthetic-order-http",
                    "scheme": "VISA",
                    "channel": "MOCK",
                    "reason_code": "13.1",
                    "amount_minor": 12500,
                    "currency": "USD",
                    "event_id": str(uuid4()),
                },
            },
        )
        assert result.status_code == 200, result.text
        yield client, app, credentials, result.json()["case"]


def prefix(case):
    return f"/api/v2/cases/{case['id']}/collaboration"


def test_trusted_sessions_share_case_and_read_receipts_without_role_switch(api):
    client, _, headers, case = api
    response = client.post(
        prefix(case) + "/messages",
        headers=headers["operator"],
        json={"command_id": str(uuid4()), "message": "请提供本案收货确认。"},
    )
    assert response.status_code == 200, response.text
    message = response.json()["message"]
    view = client.get(prefix(case), headers=headers["merchant"]).json()
    assert view["messages"][0]["id"] == message["id"]
    assert view["case_revision"] == case["revision"]
    assert {p["user_id"] for p in view["participants"]} == {"operator", "merchant"}
    read = client.post(
        prefix(case) + "/read", headers=headers["merchant"], json={"cursor": message["cursor"]}
    )
    assert read.status_code == 200
    seen = client.get(prefix(case), headers=headers["operator"]).json()
    assert {"actor_id": "merchant", "cursor": message["cursor"]} in seen["read_receipts"]


def test_internal_scope_and_demo_header_forgery_are_denied(api):
    client, _, headers, case = api
    client.post(
        prefix(case) + "/messages",
        headers=headers["operator"],
        json={"command_id": str(uuid4()), "scope": "OP_INTERNAL", "message": "private-op-notes"},
    )
    forged = headers["merchant"] | {"X-Demo-Role": "OPERATOR", "X-Demo-Actor": "operator"}
    assert client.get(prefix(case) + "?scope=OP_INTERNAL", headers=forged).status_code == 404
    assert "private-op-notes" not in client.get(prefix(case), headers=forged).text
    assert client.get(prefix(case), headers=headers["outsider"]).status_code == 404
    assert (
        client.post(
            prefix(case) + "/messages",
            headers=headers["outsider"],
            json={"command_id": str(uuid4()), "message": "other case"},
        ).status_code
        == 404
    )


def test_mutating_shared_route_requires_csrf_and_rejects_wrong_types(api):
    client, _, headers, case = api
    no_csrf = {"Cookie": headers["merchant"]["Cookie"]}
    assert (
        client.post(
            prefix(case) + "/messages",
            headers=no_csrf,
            json={"command_id": str(uuid4()), "message": "hello"},
        ).status_code
        == 403
    )
    for payload in [
        {"command_id": str(uuid4()), "message": 42},
        {"command_id": str(uuid4()), "message": "hi", "ask_agent": "yes"},
        {"command_id": str(uuid4()), "message": "hi", "scope": "OPERATIONS"},
    ]:
        assert (
            client.post(
                prefix(case) + "/messages", headers=headers["merchant"], json=payload
            ).status_code
            == 422
        )
    assert client.get(prefix(case), headers=headers["merchant"]).json()["messages"] == []


def test_assigned_op_can_claim_resolve_actual_merchant_handoff(api):
    client, _, headers, case = api
    response = client.post(
        prefix(case) + "/handoffs",
        headers=headers["merchant"],
        json={"command_id": str(uuid4()), "reason": "请人工解释收货确认的要求。"},
    )
    assert response.status_code == 200, response.text
    handoff = response.json()["handoff"]
    assert handoff["assignee_id"] == "operator"
    endpoint = prefix(case) + "/handoffs/" + handoff["id"]
    assert (
        client.post(
            endpoint,
            headers=headers["merchant"],
            json={"command_id": str(uuid4()), "action": "CLAIM", "reason": "take"},
        ).status_code
        == 403
    )
    for action in ("CLAIM", "RESOLVE"):
        response = client.post(
            endpoint,
            headers=headers["operator"],
            json={"command_id": str(uuid4()), "action": action, "reason": "已解释具体材料要求。"},
        )
        assert response.status_code == 200, response.text
    assert response.json()["handoff"]["status"] == "RESOLVED"
    assert (
        client.get(prefix(case), headers=headers["merchant"]).json()["case_revision"]
        == case["revision"]
    )


def test_file_http_returns_merchant_projection_and_original_authenticated_bytes(api):
    client, _, headers, case = api
    for action, data, actor in [
        ("PUBLISH_TASK", {}, "operator"),
        ("MERCHANT_DECISION", {"decision": "CONTEST", "reason": "提供合成签收证据。"}, "merchant"),
    ]:
        response = client.post(
            "/api/v2/commands",
            headers=headers[actor],
            json={
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "action": action,
                "confirmed": True,
                "data": data,
            },
        )
        assert response.status_code == 200, response.text
        case = response.json()["case"]
    content = json.dumps(
        {
            "transaction_id": "synthetic-order-http",
            "currency": "USD",
            "amount_minor": 12500,
            "delivered_at": "2026-09-01",
            "recipient_confirmation": "synthetic receipt",
        }
    ).encode()
    response = client.post(
        prefix(case) + "/files",
        headers=headers["merchant"],
        json={
            "command_id": str(uuid4()),
            "expected_revision": case["revision"],
            "code": "fulfillment.proof_of_delivery",
            "title": "合成签收凭证",
            "filename": "delivery.json",
            "mime_type": "application/json",
            "content_base64": base64.b64encode(content).decode(),
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["file"]["content_check"]["status"] == "SUPPORTED"
    assert not {"audit", "reviews", "packages", "financial_events"}.intersection(result["case"])
    endpoint = prefix(case) + "/files/" + result["file"]["object_id"]
    download = client.get(endpoint, headers=headers["operator"])
    assert download.status_code == 200 and download.content == content
    assert download.headers["x-content-type-options"] == "nosniff"
    assert client.get(endpoint, headers=headers["outsider"]).status_code == 404
    assert client.get(endpoint).status_code == 401


def test_disabled_account_loses_read_and_file_scope_immediately(api):
    client, app, headers, case = api
    app.state.v21_auth.set_disabled("merchant", True)
    assert client.get(prefix(case), headers=headers["merchant"]).status_code == 401
