"""Independent V2 review scenarios: event ownership, action rights and closure."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.api.disputes import dispute_error_handler, router
from oceanpilot.application.disputes import DisputeError, DisputeService
from oceanpilot.domain.dispute import close_blockers
from oceanpilot.domain.dispute_rules import case_plan, match_rule

OP = {"role": "OPERATOR", "actor_id": "review-operator"}
RISK = {"role": "RISK_OFFICER", "actor_id": "review-risk"}
SUPERVISOR = {"role": "SUPERVISOR", "actor_id": "review-supervisor"}
MERCHANT = {"role": "MERCHANT", "actor_id": "review-merchant", "merchant_id": "merchant-a"}
NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


def command(case, action, data=None):
    return {
        "command_id": uuid4().hex,
        "case_id": case["id"] if case else None,
        "expected_revision": case["revision"] if case else None,
        "action": action,
        "confirmed": True,
        "data": data or {},
    }


def run(service, case, action, data=None, identity=OP):
    return service.execute(command(case, action, data), identity)["case"]


def intake_data(**overrides):
    return {
        "merchant_id": "merchant-a",
        "transaction_id": "synthetic-transaction",
        "scheme": "VISA",
        "channel": "MOCK",
        "reason_code": "13.1",
        "amount_minor": 12500,
        "currency": "USD",
        "event_id": uuid4().hex,
        **overrides,
    }


def intake(service, **overrides):
    return run(service, None, "INTAKE", intake_data(**overrides))


def frozen(service):
    case = run(service, intake(service), "PUBLISH_TASK")
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "CONTEST",
            "reason": "Synthetic merchant authorized Contest",
        },
        MERCHANT,
    )
    for code in case["rule_snapshot"]["required_evidence"]:
        case = run(
            service,
            case,
            "REGISTER_EVIDENCE",
            {
                "code": code,
                "title": "Synthetic evidence",
                "reference": "synthetic://test/evidence",
            },
            MERCHANT,
        )
    case = run(service, case, "SUBMIT_EVIDENCE", identity=MERCHANT)
    case = run(
        service, case, "REVIEW", {"decision": "PASS", "reason": "Human content review"}, RISK
    )
    case = run(service, case, "BUILD_PACKAGE")
    return run(
        service,
        case,
        "APPROVE_PACKAGE",
        {
            "reason": "Independent final human review",
            "pii_checked": True,
        },
        SUPERVISOR,
    )


def submitted(service):
    return run(service, frozen(service), "SUBMIT")


def terminal(service):
    return run(
        service,
        submitted(service),
        "RECORD_OUTCOME",
        {
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "outcome": "WON",
            "final": True,
        },
    )


def reconciled(service):
    case = run(
        service,
        terminal(service),
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "source": "mock-ledger",
            "kind": "CREDIT",
            "amount_minor": 12500,
            "currency": "USD",
            "reference": "synthetic://ledger/return",
        },
    )
    return run(
        service,
        case,
        "RECONCILE",
        {
            "status": "RECONCILED",
            "expected_net_minor": 12500,
            "reason": "Source ledger net independently confirmed",
            "reference": "synthetic://review",
        },
        SUPERVISOR,
    )


@pytest.fixture
def service(tmp_path):
    return DisputeService(SQLiteDisputeStore(tmp_path / "review.db"), clock=lambda: NOW)


@pytest.mark.parametrize("action", ["RECORD_FINANCIAL", "RECORD_OUTCOME"])
def test_one_source_event_cannot_be_rebound_to_a_different_case(service, action):
    """The same external event must never create two ledger/result effects."""
    first, second = submitted(service), submitted(service)
    data = {"event_id": "one-external-event", "source": "same-source-system"}
    if action == "RECORD_FINANCIAL":
        data.update(kind="DEBIT", amount_minor=12500, currency="USD", reference="one-ledger-row")
    else:
        data.update(outcome="WON", final=True, reason="one upstream result")
    applied = run(service, first, action, data)
    with pytest.raises(DisputeError) as error:
        run(service, second, action, data)
    assert error.value.status == 409
    assert error.value.code == "EVENT_CASE_CONFLICT"
    assert service.get_case(second["id"], OP) == second
    assert service.get_case(first["id"], OP) == applied
    replay = service.execute(command(applied, action, data), OP)
    assert replay["replayed"] is True
    assert service.get_case(first["id"], OP) == applied


def test_next_stage_event_also_remains_bound_to_its_original_case(service):
    cases = []
    for _ in range(2):
        cases.append(
            run(
                service,
                submitted(service),
                "RECORD_OUTCOME",
                {
                    "event_id": uuid4().hex,
                    "source": "mock-upstream",
                    "outcome": "OTHER",
                    "final": False,
                },
            )
        )
    event = {"event_id": "one-stage-event", "source": "mock-upstream", "stage": "REPRESENTMENT"}
    run(service, cases[0], "NEXT_STAGE", event)
    with pytest.raises(DisputeError) as error:
        run(service, cases[1], "NEXT_STAGE", event)
    assert error.value.code == "EVENT_CASE_CONFLICT"
    assert service.get_case(cases[1]["id"], OP) == cases[1]


def test_confirmed_accept_only_rule_cannot_authorize_contest(tmp_path):
    def accept_only(*args):
        rule = match_rule(*args)
        rule["allowed_actions"] = ["ACCEPT"]
        return rule

    service = DisputeService(
        SQLiteDisputeStore(tmp_path / "accept-only.db"),
        rule_matcher=accept_only,
        clock=lambda: NOW,
    )
    case = run(service, intake(service), "PUBLISH_TASK")
    with pytest.raises(DisputeError):
        run(
            service,
            case,
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "Have proof"},
            MERCHANT,
        )
    assert service.get_case(case["id"], OP) == case
    accepted = run(
        service,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "ACCEPT",
            "reason": "Authorized merchant acceptance",
        },
        MERCHANT,
    )
    assert accepted["merchant_decision"] == "ACCEPT"
    assert accepted["financial_events"] == []  # An acceptance is not a refund command.


def test_unknown_rule_requires_risk_confirmation_of_actions_as_well_as_deadlines(service):
    case = intake(service, channel="UNCONFIRMED_CHANNEL")
    assert case["work_status"] == "RECEIVED"
    assert case["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"
    with pytest.raises(DisputeError):
        run(service, case, "PUBLISH_TASK")
    rule = {
        "source_id": "synthetic-enterprise-confirmation",
        "source_locator": "synthetic://policy",
        "rule_version": "synthetic-confirmed-v1",
        "reason": "Human confirmed limited rights",
        "external_deadline": "2026-09-20T00:00:00+00:00",
        "required_evidence": ["order"],
    }
    with pytest.raises(DisputeError):
        run(service, case, "CONFIRM_RULE", rule, RISK)
    rule["allowed_actions"] = ["ACCEPT"]
    with pytest.raises(DisputeError) as error:
        run(service, case, "CONFIRM_RULE", rule, OP)
    assert error.value.status == 403
    confirmed = run(service, case, "CONFIRM_RULE", rule, RISK)
    assert confirmed["rule_snapshot"]["allowed_actions"] == ["ACCEPT"]
    assert confirmed["rule_snapshot"]["source_id"] == rule["source_id"]
    assert confirmed["deadlines"]["status"] == "CONFIRMED"
    assert confirmed["audit"][-1]["actor_id"] == RISK["actor_id"]


def test_late_ledger_event_requires_fresh_reconciliation_and_notification(service):
    case = run(service, reconciled(service), "NOTIFY_MERCHANT")
    original_net = case["reconciliation"]["actual_net_minor"]
    original_financial_version = case["financial_version"]
    case = run(
        service,
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "source": "mock-ledger",
            "kind": "FEE",
            "amount_minor": 75,
            "currency": "USD",
            "reference": "late-fee-confirmation",
        },
    )
    assert case["financial_status"] == "PENDING"
    assert case["financial_version"] == original_financial_version + 1
    assert case["merchant_notification_completed"] is False
    with pytest.raises(DisputeError):
        run(service, case, "CLOSE", identity=SUPERVISOR)
    review = {
        "status": "RECONCILED",
        "expected_net_minor": original_net,
        "reason": "Review latest source statement",
        "reference": "statement-version-2",
    }
    with pytest.raises(DisputeError):
        run(service, case, "RECONCILE", review, SUPERVISOR)
    review["expected_net_minor"] = original_net - 75
    case = run(service, case, "RECONCILE", review, SUPERVISOR)
    with pytest.raises(DisputeError):
        run(service, case, "CLOSE", identity=SUPERVISOR)
    case = run(service, run(service, case, "NOTIFY_MERCHANT"), "CLOSE", identity=SUPERVISOR)
    assert case["work_status"] == "CLOSED"


def test_not_applicable_cannot_hide_an_existing_refund(service):
    case = run(
        service,
        terminal(service),
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "source": "mock-ledger",
            "kind": "REFUND",
            "amount_minor": 12500,
            "currency": "USD",
            "reference": "refund-source-row",
        },
    )
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "RECONCILE",
            {
                "status": "NOT_APPLICABLE",
                "expected_net_minor": 0,
                "reason": "Cannot omit the recorded refund",
                "reference": "statement-review",
            },
            SUPERVISOR,
        )
    assert error.value.code == "FINANCIAL_EVENTS_PRESENT"
    assert service.get_case(case["id"], OP) == case
    assert case["financial_events"][0]["net_minor"] == -12500


def test_closed_case_rejects_new_financial_or_result_commands(service):
    case = run(
        service, run(service, reconciled(service), "NOTIFY_MERCHANT"), "CLOSE", identity=SUPERVISOR
    )
    for action, data in (
        (
            "RECORD_FINANCIAL",
            {
                "event_id": uuid4().hex,
                "source": "mock-ledger",
                "kind": "FEE",
                "amount_minor": 5,
                "currency": "USD",
                "reference": "late-row",
            },
        ),
        (
            "RECORD_OUTCOME",
            {"event_id": uuid4().hex, "source": "mock-upstream", "outcome": "LOST", "final": True},
        ),
    ):
        with pytest.raises(DisputeError) as error:
            run(service, case, action, data)
        assert error.value.code == "CASE_CLOSED"
        assert service.get_case(case["id"], OP) == case


def test_close_gate_requires_each_required_audit_artifact(service):
    case = run(service, reconciled(service), "NOTIFY_MERCHANT")
    assert close_blockers(case) == []
    for action in ("INTAKE", "RECORD_OUTCOME", "RECONCILE", "NOTIFY_MERCHANT"):
        damaged = deepcopy(case)
        damaged["audit"] = [entry for entry in damaged["audit"] if entry["action"] != action]
        assert "Required audit artifacts are missing" in close_blockers(damaged)


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount_minor", True),
        ("amount_minor", 1.5),
        ("amount_minor", "100"),
        ("currency", ["USD"]),
        ("event_id", {"id": "event"}),
        ("kind", ["FEE"]),
    ],
)
def test_financial_http_invalid_types_are_422_and_leave_no_partial_audit(service, field, value):
    case = terminal(service)
    app = FastAPI()
    app.state.disputes = service
    app.add_exception_handler(DisputeError, dispute_error_handler)
    app.include_router(router)
    payload = command(
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "source": "mock-ledger",
            "kind": "FEE",
            "amount_minor": 75,
            "currency": "USD",
            "reference": "one-ledger-row",
        },
    )
    payload["data"][field] = value
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v2/commands", json=payload, headers={"X-Demo-Role": "OPERATOR"}
        )
    assert response.status_code == 422, response.text
    assert service.get_case(case["id"], OP) == case


def test_frozen_human_approved_package_plan_recommends_submission(service):
    case = frozen(service)
    assert case["packages"][-1]["status"] == "FROZEN"
    plan = case_plan(case, now=NOW)
    assert plan["next_action"]["action"] == "SUBMIT"
    assert plan["next_action"]["owner"] == "OPERATOR"
    assert plan["proposal"]["expected_revision"] == case["revision"]


@pytest.mark.parametrize(
    "received_at",
    [
        "0001-01-01T00:00:00+14:00",
        "9999-12-31T23:59:59-14:00",
    ],
)
def test_intake_date_outside_representable_utc_range_is_422(service, received_at):
    app = FastAPI()
    app.state.disputes = service
    app.add_exception_handler(DisputeError, dispute_error_handler)
    app.include_router(router)
    payload = command(None, "INTAKE", intake_data(received_at=received_at))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v2/commands", json=payload, headers={"X-Demo-Role": "OPERATOR"}
        )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "INVALID_DATE"
    assert service.list_cases(OP) == []
