from fastapi.testclient import TestClient

from oceanpilot.admin import create_admin_app
from oceanpilot.config import Settings
from oceanpilot.main import create_app


def test_admin_overview_exposes_api_health_and_threshold_predictions(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    app.get("/boom")(lambda: (_ for _ in ()).throw(RuntimeError("synthetic failure")))

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/boom").status_code == 500
        response = client.get("/api/v1/admin/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["service_status"]["overall"] == "DEGRADED"
    assert body["service_status"]["database"] == "HEALTHY"
    assert body["request_summary"]["total"] == 2
    assert body["request_summary"]["server_errors"] == 1
    assert any(item["route"] == "/health" and item["observed"] for item in body["endpoints"])
    assert any(
        item["route"] == "/boom" and item["status"] == "DEGRADED" for item in body["endpoints"]
    )
    assert any(item["severity"] == "CRITICAL" for item in body["predictions"])
    assert body["prediction_method"] == "DETERMINISTIC_THRESHOLDS_V1"
    assert "不是故障概率" in body["prediction_disclaimer"]


def test_client_allows_read_only_admin_origin(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.options(
            "/api/v1/admin/overview",
            headers={
                "Origin": "http://127.0.0.1:8003",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8003"


def test_separate_admin_app_serves_management_console():
    app = create_admin_app("http://127.0.0.1:9123")
    with TestClient(app, raise_server_exceptions=False) as client:
        root = client.get("/", follow_redirects=False)
        page = client.get("/admin")
        health = client.get("/health")

    assert root.headers["location"] == "/admin"
    assert page.status_code == 200
    assert "Oceanpayment · 维护中心" in page.text
    assert "API 监控" in page.text and "故障预判" in page.text and "业务指标" in page.text
    assert "审计与配置" in page.text and "--accent:#087a70" in page.text
    assert 'const CLIENT_BASE="http://127.0.0.1:9123"' in page.text
    assert "不是故障概率" in page.text
    assert health.json() == {
        "status": "ok",
        "client_base_url": "http://127.0.0.1:9123",
    }
