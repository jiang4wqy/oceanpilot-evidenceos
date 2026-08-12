from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app
from tests.demo.test_demo_case_api import _diagnosed_case


def test_demo_home_truthfully_separates_live_and_concept_capabilities(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        before = client.get("/api/v1/cases/00000000-0000-4000-8000-000000000001")
        page = client.get("/demo")
        styles = client.get("/demo/assets/styles.css")
        script = client.get("/demo/assets/app.js")
        after = client.get("/api/v1/cases/00000000-0000-4000-8000-000000000001")

    assert before.status_code == after.status_code == 404
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert '<html lang="zh-CN">' in page.text
    assert '<meta name="viewport"' in page.text
    assert 'href="#main-content"' in page.text
    assert 'href="/demo/assets/styles.css?v=task6"' in page.text
    assert 'src="/demo/assets/app.js?v=task6"' in page.text
    assert page.text.count("<h1") == 1
    assert "LIVE" in page.text
    assert "SYNTHETIC" in page.text
    assert page.text.count("CONCEPT PREVIEW") == 4
    assert "不执行任何资金或生产动作" in page.text
    assert "未来产品设想，当前不会调用后端或生成结论" in page.text
    assert "<form" not in page.text
    assert "onclick=" not in page.text
    assert styles.status_code == 200
    assert "focus-visible" in styles.text
    assert "prefers-reduced-motion" in styles.text
    assert script.status_code == 200
    assert 'if (document.body.dataset.page === "case") loadCase()' in script.text
    assert 'method: "POST"' not in script.text
    assert "innerHTML" not in script.text


def test_demo_case_shell_is_read_only_accessible_and_fetches_only_safe_detail(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, _ = _diagnosed_case(client)
        page = client.get(f"/demo/cases/{case_id}")
        styles = client.get("/demo/assets/styles.css")
        script = client.get("/demo/assets/app.js")

    assert page.status_code == 200
    assert '<html lang="zh-CN">' in page.text
    assert page.text.count("<h1") == 1
    assert 'href="#case-main"' in page.text
    assert 'href="/demo/assets/styles.css?v=task6"' in page.text
    assert 'src="/demo/assets/app.js?v=task6"' in page.text
    assert 'id="case-status"' in page.text
    assert 'id="readiness"' in page.text
    assert 'id="evidence-ledger"' in page.text
    assert 'id="diagnosis"' in page.text
    assert 'id="responsibility"' in page.text
    assert 'id="confirmation"' in page.text
    assert 'id="audit-timeline"' in page.text
    assert "SYNTHETIC CASE" in page.text
    assert "未执行支付、退款、风控放行、资金移动或生产配置变更" in page.text
    assert "<form" not in page.text
    assert "<button" not in page.text
    assert 'method="post"' not in page.text.lower()
    assert "/api/v1/demo/cases/" in script.text
    assert 'method: "POST"' not in script.text
    assert "innerHTML" not in script.text
    assert ".textContent" in script.text
    assert ".cockpit-main { padding-top: 24px; overflow-wrap: anywhere; }" in styles.text
    for forbidden in (
        "source_ref",
        "content_hash",
        "request_id",
        "trace_id",
        "actor_hash",
        "approval_id",
    ):
        assert forbidden not in script.text
