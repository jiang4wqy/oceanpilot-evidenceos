"""V2.1 accounts are server sessions, never roles inferred from a URL or header."""

import json
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app
from tests.v21_support import normalized_intake


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path / "identity.db"))) as result:
        yield result


@pytest.mark.parametrize("role", ["MERCHANT", "OPERATOR", "ADMIN"])
def test_client_role_headers_do_not_authenticate(client, role):
    response = client.get("/api/v2/cases", headers={"X-Demo-Role": role})
    assert response.status_code == 401


@pytest.mark.parametrize("surface", ["merchant", "operations", "governance"])
def test_business_page_requires_a_trusted_login(client, surface):
    response = client.get(f"/v2/{surface}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/v2/login?")


@pytest.fixture
def accounts(client):
    """Actual sessions with two tenants and separately provisioned decision makers."""
    specs = [
        ("merchant-a", "MERCHANT", ["merchant-a"]),
        ("merchant-b", "MERCHANT", ["merchant-b"]),
        ("operator-a", "OPERATOR", ["merchant-a"]),
        ("operator-b", "OPERATOR", ["merchant-b"]),
        ("risk-reviewer", "RISK_OFFICER", ["merchant-a", "merchant-b"]),
        ("director", "DIRECTOR", []),
    ]
    users, sessions = {}, {}
    for name, role, merchants in specs:
        users[name] = client.app.state.v21_auth.create_user(
            username=name,
            password="test-only-password-2026",
            display_name=name,
            role=role,
            merchant_ids=merchants,
            merchant_id=merchants[0] if role == "MERCHANT" else None,
        )
        actor_client = TestClient(client.app)
        response = actor_client.post(
            "/api/v2/session/login",
            json={
                "username": name,
                "password": "test-only-password-2026",
            },
        )
        assert response.status_code == 200, response.text
        actor_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        sessions[name] = actor_client
    yield users, sessions
    for actor_client in sessions.values():
        actor_client.close()


