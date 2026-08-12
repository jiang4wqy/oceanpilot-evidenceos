import asyncio
import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from time import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.feishu.security import FeishuRequestVerifier
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.main import create_app

_FEISHU_ENV_NAMES = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
    "FEISHU_ENCRYPT_KEY",
)
_CALLBACK_FIXTURES = (
    "url_verification.json",
    "message_received.json",
    "evidence_action.json",
    "confirmation_action.json",
)


def _feishu_settings(tmp_path):
    marker = uuid4().hex
    return FeishuSettings(
        app_id=f"app-{marker}",
        app_secret=f"secret-{marker}",
        verification_token=f"token-{marker}",
        encrypt_key=f"key-{marker}",
        callback_db_path=tmp_path / "feishu.db",
    )


def _signed_headers(feishu, raw_body, *, timestamp=None):
    timestamp = str(int(time()) if timestamp is None else timestamp)
    nonce = f"nonce-{uuid4().hex}"
    signature = hashlib.sha256(
        f"{timestamp}{nonce}{feishu.encrypt_key}".encode() + raw_body
    ).hexdigest()
    return {
        "content-type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def _url_verification_body(feishu):
    fixture_path = Path(__file__).with_name("fixtures") / "url_verification.json"
    return fixture_path.read_bytes().replace(
        b"__VERIFICATION_TOKEN__",
        feishu.verification_token.encode(),
    )


def _callback_fixture_body(feishu, fixture_name):
    fixture_path = Path(__file__).with_name("fixtures") / fixture_name
    return (
        fixture_path.read_bytes()
        .replace(b"__VERIFICATION_TOKEN__", feishu.verification_token.encode())
        .replace(b"__APP_ID__", feishu.app_id.encode())
    )


@pytest.mark.parametrize("fixture_name", _CALLBACK_FIXTURES)
def test_callback_fixture_templates_are_valid_json_without_credentials(fixture_name):
    fixture_path = Path(__file__).with_name("fixtures") / fixture_name
    raw_body = fixture_path.read_bytes()

    assert isinstance(json.loads(raw_body), dict)
    assert b"__VERIFICATION_TOKEN__" in raw_body
    assert b"app_secret" not in raw_body.lower()


@pytest.mark.parametrize(
    "path",
    ("/api/v1/feishu/events", "/api/v1/feishu/card-actions"),
)
def test_unconfigured_callbacks_are_safe_503_without_breaking_core(tmp_path, path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))
    sentinel = "CALLBACK-BODY-SENTINEL"

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post(
            path,
            content=sentinel,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "FEISHU_UNAVAILABLE"
    assert response.headers["X-Trace-ID"] == response.json()["trace_id"]
    assert sentinel not in response.text


@pytest.mark.parametrize("present_count", (0, 1, 2, 3))
def test_partial_environment_configuration_is_disabled_and_secret_safe(
    monkeypatch,
    present_count,
):
    marker = uuid4().hex
    for index, name in enumerate(_FEISHU_ENV_NAMES):
        if index < present_count:
            monkeypatch.setenv(name, f"{name.lower()}-{marker}")
        else:
            monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.feishu is None
    assert marker not in repr(settings)


def test_complete_runtime_is_initialized_only_inside_lifespan(tmp_path):
    feishu = _feishu_settings(tmp_path)
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    assert not (tmp_path / "core.db").exists()
    assert not feishu.callback_db_path.exists()
    assert app.state.feishu_runtime is None

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert (tmp_path / "core.db").is_file()
        assert feishu.callback_db_path.is_file()
        assert app.state.feishu_runtime is not None

    assert app.state.feishu_runtime is None
    assert feishu.app_secret not in repr(feishu)
    assert feishu.verification_token not in repr(feishu)
    assert feishu.encrypt_key not in repr(feishu)


def test_feishu_database_failure_degrades_only_the_integration(tmp_path):
    feishu = _feishu_settings(tmp_path)
    feishu.callback_db_path.write_text("not a sqlite database", encoding="utf-8")
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        response = client.post(
            "/api/v1/feishu/events",
            content="DATABASE-FAILURE-SENTINEL",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "FEISHU_UNAVAILABLE"
    assert "DATABASE-FAILURE-SENTINEL" not in response.text


@pytest.mark.parametrize(
    "field",
    ("app_id", "app_secret", "verification_token", "encrypt_key"),
)
def test_incomplete_programmatic_configuration_does_not_break_core(tmp_path, field):
    feishu = replace(_feishu_settings(tmp_path), **{field: ""})
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        response = client.post(
            "/api/v1/feishu/events",
            content="INCOMPLETE-CONFIG-SENTINEL",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "FEISHU_UNAVAILABLE"
    assert not feishu.callback_db_path.exists()


def test_malformed_legacy_feishu_data_does_not_break_core(tmp_path):
    feishu = _feishu_settings(tmp_path)
    FeishuCallbackStoreFactory(feishu.callback_db_path)
    connection = sqlite3.connect(feishu.callback_db_path)
    try:
        connection.execute(
            """
            INSERT INTO feishu_action_receipts (
                action_id, payload_hash, status, response_json, case_id, diagnosis_id,
                actor_id, created_at, completed_at
            ) VALUES (?, ?, 'COMPLETED', '{}', ?, ?, '', ?, ?)
            """,
            (
                "action-malformed-legacy",
                "a" * 64,
                "00000000-0000-4000-8000-000000000010",
                "00000000-0000-4000-8000-000000000050",
                "2026-08-05T04:00:00Z",
                "2026-08-05T04:00:01Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        response = client.post(
            "/api/v1/feishu/events",
            content="MALFORMED-LEGACY-SENTINEL",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "FEISHU_UNAVAILABLE"


def test_signed_url_verification_uses_exact_raw_fixture_bytes(
    tmp_path,
    monkeypatch,
):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    received_bodies = []
    original_verify = FeishuRequestVerifier.verify

    def recording_verify(self, headers, body):
        received_bodies.append(body)
        return original_verify(self, headers, body)

    monkeypatch.setattr(FeishuRequestVerifier, "verify", recording_verify)
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body),
        )

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-from-fixture"}
    assert received_bodies == [raw_body]


def test_invalid_signature_is_fixed_401_without_sensitive_echo(tmp_path):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    headers = _signed_headers(feishu, raw_body)
    headers["X-Lark-Signature"] = "SIGNATURE-SENTINEL"
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=headers,
        )

    assert response.status_code == 401
    assert response.json()["code"] == "FEISHU_CALLBACK_UNAUTHORIZED"
    assert "SIGNATURE-SENTINEL" not in response.text
    assert feishu.verification_token not in response.text


@pytest.mark.parametrize("failure", ("expired", "wrong_token"))
def test_verification_failures_share_fixed_401_contract(tmp_path, failure):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    timestamp = None
    sentinel = ""
    if failure == "expired":
        timestamp = int(time()) - 301
        sentinel = str(timestamp)
    else:
        sentinel = f"wrong-token-{uuid4().hex}"
        raw_body = json.dumps(
            {
                "token": sentinel,
                "type": "url_verification",
                "challenge": "challenge-from-fixture",
            },
            separators=(",", ":"),
        ).encode()
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body, timestamp=timestamp),
        )

    assert response.status_code == 401
    assert response.json()["code"] == "FEISHU_CALLBACK_UNAUTHORIZED"
    assert sentinel not in response.text


