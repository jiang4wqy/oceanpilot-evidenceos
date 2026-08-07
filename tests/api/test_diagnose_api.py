from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from oceanpilot.api.dependencies import get_case_service
from oceanpilot.application.errors import (
    CaseNotReady,
    DiagnosisInputStale,
    PersistenceInvariantViolation,
)
from oceanpilot.config import Settings
from oceanpilot.domain.enums import (
    CaseStatus,
    DiagnosisStatus,
    Priority,
    ResponsibleTeam,
    WriteOutcome,
)
from oceanpilot.domain.errors import InvalidTransition
from oceanpilot.domain.models import (
    CommandResult,
    DiagnosisSnapshot,
    DiagnosisView,
    Hypothesis,
    HypothesisDraft,
    RoutingDecision,
    TicketDraft,
)
from oceanpilot.main import create_app

CASE_ID = "00000000-0000-4000-8000-000000000010"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
EVIDENCE_REFS = (
    "00000000-0000-4000-8000-000000000101",
    "00000000-0000-4000-8000-000000000103",
)


def _diagnosis_result(outcome: WriteOutcome) -> CommandResult[DiagnosisView]:
    hypothesis = Hypothesis(
        hypothesis_id="00000000-0000-4000-8000-000000000301",
        cause_code="SYNTHETIC_CAUSE",
        explanation="Synthetic explanation",
        evidence_refs=EVIDENCE_REFS,
        confidence_score=Decimal("0.91"),
        confidence_method="HEURISTIC_V1",
        next_verification_action="Verify synthetic evidence",
        rule_id="SYNTHETIC_RULE_V1",
    )
    draft = HypothesisDraft(**hypothesis.model_dump(exclude={"hypothesis_id"}))
    route = RoutingDecision(
        responsible_team=ResponsibleTeam.TECHNICAL_SUPPORT,
        priority=Priority.HIGH,
        reason="Synthetic route",
        evidence_refs=EVIDENCE_REFS,
        requires_human=False,
        review_reasons=frozenset(),
    )
    ticket = TicketDraft(
        title="Synthetic ticket",
        summary=hypothesis.explanation,
        evidence_summary=("transaction.reference=txn_001",),
        missing_material=(),
        hypotheses=(draft,),
        next_action=hypothesis.next_verification_action,
        responsible_team=route.responsible_team,
        synthetic=True,
    )
    snapshot = DiagnosisSnapshot(
        diagnosis_id=DIAGNOSIS_ID,
        case_id=CASE_ID,
        evidence_revision=5,
        policy_version="POLICY_V1",
        engine_version="RULES_V1",
        status=DiagnosisStatus.CURRENT,
        hypotheses=(hypothesis,),
        routing_decision=route,
        ticket_draft=ticket,
        requires_human=False,
        review_reasons=frozenset(),
        synthetic=True,
        created_at=datetime(2026, 8, 5, 4, 0, tzinfo=UTC),
    )
    return CommandResult[DiagnosisView](
        outcome=outcome,
        value=DiagnosisView(
            case_id=CASE_ID,
            case_status=CaseStatus.DIAGNOSED,
            case_revision=7,
            evidence_revision=5,
            diagnosis=snapshot,
        ),
    )


class _DiagnosisService:
    def __init__(self, result_or_error):
        self._result_or_error = result_or_error
        self.command = None

    def diagnose(self, command):
        self.command = command
        if isinstance(self._result_or_error, BaseException):
            raise self._result_or_error
        return self._result_or_error


