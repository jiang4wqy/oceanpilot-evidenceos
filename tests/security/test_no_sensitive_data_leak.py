"""Cross-surface sentinel: Feishu credentials and external IDs stay private."""

import json
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from tests.feishu.conftest import (
    APP_ID,
    APP_SECRET,
    CARD_PATH,
    ENCRYPT_KEY,
    EVENTS_PATH,
    TENANT_TOKEN,
    TOKEN,
    RecordingTransport,
    confirm_payload,
    evidence_payload,
    make_app,
    message_payload,
    sign,
    to_bytes,
)

CHAT_ID = "oc_security_chat"
REPORTER_ID = "ou_reporter_security_sentinel"
REVIEWER_ID = "ou_reviewer_security_sentinel"
_SENTINELS = (APP_SECRET, ENCRYPT_KEY, TOKEN, TENANT_TOKEN, CHAT_ID, REPORTER_ID, REVIEWER_ID)
_SENTINEL_BYTES = tuple(value.encode() for value in _SENTINELS)

FLOW_FACTS = (
    ("callback.delivery_status", "NOT_RECEIVED"),
    ("authentication.status", "REQUIRED"),
    ("transaction.reference", "txn_threeds_001"),
    ("transaction.occurred_at", "2026-08-05T04:00:00+00:00"),
    ("context.environment", "PROD"),
    ("symptom.status", "PENDING"),
    ("integration.type", "API"),
)


def _post(client, path, raw):
    return client.post(path, content=raw, headers=sign(raw))


def _database_artifacts(path: Path) -> tuple[Path, ...]:
    candidates = (path, Path(f"{path}-journal"), Path(f"{path}-wal"), Path(f"{path}-shm"))
    return tuple(candidate for candidate in candidates if candidate.exists())


def test_credentials_and_external_ids_never_appear_in_runtime_surfaces(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    responses: list[str] = []
    callback_bodies: list[bytes] = []
    with TestClient(app, raise_server_exceptions=False) as client:
        message_raw = to_bytes(
            message_payload(
                event_id="sec-msg",
                chat_id=CHAT_ID,
                text="synthetic payment incident",
                open_id=REPORTER_ID,
            )
        )
        callback_bodies.append(message_raw)
        message = _post(
            client,
            EVENTS_PATH,
            message_raw,
        )
        responses.append(message.text)
        case_id = message.json()["case_id"]

        diagnosis_id = None
        for index, (code, value) in enumerate(FLOW_FACTS):
            evidence_raw = to_bytes(
                evidence_payload(
                    event_id=f"sec-ev-{index}",
                    chat_id=CHAT_ID,
                    case_id=case_id,
                    evidence_id=f"00000000-0000-4000-8000-{index + 1:012d}",
                    evidence_code=code,
                    typed_value=value,
                    open_id=REPORTER_ID,
                )
            )
            callback_bodies.append(evidence_raw)
            resp = _post(
                client,
                CARD_PATH,
                evidence_raw,
            )
            responses.append(resp.text)
            if resp.json().get("diagnosis_id"):
                diagnosis_id = resp.json()["diagnosis_id"]

        confirmation_raw = to_bytes(
            confirm_payload(
                event_id="sec-confirm",
                chat_id=CHAT_ID,
                case_id=case_id,
                diagnosis_id=diagnosis_id,
                open_id=REVIEWER_ID,
            )
        )
        callback_bodies.append(confirmation_raw)
        confirm = _post(
            client,
            CARD_PATH,
            confirmation_raw,
        )
        responses.append(confirm.text)

        feishu_db = app.state.feishu_store_factory.db_path
        case_db = app.state.settings.db_path
        with app.state.feishu_store_factory.session() as store:
            approval_audit = store.get_approval_audit("sec-confirm")

    for body in responses:
        for sentinel in _SENTINELS:
            assert sentinel not in body

    for db_path in (feishu_db, case_db):
        for artifact in _database_artifacts(db_path):
            blob = artifact.read_bytes()
            for sentinel in _SENTINEL_BYTES:
                assert sentinel not in blob
            for callback_body in callback_bodies:
                assert callback_body not in blob

    # The outbound transport is the authorized chat-ID disclosure boundary: routing needs the
    # raw receive_id, but card content must not copy it and no actor/credential may leave.
    for message in transport.sent:
        serialized = json.dumps(message)
        for sentinel in (APP_SECRET, ENCRYPT_KEY, TOKEN, TENANT_TOKEN, REPORTER_ID, REVIEWER_ID):
            assert sentinel not in serialized
        assert message["receive_id"] == CHAT_ID
        assert CHAT_ID not in message["content"]
        for callback_body in callback_bodies:
            assert callback_body not in serialized.encode()

    # Hydrated audit values expose only the namespaced actor digest.
    assert approval_audit is not None
    serialized_audit = json.dumps(asdict(approval_audit))
    for sentinel in _SENTINELS:
        assert sentinel not in serialized_audit
    assert APP_ID  # sanity: fixture wiring is real
