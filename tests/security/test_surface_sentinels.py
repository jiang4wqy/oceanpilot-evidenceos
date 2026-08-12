import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict
from pathlib import Path
from time import time
from uuid import uuid4

from fastapi.testclient import TestClient

from oceanpilot.adapters.feishu.client import FeishuHttpRequest, FeishuHttpResponse
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.adapters.persistence.sqlite import SqliteCaseStoreFactory
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.main import create_app
from tests.feishu.test_confirmation_action import (
    _action_body,
    _open_human_review_card,
    _signed_headers,
)


class _Transport:
    def __init__(self) -> None:
        self.requests: list[FeishuHttpRequest] = []

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        self.requests.append(request)
        body = (
            {"code": 0, "tenant_access_token": "synthetic-access-token"}
            if request.url.endswith("/tenant_access_token/internal")
            else {"code": 0, "data": {"message_id": f"om_{len(self.requests)}"}}
        )
        return FeishuHttpResponse(status_code=200, body=json.dumps(body).encode())


def _signed_message(
    *,
    app_id: str,
    verification_token: str,
    encrypt_key: str,
    marker: str,
    text: str,
) -> tuple[bytes, dict[str, str]]:
    timestamp = str(int(time()))
    nonce = f"nonce-{marker}"
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": f"evt-{marker}",
            "token": verification_token,
            "create_time": f"{timestamp}000",
            "event_type": "im.message.receive_v1",
            "tenant_key": f"tenant-{marker}",
            "app_id": app_id,
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": f"ou-{marker}"},
                "sender_type": "user",
                "tenant_key": f"tenant-{marker}",
            },
            "message": {
                "message_id": f"om-{marker}",
                "root_id": f"root-{marker}",
                "parent_id": "",
                "create_time": f"{timestamp}000",
                "chat_id": "oc_demo_group",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": text}, separators=(",", ":")),
            },
        },
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hashlib.sha256(f"{timestamp}{nonce}{encrypt_key}".encode() + raw_body).hexdigest()
    return raw_body, {
        "content-type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def _database_artifacts(path: Path) -> bytes:
    return b"".join(
        candidate.read_bytes()
        for candidate in (
            path,
            Path(f"{path}-journal"),
            Path(f"{path}-wal"),
            Path(f"{path}-shm"),
        )
        if candidate.is_file()
    )


def test_sensitive_signed_callback_is_rejected_without_cross_surface_residue(tmp_path, caplog):
    marker = uuid4().hex
    sentinel = f"Authorization: Bearer CALLBACK-BODY-{marker}"
    feishu = FeishuSettings(
        app_id=f"app-{marker}",
        app_secret=f"secret-{marker}",
        verification_token=f"verification-{marker}",
        encrypt_key=f"encrypt-{marker}",
        callback_db_path=tmp_path / "feishu.db",
        demo_chat_id="oc_demo_group",
        demo_merchant_ref="merchant_security_rejection",
    )
    app = create_app(Settings(db_path=tmp_path / "core.db", feishu=feishu))
    raw_body, headers = _signed_message(
        app_id=feishu.app_id,
        verification_token=feishu.verification_token,
        encrypt_key=feishu.encrypt_key,
        marker=marker,
        text=sentinel,
    )

    with (
        caplog.at_level(logging.DEBUG),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post("/api/v1/feishu/events", content=raw_body, headers=headers)
        static_assets = b"".join(
            client.get(path).content
            for path in ("/demo", "/demo/assets/styles.css", "/demo/assets/app.js")
        )

    with sqlite3.connect(feishu.callback_db_path) as connection:
        receipt_count = connection.execute(
            "SELECT COUNT(*) FROM feishu_event_receipts WHERE event_id = ?",
            (f"evt-{marker}",),
        ).fetchone()[0]
    assert response.status_code == 422
    assert response.json()["code"] == "SENSITIVE_DATA_REJECTED"
    # Only replay identity and the payload hash are stored; the callback body is not.
    assert receipt_count == 1
    for surface in (
        response.content,
        caplog.text.encode(),
        _database_artifacts(tmp_path / "core.db"),
        _database_artifacts(feishu.callback_db_path),
        static_assets,
    ):
        assert sentinel.encode() not in surface


def test_credentials_and_callback_identities_are_absent_from_all_persisted_surfaces(
    tmp_path,
    caplog,
):
    marker = uuid4().hex
    raw_actor = f"ou_security_actor_{marker}"
    feishu = FeishuSettings(
        app_id=f"app-security-{marker}",
        app_secret=f"secret-security-{marker}",
        verification_token=f"token-security-{marker}",
        encrypt_key=f"key-security-{marker}",
        callback_db_path=tmp_path / "feishu.db",
        demo_chat_id="oc_demo_group",
        demo_merchant_ref=f"merchant_security_{marker}",
    )
    transport = _Transport()
    app = create_app(
        Settings(db_path=tmp_path / "core.db", feishu=feishu),
        feishu_transport=transport,
    )

    with (
        caplog.at_level(logging.DEBUG),
        TestClient(
            app,
            raise_server_exceptions=False,
        ) as client,
    ):
        _, confirmation_value = _open_human_review_card(client, transport, feishu)
        confirmation_body = _action_body(
            feishu,
            event_id=f"evt_security_{marker}",
            actor_id=raw_actor,
            open_message_id=f"om_security_{marker}",
            value=confirmation_value,
        )
        confirmation = client.post(
            "/api/v1/feishu/card-actions",
            content=confirmation_body,
            headers=_signed_headers(feishu, confirmation_body),
        )
        cockpit = client.get(f"/api/v1/demo/cases/{confirmation_value['case_id']}")
        invalid = client.post(
            "/api/v1/feishu/card-actions",
            content=confirmation_body,
            headers={"content-type": "application/json"},
        )
        static_assets = b"".join(
            client.get(path).content
            for path in (
                "/demo",
                "/demo/cases/00000000-0000-4000-8000-000000000001",
                "/demo/assets/styles.css",
                "/demo/assets/app.js",
            )
        )

    core_view, audit_events, _ = SqliteCaseStoreFactory(tmp_path / "core.db").get_case_history(
        confirmation_value["case_id"]
    )
    assert core_view is not None and core_view.current_diagnosis is not None
    with FeishuCallbackStoreFactory(feishu.callback_db_path).session() as store:
        approval = store.find_approval_audit(
            case_id=confirmation_value["case_id"],
            diagnosis_id=confirmation_value["diagnosis_id"],
            action_kind="CONFIRM_REVIEW",
        )
    assert approval is not None
    serialized_models = json.dumps(
        {
            "case": core_view.model_dump(mode="json"),
            "audit": [event.model_dump(mode="json") for event in audit_events],
            "approval": asdict(approval),
        },
        ensure_ascii=True,
        sort_keys=True,
    ).encode()
    surfaces = (
        confirmation.content,
        cockpit.content,
        invalid.content,
        caplog.text.encode(),
        _database_artifacts(tmp_path / "core.db"),
        _database_artifacts(feishu.callback_db_path),
        serialized_models,
        static_assets,
    )
    for sentinel in (
        feishu.app_secret,
        feishu.verification_token,
        feishu.encrypt_key,
        raw_actor,
        "tenant_demo",
        feishu.demo_chat_id,
    ):
        encoded = sentinel.encode()
        assert all(encoded not in surface for surface in surfaces), sentinel

    assert confirmation.status_code == 200
    assert cockpit.status_code == 200
    assert invalid.status_code == 401
    assert core_view.current_diagnosis.synthetic is True
    assert approval.synthetic is True
