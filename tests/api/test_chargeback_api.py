import sqlite3

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
    assert body["next_evidence_label"] in body["missing_labels"]
    assert len(body["missing_labels"]) == len(body["missing"])
    assert all("." not in label for label in body["missing_labels"])


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


def test_list_cases_returns_only_persisted_cases_and_each_detail_resolves(tmp_path):
    with _client(tmp_path) as client:
        first = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()
        second = client.post(
            "/api/v1/chargeback/cases", json={"description": "被重复扣款了"}
        ).json()

        listed = client.get("/api/v1/chargeback/cases")

        assert listed.status_code == 200
        bodies = listed.json()
        assert [item["case_id"] for item in bodies] == [second["case_id"], first["case_id"]]
        for item in bodies:
            detail = client.get(f"/api/v1/chargeback/cases/{item['case_id']}")
            assert detail.status_code == 200
            assert detail.json()["case_id"] == item["case_id"]


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


def test_withdraw_latest_evidence_reopens_collection_and_audits(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()
        case_id = body["case_id"]
        first = body["next_evidence"]
        body = client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence",
            json={"evidence_code": first},
        ).json()
        second = body["next_evidence"]
        client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence",
            json={"evidence_code": second},
        )
        client.post(f"/api/v1/chargeback/cases/{case_id}/finalize")

        response = client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence/withdraw-latest",
            json={"evidence_code": second},
        )
        audit = client.get(f"/api/v1/chargeback/cases/{case_id}/audit").json()

    assert response.status_code == 200
    withdrawn = response.json()
    assert withdrawn["phase"] == "NEED_EVIDENCE"
    assert withdrawn["collection_finalized"] is False
    assert second not in withdrawn["collected"]
    assert withdrawn["next_evidence"] == second
    assert audit["events"][-1]["event_type"] == "EVIDENCE_WITHDRAWN"
    assert audit["events"][-1]["detail"] == second


def test_duplicate_withdrawal_returns_concurrent_conflict(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()
        case_id = body["case_id"]
        first = body["next_evidence"]
        body = client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence",
            json={"evidence_code": first},
        ).json()
        second = body["next_evidence"]
        client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence",
            json={"evidence_code": second},
        )
        endpoint = f"/api/v1/chargeback/cases/{case_id}/evidence/withdraw-latest"
        assert client.post(endpoint, json={"evidence_code": second}).status_code == 200
        duplicate = client.post(endpoint, json={"evidence_code": second})

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CONCURRENT_CASE_WRITE"


