from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def _client(tmp_path):
    return TestClient(
        create_app(Settings(db_path=tmp_path / "api.db")),
        raise_server_exceptions=False,
    )


def test_payment_incident_cockpit_is_served_but_not_in_openapi(tmp_path):
    with _client(tmp_path) as client:
        response = client.get("/demo/payment-incident")
        paths = client.get("/openapi.json").json()["paths"]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>OceanPilot · 支付异常协作</title>" in response.text
    assert "支付异常协作" in response.text
    assert "返回拒付处理" in response.text
    assert "确定性诊断" in response.text
    assert "证据就绪度" in response.text
    for mojibake in ("鏀粯", "寮傚父", "鍗忎綔", "璇婃柇", "璇佹嵁"):
        assert mojibake not in response.text
    assert "/demo/payment-incident" not in paths


def test_payment_incident_cockpit_declares_truthful_synthetic_boundary(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo/payment-incident").text

    assert 'href="/demo"' in body
    assert "SYNTHETIC" in body
    assert "仅使用合成数据" in body
    for prohibited_action in (
        "支付",
        "退款",
        "风控放行",
        "资金移动",
        "生产配置变更",
    ):
        assert prohibited_action in body


def test_payment_incident_cockpit_runs_four_scenarios_through_public_api(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo/payment-incident").text

    for scenario in (
        "3ds_callback_incomplete",
        "risk_decline",
        "merchant_configuration_mismatch",
        "psp_configuration_mismatch",
    ):
        assert f'data-scenario="{scenario}"' in body

    assert 'const CASES_API = "/api/v1/cases"' in body
    assert 'case_type: "PAYMENT_INCIDENT"' in body
    assert "synthetic: true" in body
    assert "crypto.randomUUID()" in body
    assert "view.case.readiness" in body
    assert "diagnosis.hypotheses" in body
    assert "diagnosis.routing_decision" in body
    assert "result.audit_reference" in body
    assert "evidence_refs" in body

    for forbidden_runtime_output in (
        "source_reliability",
        "THREEDS_INCOMPLETE_V1",
        "RISK_DECLINE_V1",
        "CONFIG_MISMATCH_MERCHANT_V1",
        "CONFIG_MISMATCH_PSP_V1",
        "TECHNICAL_SUPPORT",
        "PSP_SUPPORT",
        'confidence_score: "0.87"',
        "confidence_score: 0.87",
    ):
        assert forbidden_runtime_output not in body


def test_payment_incident_cockpit_stops_with_a_safe_traceable_error(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo/payment-incident").text

    assert 'response.headers.get("X-Trace-ID")' in body
    assert "problem.code" in body
    assert "response.status" in body
    assert "failedStage" in body
    assert "problem.detail" not in body
    assert "innerHTML" not in body
    assert "button.disabled" in body
