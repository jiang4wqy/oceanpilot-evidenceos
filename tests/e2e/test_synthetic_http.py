from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app

OBSERVED_AT = "2026-08-05T04:00:00Z"
COMMON_FACTS = (
    ("transaction.reference", "txn_synthetic_001"),
    ("transaction.occurred_at", OBSERVED_AT),
    ("context.environment", "PROD"),
    ("integration.type", "API"),
)


@dataclass(frozen=True)
class Scenario:
    name: str
    facts: tuple[tuple[str, str], ...]
    rule_id: str
    team: str
    priority: str
    decisive_codes: frozenset[str]
    review_reasons: frozenset[str]


SCENARIOS = (
    Scenario(
        name="3ds_callback_incomplete",
        facts=(
            ("symptom.status", "PENDING"),
            ("authentication.status", "REQUIRED"),
            ("callback.delivery_status", "NOT_RECEIVED"),
        ),
        rule_id="THREEDS_INCOMPLETE_V1",
        team="TECHNICAL_SUPPORT",
        priority="MEDIUM",
        decisive_codes=frozenset(
            {
                "symptom.status",
                "authentication.status",
                "callback.delivery_status",
            }
        ),
        review_reasons=frozenset(
            {
                "LOW_CONFIDENCE",
                "INSUFFICIENT_SOURCE_QUALITY",
            }
        ),
    ),
    Scenario(
        name="risk_decline",
        facts=(
            ("symptom.status", "DECLINED"),
            ("risk.decision_code", "RISK_DECLINE"),
        ),
        rule_id="RISK_DECLINE_V1",
        team="RISK",
        priority="HIGH",
        decisive_codes=frozenset({"symptom.status", "risk.decision_code"}),
        review_reasons=frozenset(
            {
                "LOW_CONFIDENCE",
                "INSUFFICIENT_SOURCE_QUALITY",
                "RISK_DECISION",
            }
        ),
    ),
    Scenario(
        name="merchant_configuration_mismatch",
        facts=(
            ("symptom.status", "PENDING"),
            ("payment.method", "CARD"),
            ("configuration.check_result", "MERCHANT_SIDE_MISMATCH"),
        ),
        rule_id="CONFIG_MISMATCH_MERCHANT_V1",
        team="TECHNICAL_SUPPORT",
        priority="MEDIUM",
        decisive_codes=frozenset(
            {
                "symptom.status",
                "context.environment",
                "payment.method",
                "configuration.check_result",
            }
        ),
        review_reasons=frozenset(
            {
                "LOW_CONFIDENCE",
                "INSUFFICIENT_SOURCE_QUALITY",
            }
        ),
    ),
    Scenario(
        name="psp_configuration_mismatch",
        facts=(
            ("symptom.status", "PENDING"),
            ("payment.method", "CARD"),
            ("configuration.check_result", "PSP_PROFILE_MISMATCH"),
        ),
        rule_id="CONFIG_MISMATCH_PSP_V1",
        team="PSP_SUPPORT",
        priority="MEDIUM",
        decisive_codes=frozenset(
            {
                "symptom.status",
                "context.environment",
                "payment.method",
                "configuration.check_result",
            }
        ),
        review_reasons=frozenset(
            {
                "LOW_CONFIDENCE",
                "INSUFFICIENT_SOURCE_QUALITY",
            }
        ),
    ),
)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_synthetic_incident_diagnoses_and_replays_through_http(tmp_path, scenario):
    app = create_app(Settings(db_path=tmp_path / f"{scenario.name}.db"))
    facts = COMMON_FACTS + scenario.facts

    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/v1/cases",
            json={
                "case_type": "PAYMENT_INCIDENT",
                "summary": f"Synthetic {scenario.name} incident",
                "merchant_ref": f"merchant_{scenario.name}",
                "synthetic": True,
            },
        )
        assert created.status_code == 201
        case_id = created.json()["case"]["case_id"]

        evidence_ids = {}
        for index, (code, value) in enumerate(facts, start=1):
            evidence_id = f"00000000-0000-4000-8000-{index:012d}"
            evidence_ids[code] = evidence_id
            added = client.post(
                f"/api/v1/cases/{case_id}/evidence",
                json={
                    "evidence_id": evidence_id,
                    "evidence_code": code,
                    "availability": "AVAILABLE",
                    "typed_value": value,
                    "observed_at": OBSERVED_AT,
                    "source_ref": "synthetic:e2e",
                },
            )
            assert added.status_code == 201

        first = client.post(f"/api/v1/cases/{case_id}/diagnose", json={})
        replay = client.post(f"/api/v1/cases/{case_id}/diagnose", json={})

    assert first.status_code == 201
    assert replay.status_code == 200
    first_body = first.json()
    replay_body = replay.json()
    assert first_body["outcome"] == "CREATED"
    assert replay_body["outcome"] == "REPLAY"
    assert replay_body == {**first_body, "outcome": "REPLAY"}

    diagnosis = first_body["diagnosis"]
    assert first_body["case_status"] == "HUMAN_REVIEW"
    assert diagnosis["requires_human"] is True
    assert set(diagnosis["review_reasons"]) == scenario.review_reasons
    assert len(diagnosis["hypotheses"]) == 1

    hypothesis = diagnosis["hypotheses"][0]
    assert hypothesis["rule_id"] == scenario.rule_id
    assert hypothesis["confidence_score"] == "0.87"
    decisive_ids = {evidence_ids[code] for code in scenario.decisive_codes}
    assert set(hypothesis["evidence_refs"]) == decisive_ids

    route = diagnosis["routing_decision"]
    assert route is not None
    assert route["responsible_team"] == scenario.team
    assert route["priority"] == scenario.priority
    assert route["requires_human"] is True
    assert set(route["review_reasons"]) == scenario.review_reasons
    assert set(route["evidence_refs"]) == decisive_ids

    ticket = diagnosis["ticket_draft"]
    assert ticket is not None
    assert ticket["responsible_team"] == route["responsible_team"]
    assert len(ticket["hypotheses"]) == 1
    ticket_hypothesis = ticket["hypotheses"][0]
    assert ticket_hypothesis == {
        key: value for key, value in hypothesis.items() if key != "hypothesis_id"
    }
    assert set(ticket_hypothesis["evidence_refs"]) == decisive_ids

    assert first_body["audit_reference"] == {
        "case_id": case_id,
        "diagnosis_id": diagnosis["diagnosis_id"],
        "case_revision": first_body["case_revision"],
        "evidence_revision": first_body["evidence_revision"],
    }
