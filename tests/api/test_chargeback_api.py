from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.domain.chargeback import DisputeReasonCode, required_evidence_for
from oceanpilot.main import create_app


def _client(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "api.db"))
    return TestClient(app, raise_server_exceptions=False)


def test_create_case_classifies_and_asks_for_evidence(tmp_path):
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/v1/chargeback/cases", json={"description": "客户下单后一直没收到货"}
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["case_id"]
    assert body["reason_code"] == DisputeReasonCode.PRODUCT_NOT_RECEIVED.value
    assert body["phase"] == "NEED_EVIDENCE"
    assert body["next_evidence"] in body["missing"]


def test_full_evidence_flow_reaches_assessment(tmp_path):
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()
        case_id = created["case_id"]
        body = created
        for _ in range(20):
            if body["phase"] == "ASSESSED":
                break
            code = body["next_evidence"]
            body = client.post(
                f"/api/v1/chargeback/cases/{case_id}/evidence",
                json={"evidence_code": code},
            ).json()
        assert body["phase"] == "ASSESSED"
        assert body["assessment"]["win_likelihood"] == "1.0000"
        assert set(body["collected"]) == {c.value for c in required_evidence_for(reason)}


def test_get_case_returns_current_state(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post(
            "/api/v1/chargeback/cases", json={"description": "被重复扣款了"}
        ).json()["case_id"]
        resp = client.get(f"/api/v1/chargeback/cases/{case_id}")
    assert resp.status_code == 200
    assert resp.json()["case_id"] == case_id
    assert resp.json()["reason_code"] == DisputeReasonCode.DUPLICATE_PROCESSING.value


def test_unknown_case_returns_safe_404(tmp_path):
    with _client(tmp_path) as client:
        resp = client.get("/api/v1/chargeback/cases/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["code"] == "CASE_NOT_FOUND"


def test_invalid_evidence_code_is_rejected(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post("/api/v1/chargeback/cases", json={"description": "没收到货"}).json()[
            "case_id"
        ]
        resp = client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence",
            json={"evidence_code": "not-a-real-code"},
        )
    assert resp.status_code == 422
