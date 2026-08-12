import hashlib
import json
import re
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


def _message_body(settings: FeishuSettings, **changes: object) -> bytes:
    fixture = Path(__file__).with_name("fixtures") / "message_received.json"
    raw = (
        fixture.read_bytes()
        .replace(b"__VERIFICATION_TOKEN__", settings.verification_token.encode())
        .replace(b"__APP_ID__", settings.app_id.encode())
    )
    payload = json.loads(raw)
    for path, value in changes.items():
        target = payload
        segments = path.split("__")
        for segment in segments[:-1]:
            target = target[segment]
        target[segments[-1]] = value
    return json.dumps(payload, separators=(",", ":")).encode()


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


class _SuccessfulFeishuTransport:
    def __init__(self) -> None:
        self.requests: list[FeishuHttpRequest] = []

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        self.requests.append(request)
        if request.url.endswith("/tenant_access_token/internal"):
            body = {"code": 0, "tenant_access_token": "synthetic-access-token"}
        else:
            body = {"code": 0, "data": {"message_id": "om_outbound_001"}}
        return FeishuHttpResponse(status_code=200, body=json.dumps(body).encode())


class _FailFirstMessageTransport(_SuccessfulFeishuTransport):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        if request.url.endswith("/tenant_access_token/internal"):
            return super().__call__(request)
        self.requests.append(request)
        if not self.failed:
            self.failed = True
            return FeishuHttpResponse(status_code=503, body=b"{}")
        body = {"code": 0, "data": {"message_id": "om_outbound_002"}}
        return FeishuHttpResponse(status_code=200, body=json.dumps(body).encode())


def _sent_card(transport: _SuccessfulFeishuTransport) -> tuple[dict[str, object], str]:
    message_request = transport.requests[-1]
    request_body = json.loads(message_request.body)
    return json.loads(request_body["content"]), request_body["uuid"]


def _post_message(client: TestClient, feishu: FeishuSettings, body: bytes):
    return client.post(
        "/api/v1/feishu/events",
        content=body,
        headers=_signed_headers(feishu, body),
    )


