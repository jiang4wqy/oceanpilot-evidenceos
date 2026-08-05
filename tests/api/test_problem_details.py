from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def _assert_problem(response, *, status: int, code: str) -> dict[str, object]:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert response.headers["X-Trace-ID"] == body["trace_id"]
    assert UUID(body["trace_id"]).version == 4
    assert UUID(body["request_id"]).version == 4
    assert set(body) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "request_id",
        "trace_id",
    }
    return body


def test_unknown_route_is_rfc9457_problem_with_request_context(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/not-a-route")

    body = _assert_problem(response, status=404, code="HTTP_ERROR")
    assert body["instance"] == f"urn:oceanpilot:request:{body['request_id']}"
    assert body["detail"] == "request could not be completed"


def test_invalid_path_value_is_not_echoed_in_problem_instance(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    sentinel = "Bearer-SECRET-PATH-SENTINEL"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/cases/{sentinel}")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert response.headers["X-Trace-ID"] == body["trace_id"]
    assert sentinel not in response.text
    assert body["instance"] == f"urn:oceanpilot:request:{body['request_id']}"


def test_unexpected_exception_is_safe_problem_and_does_not_echo(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    app.get("/boom")(lambda: (_ for _ in ()).throw(RuntimeError("SECRET-SENTINEL")))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    _assert_problem(response, status=500, code="INTERNAL_ERROR")
    assert "SECRET-SENTINEL" not in response.text


def test_validation_problem_exposes_only_safe_location_and_reason(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    sentinel = "password=SECRET-UNKNOWN-KEY"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/cases",
            json={
                "case_type": "PAYMENT_INCIDENT",
                "summary": "Synthetic incident",
                "merchant_ref": "merchant_demo_001",
                "synthetic": True,
                sentinel: "SECRET-UNKNOWN-VALUE",
            },
        )

    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "body.<extra>", "reason": "extra_field"}]
    assert sentinel not in response.text
    assert "SECRET-UNKNOWN-VALUE" not in response.text


@pytest.mark.parametrize("method", ["post", "put"])
def test_method_not_allowed_preserves_only_allow_header(tmp_path, method: str):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = getattr(client, method)("/health")

    _assert_problem(response, status=405, code="HTTP_ERROR")
    assert response.headers["allow"] == "GET"
