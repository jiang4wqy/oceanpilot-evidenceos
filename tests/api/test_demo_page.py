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


def test_root_redirects_to_demo(tmp_path):
    with _client(tmp_path) as client:
        r = client.get("/", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/demo"
        followed = client.get("/")
    assert followed.status_code == 200
    assert "跨境拒付" in followed.text


def test_demo_links_to_api_docs(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert 'href="/docs"' in body
    assert 'href="/health"' in body
