import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.application.demo_query import (
    DemoConfirmationRecord,
    DemoConfirmationState,
    DemoQuery,
)
from oceanpilot.application.errors import DatabaseUnavailable
from oceanpilot.application.feishu_models import FeishuApprovalRecord
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.domain.enums import CaseStatus
from oceanpilot.main import create_app


def _diagnosed_case(client: TestClient) -> tuple[str, dict[str, object]]:
    created = client.post(
        "/api/v1/cases",
        json={
            "case_type": "PAYMENT_INCIDENT",
            "summary": "Synthetic 3DS callback incident",
            "merchant_ref": "merchant_demo_cockpit",
            "synthetic": True,
        },
    )
    assert created.status_code == 201
    case_id = created.json()["case"]["case_id"]
    facts = (
        ("transaction.reference", "txn_demo_cockpit"),
        ("transaction.occurred_at", "2026-08-05T04:00:00Z"),
        ("context.environment", "PROD"),
        ("symptom.status", "PENDING"),
        ("authentication.status", "REQUIRED"),
        ("callback.delivery_status", "NOT_RECEIVED"),
        ("integration.type", "API"),
    )
    for index, (code, value) in enumerate(facts, start=1):
        added = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={
                "evidence_id": f"00000000-0000-4000-8000-{index:012d}",
                "evidence_code": code,
                "availability": "AVAILABLE",
                "typed_value": value,
                "source_ref": "synthetic:demo-cockpit:private-ref",
            },
        )
        assert added.status_code == 201
    diagnosed = client.post(f"/api/v1/cases/{case_id}/diagnose")
    assert diagnosed.status_code == 201
    return case_id, diagnosed.json()


def test_demo_case_api_is_a_safe_projection_of_persisted_case_and_audit(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, diagnosed = _diagnosed_case(client)
        public_case = client.get(f"/api/v1/cases/{case_id}")
        cockpit = client.get(f"/api/v1/demo/cases/{case_id}")

    assert public_case.status_code == cockpit.status_code == 200
    body = cockpit.json()
    persisted = public_case.json()
    assert body["synthetic"] is True
    assert body["read_only"] is True
    assert body["data_consistency"] == "READ_ONLY_BEST_EFFORT"
    assert body["case"]["case_id"] == persisted["case"]["case_id"]
    assert body["case"]["status"] == persisted["case"]["status"] == "HUMAN_REVIEW"
    assert body["case"]["case_revision"] == persisted["case"]["case_revision"]
    assert body["case"]["evidence_revision"] == persisted["case"]["evidence_revision"]
    assert body["readiness"]["ready"] is True
    assert len(body["evidence"]) == len(persisted["evidence"]) == 7
    assert {item["active_state"] for item in body["evidence"]} == {"SELECTED"}
    assert body["diagnosis"]["diagnosis_id"] == diagnosed["diagnosis"]["diagnosis_id"]
    hypothesis = body["diagnosis"]["hypotheses"][0]
    assert hypothesis["rule_id"] == "THREEDS_INCOMPLETE_V1"
    assert hypothesis["confidence_score"] == "0.87"
    assert {citation["evidence_id"] for citation in hypothesis["citations"]} <= {
        item["evidence_id"] for item in body["evidence"]
    }
    assert body["diagnosis"]["routing"]["responsible_team"] == "TECHNICAL_SUPPORT"
    assert body["confirmation"] == {
        "state": "UNAVAILABLE",
        "result": None,
        "occurred_at": None,
    }
    assert body["audit_truncated"] is False
    assert body["timeline"][0]["event_type"] == "CASE_CREATED"
    assert body["timeline"][-1]["event_type"] == "STATE_TRANSITIONED"
    serialized = cockpit.text
    for forbidden in (
        "source_ref",
        "content_hash",
        "request_id",
        "trace_id",
        "sanitized_metadata",
        "actor_hash",
        "approval_id",
        "private-ref",
    ):
        assert forbidden not in serialized


def test_demo_case_api_uses_safe_problem_for_unknown_case(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))
    case_id = "00000000-0000-4000-8000-000000008888"

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/demo/cases/{case_id}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "CASE_NOT_FOUND"


