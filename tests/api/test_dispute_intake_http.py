"""Real-session HTTP tests for normalized events and the distinct synthetic registry."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oceanpilot.adapters.knowledge.dispute_case_library import DisputeCaseLibrary
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.api.dispute_identity import initialize_dispute_identity
from oceanpilot.api.dispute_identity import router as identity_router
from oceanpilot.api.dispute_intake import initialize_dispute_intake
from oceanpilot.api.dispute_intake import router as intake_router
from oceanpilot.api.disputes import dispute_error_handler
from oceanpilot.api.disputes import router as business_router
from oceanpilot.application.disputes import DisputeError, DisputeService
from tests.application.test_dispute_intake import envelope
from tests.workflow.test_dispute_engine import NOW


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    path = tmp_path_factory.mktemp("normalized-http") / "http.db"
    app = FastAPI()
    app.state.settings = SimpleNamespace(v21_secure_cookies=False)
    app.state.disputes = DisputeService(
        SQLiteDisputeStore(path), clock=lambda: NOW, case_library=DisputeCaseLibrary()
    )
    initialize_dispute_identity(app, path)
    initialize_dispute_intake(app, path)
    app.state.dispute_intake.clock = lambda: NOW
    app.add_exception_handler(DisputeError, dispute_error_handler)
    app.include_router(identity_router)
    app.include_router(intake_router)
    app.include_router(business_router)
    sessions = {}
    for name, role, merchant in [
        ("director", "DIRECTOR", None),
        ("operator-a", "OPERATOR", "merchant-a"),
        ("operator-b", "OPERATOR", "merchant-b"),
        ("merchant-a", "MERCHANT", "merchant-a"),
    ]:
        app.state.v21_auth.create_user(
            username=name,
            password="synthetic-test-password",
            display_name=name,
            role=role,
            merchant_ids=[merchant] if merchant else [],
            merchant_id=merchant if role == "MERCHANT" else None,
        )
        client = TestClient(app)
        result = client.post(
            "/api/v2/session/login", json={"username": name, "password": "synthetic-test-password"}
        )
        assert result.status_code == 200
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        sessions[name] = client
    yield app, sessions
    for client in sessions.values():
        client.close()


def registry_payload(event):
    return {
        k: event[k]
        for k in ("transaction_id", "merchant_id", "channel", "scheme", "amount_minor", "currency")
    } | {"reference": "director synthetic record"}


def receive(client, event):
    return client.post("/api/v2/intake/events", json={"event": event, "confirmed": True})


def test_unauthenticated_and_forged_role_headers_do_not_admit_source_events(stack):
    app, _ = stack
    with TestClient(app) as client:
        assert receive(client, envelope()).status_code == 401
        assert (
            client.get("/api/v2/intake/events", headers={"X-Demo-Role": "OPERATOR"}).status_code
            == 401
        )


def test_operator_cannot_provision_transaction_truth_and_director_cannot_run_business_intake(stack):
    _, sessions = stack
    event = envelope()
    assert (
        sessions["operator-a"]
        .post("/api/v2/director/transactions", json=registry_payload(event))
        .status_code
        == 403
    )
    assert receive(sessions["director"], event).status_code == 403
    assert receive(sessions["merchant-a"], event).status_code == 403


def test_director_registry_then_actual_operator_session_creates_template_reference_case(stack):
    app, sessions = stack
    event = envelope(case_template_id="CB-CASE-041")
    assert (
        sessions["director"]
        .post("/api/v2/director/transactions", json=registry_payload(event))
        .status_code
        == 200
    )
    result = receive(sessions["operator-a"], event)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["event"]["status"] == "PROCESSED"
    raw = app.state.disputes.store.get_case(body["case_id"])
    assert raw["library_reference"]["template_id"] == "CB-CASE-041"
    assert (
        raw["amount_minor"] == 12800
        and raw["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"
    )
    assert raw["deadlines"]["status"] == "NEEDS_CONFIRMATION"
    assert raw["assigned_op_user_id"]
    assert body["case"]["id"] == body["case_id"] and "snapshot" not in body
    assert receive(sessions["operator-a"], event).json()["replayed"]


@pytest.mark.parametrize("kind", ["ALERT", "INQUIRY"])
def test_alert_and_inquiry_do_not_offer_case_navigation(stack, kind):
    _, sessions = stack
    event = envelope(event_type=kind)
    sessions["director"].post("/api/v2/director/transactions", json=registry_payload(event))
    result = receive(sessions["operator-a"], event)
    assert result.status_code == 200
    assert result.json()["event"]["status"] == "RECORDED" and result.json()["case_id"] is None


def test_merchant_scope_applies_before_receipt_lookup_and_to_queue(stack):
    _, sessions = stack
    event = envelope()
    original = receive(sessions["operator-a"], event).json()
    assert original["event"]["status"] == "QUARANTINED"
    assert receive(sessions["operator-b"], event).status_code == 403
    other_ids = {
        item["id"] for item in sessions["operator-b"].get("/api/v2/intake/events").json()["events"]
    }
    assert original["event"]["id"] not in other_ids
    retry = sessions["operator-b"].post(
        "/api/v2/intake/events/" + original["event"]["id"] + "/retry",
        json={"confirmed": True, "reason": "Try other merchant event"},
    )
    assert retry.status_code == 404


def test_quarantine_retry_uses_original_envelope_after_director_registration(stack):
    _, sessions = stack
    event = envelope()
    before = receive(sessions["operator-a"], event).json()
    sessions["director"].post("/api/v2/director/transactions", json=registry_payload(event))
    response = sessions["operator-a"].post(
        "/api/v2/intake/events/" + before["event"]["id"] + "/retry",
        json={"confirmed": True, "reason": "Director registered source facts"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["event"]["status"] == "PROCESSED"
    assert response.json()["event"]["envelope"] == before["event"]["envelope"]


@pytest.mark.parametrize(
    "field,value",
    [("amount_minor", True), ("currency", "usd"), ("occurred_at", None), ("event_type", "UNKNOWN")],
)
def test_event_dto_rejects_invalid_boundary_before_inbox_write(stack, field, value):
    app, sessions = stack
    event = envelope(**{field: value})
    before = len(app.state.dispute_intake.store.list_events())
    response = receive(sessions["operator-a"], event)
    assert response.status_code == 422
    assert len(app.state.dispute_intake.store.list_events()) == before


def test_withdrawal_http_command_is_safe_human_verification_not_automatic_finality(stack):
    app, sessions = stack
    event = envelope()
    sessions["director"].post("/api/v2/director/transactions", json=registry_payload(event))
    first = receive(sessions["operator-a"], event).json()
    result = receive(
        sessions["operator-a"],
        event
        | {
            "event_type": "WITHDRAWAL",
            "source_event_id": str(uuid4()),
            "target_case_id": first["case_id"],
            "basis_reference": "synthetic-withdrawal-notice",
        },
    )
    assert result.status_code == 200, result.text
    case = app.state.disputes.store.get_case(first["case_id"])
    assert case["work_status"] == "OUTCOME_VERIFICATION" and case["finality"] == "NOT_FINAL"


def test_new_account_with_only_merchant_grant_cannot_read_existing_case_bound_inbox(stack):
    app, sessions = stack
    event = envelope()
    sessions["director"].post("/api/v2/director/transactions", json=registry_payload(event))
    first = receive(sessions["operator-a"], event).json()
    name = "later-operator-" + uuid4().hex[:6]
    app.state.v21_auth.create_user(
        username=name,
        password="synthetic-test-password",
        display_name=name,
        role="OPERATOR",
        merchant_ids=["merchant-a"],
    )
    with TestClient(app) as later:
        login = later.post(
            "/api/v2/session/login", json={"username": name, "password": "synthetic-test-password"}
        )
        later.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        assert receive(later, event).status_code == 404
        assert first["event"]["id"] not in {
            r["id"] for r in later.get("/api/v2/intake/events").json()["events"]
        }


def test_legacy_command_and_full_demo_routes_cannot_bypass_registry_or_human_roles(stack):
    app, sessions = stack
    data = envelope()
    command_data = {
        k: v for k, v in data.items() if k not in {"event_type", "source_event_id", "occurred_at"}
    } | {"event_id": data["source_event_id"]}
    payload = {
        "command_id": str(uuid4()),
        "action": "INTAKE",
        "confirmed": True,
        "data": command_data,
    }
    before = len(app.state.disputes.store.list_cases())
    for client, expected in [
        (sessions["operator-a"], 410),
        (sessions["merchant-a"], 403),
        (sessions["director"], 403),
    ]:
        old = client.post("/api/v2/commands", json=payload)
        assert old.status_code == expected, old.text
        demo = client.post("/api/v2/demo", json={"scenario": "A"})
        assert demo.status_code == expected, demo.text
    assert len(app.state.disputes.store.list_cases()) == before
    assert (
        sessions["director"]
        .post("/api/v2/director/transactions", json=registry_payload(data))
        .status_code
        == 200
    )
    assert sessions["operator-a"].post("/api/v2/commands", json=payload).status_code == 410
    assert receive(sessions["operator-a"], data).json()["event"]["status"] == "PROCESSED"
    assert len(app.state.disputes.store.list_cases()) == before + 1


def test_shared_normalized_fixture_helper_keeps_actual_session_and_participant_directory(stack):
    from tests.v21_support import normalized_intake

    app, sessions = stack
    before = {u["id"] for u in app.state.v21_auth.list_users() if u["role"] != "DIRECTOR"}
    actual = sessions["operator-a"].get("/api/v2/session").json()["user"]["id"]
    event = envelope()
    data = {
        k: v for k, v in event.items() if k not in {"event_type", "source_event_id", "occurred_at"}
    } | {"event_id": event["source_event_id"]}
    response = normalized_intake(
        sessions["operator-a"],
        {"action": "INTAKE", "confirmed": True, "data": data},
        request_headers={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["case"]["assigned_op_user_id"] == actual
    after = {u["id"] for u in app.state.v21_auth.list_users() if u["role"] != "DIRECTOR"}
    assert before == after
