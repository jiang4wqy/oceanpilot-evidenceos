"""Independent V2.1 acceptance probes through real server-issued sessions."""

import base64
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app
from tests.application.test_dispute_intake import envelope
from tests.workflow.test_dispute_engine import NOW


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    path = tmp_path_factory.mktemp("independent-v21-review")
    app = create_app(Settings(db_path=path / "base.db", chargeback_db_path=path / "v2.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.dispute_agent.model = None
        app.state.dispute_agent_events.enabled = False
        app.state.disputes.clock = lambda: NOW
        app.state.dispute_intake.clock = lambda: NOW
        sessions = {}
        for name, role, merchant in (
            ("director", "DIRECTOR", None),
            ("operator", "OPERATOR", "merchant-a"),
            ("risk", "RISK_OFFICER", "merchant-a"),
            ("supervisor", "SUPERVISOR", "merchant-a"),
            ("merchant", "MERCHANT", "merchant-a"),
            ("outsider", "MERCHANT", "merchant-b"),
        ):
            app.state.v21_auth.create_user(
                username=name,
                password="Synthetic-review-password!",
                display_name=name,
                role=role,
                user_id=name,
                merchant_ids=[merchant] if merchant else [],
                merchant_id=merchant if role == "MERCHANT" else None,
            )
            result = client.post(
                "/api/v2/session/login",
                json={"username": name, "password": "Synthetic-review-password!"},
            )
            assert result.status_code == 200, result.text
            sessions[name] = {
                "Cookie": "oceanpilot_session=" + client.cookies.get("oceanpilot_session"),
                "X-CSRF-Token": result.json()["csrf_token"],
            }
            client.cookies.clear()
        yield client, app, sessions


def intake(api, **changes):
    client, _, headers = api
    event = envelope(**changes)
    response = client.post(
        "/api/v2/director/transactions",
        headers=headers["director"],
        json={
            key: event[key]
            for key in (
                "transaction_id",
                "merchant_id",
                "channel",
                "scheme",
                "amount_minor",
                "currency",
            )
        }
        | {"reference": "explicit synthetic review registry"},
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/v2/intake/events",
        headers=headers["operator"],
        json={"event": event, "confirmed": True},
    )
    assert response.status_code == 200, response.text
    return response.json()["case"]


def command(api, case, action, data=None, *, actor="operator", command_id=None):
    client, _, headers = api
    return client.post(
        "/api/v2/commands",
        headers=headers[actor],
        json={
            "command_id": command_id or str(uuid4()),
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "action": action,
            "confirmed": True,
            "data": data or {},
        },
    )


@pytest.mark.parametrize("outcome,supported,liable", [("WON", 12800, 0), ("LOST", 0, 12800)])
def test_currency_only_terminal_outcome_uses_full_allocation_after_source_verification(
    api, outcome, supported, liable
):
    case = intake(api)
    event_id = str(uuid4())
    result = command(
        api,
        case,
        "RECORD_OUTCOME",
        {
            "source": "synthetic-source",
            "event_id": event_id,
            "outcome": outcome,
            "final": True,
            "disposition": "FINAL",
            "currency": "USD",
        },
    )
    assert result.status_code == 200, result.text
    result = command(
        api,
        result.json()["case"],
        "VERIFY_OUTCOME",
        {
            "event_id": event_id,
            "decision": "CONFIRM",
            "reason": "Source notice verified",
            "authorization_reference": "synthetic-risk-basis",
        },
        actor="risk",
    )
    assert result.status_code == 200, result.text
    assert result.json()["case"]["outcome_amounts"]["supported_minor"] == supported
    assert result.json()["case"]["outcome_amounts"]["liable_minor"] == liable


@pytest.mark.parametrize("outcome,currency", [("WON", "EUR"), ("PARTIAL", "USD")])
def test_currency_only_rejects_wrong_currency_and_missing_partial_allocation(
    api, outcome, currency
):
    case = intake(api)
    result = command(
        api,
        case,
        "RECORD_OUTCOME",
        {
            "source": "synthetic-source",
            "event_id": str(uuid4()),
            "outcome": outcome,
            "final": True,
            "currency": currency,
        },
    )
    assert result.status_code == 422
    assert api[1].state.disputes.store.get_case(case["id"])["revision"] == case["revision"]


def advance(api, case, action, data=None, *, actor="operator"):
    response = command(api, case, action, data, actor=actor)
    assert response.status_code == 200, response.text
    return response.json()["case"]


def contest(api, *, code=None):
    case = intake(api)
    if code:
        case = advance(
            api,
            case,
            "CONFIRM_RULE",
            {
                "allowed_actions": ["ACCEPT", "CONTEST"],
                "source_id": "synthetic-review-rule",
                "source_locator": "synthetic-section",
                "rule_version": "review-v1",
                "required_evidence": [code],
                "external_deadline": (NOW + timedelta(days=12)).isoformat(),
                "internal_deadline": (NOW + timedelta(days=10)).isoformat(),
                "merchant_deadline": (NOW + timedelta(days=8)).isoformat(),
                "reason": "Risk reviewed the synthetic material requirement",
            },
            actor="risk",
        )
    case = advance(api, case, "PUBLISH_TASK")
    return advance(
        api,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "CONTEST",
            "reason": "Provide relevant synthetic material",
        },
        actor="merchant",
    )


def upload(api, case, code, facts, *, evidence_id=None):
    client, _, headers = api
    content = json.dumps(
        {
            "transaction_id": case["transaction_id"],
            "amount_minor": case["amount_minor"],
            "currency": case["currency"],
            **facts,
        }
    ).encode()
    result = client.post(
        f"/api/v2/cases/{case['id']}/collaboration/files",
        headers=headers["merchant"],
        json={
            "command_id": str(uuid4()),
            "expected_revision": case["revision"],
            "code": code,
            "title": "Synthetic document",
            "filename": "document.json",
            "mime_type": "application/json",
            "content_base64": base64.b64encode(content).decode(),
            **({"evidence_id": evidence_id} if evidence_id else {}),
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_new_metadata_reference_does_not_satisfy_real_content_submission(api):
    case = contest(api, code="fulfillment.proof_of_delivery")
    assert api[1].state.disputes.evidence_objects is not None
    registered = command(
        api,
        case,
        "REGISTER_EVIDENCE",
        {
            "code": "fulfillment.proof_of_delivery",
            "title": "No real file",
            "reference": "synthetic://does-not-exist",
        },
        actor="merchant",
    )
    assert registered.status_code == 422, registered.text
    assert registered.json()["code"] == "EVIDENCE_FILE_REQUIRED"
    submitted = command(api, case, "SUBMIT_EVIDENCE", actor="merchant")
    assert submitted.status_code == 409, submitted.text


def test_agent_activity_does_not_restore_internal_deadlines_removed_from_case_view(api):
    client, _, headers = api
    case = intake(api)
    merchant_case = client.get(f"/api/v2/cases/{case['id']}", headers=headers["merchant"]).json()
    assert "internal" not in merchant_case["deadlines"]
    result = client.get(f"/api/v2/cases/{case['id']}/agent", headers=headers["merchant"])
    assert result.status_code == 200, result.text
    sla = next(
        step for step in result.json()["run"]["steps"] if step["capability"] == "sla_monitor"
    )
    assert "internal" not in sla["output"]["deadlines"]


def test_agent_similar_cases_respects_reader_case_participation(api):
    client, app, _ = api
    old = intake(api, reason_code="99.9")
    user = "late-merchant-" + uuid4().hex[:8]
    app.state.v21_auth.create_user(
        username=user,
        password="Synthetic-review-password!",
        display_name=user,
        role="MERCHANT",
        user_id=user,
        merchant_ids=["merchant-a"],
        merchant_id="merchant-a",
    )
    logged_in = client.post(
        "/api/v2/session/login",
        json={
            "username": user,
            "password": "Synthetic-review-password!",
        },
    )
    assert logged_in.status_code == 200
    headers = {"Cookie": "oceanpilot_session=" + client.cookies.get("oceanpilot_session")}
    client.cookies.clear()
    current = intake(api, reason_code="99.9")
    assert client.get(f"/api/v2/cases/{old['id']}", headers=headers).status_code == 404
    activity = client.get(f"/api/v2/cases/{current['id']}/agent", headers=headers)
    assert activity.status_code == 200, activity.text
    assert old["id"] not in activity.text


def manual_data(case, **changes):
    return {
        "evidence_id": case["evidence"][-1]["id"],
        "decision": "SUPPORTED",
        "reason": "The original document links the explicit fulfillment observation to this case",
        "applicable_facts": ["synthetic-observation-present"],
        "locators": ["line:1"],
    } | changes


def manual_case(api):
    code = "custom.unmapped_fulfillment_record"
    case = contest(api, code=code)
    result = upload(api, case, code, {"observation": "synthetic-observation-present"})
    assert result["file"]["content_check"]["status"] == "NEEDS_MANUAL"
    return result["case"]


def test_unknown_file_has_content_bound_manual_exit_and_still_needs_two_approvals(api):
    client, app, headers = api
    case = manual_case(api)
    assert command(api, case, "SUBMIT_EVIDENCE", actor="merchant").status_code == 409
    risk_case = client.get(f"/api/v2/cases/{case['id']}", headers=headers["risk"]).json()
    action = next(
        a for a in risk_case["available_actions"] if a["action"] == "REVIEW_EVIDENCE_CONTENT"
    )
    assert action["enabled"] and action["choices"]["evidence_id"] == [case["evidence"][-1]["id"]]
    assert risk_case["current_task"]["action"] == "REVIEW_EVIDENCE_CONTENT"
    command_id = str(uuid4())
    body = manual_data(case)
    result = command(
        api, case, "REVIEW_EVIDENCE_CONTENT", body, actor="risk", command_id=command_id
    )
    assert result.status_code == 200, result.text
    assert command(
        api, case, "REVIEW_EVIDENCE_CONTENT", body, actor="risk", command_id=command_id
    ).json()["replayed"]
    case = result.json()["case"]
    item = case["evidence"][-1]
    assert item["content_status"] == "SUPPORTED"
    assert item["content_reviews"][-1]["reviewer"] == "risk"
    original = app.state.disputes.evidence_objects.get_evidence_object(
        case["id"], item["object_id"]
    )
    assert original["content_check"]["status"] == "NEEDS_MANUAL"
    assert not any(t["status"] == "OPEN" for t in case["tasks"] if t["type"] == "CONTENT_REVIEW")
    assert (
        command(
            api, case, "REVIEW", {"decision": "PASS", "reason": "Too early"}, actor="risk"
        ).status_code
        == 409
    )
    case = advance(api, case, "SUBMIT_EVIDENCE", actor="merchant")
    case = advance(
        api, case, "REVIEW", {"decision": "PASS", "reason": "Full evidence reviewed"}, actor="risk"
    )
    case = advance(api, case, "BUILD_PACKAGE", {"draft": "Human reviewed synthetic response"})
    assert command(api, case, "SUBMIT").status_code == 409
    case = advance(
        api,
        case,
        "FINAL_REVIEW",
        {
            "decision": "APPROVE",
            "reason": "Independent final review",
            "pii_checked": True,
        },
        actor="supervisor",
    )
    case = advance(api, case, "SUBMIT")
    assert case["work_status"] == "WAITING_UPSTREAM"


@pytest.mark.parametrize("actor", ["merchant", "operator", "supervisor"])
def test_manual_file_assessment_cannot_be_self_granted_by_other_roles(api, actor):
    case = manual_case(api)
    assert (
        command(api, case, "REVIEW_EVIDENCE_CONTENT", manual_data(case), actor=actor).status_code
        == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"applicable_facts": ["not present in this document"]},
        {"locators": ["line:900"]},
        {"locators": ["line:" + "9" * 5000]},
        {"applicable_facts": []},
        {"applicable_facts": [42]},
    ],
)
def test_manual_file_assessment_requires_real_located_excerpts(api, changes):
    case = manual_case(api)
    result = command(
        api, case, "REVIEW_EVIDENCE_CONTENT", manual_data(case, **changes), actor="risk"
    )
    assert result.status_code == 422, result.text
    assert api[1].state.disputes.store.get_case(case["id"])["revision"] == case["revision"]


def test_known_insufficient_file_cannot_use_manual_override(api):
    case = contest(api, code="fulfillment.proof_of_delivery")
    result = upload(
        api,
        case,
        "fulfillment.proof_of_delivery",
        {
            "observation": "synthetic-observation-present",
        },
    )
    assert result["file"]["content_check"]["status"] == "INSUFFICIENT"
    response = command(
        api, result["case"], "REVIEW_EVIDENCE_CONTENT", manual_data(result["case"]), actor="risk"
    )
    assert response.status_code == 409


def test_manual_rejection_and_withdrawal_resolve_truthful_tasks(api):
    case = manual_case(api)
    case = advance(
        api,
        case,
        "REVIEW_EVIDENCE_CONTENT",
        manual_data(case, decision="INSUFFICIENT"),
        actor="risk",
    )
    assert command(api, case, "SUBMIT_EVIDENCE", actor="merchant").status_code == 409
    case = advance(
        api,
        case,
        "WITHDRAW_EVIDENCE",
        {
            "evidence_id": case["evidence"][-1]["id"],
            "reason": "Withdraw insufficient source document",
        },
        actor="merchant",
    )
    assert not any(t["status"] == "OPEN" for t in case["tasks"] if t["type"] == "CONTENT_REVIEW")


def test_replacing_human_verified_file_invalidates_approval_and_requires_new_content_review(api):
    client, _, headers = api
    case = manual_case(api)
    case = advance(api, case, "REVIEW_EVIDENCE_CONTENT", manual_data(case), actor="risk")
    case = advance(api, case, "SUBMIT_EVIDENCE", actor="merchant")
    case = advance(
        api, case, "REVIEW", {"decision": "PASS", "reason": "Current files reviewed"}, actor="risk"
    )
    case = advance(api, case, "BUILD_PACKAGE")
    case = advance(
        api,
        case,
        "FINAL_REVIEW",
        {
            "decision": "APPROVE",
            "reason": "Final current package reviewed",
            "pii_checked": True,
        },
        actor="supervisor",
    )
    item = case["evidence"][-1]
    denied = command(
        api,
        case,
        "REGISTER_EVIDENCE",
        {
            "evidence_id": item["id"],
            "code": item["code"],
            "title": "Replace with no file",
            "reference": "synthetic://unavailable",
        },
        actor="merchant",
    )
    assert denied.status_code == 422 and denied.json()["code"] == "EVIDENCE_FILE_REQUIRED"
    replaced = upload(
        api,
        case,
        item["code"],
        {
            "observation": "a revised synthetic observation",
        },
        evidence_id=item["id"],
    )
    case = client.get(f"/api/v2/cases/{case['id']}", headers=headers["operator"]).json()
    assert replaced["case"]["revision"] == case["revision"]
    current = case["evidence"][-1]
    assert current["id"] == item["id"] and current["revision"] == item["revision"] + 1
    assert current["content_status"] == "NEEDS_MANUAL" and current["object_id"] != item["object_id"]
    assert current["history"][-1]["content_reviews"][-1]["decision"] == "SUPPORTED"
    assert all(package["status"] == "INVALIDATED" for package in case["packages"])
    assert not any(review["valid"] for review in case["reviews"])
    assert command(api, case, "SUBMIT_EVIDENCE", actor="merchant").status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"transaction_id": "wrong-source-transaction"},
        {"currency": "EUR"},
        {"amount_minor": 1},
    ],
)
def test_unknown_file_with_conflicting_common_facts_has_no_manual_override(api, changes):
    code = "custom.unmapped_fulfillment_record"
    case = contest(api, code=code)
    result = upload(api, case, code, {"observation": "synthetic-observation-present", **changes})
    assert result["file"]["content_check"]["status"] == "INSUFFICIENT"
    response = command(
        api, result["case"], "REVIEW_EVIDENCE_CONTENT", manual_data(result["case"]), actor="risk"
    )
    assert response.status_code == 409


