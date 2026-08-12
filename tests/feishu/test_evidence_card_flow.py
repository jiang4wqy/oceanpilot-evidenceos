import hashlib
import json
from pathlib import Path
from time import time
from uuid import uuid4

from fastapi.testclient import TestClient

from oceanpilot.adapters.feishu.client import FeishuHttpRequest, FeishuHttpResponse
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.main import create_app


def _settings(tmp_path: Path) -> FeishuSettings:
    marker = uuid4().hex
    return FeishuSettings(
        app_id=f"app-{marker}",
        app_secret=f"secret-{marker}",
        verification_token=f"token-{marker}",
        encrypt_key=f"key-{marker}",
        callback_db_path=tmp_path / "feishu.db",
        demo_chat_id="oc_demo_group",
        demo_merchant_ref="merchant_feishu_demo",
    )


def _signed_headers(settings: FeishuSettings, raw_body: bytes) -> dict[str, str]:
    timestamp = str(int(time()))
    nonce = f"nonce-{uuid4().hex}"
    signature = hashlib.sha256(
        f"{timestamp}{nonce}{settings.encrypt_key}".encode() + raw_body
    ).hexdigest()
    return {
        "content-type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def _message_body(settings: FeishuSettings) -> bytes:
    fixture = Path(__file__).with_name("fixtures") / "message_received.json"
    return (
        fixture.read_bytes()
        .replace(b"__VERIFICATION_TOKEN__", settings.verification_token.encode())
        .replace(b"__APP_ID__", settings.app_id.encode())
    )


def _action_body(
    settings: FeishuSettings,
    *,
    event_id: str,
    value: dict[str, object],
) -> bytes:
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "token": settings.verification_token,
            "create_time": str(int(time() * 1000)),
            "event_type": "card.action.trigger",
            "tenant_key": "tenant_demo",
            "app_id": settings.app_id,
        },
        "event": {
            "operator": {"open_id": "ou_synthetic_merchant"},
            "context": {
                "open_message_id": "om_question_001",
                "open_chat_id": settings.demo_chat_id,
            },
            "action": {"tag": "button", "value": value},
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode()


class _Transport:
    def __init__(self) -> None:
        self.requests: list[FeishuHttpRequest] = []

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        self.requests.append(request)
        if request.url.endswith("/tenant_access_token/internal"):
            body = {"code": 0, "tenant_access_token": "synthetic-access-token"}
        else:
            body = {
                "code": 0,
                "data": {"message_id": f"om_outbound_{len(self.requests)}"},
            }
        return FeishuHttpResponse(status_code=200, body=json.dumps(body).encode())


class _FailingCardTransport(_Transport):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_card = False

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        if self.fail_next_card and not request.url.endswith("/tenant_access_token/internal"):
            self.requests.append(request)
            self.fail_next_card = False
            return FeishuHttpResponse(status_code=503, body=b"{}")
        return super().__call__(request)


def _last_card(transport: _Transport) -> dict[str, object]:
    request_body = json.loads(transport.requests[-1].body)
    return json.loads(request_body["content"])


def _button_values(value: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(value, dict):
        if value.get("tag") == "button" and isinstance(value.get("value"), dict):
            found.append(value["value"])
        for child in value.values():
            found.extend(_button_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_button_values(child))
    return found


def test_evidence_action_rejects_caller_controlled_trust_without_side_effects(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        opened = client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected = _button_values(_last_card(transport))[0]
        selected["source_reliability"] = "SYSTEM_OF_RECORD"
        action_body = _action_body(
            feishu,
            event_id="evt_evidence_forbidden_trust_001",
            value=selected,
        )
        rejected = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")

    assert opened.status_code == 200
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "FEISHU_INVALID_CALLBACK"
    assert "SYSTEM_OF_RECORD" not in rejected.text
    assert persisted.json()["case"]["evidence_revision"] == 0
    assert persisted.json()["evidence"] == []


def test_evidence_action_rejects_a_tampered_server_owned_value(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected = _button_values(_last_card(transport))[0]
        selected["typed_value"] = "txn_tampered_accepted"
        action_body = _action_body(
            feishu,
            event_id="evt_tampered_value_001",
            value=selected,
        )
        rejected = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "FEISHU_INVALID_CALLBACK"
    assert "txn_tampered_accepted" not in rejected.text
    assert persisted.json()["case"]["evidence_revision"] == 0
    assert persisted.json()["evidence"] == []


def test_evidence_action_rejects_unavailable_instead_of_the_signed_demo_value(
    tmp_path,
):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected = _button_values(_last_card(transport))[0]
        selected["availability"] = "CONFIRMED_UNAVAILABLE"
        selected["typed_value"] = None
        action_body = _action_body(
            feishu,
            event_id="evt_tampered_availability_001",
            value=selected,
        )
        rejected = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "FEISHU_INVALID_CALLBACK"
    assert persisted.json()["case"]["evidence_revision"] == 0


def test_valid_evidence_action_advances_to_the_next_server_owned_question(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        opened = client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        first_card = _last_card(transport)
        first_values = _button_values(first_card)
        assert first_values
        assert {item["evidence_code"] for item in first_values} == {"transaction.reference"}
        selected = first_values[0]

        action_body = _action_body(
            feishu,
            event_id="evt_evidence_reference_001",
            value=selected,
        )
        submitted = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        next_card = _last_card(transport)
        next_values = _button_values(next_card)
        case_id = selected["case_id"]
        persisted = client.get(f"/api/v1/cases/{case_id}")

    assert opened.status_code == 200
    assert submitted.status_code == 200
    assert submitted.json() == {"ok": True}
    assert persisted.status_code == 200
    body = persisted.json()
    assert body["case"]["case_revision"] == 2
    assert body["case"]["evidence_revision"] == 1
    assert body["case"]["current_diagnosis_id"] is None
    assert body["evidence"][0]["evidence_code"] == "transaction.reference"
    assert body["evidence"][0]["source_reliability"] == "USER_REPORTED"
    assert {item["evidence_code"] for item in next_values} == {"transaction.occurred_at"}


def test_seven_server_owned_answers_trigger_the_real_threeds_diagnosis(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )
    expected_codes = (
        "transaction.reference",
        "transaction.occurred_at",
        "context.environment",
        "symptom.status",
        "authentication.status",
        "callback.delivery_status",
        "integration.type",
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        opened = client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected_case_id = None
        for index, expected_code in enumerate(expected_codes, start=1):
            values = _button_values(_last_card(transport))
            selected = next(
                item
                for item in values
                if item.get("evidence_code") == expected_code
                and item.get("typed_value") != "DECLINED"
            )
            selected_case_id = selected["case_id"]
            action_body = _action_body(
                feishu,
                event_id=f"evt_threeds_step_{index:02d}",
                value=selected,
            )
            submitted = client.post(
                "/api/v1/feishu/card-actions",
                content=action_body,
                headers=_signed_headers(feishu, action_body),
            )
            assert submitted.status_code == 200
            assert submitted.json() == {"ok": True}

        persisted = client.get(f"/api/v1/cases/{selected_case_id}")
        diagnosis_card = _last_card(transport)

    assert opened.status_code == 200
    body = persisted.json()
    assert body["case"]["case_revision"] == 9
    assert body["case"]["evidence_revision"] == 7
    assert body["case"]["status"] == "HUMAN_REVIEW"
    assert {item["evidence_code"] for item in body["evidence"]} == set(expected_codes)
    occurred_at = next(
        item for item in body["evidence"] if item["evidence_code"] == "transaction.occurred_at"
    )
    assert occurred_at["typed_value"] == "2026-08-05T04:00:00Z"
    diagnosis = body["current_diagnosis"]
    assert diagnosis["hypotheses"][0]["rule_id"] == "THREEDS_INCOMPLETE_V1"
    assert diagnosis["hypotheses"][0]["confidence_score"] == "0.87"
    assert diagnosis["routing_decision"]["responsible_team"] == "TECHNICAL_SUPPORT"
    assert diagnosis["routing_decision"]["priority"] == "MEDIUM"
    assert diagnosis["requires_human"] is True
    assert set(diagnosis["review_reasons"]) == {
        "LOW_CONFIDENCE",
        "INSUFFICIENT_SOURCE_QUALITY",
    }
    rendered = json.dumps(diagnosis_card, ensure_ascii=False)
    assert "THREEDS_INCOMPLETE_V1" in rendered
    assert "TECHNICAL_SUPPORT" in rendered
    assert "MEDIUM" in rendered
    assert "0.87" in rendered
    assert "仅限 synthetic 演示" in rendered


def test_declined_status_asks_for_risk_code_before_integration_type(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        for index, expected_code in enumerate(
            (
                "transaction.reference",
                "transaction.occurred_at",
                "context.environment",
                "symptom.status",
            ),
            start=1,
        ):
            values = _button_values(_last_card(transport))
            selected = next(
                item
                for item in values
                if item.get("evidence_code") == expected_code
                and (expected_code != "symptom.status" or item.get("typed_value") == "DECLINED")
            )
            action_body = _action_body(
                feishu,
                event_id=f"evt_risk_step_{index:02d}",
                value=selected,
            )
            response = client.post(
                "/api/v1/feishu/card-actions",
                content=action_body,
                headers=_signed_headers(feishu, action_body),
            )
            assert response.status_code == 200

        risk_values = _button_values(_last_card(transport))

    assert risk_values == [
        {
            "action_kind": "submit_evidence",
            "case_id": selected["case_id"],
            "case_revision": 5,
            "evidence_code": "risk.decision_code",
            "availability": "AVAILABLE",
            "typed_value": "RISK_DECLINE",
        }
    ]


def test_risk_answers_trigger_the_real_risk_decline_diagnosis(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )
    codes = (
        "transaction.reference",
        "transaction.occurred_at",
        "context.environment",
        "symptom.status",
        "risk.decision_code",
        "integration.type",
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected = None
        for index, code in enumerate(codes, start=1):
            selected = next(
                value
                for value in _button_values(_last_card(transport))
                if value.get("evidence_code") == code
                and (code != "symptom.status" or value.get("typed_value") == "DECLINED")
            )
            action_body = _action_body(
                feishu,
                event_id=f"evt_risk_diagnosis_{index:02d}",
                value=selected,
            )
            response = client.post(
                "/api/v1/feishu/card-actions",
                content=action_body,
                headers=_signed_headers(feishu, action_body),
            )
            assert response.status_code == 200

        assert selected is not None
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")
        result_card = json.dumps(_last_card(transport), ensure_ascii=False)

    body = persisted.json()
    diagnosis = body["current_diagnosis"]
    assert body["case"]["case_revision"] == 8
    assert body["case"]["evidence_revision"] == 6
    assert body["case"]["status"] == "HUMAN_REVIEW"
    assert diagnosis["hypotheses"][0]["rule_id"] == "RISK_DECLINE_V1"
    assert diagnosis["hypotheses"][0]["confidence_score"] == "0.87"
    assert diagnosis["routing_decision"]["responsible_team"] == "RISK"
    assert diagnosis["routing_decision"]["priority"] == "HIGH"
    assert set(diagnosis["review_reasons"]) == {
        "INSUFFICIENT_SOURCE_QUALITY",
        "LOW_CONFIDENCE",
        "RISK_DECISION",
    }
    assert "RISK_DECLINE_V1" in result_card
    assert "RISK_DECISION" in result_card


def test_evidence_action_replay_and_new_event_double_click_do_not_duplicate(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected = _button_values(_last_card(transport))[0]
        action_body = _action_body(
            feishu,
            event_id="evt_replayed_action_001",
            value=selected,
        )
        first = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        request_count = len(transport.requests)
        replay = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        second_event_body = _action_body(
            feishu,
            event_id="evt_replayed_action_002",
            value=selected,
        )
        second_event = client.post(
            "/api/v1/feishu/card-actions",
            content=second_event_body,
            headers=_signed_headers(feishu, second_event_body),
        )
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert len(transport.requests) == request_count + 2
    assert second_event.status_code == 200
    body = persisted.json()
    assert body["case"]["case_revision"] == 2
    assert body["case"]["evidence_revision"] == 1
    assert len(body["evidence"]) == 1


def test_evidence_action_id_reused_with_different_payload_is_409(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected = _button_values(_last_card(transport))[0]
        action_body = _action_body(
            feishu,
            event_id="evt_conflicting_action_001",
            value=selected,
        )
        first = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        changed = dict(selected)
        changed["typed_value"] = "txn_changed_001"
        conflict_body = _action_body(
            feishu,
            event_id="evt_conflicting_action_001",
            value=changed,
        )
        conflict = client.post(
            "/api/v1/feishu/card-actions",
            content=conflict_body,
            headers=_signed_headers(feishu, conflict_body),
        )
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "FEISHU_IDEMPOTENCY_CONFLICT"
    body = persisted.json()
    assert body["case"]["evidence_revision"] == 1
    assert len(body["evidence"]) == 1


def test_retry_after_outbound_failure_recovers_without_duplicate_evidence(tmp_path):
    feishu = _settings(tmp_path)
    transport = _FailingCardTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        selected = _button_values(_last_card(transport))[0]
        action_body = _action_body(
            feishu,
            event_id="evt_outbound_retry_001",
            value=selected,
        )
        transport.fail_next_card = True
        failed = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        after_failure = client.get(f"/api/v1/cases/{selected['case_id']}")
        retried = client.post(
            "/api/v1/feishu/card-actions",
            content=action_body,
            headers=_signed_headers(feishu, action_body),
        )
        recovered_card = _last_card(transport)
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")

    assert failed.status_code == 503
    assert failed.json()["code"] == "FEISHU_UNAVAILABLE"
    assert after_failure.json()["case"]["evidence_revision"] == 1
    assert retried.status_code == 200
    assert {item["evidence_code"] for item in _button_values(recovered_card)} == {
        "transaction.occurred_at"
    }
    body = persisted.json()
    assert body["case"]["case_revision"] == 2
    assert body["case"]["evidence_revision"] == 1
    assert len(body["evidence"]) == 1


def test_retry_after_final_card_failure_replays_the_persisted_diagnosis(tmp_path):
    feishu = _settings(tmp_path)
    transport = _FailingCardTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )
    codes = (
        "transaction.reference",
        "transaction.occurred_at",
        "context.environment",
        "symptom.status",
        "authentication.status",
        "callback.delivery_status",
        "integration.type",
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _message_body(feishu)
        client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(feishu, message_body),
        )
        final_body = None
        selected = None
        for index, code in enumerate(codes, start=1):
            selected = next(
                value
                for value in _button_values(_last_card(transport))
                if value.get("evidence_code") == code and value.get("typed_value") != "DECLINED"
            )
            action_body = _action_body(
                feishu,
                event_id=f"evt_final_retry_{index:02d}",
                value=selected,
            )
            if code == "integration.type":
                transport.fail_next_card = True
                final_body = action_body
            response = client.post(
                "/api/v1/feishu/card-actions",
                content=action_body,
                headers=_signed_headers(feishu, action_body),
            )
            if code != "integration.type":
                assert response.status_code == 200

        assert selected is not None
        assert final_body is not None
        after_failure = client.get(f"/api/v1/cases/{selected['case_id']}")
        retried = client.post(
            "/api/v1/feishu/card-actions",
            content=final_body,
            headers=_signed_headers(feishu, final_body),
        )
        recovered_card = _last_card(transport)
        persisted = client.get(f"/api/v1/cases/{selected['case_id']}")

    assert response.status_code == 503
    failed_body = after_failure.json()
    diagnosis_id = failed_body["current_diagnosis"]["diagnosis_id"]
    assert failed_body["case"]["status"] == "HUMAN_REVIEW"
    assert failed_body["case"]["evidence_revision"] == 7
    assert len(failed_body["evidence"]) == 7
    assert retried.status_code == 200
    assert retried.json() == {"ok": True}
    recovered = json.dumps(recovered_card, ensure_ascii=False)
    assert diagnosis_id in recovered
    assert "THREEDS_INCOMPLETE_V1" in recovered
    body = persisted.json()
    assert body["case"]["case_revision"] == 9
    assert body["case"]["evidence_revision"] == 7
    assert len(body["evidence"]) == 7
    assert body["current_diagnosis"]["diagnosis_id"] == diagnosis_id
