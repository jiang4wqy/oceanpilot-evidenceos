import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time
from uuid import uuid4

from fastapi.testclient import TestClient

from oceanpilot.adapters.feishu.client import FeishuHttpRequest, FeishuHttpResponse
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
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
    actor_id: str,
    open_message_id: str,
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
            "operator": {"open_id": actor_id},
            "context": {
                "open_message_id": open_message_id,
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


def _open_human_review_card(
    client: TestClient,
    transport: _Transport,
    settings: FeishuSettings,
) -> tuple[object, dict[str, object]]:
    opened = client.post(
        "/api/v1/feishu/events",
        content=(message_body := _message_body(settings)),
        headers=_signed_headers(settings, message_body),
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
    for index, expected_code in enumerate(expected_codes, start=1):
        selected = next(
            value
            for value in _button_values(_last_card(transport))
            if value.get("evidence_code") == expected_code
            and value.get("typed_value") != "DECLINED"
        )
        evidence_body = _action_body(
            settings,
            event_id=f"evt_confirmation_prerequisite_{index:02d}",
            actor_id="ou_synthetic_merchant",
            open_message_id=f"om_question_{index:02d}",
            value=selected,
        )
        submitted = client.post(
            "/api/v1/feishu/card-actions",
            content=evidence_body,
            headers=_signed_headers(settings, evidence_body),
        )
        assert submitted.status_code == 200
    confirmation_value = next(
        value
        for value in _button_values(_last_card(transport))
        if value.get("action_kind") == "confirm_review"
    )
    return opened, confirmation_value


def test_current_human_review_diagnosis_can_be_confirmed_once_without_state_change(
    tmp_path,
):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )
    raw_actor = "ou_confirmation_reviewer"

    with TestClient(app, raise_server_exceptions=False) as client:
        opened, confirmation_value = _open_human_review_card(client, transport, feishu)
        confirmation_body = _action_body(
            feishu,
            event_id="evt_confirmation_http_001",
            actor_id=raw_actor,
            open_message_id="om_diagnosis_001",
            value=confirmation_value,
        )
        confirmed = client.post(
            "/api/v1/feishu/card-actions",
            content=confirmation_body,
            headers=_signed_headers(feishu, confirmation_body),
        )
        case_response = client.get(f"/api/v1/cases/{confirmation_value['case_id']}")

    assert opened.status_code == 200
    assert confirmed.status_code == 200
    assert confirmed.json() == {
        "ok": True,
        "result": "confirmed",
        "message": ("Recommendation confirmed and recorded; no business action was executed."),
    }
    assert case_response.json()["case"]["status"] == "HUMAN_REVIEW"
    assert (
        case_response.json()["case"]["current_diagnosis_id"] == confirmation_value["diagnosis_id"]
    )

    with FeishuCallbackStoreFactory(feishu.callback_db_path).session() as store:
        audit = store.find_approval_audit(
            case_id=confirmation_value["case_id"],
            diagnosis_id=confirmation_value["diagnosis_id"],
            action_kind="CONFIRM_REVIEW",
        )
    assert audit is not None
    assert audit.result == "CONFIRMED"
    actor_material = json.dumps(
        ["tenant_demo", raw_actor],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode()
    assert audit.actor_hash == hashlib.sha256(actor_material).hexdigest()
    assert audit.synthetic is True

    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM feishu_approval_audits").fetchone()[
            0
        ]
    assert audit_count == 1
    assert raw_actor.encode() not in feishu.callback_db_path.read_bytes()
    for sensitive in (
        "tenant_demo",
        feishu.demo_chat_id,
        feishu.app_secret,
        feishu.verification_token,
    ):
        assert sensitive.encode() not in feishu.callback_db_path.read_bytes()


def test_repeated_confirmation_callbacks_create_one_approval(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        first_body = _action_body(
            feishu,
            event_id="evt_confirmation_replay_001",
            actor_id="ou_confirmation_reviewer",
            open_message_id="om_diagnosis_replay_001",
            value=confirmation_value,
        )
        first = client.post(
            "/api/v1/feishu/card-actions",
            content=first_body,
            headers=_signed_headers(feishu, first_body),
        )
        same_callback = client.post(
            "/api/v1/feishu/card-actions",
            content=first_body,
            headers=_signed_headers(feishu, first_body),
        )
        new_event_body = _action_body(
            feishu,
            event_id="evt_confirmation_replay_002",
            actor_id="ou_confirmation_reviewer",
            open_message_id="om_diagnosis_replay_001",
            value=confirmation_value,
        )
        new_event = client.post(
            "/api/v1/feishu/card-actions",
            content=new_event_body,
            headers=_signed_headers(feishu, new_event_body),
        )

    assert first.status_code == 200
    assert same_callback.json() == first.json()
    assert new_event.json() == first.json()
    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_rows = connection.execute("SELECT action_id FROM feishu_approval_audits").fetchall()
    assert audit_rows == [("evt_confirmation_replay_001",)]


def test_stale_confirmation_card_returns_refresh_message_without_approval(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        changed = client.post(
            f"/api/v1/cases/{confirmation_value['case_id']}/evidence",
            json={
                "evidence_id": "00000000-0000-4000-8000-000000009999",
                "evidence_code": "transaction.reference",
                "availability": "AVAILABLE",
                "typed_value": "txn_changed_after_diagnosis",
                "source_ref": "synthetic:stale-card-test",
            },
        )
        stale_body = _action_body(
            feishu,
            event_id="evt_confirmation_stale_001",
            actor_id="ou_confirmation_reviewer",
            open_message_id="om_diagnosis_stale_001",
            value=confirmation_value,
        )
        stale = client.post(
            "/api/v1/feishu/card-actions",
            content=stale_body,
            headers=_signed_headers(feishu, stale_body),
        )

    assert changed.status_code == 201
    assert stale.status_code == 200
    assert stale.json() == {
        "ok": True,
        "result": "refresh_required",
        "message": "This diagnosis is no longer current; refresh before confirming.",
    }
    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM feishu_approval_audits").fetchone()[
            0
        ]
    assert audit_count == 0


def test_confirmation_for_unknown_case_returns_refresh_message_without_approval(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        confirmation_value["case_id"] = "00000000-0000-4000-8000-000000008888"
        stale_body = _action_body(
            feishu,
            event_id="evt_confirmation_missing_case_001",
            actor_id="ou_confirmation_reviewer",
            open_message_id="om_diagnosis_missing_case_001",
            value=confirmation_value,
        )
        stale = client.post(
            "/api/v1/feishu/card-actions",
            content=stale_body,
            headers=_signed_headers(feishu, stale_body),
        )

    assert stale.status_code == 200
    assert stale.json()["result"] == "refresh_required"
    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM feishu_approval_audits").fetchone()[
            0
        ]
    assert audit_count == 0


def test_confirmation_callback_rejects_same_event_with_different_payload(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        first_body = _action_body(
            feishu,
            event_id="evt_confirmation_conflict_001",
            actor_id="ou_confirmation_reviewer",
            open_message_id="om_diagnosis_conflict_001",
            value=confirmation_value,
        )
        first = client.post(
            "/api/v1/feishu/card-actions",
            content=first_body,
            headers=_signed_headers(feishu, first_body),
        )
        changed_body = _action_body(
            feishu,
            event_id="evt_confirmation_conflict_001",
            actor_id="ou_different_reviewer",
            open_message_id="om_diagnosis_conflict_001",
            value=confirmation_value,
        )
        conflict = client.post(
            "/api/v1/feishu/card-actions",
            content=changed_body,
            headers=_signed_headers(feishu, changed_body),
        )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "FEISHU_IDEMPOTENCY_CONFLICT"
    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM feishu_approval_audits").fetchone()[
            0
        ]
    assert audit_count == 1


def test_confirmation_callback_rejects_caller_controlled_fields_without_writes(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        confirmation_value["approval_id"] = "caller-controlled"
        forged_body = _action_body(
            feishu,
            event_id="evt_confirmation_forged_001",
            actor_id="ou_confirmation_reviewer",
            open_message_id="om_diagnosis_forged_001",
            value=confirmation_value,
        )
        forged = client.post(
            "/api/v1/feishu/card-actions",
            content=forged_body,
            headers=_signed_headers(feishu, forged_body),
        )

    assert forged.status_code == 422
    assert forged.json()["code"] == "FEISHU_INVALID_CALLBACK"
    assert b"caller-controlled" not in forged.content
    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM feishu_approval_audits").fetchone()[
            0
        ]
        receipt_count = connection.execute(
            "SELECT COUNT(*) FROM feishu_action_receipts "
            "WHERE action_id = 'evt_confirmation_forged_001'"
        ).fetchone()[0]
    assert audit_count == 0
    assert receipt_count == 0


def test_confirmation_from_other_group_is_ignored_without_writes(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        other_group_body = json.loads(
            _action_body(
                feishu,
                event_id="evt_confirmation_other_group_001",
                actor_id="ou_confirmation_reviewer",
                open_message_id="om_diagnosis_other_group_001",
                value=confirmation_value,
            )
        )
        other_group_body["event"]["context"]["open_chat_id"] = "oc_other_group"
        raw_body = json.dumps(other_group_body, separators=(",", ":")).encode()
        ignored = client.post(
            "/api/v1/feishu/card-actions",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body),
        )

    assert ignored.status_code == 200
    assert ignored.json() == {"ok": True}
    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM feishu_approval_audits").fetchone()[
            0
        ]
        receipt_count = connection.execute(
            "SELECT COUNT(*) FROM feishu_action_receipts "
            "WHERE action_id = 'evt_confirmation_other_group_001'"
        ).fetchone()[0]
    assert audit_count == 0
    assert receipt_count == 0


def test_active_confirmation_lease_returns_safe_retryable_error(tmp_path):
    feishu = _settings(tmp_path)
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        pending_body = _action_body(
            feishu,
            event_id="evt_confirmation_in_progress_001",
            actor_id="ou_confirmation_reviewer",
            open_message_id="om_diagnosis_in_progress_001",
            value=confirmation_value,
        )
        now = datetime.now(UTC)
        with FeishuCallbackStoreFactory(feishu.callback_db_path).session() as store:
            store.claim_confirmation_action(
                "evt_confirmation_in_progress_001",
                payload_hash=hashlib.sha256(pending_body).hexdigest(),
                claim_token="active-worker-token",
                now=now.isoformat(),
                lease_expires_at=(now + timedelta(seconds=30)).isoformat(),
            )
        pending = client.post(
            "/api/v1/feishu/card-actions",
            content=pending_body,
            headers=_signed_headers(feishu, pending_body),
        )

    assert pending.status_code == 503
    assert pending.json()["code"] == "FEISHU_UNAVAILABLE"
    assert confirmation_value["case_id"].encode() not in pending.content
    with sqlite3.connect(feishu.callback_db_path) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM feishu_approval_audits").fetchone()[
            0
        ]
    assert audit_count == 0