def test_signed_group_message_creates_case_and_sends_first_readiness_question(
    tmp_path,
):
    feishu = _settings(tmp_path)
    raw_body = _message_body(feishu)
    transport = _SuccessfulFeishuTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post_message(client, feishu, raw_body)
        card, idempotency_key = _sent_card(transport)
        rendered = json.dumps(card, ensure_ascii=False)
        case_id = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            rendered,
        ).group()
        case_response = client.get(f"/api/v1/cases/{case_id}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert case_response.status_code == 200
    assert case_response.json()["case"]["merchant_ref"] == "merchant_feishu_demo"
    assert len(transport.requests) == 2
    assert "OceanPilot 需要补充信息" in rendered
    assert "证据完成度" in rendered
    assert "商户技术" in rendered
    assert re.fullmatch(r"opq_[0-9a-f]{60}", idempotency_key)
    callback_bytes = feishu.callback_db_path.read_bytes()
    for raw_identifier in (
        b"tenant_demo",
        b"oc_demo_group",
        b"om_thread_001",
        b"ou_synthetic_merchant",
    ):
        assert raw_identifier not in callback_bytes


def test_replayed_event_does_not_create_or_send_again(tmp_path):
    feishu = _settings(tmp_path)
    raw_body = _message_body(feishu)
    transport = _SuccessfulFeishuTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        first = _post_message(client, feishu, raw_body)
        replay = _post_message(client, feishu, raw_body)

    assert first.status_code == replay.status_code == 200
    assert replay.json() == {"ok": True}
    assert len(transport.requests) == 2


def test_second_event_in_same_thread_reuses_case_and_card_identity(tmp_path):
    feishu = _settings(tmp_path)
    first_body = _message_body(feishu)
    second_body = _message_body(
        feishu,
        header__event_id="evt_message_002",
        event__message__message_id="om_message_002",
    )
    transport = _SuccessfulFeishuTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        assert _post_message(client, feishu, first_body).status_code == 200
        first_card, first_key = _sent_card(transport)
        assert _post_message(client, feishu, second_body).status_code == 200
        second_card, second_key = _sent_card(transport)

    assert first_key == second_key
    assert first_card == second_card
    assert len(transport.requests) == 4


def test_different_thread_creates_a_different_case_and_card_identity(tmp_path):
    feishu = _settings(tmp_path)
    first_body = _message_body(feishu)
    second_body = _message_body(
        feishu,
        header__event_id="evt_message_002",
        event__message__message_id="om_message_002",
        event__message__root_id="om_thread_002",
    )
    transport = _SuccessfulFeishuTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        assert _post_message(client, feishu, first_body).status_code == 200
        _, first_key = _sent_card(transport)
        assert _post_message(client, feishu, second_body).status_code == 200
        _, second_key = _sent_card(transport)

    assert first_key != second_key
    assert len(transport.requests) == 4


def test_app_sender_and_other_group_are_acknowledged_without_side_effects(tmp_path):
    feishu = _settings(tmp_path)
    app_body = _message_body(feishu, event__sender__sender_type="app")
    other_group_body = _message_body(
        feishu,
        header__event_id="evt_message_002",
        event__message__chat_id="oc_other_group",
    )
    transport = _SuccessfulFeishuTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        app_response = _post_message(client, feishu, app_body)
        group_response = _post_message(client, feishu, other_group_body)

    assert app_response.status_code == group_response.status_code == 200
    assert transport.requests == []


def test_wrong_app_id_is_fixed_401_without_side_effects(tmp_path):
    feishu = _settings(tmp_path)
    raw_body = _message_body(feishu, header__app_id="cli_other_app")
    transport = _SuccessfulFeishuTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post_message(client, feishu, raw_body)

    assert response.status_code == 401
    assert response.json()["code"] == "FEISHU_CALLBACK_UNAUTHORIZED"
    assert "cli_other_app" not in response.text
    assert transport.requests == []


def test_callback_id_reused_with_different_signed_payload_returns_safe_conflict(
    tmp_path,
):
    feishu = _settings(tmp_path)
    first_body = _message_body(feishu)
    conflicting_body = _message_body(
        feishu,
        event__message__content=json.dumps({"text": "Different synthetic symptom"}),
    )
    transport = _SuccessfulFeishuTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        assert _post_message(client, feishu, first_body).status_code == 200
        conflict = _post_message(client, feishu, conflicting_body)

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "FEISHU_IDEMPOTENCY_CONFLICT"
    assert "Different synthetic symptom" not in conflict.text
    assert len(transport.requests) == 2


def test_outbound_failure_is_safe_503_and_retry_reuses_the_case(tmp_path):
    feishu = _settings(tmp_path)
    raw_body = _message_body(feishu)
    transport = _FailFirstMessageTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        failed = _post_message(client, feishu, raw_body)
        retried = _post_message(client, feishu, raw_body)

    assert failed.status_code == 503
    assert failed.json()["code"] == "FEISHU_UNAVAILABLE"
    assert retried.status_code == 200
    assert retried.json() == {"ok": True}
    assert len(transport.requests) == 4


def test_outbound_failure_does_not_release_event_identity(tmp_path):
    feishu = _settings(tmp_path)
    first_body = _message_body(feishu)
    conflicting_body = _message_body(
        feishu,
        event__message__content=json.dumps({"text": "Conflicting retry symptom"}),
    )
    transport = _FailFirstMessageTransport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        failed = _post_message(client, feishu, first_body)
        conflict = _post_message(client, feishu, conflicting_body)

    assert failed.status_code == 503
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "FEISHU_IDEMPOTENCY_CONFLICT"
    assert "Conflicting retry symptom" not in conflict.text
    assert len(transport.requests) == 2