class _ConfirmationReader:
    def __init__(self, record=None, error=None) -> None:
        self.record = record
        self.error = error
        self.calls = []

    def find_confirmation(self, *, case_id, diagnosis_id):
        self.calls.append((case_id, diagnosis_id))
        if self.error is not None:
            raise self.error
        return self.record


def test_demo_query_distinguishes_awaiting_confirmed_and_unavailable(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, diagnosed = _diagnosed_case(client)

    core_store = app.state.store_factory
    diagnosis_id = diagnosed["diagnosis"]["diagnosis_id"]
    awaiting_reader = _ConfirmationReader()
    awaiting = DemoQuery(core_store, awaiting_reader).get_case_detail(case_id)
    confirmed_at = datetime.now(UTC) - timedelta(seconds=1)
    confirmed_reader = _ConfirmationReader(
        DemoConfirmationRecord(
            result="CONFIRMED",
            occurred_at=confirmed_at,
            synthetic=True,
        )
    )
    confirmed = DemoQuery(core_store, confirmed_reader).get_case_detail(case_id)
    unavailable = DemoQuery(
        core_store,
        _ConfirmationReader(error=DatabaseUnavailable()),
    ).get_case_detail(case_id)

    assert awaiting.confirmation.state == "AWAITING_CONFIRMATION"
    assert awaiting_reader.calls == [(case_id, diagnosis_id)]
    assert confirmed.confirmation.model_dump(mode="json") == {
        "state": "CONFIRMED",
        "result": "CONFIRMED",
        "occurred_at": confirmed_at.isoformat().replace("+00:00", "Z"),
    }
    assert confirmed_reader.calls == [(case_id, diagnosis_id)]
    assert unavailable.confirmation.state == "UNAVAILABLE"


def test_demo_case_api_reads_persisted_confirmation_without_identity_leakage(tmp_path):
    feishu = FeishuSettings(
        app_id="app-demo",
        app_secret="secret-demo",
        verification_token="token-demo",
        encrypt_key="key-demo",
        callback_db_path=tmp_path / "feishu.db",
    )
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, diagnosed = _diagnosed_case(client)
        diagnosis_id = diagnosed["diagnosis"]["diagnosis_id"]
        callback_store = FeishuCallbackStoreFactory(feishu.callback_db_path)
        with callback_store.session() as store:
            store.claim_confirmation_action(
                "action-private",
                payload_hash="1" * 64,
                claim_token="claim-private",
                now="2026-08-12T03:59:00+00:00",
                lease_expires_at="2026-08-12T04:01:00+00:00",
            )
        callback_store.record_confirmation(
            FeishuApprovalRecord(
                approval_id="approval-private",
                action_id="action-private",
                claim_token="claim-private",
                case_id=case_id,
                diagnosis_id=diagnosis_id,
                actor_hash=hashlib.sha256(b"actor-private").hexdigest(),
                request_id="00000000-0000-4000-8000-000000001111",
                trace_id="00000000-0000-4000-8000-000000002222",
                occurred_at=datetime(2026, 8, 12, 4, tzinfo=UTC),
                synthetic=True,
            )
        )
        response = client.get(f"/api/v1/demo/cases/{case_id}")

    assert response.status_code == 200
    assert response.json()["confirmation"] == {
        "state": "CONFIRMED",
        "result": "CONFIRMED",
        "occurred_at": "2026-08-12T04:00:00Z",
    }
    for forbidden in (
        "approval-private",
        "action-private",
        hashlib.sha256(b"actor-private").hexdigest(),
        "00000000-0000-4000-8000-000000001111",
        "00000000-0000-4000-8000-000000002222",
        feishu.app_secret,
        feishu.verification_token,
    ):
        assert forbidden not in response.text


def test_demo_query_skips_confirmation_reader_without_current_diagnosis(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/v1/cases",
            json={
                "case_type": "PAYMENT_INCIDENT",
                "summary": "Synthetic undiagnosed incident",
                "merchant_ref": "merchant_demo_undiagnosed",
                "synthetic": True,
            },
        )

    reader = _ConfirmationReader()
    detail = DemoQuery(app.state.store_factory, reader).get_case_detail(
        created.json()["case"]["case_id"]
    )

    assert detail.confirmation.state == "NOT_APPLICABLE"
    assert reader.calls == []


def test_demo_case_api_distinguishes_awaiting_confirmation_from_unavailable(tmp_path):
    feishu = FeishuSettings(
        app_id="app-demo",
        app_secret="secret-demo",
        verification_token="token-demo",
        encrypt_key="key-demo",
        callback_db_path=tmp_path / "feishu.db",
    )
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, _ = _diagnosed_case(client)
        awaiting = client.get(f"/api/v1/demo/cases/{case_id}")
        feishu.callback_db_path.write_bytes(b"not a sqlite database")
        unavailable = client.get(f"/api/v1/demo/cases/{case_id}")

    assert awaiting.status_code == unavailable.status_code == 200
    assert awaiting.json()["confirmation"]["state"] == "AWAITING_CONFIRMATION"
    assert unavailable.json()["confirmation"] == {
        "state": "UNAVAILABLE",
        "result": None,
        "occurred_at": None,
    }


class _CoreStore:
    def __init__(self, view, audit_events, truncated) -> None:
        self.result = view, audit_events, truncated

    def get_case_history(self, case_id, *, limit=200):
        del case_id, limit
        return self.result


def test_demo_query_skips_confirmation_reader_when_review_is_not_required(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, _ = _diagnosed_case(client)

    view, audit_events, truncated = app.state.store_factory.get_case_history(case_id)
    assert view is not None and view.current_diagnosis is not None
    snapshot = view.current_diagnosis
    assert snapshot.routing_decision is not None
    snapshot = snapshot.model_copy(
        update={
            "requires_human": False,
            "review_reasons": frozenset(),
            "routing_decision": snapshot.routing_decision.model_copy(
                update={"requires_human": False, "review_reasons": frozenset()}
            ),
        }
    )
    view = view.model_copy(
        update={
            "case": view.case.model_copy(update={"status": CaseStatus.DIAGNOSED}),
            "current_diagnosis": snapshot,
        }
    )
    reader = _ConfirmationReader()

    detail = DemoQuery(_CoreStore(view, audit_events, truncated), reader).get_case_detail(case_id)

    assert detail.confirmation.state == "NOT_REQUIRED"
    assert reader.calls == []


def test_demo_response_models_do_not_coerce_untrusted_values():
    with pytest.raises(ValidationError):
        DemoConfirmationRecord(
            result="CONFIRMED",
            occurred_at="2026-08-12T04:00:00Z",
            synthetic=True,
        )
    with pytest.raises(ValidationError):
        DemoConfirmationRecord(
            result=DemoConfirmationState.CONFIRMED,
            occurred_at=datetime(2026, 8, 12, 4, tzinfo=UTC),
            synthetic=1,
        )


def test_demo_confirmation_rejects_malformed_legacy_synthetic_flag(tmp_path):
    callback_store = FeishuCallbackStoreFactory(tmp_path / "feishu.db")
    with callback_store.session() as store:
        store._connection.execute("PRAGMA ignore_check_constraints = ON")
        store._connection.execute(
            """
            INSERT INTO feishu_approval_audits (
                approval_id, action_id, case_id, diagnosis_id, actor_id,
                action_kind, result, request_id, trace_id, occurred_at, synthetic
            ) VALUES (?, ?, ?, ?, ?, 'CONFIRM_REVIEW', 'CONFIRMED', ?, ?, ?, 2)
            """,
            (
                "approval-malformed",
                "action-malformed",
                "00000000-0000-4000-8000-000000003333",
                "00000000-0000-4000-8000-000000004444",
                hashlib.sha256(b"actor-malformed").hexdigest(),
                "00000000-0000-4000-8000-000000005555",
                "00000000-0000-4000-8000-000000006666",
                "2026-08-12T04:00:00+00:00",
            ),
        )

    with pytest.raises(DatabaseUnavailable):
        callback_store.find_confirmation(
            case_id="00000000-0000-4000-8000-000000003333",
            diagnosis_id="00000000-0000-4000-8000-000000004444",
        )