def test_manual_review_uses_normalized_valid_integer_source_amount(api):
    code = "custom.unmapped_fulfillment_record"
    case = contest(api, code=code)
    result = upload(
        api,
        case,
        code,
        {
            "amount_minor": "012800",
            "observation": "synthetic-observation-present",
        },
    )
    assert result["file"]["content_check"]["status"] == "NEEDS_MANUAL"
    response = command(
        api, result["case"], "REVIEW_EVIDENCE_CONTENT", manual_data(result["case"]), actor="risk"
    )
    assert response.status_code == 200, response.text


def awaiting_risk(api):
    case = contest(api, code="fulfillment.proof_of_delivery")
    result = upload(
        api,
        case,
        "fulfillment.proof_of_delivery",
        {
            "delivered_at": "2026-09-01",
            "recipient_confirmation": "synthetic receipt confirmed",
        },
    )
    return advance(api, result["case"], "SUBMIT_EVIDENCE", actor="merchant")


def pending_package(api):
    case = awaiting_risk(api)
    case = advance(
        api,
        case,
        "REVIEW",
        {
            "decision": "PASS",
            "reason": "Current evidence and association verified",
        },
        actor="risk",
    )
    return advance(api, case, "BUILD_PACKAGE", {"draft": "Reviewed synthetic response"})


