"""Cross-surface sentinel: Feishu credentials never reach responses or storage."""

import json

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
_SECRETS = (APP_SECRET, ENCRYPT_KEY, TOKEN, TENANT_TOKEN)
_SECRET_BYTES = (APP_SECRET.encode(), ENCRYPT_KEY.encode(), TENANT_TOKEN.encode())

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


def test_credentials_never_appear_in_responses_or_databases(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    responses: list[str] = []
    with TestClient(app, raise_server_exceptions=False) as client:
        message = _post(
            client,
            EVENTS_PATH,
            to_bytes(message_payload(event_id="sec-msg", chat_id=CHAT_ID, text="hi")),
        )
        responses.append(message.text)
        case_id = message.json()["case_id"]

        diagnosis_id = None
        for index, (code, value) in enumerate(FLOW_FACTS):
            resp = _post(
                client,
                CARD_PATH,
                to_bytes(
                    evidence_payload(
                        event_id=f"sec-ev-{index}",
                        chat_id=CHAT_ID,
                        case_id=case_id,
                        evidence_id=f"00000000-0000-4000-8000-{index + 1:012d}",
                        evidence_code=code,
                        typed_value=value,
                    )
                ),
            )
            responses.append(resp.text)
            if resp.json().get("diagnosis_id"):
                diagnosis_id = resp.json()["diagnosis_id"]

        confirm = _post(
            client,
            CARD_PATH,
            to_bytes(
                confirm_payload(
                    event_id="sec-confirm",
                    chat_id=CHAT_ID,
                    case_id=case_id,
                    diagnosis_id=diagnosis_id,
                )
            ),
        )
        responses.append(confirm.text)

        feishu_db = app.state.feishu_store_factory.db_path
        case_db = app.state.settings.db_path

    for body in responses:
        for secret in _SECRETS:
            assert secret not in body

    for db_path in (feishu_db, case_db):
        blob = db_path.read_bytes()
        for secret in _SECRET_BYTES:
            assert secret not in blob

    # outbound card payloads must carry no credentials either
    for message in transport.sent:
        serialized = json.dumps(message)
        for secret in _SECRETS:
            assert secret not in serialized
    assert APP_ID  # sanity: fixture wiring is real
