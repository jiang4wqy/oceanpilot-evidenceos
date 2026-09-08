from concurrent.futures import ThreadPoolExecutor
from time import sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.config import Settings
from oceanpilot.main import create_app


def headers(role="OPERATOR", merchant="sync-a"):
    return {"X-Demo-Role": role, "X-Demo-Actor": f"sync-{role}", "X-Demo-Merchant": merchant}


@pytest.fixture
def stack(tmp_path):
    model = ScriptedModelProvider(default_text="合成模型回复，不访问任何真实模型。")
    app = create_app(Settings(db_path=tmp_path / "updates-api.db"), chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, model


def intake(client, merchant="sync-a"):
    response = client.post(
        "/api/v2/commands",
        headers=headers(),
        json={
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "merchant_id": merchant,
                "transaction_id": "sync-transaction",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 12500,
                "currency": "USD",
                "event_id": str(uuid4()),
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["case"]


def updates(client, role="OPERATOR", merchant="sync-a", **params):
    return client.get(
        "/api/v2/updates", headers=headers(role, merchant), params={"timeout": 0, **params}
    )


def test_http_scoped_baseline_and_case_filter_do_not_invoke_models(stack):
    client, model = stack
    own, foreign = intake(client), intake(client, "sync-b")
    response = updates(client, "MERCHANT")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["changed_case_ids"] == [own["id"]]
    assert foreign["id"] not in response.text
    assert updates(client, "MERCHANT", case_id=foreign["id"]).status_code == 404
    assert model.requests == []
    cursor = response.json()["cursor"]
    assert updates(client, "MERCHANT", cursor=cursor).json()["changes"] == []
    assert model.requests == []


def test_http_long_poll_returns_on_commit_without_client_refresh(stack):
    client, model = stack
    case = intake(client)
    cursor = updates(client, "MERCHANT", case_id=case["id"]).json()["cursor"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            updates, client, "MERCHANT", case_id=case["id"], cursor=cursor, timeout=2
        )
        sleep(0.04)
        changed = client.post(
            "/api/v2/commands",
            headers=headers(),
            json={
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "action": "PUBLISH_TASK",
                "confirmed": True,
                "data": {"message": "请商户确认本案"},
            },
        )
        assert changed.status_code == 200, changed.text
        response = future.result(timeout=3)
    assert response.status_code == 200, response.text
    assert response.json()["changed_case_ids"] == [case["id"]]
    assert response.json()["changes"][0]["revision"] == 2
    assert response.json()["timed_out"] is False
    assert model.requests == []


def test_http_private_ai_message_wakes_only_its_workspace(stack):
    client, model = stack
    case = intake(client)
    op_cursor = updates(client).json()["cursor"]
    merchant_cursor = updates(client, "MERCHANT").json()["cursor"]
    answer = client.post(
        f"/api/v2/cases/{case['id']}/agent/messages",
        headers=headers("MERCHANT"),
        json={"expected_revision": case["revision"], "message": "请协助商户补证"},
    )
    assert answer.status_code == 200, answer.text
    count = len(model.requests)
    assert count == 1
    assert updates(client, cursor=op_cursor).json()["changes"] == []
    changes = updates(client, "MERCHANT", cursor=merchant_cursor).json()["changes"]
    assert changes == [
        {
            "case_id": case["id"],
            "revision": case["revision"],
            "case_changed": False,
            "agent_changed": False,
            "conversation_changed": True,
        }
    ]
    assert len(model.requests) == count


@pytest.mark.parametrize("timeout", [-1, 21, "NaN", "Infinity", "bad"])
def test_http_rejects_unbounded_timeout(stack, timeout):
    response = updates(stack[0], timeout=timeout)
    assert response.status_code == 422


def test_http_no_changes_timeout_preserves_cursor(stack):
    client, _ = stack
    intake(client)
    cursor = updates(client).json()["cursor"]
    response = updates(client, cursor=cursor, timeout=0.05)
    assert response.status_code == 200, response.text
    assert response.json()["cursor"] == cursor
    assert response.json()["timed_out"] is True
    assert response.json()["changes"] == []