def test_final_hold_has_recoverable_document_return_and_no_unexecutable_approval_choice(api):
    client, _, headers = api
    case = pending_package(api)
    case = advance(
        api,
        case,
        "FINAL_REVIEW",
        {
            "decision": "HOLD",
            "reason": "Clarify narrative before a final decision",
        },
        actor="supervisor",
    )
    assert case["work_status"] == "ON_HOLD"
    view = client.get(f"/api/v2/cases/{case['id']}", headers=headers["supervisor"]).json()
    gate = next(a for a in view["available_actions"] if a["action"] == "FINAL_REVIEW")
    assert gate["enabled"]
    rejected = command(
        api,
        case,
        "FINAL_REVIEW",
        {
            "decision": "APPROVE",
            "reason": "Approve held package",
            "pii_checked": True,
        },
        actor="supervisor",
    )
    assert rejected.status_code == 409
    case = advance(
        api,
        case,
        "FINAL_REVIEW",
        {
            "decision": "RETURN_DOCUMENT",
            "reason": "Revise disputed fulfillment explanation",
        },
        actor="supervisor",
    )
    assert case["work_status"] == "DOCUMENT_REVISION_REQUIRED"
    case = advance(api, case, "BUILD_PACKAGE", {"draft": "Corrected source-based explanation"})
    case = advance(
        api,
        case,
        "FINAL_REVIEW",
        {
            "decision": "APPROVE",
            "reason": "Corrected package independently checked",
            "pii_checked": True,
        },
        actor="supervisor",
    )
    assert case["work_status"] == "READY_TO_SUBMIT"
    assert "APPROVE" not in gate["choices"]["decision"]


