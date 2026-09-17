"""Every catalogue entry can start an explicitly separate synthetic rehearsal."""

import re
from uuid import uuid4

import pytest

from oceanpilot.adapters.knowledge.dispute_case_library import DisputeCaseLibrary
from oceanpilot.adapters.persistence.dispute_intake import SQLiteDisputeIntakeStore
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_intake import DisputeIntakeService
from oceanpilot.application.dispute_simulation import DisputeSimulation
from oceanpilot.application.disputes import DisputeService
from tests.workflow.test_dispute_engine import NOW

MANAGER = {"role": "SUPERVISOR", "actor_id": "simulation-manager"}

REFERENCES = DisputeCaseLibrary().list_references()


@pytest.mark.parametrize("reference", REFERENCES, ids=[r["template_id"] for r in REFERENCES])
def test_every_reference_can_create_without_inheriting_facts(tmp_path, reference):
    path = tmp_path / "all.db"
    disputes = DisputeService(
        SQLiteDisputeStore(path), clock=lambda: NOW, case_library=DisputeCaseLibrary()
    )
    intake = DisputeIntakeService(SQLiteDisputeIntakeStore(path), disputes, clock=lambda: NOW)
    simulation = DisputeSimulation(intake)
    scheme = reference["scheme"]
    if scheme not in {"VISA", "MASTERCARD", "AMEX", "DISCOVER"}:
        scheme = "OTHER"
    reasons = re.findall(r"[A-Z]\d{2}|\d{2}\.\d|\d{4}", reference["reason_code"])
    data = dict(
        case_template_id=reference["template_id"],
        merchant_id="merchant-a",
        scheme=scheme,
        reason_code=reasons[0] if reasons else "SIMULATION",
        amount_minor=10000,
        currency="USD",
        received_at=NOW.isoformat(),
    )
    preview = simulation.preview(data, MANAGER)
    args = dict(
        confirmed=True, request_id=str(uuid4()), confirmation_token=preview["confirmation_token"]
    )
    result = simulation.create(data, MANAGER, **args)
    assert result["simulation_status"] in {"READY", "NEEDS_RULE_CONFIRMATION"}, result
    case = result["case"]
    assert case["merchant_decision"] == "NONE"
    assert not case["evidence"] and not case["packages"]
    assert case["business_outcome"] == "UNKNOWN"
    assert case["library_reference"]["template_id"] == reference["template_id"]
    if preview["requires_rule_confirmation"]:
        assert not case["rule_snapshot"]["allowed_actions"]
        assert not case["rule_snapshot"]["required_evidence"]
        assert case["deadlines"]["status"] == "NEEDS_CONFIRMATION"
        assert result["notification_intent"] is None
    assert simulation.create(data, MANAGER, **args)["case"]["revision"] == case["revision"]