def _post_diagnose(tmp_path, service: _DiagnosisService, json_body=None, *, send_body=False):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            if send_body:
                return client.post(f"/api/v1/cases/{CASE_ID}/diagnose", json=json_body)
            return client.post(f"/api/v1/cases/{CASE_ID}/diagnose")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "outcome, expected_status",
    [(WriteOutcome.CREATED, 201), (WriteOutcome.REPLAY, 200)],
)
def test_diagnose_created_and_replay_share_strict_response(
    tmp_path,
    outcome: WriteOutcome,
    expected_status: int,
):
    service = _DiagnosisService(_diagnosis_result(outcome))
    response = _post_diagnose(tmp_path, service)

    assert response.status_code == expected_status
    assert response.headers["X-Trace-ID"] == service.command.trace_id
    body = response.json()
    assert body["outcome"] == outcome.value
    assert body["case_id"] == CASE_ID
    assert body["diagnosis"]["diagnosis_id"] == DIAGNOSIS_ID
    assert body["diagnosis"]["hypotheses"][0]["evidence_refs"] == list(EVIDENCE_REFS)
    assert body["audit_reference"] == {
        "case_id": CASE_ID,
        "diagnosis_id": DIAGNOSIS_ID,
        "case_revision": 7,
        "evidence_revision": 5,
    }


def test_diagnose_rejects_nonempty_body_without_echo(tmp_path):
    service = _DiagnosisService(_diagnosis_result(WriteOutcome.CREATED))
    sentinel = "SECRET-BODY-FIELD"
    response = _post_diagnose(
        tmp_path,
        service,
        {sentinel: "SECRET-BODY-VALUE"},
        send_body=True,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert sentinel not in response.text
    assert "SECRET-BODY-VALUE" not in response.text
    assert service.command is None


def test_case_not_ready_has_only_whitelisted_extensions(tmp_path):
    error = CaseNotReady(
        case_id=CASE_ID,
        missing_fields=("symptom.signal", "transaction.reference"),
        current_revision=3,
    )
    response = _post_diagnose(tmp_path, _DiagnosisService(error))

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "CASE_NOT_READY"
    assert body["case_id"] == CASE_ID
    assert body["missing_fields"] == ["symptom.signal", "transaction.reference"]
    assert body["current_revision"] == 3
    assert set(body) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "request_id",
        "trace_id",
        "case_id",
        "missing_fields",
        "current_revision",
    }


@pytest.mark.parametrize(
    "error, status, code",
    [
        (DiagnosisInputStale(), 409, "DIAGNOSIS_INPUT_STALE"),
        (InvalidTransition(), 409, "INVALID_TRANSITION"),
        (PersistenceInvariantViolation(), 500, "INTERNAL_ERROR"),
    ],
)
def test_diagnosis_failures_map_to_safe_problems(tmp_path, error, status: int, code: str):
    response = _post_diagnose(tmp_path, _DiagnosisService(error))

    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["X-Trace-ID"] == response.json()["trace_id"]


def test_real_sqlite_rule_diagnosis_creates_then_replays(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    facts = (
        ("transaction.reference", "txn_001"),
        ("transaction.occurred_at", "2026-08-05T04:00:00Z"),
        ("context.environment", "PROD"),
        ("symptom.status", "PENDING"),
        ("integration.type", "API"),
        ("authentication.status", "REQUIRED"),
        ("callback.delivery_status", "NOT_RECEIVED"),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/v1/cases",
            json={
                "case_type": "PAYMENT_INCIDENT",
                "summary": "Synthetic 3DS incident",
                "merchant_ref": "merchant_demo_001",
                "synthetic": True,
            },
        )
        assert created.status_code == 201
        case_id = created.json()["case"]["case_id"]
        for index, (code, value) in enumerate(facts, start=1):
            evidence = client.post(
                f"/api/v1/cases/{case_id}/evidence",
                json={
                    "evidence_id": f"00000000-0000-4000-8000-{index:012d}",
                    "evidence_code": code,
                    "availability": "AVAILABLE",
                    "typed_value": value,
                    "source_ref": f"synthetic:http:{index}",
                },
            )
            assert evidence.status_code == 201

        first = client.post(f"/api/v1/cases/{case_id}/diagnose")
        replay = client.post(f"/api/v1/cases/{case_id}/diagnose")

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.json()["outcome"] == "CREATED"
    assert replay.json()["outcome"] == "REPLAY"
    assert first.json()["diagnosis"]["diagnosis_id"] == replay.json()["diagnosis"]["diagnosis_id"]
    assert first.json()["audit_reference"] == replay.json()["audit_reference"]
    assert first.json()["diagnosis"]["hypotheses"][0]["rule_id"] == "THREEDS_INCOMPLETE_V1"