@pytest.mark.parametrize(
    "reviewer,decision", [("risk", "ACCEPT"), ("supervisor", "RECOMMEND_ACCEPT")]
)
def test_accept_recommendation_keeps_merchant_decision_and_allows_explicit_recovery(
    api, reviewer, decision
):
    case = awaiting_risk(api) if reviewer == "risk" else pending_package(api)
    case = advance(
        api,
        case,
        "REVIEW" if reviewer == "risk" else "FINAL_REVIEW",
        {
            "decision": decision,
            "reason": "Please explicitly decide responsibility based on these facts",
        },
        actor=reviewer,
    )
    assert case["work_status"] == "ACCEPT_RECOMMENDATION" and case["merchant_decision"] == "CONTEST"
    assert any(t["type"] == "ACCEPT_DECISION" and t["status"] == "OPEN" for t in case["tasks"])
    assert not any(t["type"] == "REVISION" and t["status"] == "OPEN" for t in case["tasks"])
    case = advance(
        api,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "CONTEST",
            "reason": "Continue contest with the existing documented facts",
        },
        actor="merchant",
    )
    assert case["work_status"] == "EVIDENCE_COLLECTING"
    assert not any(t["type"] == "ACCEPT_DECISION" and t["status"] == "OPEN" for t in case["tasks"])
    case = advance(api, case, "SUBMIT_EVIDENCE", actor="merchant")
    assert case["work_status"] == "OP_REVIEW"