def test_withdraw_without_evidence_returns_named_conflict(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()["case_id"]
        response = client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence/withdraw-latest",
            json={"evidence_code": "transaction.receipt"},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "NO_EVIDENCE_TO_WITHDRAW"


def test_withdraw_unknown_case_returns_safe_404(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chargeback/cases/does-not-exist/evidence/withdraw-latest",
            json={"evidence_code": "transaction.receipt"},
        )
    assert response.status_code == 404
    assert response.json()["code"] == "CASE_NOT_FOUND"


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
    assert a["evidence_readiness"] == a["win_likelihood"]
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


def _ready_case(client):
    """Open a PRODUCT_NOT_RECEIVED case and submit its full checklist."""
    from oceanpilot.domain.chargeback import DisputeReasonCode, required_evidence_for

    body = client.post("/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}).json()
    case_id = body["case_id"]
    for code in required_evidence_for(DisputeReasonCode.PRODUCT_NOT_RECEIVED):
        client.post(
            f"/api/v1/chargeback/cases/{case_id}/evidence", json={"evidence_code": code.value}
        )
    return case_id


def test_package_endpoint_returns_labeled_representment(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        pkg = client.get(f"/api/v1/chargeback/cases/{case_id}/package").json()
    assert pkg["reason_label"]
    assert pkg["ready_to_submit"] is True
    assert pkg["ordered_evidence"]
    first = pkg["ordered_evidence"][0]
    assert set(first) == {"code", "label"}
    assert first["label"] and "." in first["code"]


def test_package_endpoint_exposes_visa_rule_provenance(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        pkg = client.get(
            f"/api/v1/chargeback/cases/{case_id}/package",
            params={"card_network": "VISA"},
        ).json()
    assert pkg["scheme_reason_code"] == "13.1"
    assert pkg["rule_version"] == "June 2024"
    assert pkg["source_document"] == "Dispute Management Guidelines for Visa Merchants"
    assert pkg["required_assertions"]
    assert "不是 Visa 官方申诉期限" in pkg["rule_limitation"]
    assert pkg["rule_version_id"] == "visa-13-1-demo-v1"
    assert pkg["verification_status"] == "UNVERIFIED_SUMMARY"
    assert pkg["submission_window_basis"] == "INTERNAL_DEMO"


def test_rules_catalog_exposes_nine_curated_summaries(tmp_path):
    with _client(tmp_path) as client:
        response = client.get("/api/v1/chargeback/rules")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 9
    assert body["demo_mapped"] == 3
    assert body["scheme_count"] == 3
    assert body["source_document_count"] == 3
    assert "生产使用前" in body["disclaimer"]
    assert len(body["items"]) == 9
    assert all(item["verification_status"] == "UNVERIFIED_SUMMARY" for item in body["items"])


def test_rules_catalog_filters_and_searches(tmp_path):
    with _client(tmp_path) as client:
        visa = client.get("/api/v1/chargeback/rules", params={"scheme": "VISA"}).json()
        searched = client.get("/api/v1/chargeback/rules", params={"q": "10.4"}).json()
    assert visa["total"] == 6
    assert all(item["scheme"] == "VISA" for item in visa["items"])
    assert searched["total"] == 1
    assert searched["items"][0]["rule_version_id"] == "visa-10-4-demo-v1"


def test_rule_detail_and_package_reference_the_same_version(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        package = client.get(
            f"/api/v1/chargeback/cases/{case_id}/package",
            params={"card_network": "VISA"},
        ).json()
        detail = client.get(f"/api/v1/chargeback/rules/{package['rule_version_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["rule_version_id"] == package["rule_version_id"]
    assert body["scheme_reason_code"] == package["scheme_reason_code"]
    assert body["document"]["source_url"].startswith("https://")
    assert body["assertions"]
    assert body["evidence"]
    assert "生产使用前" in body["disclaimer"]


def test_rule_reference_resolves_exact_package_and_detail_version(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        reference = client.get(
            f"/api/v1/chargeback/cases/{case_id}/rule-reference",
            params={"card_network": "VISA"},
        )
        package = client.get(
            f"/api/v1/chargeback/cases/{case_id}/package",
            params={"card_network": "VISA"},
        ).json()

        assert reference.status_code == 200
        body = reference.json()
        assert body["match_status"] == "EXACT_MATCH"
        assert body["rule_reference"]["rule_version_id"] == package["rule_version_id"]
        assert body["rule_reference"]["rule_version_id"] == "visa-13-1-demo-v1"
        detail = client.get(f"/api/v1/chargeback/rules/{body['rule_reference']['rule_version_id']}")

    assert detail.status_code == 200
    assert detail.json()["rule_version_id"] == body["rule_reference"]["rule_version_id"]
    assert detail.json()["source_section"] == body["rule_reference"]["source_section"]


def test_rule_reference_requires_explicit_card_network(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        responses = [
            client.get(f"/api/v1/chargeback/cases/{case_id}/rule-reference"),
            client.get(
                f"/api/v1/chargeback/cases/{case_id}/rule-reference",
                params={"card_network": ""},
            ),
            client.get(
                f"/api/v1/chargeback/cases/{case_id}/rule-reference",
                params={"card_network": "   "},
            ),
        ]
    assert all(response.status_code == 422 for response in responses)
    assert all(response.json()["code"] == "INVALID_REQUEST" for response in responses)


def test_rule_reference_rejects_unconfirmed_reason(tmp_path):
    with _client(tmp_path) as client:
        case_id = client.post(
            "/api/v1/chargeback/cases", json={"description": "这是一段用于测试的中性内容"}
        ).json()["case_id"]
        response = client.get(
            f"/api/v1/chargeback/cases/{case_id}/rule-reference",
            params={"card_network": "VISA"},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "HTTP_ERROR"


def test_rule_reference_does_not_guess_across_card_networks(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        response = client.get(
            f"/api/v1/chargeback/cases/{case_id}/rule-reference",
            params={"card_network": "MASTERCARD"},
        )
    assert response.status_code == 200
    assert response.json()["match_status"] == "NO_EXACT_MAPPING"
    assert response.json()["rule_reference"] is None
    assert "visa-13-1-demo-v1" not in response.text


def test_rule_reference_returns_503_when_rule_database_fails(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        connection = sqlite3.connect(tmp_path / "oceanpilot-rules.db")
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DROP TABLE rule_requirements")
        connection.close()

        response = client.get(
            f"/api/v1/chargeback/cases/{case_id}/rule-reference",
            params={"card_network": "VISA"},
        )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"


def test_unknown_rule_detail_returns_safe_404(tmp_path):
    with _client(tmp_path) as client:
        response = client.get("/api/v1/chargeback/rules/not-a-rule")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "HTTP_ERROR"


def test_package_returns_503_when_rule_database_fails(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        connection = sqlite3.connect(tmp_path / "oceanpilot-rules.db")
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DROP TABLE rule_requirements")
        connection.close()

        response = client.get(
            f"/api/v1/chargeback/cases/{case_id}/package",
            params={"card_network": "VISA"},
        )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"


def test_appeal_without_approval_is_blocked_and_never_submits(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        resp = client.post(f"/api/v1/chargeback/cases/{case_id}/appeal", json={})
    body = resp.json()
    assert resp.status_code == 200
    assert body["submitted"] is False
    assert body["blocked_reason"] == "NOT_APPROVED"
    assert body["draft"]
    assert body["synthetic"] is True
    assert body["connector_kind"] == "IN_PROCESS_MOCK"


def test_appeal_with_human_approval_submits_once(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        body = client.post(
            f"/api/v1/chargeback/cases/{case_id}/appeal",
            json={"human_approved": True, "actor_id": "ou_reviewer"},
        ).json()
    assert body["submitted"] is True
    assert body["blocked_reason"] is None
    assert body["submission_id"]
    assert body["synthetic"] is True
    assert body["connector_kind"] == "IN_PROCESS_MOCK"


def test_appeal_approval_requires_actor(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        resp = client.post(
            f"/api/v1/chargeback/cases/{case_id}/appeal", json={"human_approved": True}
        )
    assert resp.status_code == 422


def test_package_unknown_case_is_safe_404(tmp_path):
    with _client(tmp_path) as client:
        resp = client.get("/api/v1/chargeback/cases/nope/package")
    assert resp.status_code == 404


def test_prevention_clean_signals_are_low_risk(tmp_path):
    with _client(tmp_path) as client:
        body = client.post("/api/v1/chargeback/prevention/assess", json={}).json()
    assert body["risk_level"] == "LOW"
    assert body["recommend_manual_review"] is False
    assert body["factors"] == []
    assert body["advice"]


def test_prevention_high_risk_signals_recommend_review_and_evidence(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/prevention/assess",
            json={
                "three_ds_authenticated": False,
                "avs_match": False,
                "cvv_match": False,
                "amount": "5000",
            },
        ).json()
    assert body["risk_level"] == "HIGH"
    assert body["recommend_manual_review"] is True
    assert body["factors"]
    assert body["recommended_evidence"]
    first = body["recommended_evidence"][0]
    assert set(first) == {"code", "label"}


def test_prevention_rejects_negative_amount(tmp_path):
    with _client(tmp_path) as client:
        resp = client.post("/api/v1/chargeback/prevention/assess", json={"amount": "-1"})
    assert resp.status_code == 422


def test_metrics_endpoint_tracks_decisions(tmp_path):
    with _client(tmp_path) as client:
        client.post(
            "/api/v1/chargeback/prevention/assess",
            json={"three_ds_authenticated": False, "avs_match": False, "amount": "5000"},
        )
        case_id = _ready_case(client)  # reaches ASSESSED on the last evidence post
        client.post(f"/api/v1/chargeback/cases/{case_id}/appeal", json={})  # blocked
        counts = client.get("/api/v1/chargeback/metrics").json()["counts"]
    assert counts.get("assessments_total", 0) >= 1
    assert any(k.startswith("requires_human_") for k in counts)
    assert any(k.startswith("explanation_source_") for k in counts)
    assert counts.get("appeal_blocked", 0) >= 1
    assert any(k.startswith("prevention_risk_") for k in counts)


def test_request_logging_emits_structured_line(tmp_path, caplog):
    import logging

    with (
        _client(tmp_path) as client,
        caplog.at_level(logging.INFO, logger="oceanpilot.request"),
    ):
        client.get("/health")
    messages = [r.getMessage() for r in caplog.records]
    assert any("path=/health" in m and "status=200" in m and "trace_id=" in m for m in messages)


def test_catalog_endpoint_localizes(tmp_path):
    with _client(tmp_path) as client:
        zh = client.get("/api/v1/chargeback/catalog").json()
        en = client.get("/api/v1/chargeback/catalog?locale=en").json()
    assert zh["locale"] == "zh" and en["locale"] == "en"
    assert len(zh["evidence"]) == 15 and len(zh["reasons"]) == 7
    zh_pod = next(
        e["label"] for e in zh["evidence"] if e["code"] == "fulfillment.proof_of_delivery"
    )
    en_pod = next(
        e["label"] for e in en["evidence"] if e["code"] == "fulfillment.proof_of_delivery"
    )
    assert zh_pod != en_pod
    assert en_pod.isascii()


def test_unknown_locale_falls_back_to_chinese(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/api/v1/chargeback/catalog?locale=fr").json()
    assert body["locale"] == "zh"


def test_package_can_be_localized(tmp_path):
    with _client(tmp_path) as client:
        case_id = _ready_case(client)
        en = client.get(f"/api/v1/chargeback/cases/{case_id}/package?locale=en").json()
    assert en["reason_label"].isascii()
    assert all(item["label"].isascii() for item in en["ordered_evidence"])


def test_agent_trace_is_present_across_the_flow(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"}
        ).json()
        # NEED_EVIDENCE step: intake + evidence agents visible.
        agents = {a["agent"] for a in body["agent_trace"]}
        assert "IntakeAgent" in agents
        assert "EvidenceAgent" in agents
        case_id = body["case_id"]
        for _ in range(20):
            if body["phase"] == "ASSESSED":
                break
            body = client.post(
                f"/api/v1/chargeback/cases/{case_id}/evidence",
                json={"evidence_code": body["next_evidence"]},
            ).json()
    trace = body["agent_trace"]
    assert any(a["agent"] == "AssessAgent" for a in trace)
    assess = next(a for a in trace if a["agent"] == "AssessAgent")
    assert assess["action"].startswith("材料就绪度 ")
    assert "胜诉" not in assess["action"]
    assert assess["source"] in ("MODEL", "FALLBACK")


def test_agent_trace_shows_human_gate_when_reason_unconfident(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/cases", json={"description": "这是一段用于测试的中性内容"}
        ).json()
    assert body["phase"] == "REASON_PROPOSED"
    assert any(a["agent"] == "HumanGate" for a in body["agent_trace"])


def test_safety_scan_blocks_card_number_without_echo(tmp_path):
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/v1/chargeback/safety/scan",
            json={"text": "请退款到卡号 4111 1111 1111 1111"},
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body["accepted"] is False
    assert body["detail"]
    assert "4111" not in body["detail"]  # never echoes the input


def test_safety_scan_accepts_clean_text(tmp_path):
    with _client(tmp_path) as client:
        body = client.post(
            "/api/v1/chargeback/safety/scan", json={"text": "客户下单后一直没收到货"}
        ).json()
    assert body["accepted"] is True