def intake(client, merchant="merchant-a"):
    response = normalized_intake(
        client,
        request_headers={},
        payload={
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "merchant_id": merchant,
                "transaction_id": str(uuid4()),
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


def command(client, case, action, data=None, **extra):
    return client.post(
        "/api/v2/commands",
        json={
            "command_id": str(uuid4()),
            "action": action,
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "confirmed": True,
            "data": data or {},
            **extra,
        },
    )


def test_cookie_is_opaque_and_privileged_header_does_not_change_session(accounts):
    _, sessions = accounts
    client = sessions["merchant-a"]
    result = client.get(
        "/api/v2/session",
        headers={
            "X-Demo-Role": "ADMIN",
            "X-Demo-Actor": "director",
            "X-Demo-Merchant": "merchant-b",
        },
    )
    assert result.json()["user"]["role"] == "MERCHANT"
    assert result.json()["user"]["merchant_id"] == "merchant-a"
    assert client.get("/api/v2/director/accounts").status_code == 403
    assert client.get("/v2/operations", follow_redirects=False).status_code == 403
    assert client.get("/v2/merchant").status_code == 200
    assert "merchant" not in client.cookies["oceanpilot_session"]


def test_csrf_logout_expiry_and_account_revocation(client, accounts):
    users, sessions = accounts
    actor = sessions["operator-a"]
    result = actor.post("/api/v2/session/logout", headers={"X-CSRF-Token": "forged"})
    assert result.status_code == 403
    assert actor.get("/api/v2/session").status_code == 200
    other_csrf = sessions["operator-b"].headers["X-CSRF-Token"]
    assert (
        actor.post("/api/v2/session/logout", headers={"X-CSRF-Token": other_csrf}).status_code
        == 403
    )
    assert actor.post("/api/v2/session/logout").status_code == 200
    assert actor.get("/api/v2/cases").status_code == 401
    client.app.state.v21_auth.set_disabled(users["merchant-b"]["id"], True)
    assert sessions["merchant-b"].get("/api/v2/cases").status_code == 401
    with closing(client.app.state.v21_auth._connect()) as conn:
        conn.execute(
            "UPDATE v21_sessions SET expires_at=0 WHERE user_id=?", (users["merchant-a"]["id"],)
        )
        conn.commit()
    assert sessions["merchant-a"].get("/api/v2/cases").status_code == 401


def test_login_rejects_cross_origin_and_rotates_session(accounts):
    _, sessions = accounts
    actor = sessions["merchant-a"]
    before = actor.cookies["oceanpilot_session"]
    credentials = {"username": "merchant-a", "password": "test-only-password-2026"}
    rejected = actor.post(
        "/api/v2/session/login", json=credentials, headers={"Origin": "https://untrusted.invalid"}
    )
    assert rejected.status_code == 403
    response = actor.post("/api/v2/session/login", json=credentials)
    assert response.status_code == 200
    assert actor.cookies["oceanpilot_session"] != before
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "password" not in response.json()["user"]


def test_scope_applies_to_list_detail_plan_commands_and_updates(client, accounts):
    users, sessions = accounts
    case_a = intake(sessions["operator-a"])
    case_b = intake(sessions["operator-b"], "merchant-b")
    assert case_a["assigned_op_user_id"] == users["operator-a"]["id"]
    assert {p["user_id"] for p in case_a["participants"]} == {
        users[name]["id"] for name in ("merchant-a", "operator-a", "risk-reviewer")
    }
    for name in ("merchant-a", "operator-a"):
        actor = sessions[name]
        listed = actor.get("/api/v2/cases").json()
        assert listed["total"] == 1 and listed["cases"][0]["id"] == case_a["id"]
        assert actor.get(f"/api/v2/cases/{case_b['id']}").status_code == 404
        assert actor.get(f"/api/v2/cases/{case_b['id']}/plan").status_code == 404
        assert actor.get(f"/api/v2/cases/{case_b['id']}/agent").status_code == 404
    denied = command(sessions["operator-b"], case_a, "PUBLISH_TASK")
    assert denied.status_code == 404
    assert client.app.state.disputes.store.get_case(case_a["id"])["revision"] == case_a["revision"]
    assert sessions["director"].get("/api/v2/cases").status_code == 403


def test_participant_removal_revokes_read_write_and_queue(client, accounts):
    users, sessions = accounts
    case = intake(sessions["operator-a"])
    store = client.app.state.disputes.store
    raw = store.get_case(case["id"])
    raw["participants"] = [
        p for p in raw["participants"] if p["user_id"] != users["operator-a"]["id"]
    ]
    with closing(store._connect()) as conn:
        conn.execute(
            "UPDATE v2_dispute_cases SET snapshot=? WHERE case_id=?", (json.dumps(raw), case["id"])
        )
        conn.commit()
    actor = sessions["operator-a"]
    assert actor.get("/api/v2/cases").json()["total"] == 0
    assert actor.get(f"/api/v2/cases/{case['id']}").status_code == 404
    assert command(actor, case, "PUBLISH_TASK").status_code == 404
    assert sessions["merchant-a"].get(f"/api/v2/cases/{case['id']}").status_code == 200


def test_merchant_projections_exclude_internal_free_text_everywhere(client, accounts):
    _, sessions = accounts
    case = intake(sessions["operator-a"])
    response = command(sessions["operator-a"], case, "PUBLISH_TASK")
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    store = client.app.state.disputes.store
    raw = store.get_case(case["id"])
    raw["internal_risk_notes"] = "INTERNAL-ONLY-RISK-MARKER"
    raw["reviews"].append(
        {"id": "internal-review", "decision": "PASS", "reason": "INTERNAL-ONLY-RISK-MARKER"}
    )
    raw["audit"][-1]["private_note"] = "INTERNAL-ONLY-RISK-MARKER"
    with closing(store._connect()) as conn:
        conn.execute(
            "UPDATE v2_dispute_cases SET snapshot=? WHERE case_id=?", (json.dumps(raw), case["id"])
        )
        conn.commit()
    actor = sessions["merchant-a"]
    for path in (
        "/api/v2/cases",
        f"/api/v2/cases/{case['id']}",
        f"/api/v2/cases/{case['id']}/plan",
        f"/api/v2/cases/{case['id']}/agent",
    ):
        result = actor.get(path)
        assert result.status_code == 200, result.text
        assert "INTERNAL-ONLY-RISK-MARKER" not in result.text
    result = command(
        actor, case, "MERCHANT_DECISION", {"decision": "CONTEST", "reason": "提供事实证明交付"}
    )
    assert result.status_code == 200, result.text
    for field in (
        "audit",
        "packages",
        "reviews",
        "knowledge_candidates",
        "financial_events",
        "internal_risk_notes",
    ):
        assert field not in result.json()["case"]
    assert "INTERNAL-ONLY-RISK-MARKER" not in result.text


def test_queue_paginates_filtered_summaries_and_counts(accounts):
    _, sessions = accounts
    actor = sessions["operator-a"]
    cases = [intake(actor) for _ in range(4)]
    published = command(actor, cases[0], "PUBLISH_TASK")
    assert published.status_code == 200
    first = actor.get("/api/v2/cases?limit=2&offset=0").json()
    second = actor.get("/api/v2/cases?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 4
    assert len(first["cases"]) == len(second["cases"]) == 2
    assert {c["id"] for c in first["cases"]}.isdisjoint(c["id"] for c in second["cases"])
    for summary in first["cases"] + second["cases"]:
        assert not {"audit", "evidence", "packages", "reviews", "conversations"}.intersection(
            summary
        )
    waiting = actor.get("/api/v2/cases?queue=MERCHANT").json()
    assert waiting["total"] == 1 and waiting["cases"][0]["id"] == cases[0]["id"]
    assert first["queue_counts"]["MERCHANT"] == 1
    assert actor.get("/api/v2/cases", params={"q": cases[2]["transaction_id"]}).json()["total"] == 1
    assert actor.get("/api/v2/cases?limit=1000").status_code == 422


def test_gate_and_command_agree_on_forbidden_or_not_ready_actions(accounts):
    _, sessions = accounts
    case = intake(sessions["operator-a"])
    merchant = sessions["merchant-a"]
    view = merchant.get(f"/api/v2/cases/{case['id']}").json()
    assert all(
        item["action"] not in {"REVIEW", "FINAL_REVIEW", "SUBMIT"}
        for item in view["available_actions"]
    )
    decision = next(
        item for item in view["available_actions"] if item["action"] == "MERCHANT_DECISION"
    )
    assert decision["enabled"] is False
    denied = command(
        merchant,
        case,
        "MERCHANT_DECISION",
        {"decision": "CONTEST", "reason": "Cannot decide before task"},
    )
    assert denied.status_code == 409
    assert denied.json()["code"] == decision["code"]
    assert (
        command(
            merchant, case, "REVIEW", {"decision": "PASS", "reason": "Cannot review myself"}
        ).status_code
        == 403
    )