def test_deeply_nested_signed_json_is_fixed_401(tmp_path):
    feishu = _feishu_settings(tmp_path)
    raw_body = (
        b'{"token":"'
        + feishu.verification_token.encode()
        + b'","event":'
        + (b"[" * 5_000)
        + b"0"
        + (b"]" * 5_000)
        + b"}"
    )
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body),
        )

    assert response.status_code == 401
    assert response.json()["code"] == "FEISHU_CALLBACK_UNAUTHORIZED"


def test_overlong_numeric_timestamp_is_fixed_401(tmp_path):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    timestamp = "9" * 5_000
    headers = _signed_headers(feishu, raw_body)
    headers["X-Lark-Request-Timestamp"] = timestamp
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=headers,
        )

    assert response.status_code == 401
    assert response.json()["code"] == "FEISHU_CALLBACK_UNAUTHORIZED"


@pytest.mark.parametrize("declared_length", (65_537, 999_999))
def test_declared_oversize_is_413_before_verification(
    tmp_path,
    monkeypatch,
    declared_length,
):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    headers = _signed_headers(feishu, raw_body)
    headers["content-length"] = str(declared_length)

    def forbidden_verify(*args, **kwargs):
        del args, kwargs
        raise AssertionError("oversize body must not reach verifier")

    monkeypatch.setattr(FeishuRequestVerifier, "verify", forbidden_verify)
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=headers,
        )

    assert response.status_code == 413
    assert response.json()["code"] == "FEISHU_CALLBACK_TOO_LARGE"


