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


def test_unconfident_case_requires_confirmation_then_proceeds(tmp_path):
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/chargeback/cases", json={"description": "这是一段用于测试的中性内容"}
        ).json()
        assert created["phase"] == "REASON_PROPOSED"
        assert created["reason_confirmed"] is False
        assert created["question"]
        case_id = created["case_id"]

        confirmed = client.post(f"/api/v1/chargeback/cases/{case_id}/confirm", json={}).json()
    assert confirmed["reason_confirmed"] is True
    assert confirmed["phase"] == "NEED_EVIDENCE"


def test_confirm_can_correct_the_reason(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post(
            "/api/v1/chargeback/cases", json={"description": "这是一段用于测试的中性内容"}
        ).json()["case_id"]
        resp = client.post(
            f"/api/v1/chargeback/cases/{case_id}/confirm",
            json={"reason_code": DisputeReasonCode.FRAUD_CARD_NOT_PRESENT.value},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == DisputeReasonCode.FRAUD_CARD_NOT_PRESENT.value
    assert body["reason_confirmed"] is True


def test_confirm_rejects_unknown_reason(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post(
            "/api/v1/chargeback/cases", json={"description": "这是一段用于测试的中性内容"}
        ).json()["case_id"]
        resp = client.post(
            f"/api/v1/chargeback/cases/{case_id}/confirm",
            json={"reason_code": "NOT_A_REASON"},
        )
    assert resp.status_code == 422


def test_finalize_routes_to_human_review(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()["case_id"]
        body = client.post(f"/api/v1/chargeback/cases/{case_id}/finalize").json()
    assert body["collection_finalized"] is True
    assert body["phase"] == "ASSESSED"
    assert body["assessment"]["requires_human"] is True


def test_response_includes_evidence_window_deadline(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/cases", json={"description": "客户下单后一直没收到货"}
        ).json()
    assert body["deadline"] is not None
    assert body["deadline"]["phase"] == "COLLECTING_EVIDENCE"
    assert body["deadline"]["overdue"] is False
    assert body["deadline"]["days_remaining"] is not None
    assert 0 <= body["deadline"]["days_remaining"] <= 15


def test_response_has_facts_field(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/cases", json={"description": "客户下单后一直没收到货"}
        ).json()
    # Offline model can't extract facts, but the field is wired into the contract.
    assert "facts" in body


def test_assessment_response_exposes_provenance_and_breakdown(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()
        case_id = body["case_id"]
        for _ in range(20):
            if body["phase"] == "ASSESSED":
                break
            body = client.post(
                f"/api/v1/chargeback/cases/{case_id}/evidence",
                json={"evidence_code": body["next_evidence"]},
            ).json()
    a = body["assessment"]
    assert a["explanation_source"] in ("MODEL", "FALLBACK")
    assert a["evidence_breakdown"]
    assert set(a["evidence_breakdown"][0]) == {"code", "label", "weight", "critical", "present"}
    assert all(item["present"] for item in a["evidence_breakdown"])


def test_audit_endpoint_returns_ordered_trail(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post(
            "/api/v1/chargeback/cases", json={"description": "客户下单后一直没收到货"}
        ).json()["case_id"]
        client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence",
            json={"evidence_code": "transaction.receipt"},
        )
        audit = client.get(f"/api/v1/chargeback/cases/{case_id}/audit").json()
    assert audit["case_id"] == case_id
    types = [e["event_type"] for e in audit["events"]]
    assert types[0] == "CASE_OPENED"
    assert "REASON_CLASSIFIED" in types
    assert "EVIDENCE_ADDED" in types
    seqs = [e["seq"] for e in audit["events"]]
    assert seqs == sorted(seqs)  # ordered
    assert all(e["occurred_at"] for e in audit["events"])


def test_audit_unknown_case_is_safe_404(tmp_path):
    with _client(tmp_path) as client:
        resp = client.get("/api/v1/chargeback/cases/does-not-exist/audit")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
