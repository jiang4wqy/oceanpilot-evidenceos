from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.domain.enums import EvidenceValueType, SourceReliability, SourceType
from oceanpilot.domain.models import CaseView
from oceanpilot.main import create_app

CASE_ID_V1 = "00000000-0000-1000-8000-000000000010"
EVIDENCE_ID = "00000000-0000-4000-8000-000000000011"
EVIDENCE_ID_V1 = "00000000-0000-1000-8000-000000000011"
SCHEMAS_AVAILABLE = importlib.util.find_spec("oceanpilot.api.schemas") is not None


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return create_app(Settings(db_path=tmp_path / "foundation.db"))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def post_case(client: TestClient, **changes: object):
    payload = {
        "case_type": "PAYMENT_INCIDENT",
        "summary": "Synthetic checkout failure",
        "merchant_ref": "merchant_demo_001",
        "synthetic": True,
    }
    payload.update(changes)
    return client.post("/api/v1/cases", json=payload)


def post_evidence(client: TestClient, case_id: str, **changes: object):
    payload = {
        "evidence_id": EVIDENCE_ID,
        "evidence_code": "context.environment",
        "availability": "AVAILABLE",
        "typed_value": "PROD",
        "observed_at": "2026-07-18T12:00:00+08:00",
        "source_ref": "synthetic:demo",
    }
    payload.update(changes)
    return client.post(f"/api/v1/cases/{case_id}/evidence", json=payload)


def post_environment(client: TestClient, case_id: str, value: str):
    return post_evidence(
        client,
        case_id,
        evidence_id=EVIDENCE_ID,
        typed_value=value,
    )


def post_sensitive_legal_field(client: TestClient, field: str, sentinel: str):
    if field == "summary":
        return post_case(client, summary=sentinel)

    created = post_case(client)
    assert created.status_code == 201
    case_id = created.json()["case"]["case_id"]
    return post_evidence(client, case_id, **{field: sentinel})


@pytest.fixture
def created_case(client: TestClient) -> str:
    response = post_case(client)
    assert response.status_code == 201
    return response.json()["case"]["case_id"]


def test_case_and_evidence_happy_path(client: TestClient):
    created = client.post(
        "/api/v1/cases",
        json={
            "case_type": "PAYMENT_INCIDENT",
            "summary": "Synthetic checkout failure",
            "merchant_ref": "merchant_demo_001",
            "synthetic": True,
        },
    )
    assert created.status_code == 201
    assert created.headers["Location"].startswith("/api/v1/cases/")
    created_view = CaseView.model_validate_json(created.content)
    case_id = created.json()["case"]["case_id"]
    evidence = client.post(
        f"/api/v1/cases/{case_id}/evidence",
        json={
            "evidence_id": EVIDENCE_ID,
            "evidence_code": "context.environment",
            "availability": "AVAILABLE",
            "typed_value": "PROD",
            "observed_at": "2026-07-18T12:00:00+08:00",
            "source_ref": "synthetic:demo",
        },
    )
    assert evidence.status_code == 201
    evidence_view = CaseView.model_validate_json(evidence.content)
    assert evidence_view.evidence[0].source_type is SourceType.MERCHANT
    assert evidence_view.evidence[0].source_reliability is SourceReliability.USER_REPORTED
    assert evidence_view.evidence[0].synthetic is True
    loaded = client.get(f"/api/v1/cases/{case_id}")
    assert loaded.status_code == 200
    loaded_view = CaseView.model_validate_json(loaded.content)
    assert created_view.case.case_revision == 1
    assert loaded_view.case.evidence_revision == 1
    assert len(loaded_view.evidence) == 1


def test_evidence_replay_is_200_and_conflict_is_409(
    client: TestClient,
    created_case: str,
):
    first = post_environment(client, created_case, "PROD")
    first_view = CaseView.model_validate_json(first.content)
    replay = post_environment(client, created_case, "PROD")
    replay_view = CaseView.model_validate_json(replay.content)
    conflict = post_environment(client, created_case, "SANDBOX")
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay_view == first_view
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "EVIDENCE_CONFLICT"
    after_conflict = client.get(f"/api/v1/cases/{created_case}")
    assert CaseView.model_validate_json(after_conflict.content) == first_view


