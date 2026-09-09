"""Normalized source intake never substitutes user-entered claims for registry facts."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest

from oceanpilot.adapters.knowledge.dispute_case_library import DisputeCaseLibrary
from oceanpilot.adapters.persistence.dispute_intake import SQLiteDisputeIntakeStore
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_intake import DisputeIntakeService
from oceanpilot.application.disputes import DisputeError, DisputeService
from tests.workflow.test_dispute_engine import NOW, OP, RISK, run

DIRECTOR = {"role": "DIRECTOR", "actor_id": "director"}


def envelope(**changes):
    return (
        dict(
            event_type="FORMAL_DISPUTE",
            source_event_id=str(uuid4()),
            channel="MOCK",
            received_at=NOW.isoformat(),
            occurred_at=(NOW - timedelta(hours=1)).isoformat(),
            merchant_id="merchant-a",
            transaction_id=str(uuid4()),
            scheme="VISA",
            amount_minor=12800,
            currency="USD",
            reason_code="13.1",
        )
        | changes
    )


def register(service, event):
    return service.register_transaction(
        {
            k: event[k]
            for k in (
                "channel",
                "merchant_id",
                "transaction_id",
                "scheme",
                "amount_minor",
                "currency",
            )
        }
        | {"reference": "explicit-synthetic-source"},
        DIRECTOR,
    )


@pytest.fixture
def service(tmp_path):
    path = tmp_path / "intake.db"
    disputes = DisputeService(
        SQLiteDisputeStore(path), clock=lambda: NOW, case_library=DisputeCaseLibrary()
    )
    return DisputeIntakeService(SQLiteDisputeIntakeStore(path), disputes, clock=lambda: NOW)


@pytest.mark.parametrize("kind", ["ALERT", "INQUIRY"])
def test_informational_event_is_recorded_without_case(service, kind):
    event = envelope(event_type=kind)
    register(service, event)
    result = service.receive(event, OP, confirmed=True)
    assert result["event"]["status"] == "RECORDED" and result["case_id"] is None
    assert not service.disputes.list_cases(OP)
    assert service.receive(event, OP, confirmed=True)["replayed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("merchant_id", "merchant-b"),
        ("scheme", "MASTERCARD"),
        ("currency", "EUR"),
        ("amount_minor", 100),
    ],
)
def test_registry_mismatch_is_quarantined_without_case(service, field, value):
    event = envelope()
    register(service, event)
    result = service.receive(event | {field: value}, OP, confirmed=True)
    assert (
        result["event"]["status"] == "QUARANTINED"
        and result["event"]["reason"] == "TRANSACTION_FACTS_MISMATCH"
    )
    assert not service.disputes.list_cases(OP)


def test_unknown_registry_event_can_be_revalidated_without_rewriting_original(service):
    event = envelope()
    result = service.receive(event, OP, confirmed=True)
    assert result["event"]["reason"] == "TRANSACTION_NOT_REGISTERED"
    register(service, event)
    result = service.retry_event(
        result["event"]["id"],
        OP,
        confirmed=True,
        reason="Director registered the verified synthetic transaction",
    )
    assert result["event"]["status"] == "PROCESSED" and result["case_id"]
    assert result["event"]["envelope"] == event
    assert [a["status"] for a in result["event"]["attempts"]] == ["QUARANTINED", "PROCESSED"]


@pytest.mark.parametrize(
    "role", ["OPERATOR", "RISK_OFFICER", "SUPERVISOR", "MERCHANT", "ADMIN", "AGENT"]
)
def test_only_director_can_create_registry_facts(service, role):
    data = envelope()
    payload = {
        k: data[k]
        for k in ("channel", "merchant_id", "transaction_id", "scheme", "amount_minor", "currency")
    } | {"reference": "synthetic-source"}
    with pytest.raises(DisputeError) as error:
        service.register_transaction(payload, {"role": role, "actor_id": "unauthorized"})
    assert error.value.status == 403
    assert not service.store.list_transactions()


def test_same_source_event_conflicting_payload_cannot_reassign_case(service):
    event = envelope()
    register(service, event)
    original = service.receive(event, OP, confirmed=True)
    with pytest.raises(DisputeError) as error:
        service.receive(event | {"amount_minor": 100}, OP, confirmed=True)
    assert error.value.code == "SOURCE_EVENT_CONFLICT"
    assert len(service.disputes.list_cases(OP)) == 1
    assert service.receive(event, OP, confirmed=True)["case_id"] == original["case_id"]


def test_concurrent_delivery_dispatches_one_business_command(service):
    event = envelope()
    register(service, event)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.receive(event, OP, confirmed=True), range(4)))
    assert len({r["case_id"] for r in results}) == 1
    cases = service.disputes.list_cases(OP)
    assert len(cases) == 1 and cases[0]["revision"] == 1
    assert len(service.store.list_events()) == 1


def test_business_commit_then_receipt_failure_recovers_by_saved_command_after_restart(
    service, monkeypatch
):
    event = envelope()
    register(service, event)
    original = service.store.finish

    def failing(*args, **kwargs):
        raise RuntimeError("synthetic crash after business commit")

    monkeypatch.setattr(service.store, "finish", failing)
    first = service.receive(event, OP, confirmed=True)
    assert first["event"]["status"] == "PENDING_RECEIPT"
    pending = deepcopy(service.store.get_event(first["event"]["id"])["attempts"][-1]["command"])
    monkeypatch.setattr(service.store, "finish", original)
    restarted = DisputeIntakeService(
        SQLiteDisputeIntakeStore(service.store.db_path), service.disputes, clock=lambda: NOW
    )
    result = restarted.receive(event, OP, confirmed=True)
    assert result["event"]["status"] == "PROCESSED" and result["replayed"]
    assert restarted.store.get_event(result["event"]["id"])["attempts"][-1]["command"] == pending
    assert service.disputes.get_case(result["case_id"], OP)["revision"] == 1


def test_withdrawal_is_associated_to_existing_case_and_enters_risk_verification(service):
    event = envelope()
    register(service, event)
    case_id = service.receive(event, OP, confirmed=True)["case_id"]
    withdrawal = event | {
        "event_type": "WITHDRAWAL",
        "source_event_id": str(uuid4()),
        "target_case_id": case_id,
        "basis_reference": "upstream-withdrawal-source",
    }
    result = service.receive(withdrawal, OP, confirmed=True)
    assert result["case_id"] == case_id
    case = service.disputes.get_case(case_id, OP)
    assert case["work_status"] == "OUTCOME_VERIFICATION" and case["finality"] == "NOT_FINAL"
    case = run(
        service.disputes,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": withdrawal["source_event_id"],
            "decision": "CONFIRM",
            "reason": "Confirmed source relationship",
            "authorization_reference": "risk-authorization",
        },
        RISK,
    )
    assert case["business_outcome"] == "WITHDRAWN" and case["finality"] == "FINAL_CONFIRMED"


def test_unknown_target_and_closed_correction_remain_quarantined(service):
    event = envelope()
    register(service, event)
    result = service.receive(
        event | {"event_type": "WITHDRAWAL", "target_case_id": "unknown"}, OP, confirmed=True
    )
    assert result["event"]["reason"] == "CASE_ASSOCIATION_REQUIRES_VERIFICATION"
    assert not service.disputes.list_cases(OP)


def test_registry_reference_is_immutable_and_no_implicit_sample_is_seeded(service):
    assert not service.list_transactions(DIRECTOR)
    event = envelope()
    first = register(service, event)
    assert register(service, event) == first
    with pytest.raises(DisputeError) as error:
        register(service, event | {"amount_minor": 1})
    assert error.value.code == "REGISTRY_CONFLICT"


def test_curated_template_survives_normalized_intake_without_fixture_sla(service):
    event = envelope(case_template_id="CB-CASE-041")
    register(service, event)
    result = service.receive(event, OP, confirmed=True)
    assert result["event"]["status"] == "PROCESSED"
    case = service.disputes.get_case(result["case_id"], OP)
    assert case["library_reference"]["template_id"] == "CB-CASE-041"
    assert case["library_reference"]["sandbox_inputs"]["amount_minor"] == 12800
    assert case["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"
    assert case["deadlines"]["status"] == "NEEDS_CONFIRMATION"
    assert case["production_eligible"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount_minor", True),
        ("source_event_id", []),
        ("event_type", "MYSTERY"),
        ("received_at", "0001-01-01T00:00:00+14:00"),
        ("occurred_at", (NOW + timedelta(hours=1)).isoformat()),
    ],
)
def test_malformed_envelope_never_creates_inbox_or_case(service, field, value):
    with pytest.raises(DisputeError) as error:
        service.receive(envelope(**{field: value}), OP, confirmed=True)
    assert error.value.status == 422
    assert not service.store.list_events() and not service.disputes.list_cases(OP)


LIBRARY = DisputeCaseLibrary()
NETWORK_TEMPLATES = [
    r
    for r in LIBRARY.list_references()
    if r["sandbox_template_available"] and r["scheme"] in {"VISA", "MASTERCARD"}
]


@pytest.mark.parametrize("reference", NETWORK_TEMPLATES, ids=lambda r: r["template_id"])
def test_all_26_network_templates_stay_unconfirmed_after_actual_event_normalization(
    service, reference
):
    assert len(NETWORK_TEMPLATES) == 26
    event = envelope(
        case_template_id=reference["template_id"],
        scheme=reference["scheme"],
        reason_code=reference["reason_codes"][0],
    )
    register(service, event)
    result = service.receive(event, OP, confirmed=True)
    assert result["event"]["status"] == "PROCESSED", result
    case = service.disputes.get_case(result["case_id"], OP)
    assert case["library_reference"]["template_id"] == reference["template_id"]
    assert case["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"
    assert case["deadlines"]["external"] is None


def test_formal_source_event_cannot_change_template_on_duplicate_upstream_case(service):
    event = envelope(case_template_id="CB-CASE-041", upstream_case_id=str(uuid4()))
    register(service, event)
    first = service.receive(event, OP, confirmed=True)
    case = service.disputes.get_case(first["case_id"], OP)
    result = service.receive(
        event | {"source_event_id": str(uuid4()), "case_template_id": "CB-CASE-060"},
        OP,
        confirmed=True,
    )
    assert result["event"]["status"] == "QUARANTINED"
    assert service.disputes.get_case(first["case_id"], OP) == case
    assert len(service.disputes.list_cases(OP)) == 1


def test_correction_requires_existing_source_relation_and_can_be_retried_after_authorized_reopen(
    service,
):
    event = envelope()
    register(service, event)
    case_id = service.receive(event, OP, confirmed=True)["case_id"]
    withdrawal = event | {
        "event_type": "WITHDRAWAL",
        "source_event_id": str(uuid4()),
        "target_case_id": case_id,
    }
    service.receive(withdrawal, OP, confirmed=True)
    case = service.disputes.get_case(case_id, OP)
    case = run(
        service.disputes,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": withdrawal["source_event_id"],
            "decision": "CONFIRM",
            "reason": "Verify original source withdrawal",
            "authorization_reference": "risk-source",
        },
        RISK,
    )
    correction = event | {
        "event_type": "CORRECTION",
        "source_event_id": str(uuid4()),
        "target_case_id": case_id,
        "outcome": "LOST",
        "final": True,
        "corrects_event_id": withdrawal["source_event_id"],
        "basis_reference": "corrected-source-notice",
    }
    result = service.receive(correction, OP, confirmed=True)
    assert result["event"]["reason"] == "AUTHORIZED_REOPEN_REQUIRED"
    from tests.workflow.test_dispute_engine import SUPERVISOR

    case = run(
        service.disputes,
        case,
        "REOPEN_CASE",
        {
            "reason": "Verified correction requires reopening",
            "authorization_reference": "supervisor-source",
            "event_reference": correction["source_event_id"],
        },
        SUPERVISOR,
    )
    result = service.retry_event(
        result["event"]["id"], OP, confirmed=True, reason="Supervisor authorized correction review"
    )
    assert result["event"]["status"] == "PROCESSED"
    case = service.disputes.get_case(case_id, OP)
    assert case["work_status"] == "OUTCOME_VERIFICATION"
    case = run(
        service.disputes,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": correction["source_event_id"],
            "decision": "CONFIRM",
            "reason": "Confirmed corrected upstream result",
            "authorization_reference": "risk-source",
        },
        RISK,
    )
    assert case["business_outcome"] == "LOST" and case["outcome_history"]
