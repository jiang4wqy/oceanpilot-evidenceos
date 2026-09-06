"""Browsing stored cases must not run the model or count a new assessment."""

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.config import Settings
from oceanpilot.domain.chargeback import (
    CardNetwork,
    ChargebackEvidenceCode,
    DisputeReasonCode,
    required_evidence_for,
)
from oceanpilot.main import create_app


@pytest.mark.parametrize("phase", ["empty", "proposed", "incomplete", "complete", "finalized"])
def test_case_detail_list_overview_and_package_are_model_free_reads(tmp_path, phase):
    model = ScriptedModelProvider(default_text="synthetic model explanation")
    app = create_app(Settings(db_path=tmp_path / "api.db"), chargeback_model=model)
    with TestClient(app) as client:
        store = app.state.chargeback_store
        case_id = store.create()
        state = store.load(case_id)
        if phase != "empty":
            state.reason_code = DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
            state.reason_confirmed = phase != "proposed"
            if phase == "complete":
                state.collected = set(required_evidence_for(state.reason_code))
            elif phase != "proposed":
                state.collected = {ChargebackEvidenceCode.TRANSACTION_RECEIPT}
            state.collection_finalized = phase == "finalized"
            store.save(case_id, state)
            store.set_card_network(case_id, CardNetwork.VISA, state.revision)

        before = store.load(case_id)
        before_audit = store.audit_trail(case_id)
        before_metrics = app.state.chargeback_metrics.snapshot()
        before_calls = len(model.requests)
        first = None
        for _ in range(2):
            detail = client.get(f"/api/v1/chargeback/cases/{case_id}")
            listing = client.get("/api/v1/chargeback/cases")
            overview = client.get("/api/v1/admin/overview")
            package = client.get(f"/api/v1/chargeback/cases/{case_id}/package")
            assert detail.status_code == listing.status_code == overview.status_code == 200
            body = detail.json()
            assert listing.json() == [body]
            assert overview.json()["cases"][0]["phase"] == body["phase"]
            assert overview.json()["cases"][0]["missing_count"] == len(body["missing"] or [])
            assert package.status_code == (404 if phase == "empty" else 200)
            if phase != "empty":
                assert package.json()["cover_note_source"] == "FALLBACK"
            assert body["revision"] == before.revision
            if first is not None:
                assert body == first
            first = body

        assert len(model.requests) == before_calls
        assert store.load(case_id) == before
        assert store.audit_trail(case_id) == before_audit
        assert app.state.chargeback_metrics.snapshot() == before_metrics


def test_explicit_case_commands_still_use_the_model_and_record_assessment(tmp_path):
    model = ScriptedModelProvider(default_text="synthetic explanation")
    app = create_app(Settings(db_path=tmp_path / "api.db"), chargeback_model=model)
    with TestClient(app) as client:
        created = client.post("/api/v1/chargeback/cases", json={"description": "没收到货，要拒付"})
        assert created.status_code == 201
        assert model.requests
        case_id = created.json()["case_id"]
        before_calls = len(model.requests)
        finalized = client.post(f"/api/v1/chargeback/cases/{case_id}/finalize")
        assert finalized.status_code == 200
        assert finalized.json()["phase"] == "ASSESSED"
        assert len(model.requests) > before_calls
        assert app.state.chargeback_metrics.snapshot()["assessments_total"] == 1
