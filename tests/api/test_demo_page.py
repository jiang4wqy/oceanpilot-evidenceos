from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def _client(tmp_path):
    return TestClient(
        create_app(Settings(db_path=tmp_path / "api.db")), raise_server_exceptions=False
    )


def test_demo_page_is_served_html(tmp_path):
    with _client(tmp_path) as client:
        resp = client.get("/demo")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "跨境拒付" in body
    assert "/api/v1/chargeback" in body  # the page drives the real API
    assert "绝不执行" in body  # the safety story is on screen


def test_demo_page_is_not_in_openapi(tmp_path):
    with _client(tmp_path) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/demo" not in paths