def test_actual_oversize_is_413_before_verification(tmp_path, monkeypatch):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    raw_body += b" " * (65_537 - len(raw_body))
    headers = _signed_headers(feishu, raw_body)
    headers["content-length"] = "1"

    def forbidden_verify(*args, **kwargs):
        del args, kwargs
        raise AssertionError("oversize body must not reach verifier")

    monkeypatch.setattr(FeishuRequestVerifier, "verify", forbidden_verify)
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=headers,
        )

    assert response.status_code == 413
    assert response.json()["code"] == "FEISHU_CALLBACK_TOO_LARGE"


def test_exact_64k_callback_is_accepted(tmp_path):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    raw_body += b" " * (65_536 - len(raw_body))
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body),
        )

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-from-fixture"}


def test_invalid_content_type_is_fixed_422_before_verification(tmp_path, monkeypatch):
    feishu = _feishu_settings(tmp_path)
    raw_body = _url_verification_body(feishu)
    headers = _signed_headers(feishu, raw_body)
    headers["content-type"] = "text/plain"

    def forbidden_verify(*args, **kwargs):
        del args, kwargs
        raise AssertionError("invalid content type must not reach verifier")

    monkeypatch.setattr(FeishuRequestVerifier, "verify", forbidden_verify)
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=headers,
        )

    assert response.status_code == 422
    assert response.json()["code"] == "FEISHU_INVALID_CALLBACK"


def test_verified_unknown_event_shape_is_fixed_422_without_echo(tmp_path):
    feishu = _feishu_settings(tmp_path)
    raw_body = json.dumps(
        {
            "token": feishu.verification_token,
            "type": "url_verification",
            "challenge": "challenge-from-fixture",
            "unknown": "DTO-SENTINEL",
        },
        separators=(",", ":"),
    ).encode()
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "FEISHU_INVALID_CALLBACK"
    assert "DTO-SENTINEL" not in response.text


@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    (("evidence_action.json", 503), ("confirmation_action.json", 422)),
)
def test_signed_card_actions_are_not_accepted_before_orchestration(
    tmp_path,
    fixture_name,
    expected_status,
):
    feishu = _feishu_settings(tmp_path)
    raw_body = _callback_fixture_body(feishu, fixture_name)
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/card-actions",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body),
        )

    assert response.status_code == expected_status
    assert response.json()["code"] == (
        "FEISHU_UNAVAILABLE" if expected_status == 503 else "FEISHU_INVALID_CALLBACK"
    )
    assert "ou_synthetic" not in response.text


def test_signed_message_requires_demo_group_configuration(tmp_path):
    feishu = _feishu_settings(tmp_path)
    raw_body = _callback_fixture_body(feishu, "message_received.json")
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/feishu/events",
            content=raw_body,
            headers=_signed_headers(feishu, raw_body),
        )

    assert response.status_code == 503
    assert response.json()["code"] == "FEISHU_UNAVAILABLE"
    assert "ou_synthetic" not in response.text


def test_unconfigured_callback_dependency_does_not_consume_asgi_body(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))
    received = 0
    messages = []

    async def receive():
        nonlocal received
        received += 1
        raise AssertionError("unavailable callback must not consume request body")

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/feishu/events",
        "raw_path": b"/api/v1/feishu/events",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }

    asyncio.run(app(scope, receive, send))

    assert received == 0
    assert (
        next(message for message in messages if message["type"] == "http.response.start")["status"]
        == 503
    )


def test_declared_oversize_does_not_consume_asgi_body(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "core.db"))
    app.state.feishu_runtime = object()
    received = 0
    messages = []

    async def receive():
        nonlocal received
        received += 1
        raise AssertionError("declared oversize callback must not consume request body")

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/feishu/events",
        "raw_path": b"/api/v1/feishu/events",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", b"65537"),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }

    asyncio.run(app(scope, receive, send))

    assert received == 0
    assert (
        next(message for message in messages if message["type"] == "http.response.start")["status"]
        == 413
    )


def test_overlong_numeric_content_length_is_fixed_422(tmp_path):
    feishu = _feishu_settings(tmp_path)
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))
    app.state.feishu_runtime = object()
    received = 0
    messages = []

    async def receive():
        nonlocal received
        received += 1
        raise AssertionError("invalid content length must not consume request body")

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/feishu/events",
        "raw_path": b"/api/v1/feishu/events",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", b"9" * 5_000),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }

    asyncio.run(app(scope, receive, send))

    assert received == 0
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = next(message for message in messages if message["type"] == "http.response.body")
    assert start["status"] == 422
    assert json.loads(body["body"])["code"] == "FEISHU_INVALID_CALLBACK"