def test_unknown_source_correction_recovers_and_later_money_requires_new_notification(api):
    client, _, headers = api
    case = intake(api)
    unknown_id, correction_id = str(uuid4()), str(uuid4())
    case = advance(
        api,
        case,
        "RECORD_OUTCOME",
        {
            "source": "synthetic-incomplete-source",
            "event_id": unknown_id,
            "outcome": "UNKNOWN",
            "final": False,
            "disposition": "VERIFY",
        },
    )
    unknown_review = {
        "event_id": unknown_id,
        "decision": "CONFIRM",
        "reason": "Source is still inconclusive",
        "authorization_reference": "synthetic-review-basis",
    }
    assert command(api, case, "VERIFY_OUTCOME", unknown_review, actor="risk").status_code == 409
    case = advance(
        api,
        case,
        "RECORD_OUTCOME",
        {
            "source": "synthetic-corrected-source",
            "event_id": correction_id,
            "outcome": "WON",
            "final": True,
            "corrects_event_id": unknown_id,
            "basis_reference": "corrected-source-notice",
            "currency": "USD",
        },
    )
    case = advance(
        api,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": correction_id,
            "decision": "CONFIRM",
            "reason": "Corrected terminal notice checked",
            "authorization_reference": "synthetic-review-basis",
        },
        actor="risk",
    )
    case = advance(
        api,
        case,
        "VERIFY_OUTCOME",
        unknown_review
        | {
            "decision": "REJECT",
            "reason": "Earlier inconclusive notice was explicitly superseded",
        },
        actor="risk",
    )
    assert case["business_outcome"] == "WON" and case["finality"] == "FINAL_CONFIRMED"
    assert (
        case["work_status"] == "FINANCIAL_RECONCILIATION"
        and not case["outcome_verification_required"]
    )
    case = advance(
        api,
        case,
        "RECONCILE",
        {
            "status": "NOT_APPLICABLE",
            "expected_net_minor": 0,
            "reason": "No settlement entries per synthetic source",
            "reference": "synthetic-reconciliation",
        },
        actor="supervisor",
    )
    case = advance(
        api, case, "NOTIFY_MERCHANT", {"message": "Current verified outcome and no funds notified"}
    )
    assert case["close_gate"]["notification_current"]
    case = advance(
        api,
        case,
        "RECORD_FINANCIAL",
        {
            "source": "synthetic-ledger",
            "event_id": str(uuid4()),
            "kind": "FEE",
            "amount_minor": 5,
            "currency": "USD",
            "reference": "new-synthetic-fee-entry",
        },
    )
    merchant = client.get(f"/api/v2/cases/{case['id']}", headers=headers["merchant"]).json()
    assert not merchant["close_gate"]["notification_current"]
    assert not merchant["close_gate"]["enabled"]
    case = advance(
        api,
        case,
        "RECONCILE",
        {
            "status": "RECONCILED",
            "expected_net_minor": -5,
            "reason": "New source fee independently checked",
            "reference": "new-synthetic-reconciliation",
        },
        actor="supervisor",
    )
    assert command(api, case, "CLOSE", actor="supervisor").status_code == 409
    case = advance(api, case, "NOTIFY_MERCHANT", {"message": "Updated result and new fee notified"})
    case = advance(api, case, "CLOSE", actor="supervisor")
    assert case["work_status"] == "CLOSED" and len(case["notification_history"]) == 1