def test_diagnosis_requires_ready_evidence(client: TestClient, created_case: str):
    response = client.post(f"/api/v1/cases/{created_case}/diagnose")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "CASE_NOT_READY"
    assert body["case_id"] == created_case
    assert body["current_revision"] == 1
    assert body["missing_fields"]
    assert response.headers["X-Trace-ID"] == body["trace_id"]


@pytest.mark.parametrize("synthetic", [False, "true", 1])
def test_synthetic_must_be_exact_true(client: TestClient, synthetic: object):
    response = post_case(client, synthetic=synthetic)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("typed_value", [1, 1.5, {"value": "PROD"}])
def test_evidence_typed_value_is_closed_and_strict(
    client: TestClient,
    created_case: str,
    typed_value: object,
):
    response = post_evidence(client, created_case, typed_value=typed_value)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("field", ["summary", "source_ref", "typed_value"])
def test_sensitive_value_in_legal_field_is_rejected_without_echo(
    client: TestClient,
    field: str,
):
    sentinel = "authorization=Bearer-SECRET-SENTINEL"
    response = post_sensitive_legal_field(client, field, sentinel)
    assert response.status_code == 422
    assert response.json()["code"] == "SENSITIVE_DATA_REJECTED"
    assert sentinel not in response.text


def test_unknown_source_fields_are_rejected_without_echo(
    client: TestClient,
    created_case: str,
):
    sentinel = "SYSTEM_OF_RECORD-SENTINEL"
    response = post_evidence(
        client,
        created_case,
        source_type=sentinel,
        source_reliability=sentinel,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert sentinel not in response.text


def test_unknown_case_field_is_rejected_without_echo(client: TestClient):
    sentinel = "SECRET-EXTRA-SENTINEL"
    response = post_case(client, source_type=sentinel)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert sentinel not in response.text


def test_disabled_case_type_is_not_enabled(client: TestClient):
    response = post_case(client, case_type="ONBOARDING_RECOMMENDATION")
    assert response.status_code == 409
    assert response.json()["code"] == "CASE_TYPE_NOT_ENABLED"


@pytest.mark.parametrize("case_id", ["not-a-uuid", CASE_ID_V1])
@pytest.mark.parametrize("route", ["case", "evidence", "diagnose"])
def test_case_path_requires_uuid4(client: TestClient, case_id: str, route: str):
    if route == "case":
        response = client.get(f"/api/v1/cases/{case_id}")
    elif route == "evidence":
        response = post_evidence(client, case_id)
    else:
        response = client.post(f"/api/v1/cases/{case_id}/diagnose")
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("evidence_id", ["not-a-uuid", EVIDENCE_ID_V1])
def test_evidence_dto_requires_uuid4(
    client: TestClient,
    created_case: str,
    evidence_id: str,
):
    response = post_evidence(client, created_case, evidence_id=evidence_id)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_transaction_timestamp_value_uses_rfc3339_parser(
    client: TestClient,
    created_case: str,
):
    response = post_evidence(
        client,
        created_case,
        evidence_code="transaction.occurred_at",
        typed_value="2026-07-18T04:00:00Z",
    )
    assert response.status_code == 201
    view = CaseView.model_validate_json(response.content)
    assert view.evidence[0].value_type is EvidenceValueType.DATETIME


@pytest.mark.parametrize(
    "field, value",
    [
        ("observed_at", "2026-07-18 04:00:00Z"),
        ("typed_value", "2026-07-18T04:00Z"),
    ],
)
def test_request_timestamp_parse_failures_are_fixed_422(
    client: TestClient,
    created_case: str,
    field: str,
    value: str,
):
    changes: dict[str, object] = {field: value}
    if field == "typed_value":
        changes["evidence_code"] = "transaction.occurred_at"
    response = post_evidence(client, created_case, **changes)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["detail"] == "request validation failed"


@pytest.mark.skipif(not SCHEMAS_AVAILABLE, reason="schemas module is created after API RED")
@pytest.mark.parametrize(
    "value, expected_offset",
    [
        ("2026-07-18T04:00:00Z", timedelta(0)),
        ("2026-07-18T12:00:00+08:00", timedelta(hours=8)),
    ],
)
def test_parse_rfc3339_accepts_exact_forms(value: str, expected_offset: timedelta):
    from oceanpilot.api.schemas import _parse_rfc3339

    parsed = _parse_rfc3339(value)
    assert parsed.utcoffset() == expected_offset


@pytest.mark.skipif(not SCHEMAS_AVAILABLE, reason="schemas module is created after API RED")
@pytest.mark.parametrize(
    "value",
    [
        "2026-07-18T04:00:00",
        "2026-07-18 04:00:00Z",
        "20260718T040000Z",
        "2026-W29-6T04:00:00Z",
        "2026-07-18T04:00Z",
        1784347200,
        "2026-07-18T04:00:00+0800",
        "2026-07-18T04:00:00+08:00:00",
    ],
)
def test_parse_rfc3339_rejects_non_exact_forms(value: object):
    from oceanpilot.api.schemas import _parse_rfc3339

    with pytest.raises(ValueError):
        _parse_rfc3339(value)  # type: ignore[arg-type]


def test_openapi_has_exact_foundation_paths(app: FastAPI):
    paths = app.openapi()["paths"]
    assert set(paths) == {
        "/health",
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/evidence",
        "/api/v1/cases/{case_id}/diagnose",
        "/api/v1/integrations/feishu/events",
        "/api/v1/integrations/feishu/card-actions",
        "/api/v1/chargeback/catalog",
        "/api/v1/chargeback/cases",
        "/api/v1/chargeback/cases/{case_id}",
        "/api/v1/chargeback/cases/{case_id}/appeal",
        "/api/v1/chargeback/cases/{case_id}/audit",
        "/api/v1/chargeback/cases/{case_id}/confirm",
        "/api/v1/chargeback/cases/{case_id}/evidence",
        "/api/v1/chargeback/cases/{case_id}/finalize",
        "/api/v1/chargeback/cases/{case_id}/package",
        "/api/v1/chargeback/metrics",
        "/api/v1/chargeback/prevention/assess",
        "/api/v1/chargeback/safety/scan",
        "/api/v1/admin/overview",
    }
    assert {path: set(item) for path, item in paths.items()} == {
        "/health": {"get"},
        "/api/v1/cases": {"post"},
        "/api/v1/cases/{case_id}": {"get"},
        "/api/v1/cases/{case_id}/evidence": {"post"},
        "/api/v1/cases/{case_id}/diagnose": {"post"},
        "/api/v1/integrations/feishu/events": {"post"},
        "/api/v1/integrations/feishu/card-actions": {"post"},
        "/api/v1/chargeback/catalog": {"get"},
        "/api/v1/chargeback/cases": {"post"},
        "/api/v1/chargeback/cases/{case_id}": {"get"},
        "/api/v1/chargeback/cases/{case_id}/appeal": {"post"},
        "/api/v1/chargeback/cases/{case_id}/audit": {"get"},
        "/api/v1/chargeback/cases/{case_id}/confirm": {"post"},
        "/api/v1/chargeback/cases/{case_id}/evidence": {"post"},
        "/api/v1/chargeback/cases/{case_id}/finalize": {"post"},
        "/api/v1/chargeback/cases/{case_id}/package": {"get"},
        "/api/v1/chargeback/metrics": {"get"},
        "/api/v1/chargeback/prevention/assess": {"post"},
        "/api/v1/chargeback/safety/scan": {"post"},
        "/api/v1/admin/overview": {"get"},
    }
