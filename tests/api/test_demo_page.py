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
    assert "Oceanpayment · 拒付管理" in body
    assert "/api/v1/chargeback" in body  # the page drives the real API
    assert "人工确认并模拟提交" in body  # the safety boundary remains in the workflow


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
    assert "Oceanpayment · 拒付管理" in followed.text


def test_demo_keeps_technical_endpoints_out_of_customer_navigation(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
        assert client.get("/docs").status_code == 200
        assert client.get("/health").status_code == 200
    assert 'href="/docs"' not in body
    assert 'href="/health"' not in body


def test_demo_has_partial_scenarios_missing_evidence_and_safety_panel(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert "选择一个常见场景" in body  # one-click scenario picker
    assert "载入示例材料" in body
    assert "材料尚未齐全" in body and "仍缺" in body
    assert "补齐缺失材料" in body
    assert "敏感信息检查" in body and "/safety/scan" in body  # visible PII guardrail
    assert "Visa 13.1" in body and "Visa 10.4" in body and "Mastercard 4853" in body
    assert "未收到货" in body and "非本人交易" in body and "商品不符" in body
    assert 'available:["transaction.receipt","fulfillment.tracking"]' in body
    assert 'available:["transaction.receipt","product.description"]' in body
    assert "规则证据就绪度" in body
    assert "预计胜诉概率" not in body


def test_demo_uses_oceanpayment_console_language_without_ai_jargon(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert "Oceanpayment" in body
    assert "--accent:#02983b" in body
    assert "拒付案件" in body and "交易预警" in body and "规则与运营" in body
    assert "已有 1 项 · 仍缺 5 项" in body
    assert "当前商户" in body and "OceanStore" in body
    assert "演示环境" not in body and "演示数据" not in body
    assert 'id="loc-zh"' not in body and 'id="loc-en"' not in body
    assert "智能体轨迹" not in body
    assert "确定性内核" not in body
    assert "toggleTheme" not in body
