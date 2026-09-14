# ruff: noqa: F811
from uuid import uuid4

import pytest

from oceanpilot.application.dispute_simulation import DisputeSimulation
from oceanpilot.domain.dispute import DisputeError
from tests.application.test_dispute_intake import service  # noqa: F401
from tests.workflow.test_dispute_engine import NOW, OP


def request():
    return dict(
        case_template_id="CB-CASE-060",
        merchant_id="merchant-a",
        scheme="VISA",
        reason_code="13.1",
        amount_minor=29900,
        currency="USD",
        received_at=NOW.isoformat(),
    )


def test_simulation_builds_empty_case_and_task_and_replays(service):  # noqa: F811
    simulation = DisputeSimulation(service)
    data = request()
    preview = simulation.preview(data, OP)
    args = dict(
        confirmed=True, confirmation_token=preview["confirmation_token"], request_id=str(uuid4())
    )
    result = simulation.create(data, OP, **args)
    case = result["case"]
    assert case["work_status"] == "MERCHANT_ACTION_REQUIRED"
    assert case["merchant_decision"] == "NONE"
    assert case["business_outcome"] == "UNKNOWN"
    assert not case["evidence"] and not case["packages"]
    assert case["rule_snapshot"]["production_eligible"] is False
    assert result["notification_intent"]["active"]
    assert case["rule_snapshot"]["critical_evidence"]
    again = simulation.create(data, OP, **args)
    assert again["case"]["revision"] == case["revision"]
    assert len(service.disputes.list_cases(OP)) == 1
    assert again["notification_intent"]["id"] == result["notification_intent"]["id"]
    with pytest.raises(DisputeError):
        simulation.create(data | {"amount_minor": 1}, OP, **args)


def test_unconfirmed_and_unsupported_simulation_do_not_create_case(service):  # noqa: F811
    simulation = DisputeSimulation(service)
    data = request()
    p = simulation.preview(data, OP)
    with pytest.raises(DisputeError):
        simulation.create(
            data,
            OP,
            confirmed=False,
            confirmation_token=p["confirmation_token"],
            request_id=str(uuid4()),
        )
    pending = simulation.preview(
        data | {"reason_code": "13.6", "case_template_id": "CB-CASE-072"}, OP
    )
    assert pending["requires_rule_confirmation"]
    assert not service.disputes.list_cases(OP)


def test_partial_command_failure_resumes_without_duplicate_tasks(service, monkeypatch):  # noqa: F811
    simulation = DisputeSimulation(service)
    data = request()
    preview = simulation.preview(data, OP)
    args = dict(
        confirmed=True, confirmation_token=preview["confirmation_token"], request_id=str(uuid4())
    )
    execute = service.disputes.execute

    def fail_task(command, identity):
        if command["action"] == "PUBLISH_TASK":
            raise RuntimeError("temporary outage")
        return execute(command, identity)

    monkeypatch.setattr(service.disputes, "execute", fail_task)
    with pytest.raises(RuntimeError):
        simulation.create(data, OP, **args)
    assert len(service.disputes.list_cases(OP)) == 1
    monkeypatch.setattr(service.disputes, "execute", execute)
    resumed = DisputeSimulation(service).create(data, OP, **args)
    assert resumed["case"]["revision"] == 3
    assert resumed["case"]["work_status"] == "MERCHANT_ACTION_REQUIRED"


@pytest.mark.parametrize("decision", ["ACCEPT", "CONTEST"])
def test_real_decision_branches_preserve_unknown_outcome(service, decision):  # noqa: F811
    simulation = DisputeSimulation(service)
    data = request()
    preview = simulation.preview(data, OP)
    result = simulation.create(
        data,
        OP,
        confirmed=True,
        confirmation_token=preview["confirmation_token"],
        request_id=str(uuid4()),
    )
    merchant = {"role": "MERCHANT", "actor_id": "merchant", "merchant_id": "merchant-a"}
    case = service.disputes.execute(
        {
            "command_id": str(uuid4()),
            "case_id": result["case_id"],
            "action": "MERCHANT_DECISION",
            "expected_revision": 3,
            "confirmed": True,
            "data": {"decision": decision, "reason": "Explicit synthetic scenario choice"},
        },
        merchant,
    )["case"]
    assert case["business_outcome"] == "UNKNOWN"
    assert case["work_status"] == (
        "ACCEPT_PROCESSING" if decision == "ACCEPT" else "EVIDENCE_COLLECTING"
    )
    assert not case["evidence"]
    assert not any(t["type"] == "DECISION" and t["status"] == "OPEN" for t in case["tasks"])


def test_expired_partial_request_does_not_publish(service, monkeypatch):  # noqa: F811
    from datetime import timedelta

    simulation = DisputeSimulation(service)
    data = request()
    preview = simulation.preview(data, OP)
    args = dict(
        confirmed=True, confirmation_token=preview["confirmation_token"], request_id=str(uuid4())
    )
    original = service.disputes.execute

    def pause(command, identity):
        if command["action"] == "PUBLISH_TASK":
            raise RuntimeError("interruption")
        return original(command, identity)

    monkeypatch.setattr(service.disputes, "execute", pause)
    with pytest.raises(RuntimeError):
        simulation.create(data, OP, **args)
    monkeypatch.setattr(service.disputes, "execute", original)
    monkeypatch.setattr(service, "clock", lambda: NOW + timedelta(days=4))
    with pytest.raises(DisputeError, match="演练期限已过"):
        simulation.create(data, OP, **args)
    assert service.disputes.list_cases(OP)[0]["work_status"] != "MERCHANT_ACTION_REQUIRED"
