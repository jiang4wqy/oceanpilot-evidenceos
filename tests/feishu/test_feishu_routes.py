import json
import time

from fastapi.testclient import TestClient

from tests.feishu.conftest import (
    APP_SECRET,
    CARD_PATH,
    ENCRYPT_KEY,
    EVENTS_PATH,
    TENANT_TOKEN,
    TOKEN,
    RecordingTransport,
    confirm_payload,
    evidence_payload,
    load_fixture,
    make_app,
    message_payload,
    sign,
    to_bytes,
)

CHAT_ID = "oc_case_chat_flow"

# integration.type is submitted last so readiness (and diagnosis) fires only then.
FLOW_FACTS = (
    ("callback.delivery_status", "NOT_RECEIVED"),
    ("authentication.status", "REQUIRED"),
    ("transaction.reference", "txn_threeds_001"),
    ("transaction.occurred_at", "2026-08-05T04:00:00+00:00"),
    ("context.environment", "PROD"),
    ("symptom.status", "PENDING"),
    ("integration.type", "API"),
)


def _post(client, path, raw, *, extra_headers=None):
    headers = sign(raw)
    if extra_headers:
        headers.update(extra_headers)
    return client.post(path, content=raw, headers=headers)


def _button_values(value):
    found = []
    if isinstance(value, dict):
        if value.get("tag") == "button" and isinstance(value.get("value"), dict):
            found.append(value["value"])
        for child in value.values():
            found.extend(_button_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_button_values(child))
    return found


def _card_action_payload(*, event_id, chat_id, value):
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "card.action.trigger",
            "token": TOKEN,
        },
        "event": {
            "operator": {"open_id": "ou_reporter_0001"},
            "context": {"open_chat_id": chat_id},
            "action": {"tag": "button", "value": value},
        },
    }


def test_url_verification_returns_challenge(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    with TestClient(app, raise_server_exceptions=False) as client:
        raw = load_fixture("url_verification.json")
        response = _post(client, EVENTS_PATH, raw)
    assert response.status_code == 200
    assert response.json() == {"challenge": "synthetic-challenge-abc123"}
    assert transport.sent == []


def test_full_message_to_confirmation_flow(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    with TestClient(app, raise_server_exceptions=False) as client:
        message = _post(
            client,
            EVENTS_PATH,
            to_bytes(
                message_payload(event_id="evt-msg-1", chat_id=CHAT_ID, text="回调一直没有收到")
            ),
        )
        assert message.status_code == 200
        assert message.json()["outcome"] == "NEED_INFO"
        case_id = message.json()["case_id"]

        last = None
        for index, (code, value) in enumerate(FLOW_FACTS):
            raw = to_bytes(
                evidence_payload(
                    event_id=f"evt-ev-{index}",
                    chat_id=CHAT_ID,
                    case_id=case_id,
                    evidence_id=f"00000000-0000-4000-8000-{index + 1:012d}",
                    evidence_code=code,
                    typed_value=value,
                )
            )
            last = _post(client, CARD_PATH, raw)
            assert last.status_code == 200

        assert last.json()["outcome"] == "DIAGNOSED"
        diagnosis_id = last.json()["diagnosis_id"]

        confirm = _post(
            client,
            CARD_PATH,
            to_bytes(
                confirm_payload(
                    event_id="evt-confirm-1",
                    chat_id=CHAT_ID,
                    case_id=case_id,
                    diagnosis_id=diagnosis_id,
                )
            ),
        )
        assert confirm.status_code == 200
        assert confirm.json()["outcome"] == "CONFIRMED"

        with app.state.feishu_store_factory.session() as store:
            audit = store.get_approval_audit("evt-confirm-1")
        assert audit is not None
        assert audit.result == "CONFIRMED"
        assert audit.case_id == case_id
        assert audit.diagnosis_id == diagnosis_id
        assert audit.synthetic is True

    # a diagnosis card carrying the confirm button was sent to the chat
    contents = [json.loads(msg["content"]) for msg in transport.sent]
    assert any("confirm_review" in json.dumps(card) for card in contents)


def test_user_can_complete_synthetic_demo_from_actual_card_buttons(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)

    with TestClient(app, raise_server_exceptions=False) as client:
        message = _post(
            client,
            EVENTS_PATH,
            to_bytes(
                message_payload(
                    event_id="ui-msg-1",
                    chat_id=CHAT_ID,
                    text="3DS 验证后支付一直停在处理中，回调也没有收到",
                )
            ),
        )
        assert message.status_code == 200
        assert message.json()["outcome"] == "NEED_INFO"
        case_id = message.json()["case_id"]

        last = None
        submitted_codes = []
        for index in range(7):
            card = json.loads(transport.sent[-1]["content"])
            actions = [
                value for value in _button_values(card) if value.get("action") == "submit_evidence"
            ]
            assert len(actions) == 1
            action = actions[0]
            assert action["case_id"] == case_id
            assert set(action) == {
                "action",
                "case_id",
                "evidence_id",
                "evidence_code",
                "availability",
                "typed_value",
                "source_ref",
            }
            assert action["availability"] == "AVAILABLE"
            assert action["source_ref"] == (f"feishu:synthetic-demo:{action['evidence_code']}")
            submitted_codes.append(action["evidence_code"])

            raw = to_bytes(
                _card_action_payload(
                    event_id=f"ui-evidence-{index}",
                    chat_id=CHAT_ID,
                    value=action,
                )
            )
            last = _post(client, CARD_PATH, raw)
            assert last.status_code == 200

            if index == 0:
                revision_after_first = client.get(f"/api/v1/cases/{case_id}").json()["case"][
                    "evidence_revision"
                ]
                replay = _post(client, CARD_PATH, raw)
                assert replay.json() == last.json()
                assert (
                    client.get(f"/api/v1/cases/{case_id}").json()["case"]["evidence_revision"]
                    == revision_after_first
                )

                second_event = to_bytes(
                    _card_action_payload(
                        event_id="ui-evidence-0-second-click",
                        chat_id=CHAT_ID,
                        value=action,
                    )
                )
                second_click = _post(client, CARD_PATH, second_event)
                assert second_click.status_code == 200
                assert (
                    client.get(f"/api/v1/cases/{case_id}").json()["case"]["evidence_revision"]
                    == revision_after_first
                )

        assert submitted_codes == [code for code, _ in FLOW_FACTS]
        assert last is not None
        assert last.json()["outcome"] == "DIAGNOSED"
        diagnosis_id = last.json()["diagnosis_id"]

        diagnosis_card = json.loads(transport.sent[-1]["content"])
        confirmation_actions = [
            value
            for value in _button_values(diagnosis_card)
            if value.get("action") == "confirm_review"
        ]
        assert confirmation_actions == [
            {
                "action": "confirm_review",
                "case_id": case_id,
                "diagnosis_id": diagnosis_id,
            }
        ]
        case_before_confirmation = client.get(f"/api/v1/cases/{case_id}").json()
        confirm_raw = to_bytes(
            _card_action_payload(
                event_id="ui-confirm-1",
                chat_id=CHAT_ID,
                value=confirmation_actions[0],
            )
        )
        confirm = _post(client, CARD_PATH, confirm_raw)
        confirm_replay = _post(client, CARD_PATH, confirm_raw)
        case_after_confirmation = client.get(f"/api/v1/cases/{case_id}").json()

        assert confirm.status_code == 200
        assert confirm.json()["outcome"] == "CONFIRMED"
        assert confirm_replay.json() == confirm.json()
        assert case_after_confirmation == case_before_confirmation
        with app.state.feishu_store_factory.session() as store:
            audit = store.get_approval_audit("ui-confirm-1")
        assert audit is not None
        assert audit.result == "CONFIRMED"


def test_duplicate_event_replays_without_second_case(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = to_bytes(message_payload(event_id="evt-dup", chat_id=CHAT_ID, text="dup"))
    with TestClient(app, raise_server_exceptions=False) as client:
        first = _post(client, EVENTS_PATH, raw)
        second = _post(client, EVENTS_PATH, raw)
        assert first.json()["case_id"] == second.json()["case_id"]
        with app.state.feishu_store_factory.session() as store:
            bound = store.get_chat_case(CHAT_ID)
    assert first.status_code == second.status_code == 200
    assert bound == first.json()["case_id"]


def test_duplicate_event_id_with_different_verified_payload_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    first_raw = to_bytes(message_payload(event_id="evt-conflict", chat_id=CHAT_ID, text="one"))
    second_raw = json.dumps(json.loads(first_raw), indent=2).encode()

    with TestClient(app, raise_server_exceptions=False) as client:
        first = _post(client, EVENTS_PATH, first_raw)
        second = _post(client, EVENTS_PATH, second_raw)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json() == {"code": 409, "msg": "conflict"}


def test_bot_message_creates_no_case(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = to_bytes(
        message_payload(event_id="evt-bot", chat_id=CHAT_ID, text="loop", sender_type="app")
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post(client, EVENTS_PATH, raw)
        with app.state.feishu_store_factory.session() as store:
            bound = store.get_chat_case(CHAT_ID)
    assert response.status_code == 200
    assert bound is None
    assert transport.sent == []


def test_unknown_event_type_is_acked_without_case(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    payload = message_payload(event_id="evt-x", chat_id=CHAT_ID, text="x")
    payload["header"]["event_type"] = "im.chat.updated_v1"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post(client, EVENTS_PATH, to_bytes(payload))
        with app.state.feishu_store_factory.session() as store:
            bound = store.get_chat_case(CHAT_ID)
    assert response.status_code == 200
    assert bound is None


def test_invalid_signature_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = to_bytes(message_payload(event_id="evt-sig", chat_id=CHAT_ID, text="x"))
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = sign(raw)
        headers["X-Lark-Signature"] = "0" * 64
        response = client.post(EVENTS_PATH, content=raw, headers=headers)
        with app.state.feishu_store_factory.session() as store:
            bound = store.get_chat_case(CHAT_ID)
    assert response.status_code == 401
    assert bound is None


def test_invalid_token_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    payload = message_payload(event_id="evt-tok", chat_id=CHAT_ID, text="x")
    payload["header"]["token"] = "wrong-token"
    raw = to_bytes(payload)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post(client, EVENTS_PATH, raw)
    assert response.status_code == 401


def test_expired_timestamp_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = to_bytes(message_payload(event_id="evt-exp", chat_id=CHAT_ID, text="x"))
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = sign(raw, timestamp=int(time.time()) - 400)
        response = client.post(EVENTS_PATH, content=raw, headers=headers)
    assert response.status_code == 401


def test_oversized_body_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = b'{"padding":"' + b"a" * (64 * 1024 + 10) + b'"}'
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(EVENTS_PATH, content=raw, headers=sign(raw))
    assert response.status_code == 413


def test_wrong_content_type_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = to_bytes(message_payload(event_id="evt-ct", chat_id=CHAT_ID, text="x"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post(client, EVENTS_PATH, raw, extra_headers={"Content-Type": "text/plain"})
    assert response.status_code == 415


def test_malformed_json_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = b'{"header": {'  # valid bytes, invalid JSON
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(EVENTS_PATH, content=raw, headers=sign(raw))
    assert response.status_code == 401


def test_feishu_disabled_returns_fixed_503(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport, with_feishu=False)
    raw = to_bytes(message_payload(event_id="evt-off", chat_id=CHAT_ID, text="x"))
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = _post(client, EVENTS_PATH, raw)
    assert response.status_code == 503
    assert response.json() == {"code": 503, "msg": "feishu integration unavailable"}


def test_outbound_failure_still_records_case(tmp_path):
    transport = RecordingTransport(fail_send=True)
    app = make_app(tmp_path, transport)
    raw = to_bytes(message_payload(event_id="evt-out", chat_id=CHAT_ID, text="x"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post(client, EVENTS_PATH, raw)
        with app.state.feishu_store_factory.session() as store:
            bound = store.get_chat_case(CHAT_ID)
    assert response.status_code == 200
    assert bound == response.json()["case_id"]


def _drive_to_confirmable(client, chat_id, prefix):
    message = _post(
        client,
        EVENTS_PATH,
        to_bytes(message_payload(event_id=f"{prefix}-msg", chat_id=chat_id, text="x")),
    )
    case_id = message.json()["case_id"]
    last = None
    for index, (code, value) in enumerate(FLOW_FACTS):
        raw = to_bytes(
            evidence_payload(
                event_id=f"{prefix}-ev-{index}",
                chat_id=chat_id,
                case_id=case_id,
                evidence_id=f"00000000-0000-4000-8000-{index + 1:012d}",
                evidence_code=code,
                typed_value=value,
            )
        )
        last = _post(client, CARD_PATH, raw)
    return case_id, last.json()["diagnosis_id"]


def test_second_confirmation_of_same_diagnosis_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    chat = "oc_double_confirm"
    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, diagnosis_id = _drive_to_confirmable(client, chat, "dc")
        first = _post(
            client,
            CARD_PATH,
            to_bytes(
                confirm_payload(
                    event_id="dc-confirm-1",
                    chat_id=chat,
                    case_id=case_id,
                    diagnosis_id=diagnosis_id,
                )
            ),
        )
        second = _post(
            client,
            CARD_PATH,
            to_bytes(
                confirm_payload(
                    event_id="dc-confirm-2",
                    chat_id=chat,
                    case_id=case_id,
                    diagnosis_id=diagnosis_id,
                )
            ),
        )
        with app.state.feishu_store_factory.session() as store:
            first_audit = store.get_approval_audit("dc-confirm-1")
            second_audit = store.get_approval_audit("dc-confirm-2")
    assert first.json()["outcome"] == "CONFIRMED"
    assert second.status_code == 409
    assert first_audit is not None
    assert second_audit is None


def test_identical_confirmation_callback_replays_without_duplicate_card_or_audit(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    chat = "oc_confirmation_replay"
    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, diagnosis_id = _drive_to_confirmable(client, chat, "cr")
        raw = to_bytes(
            confirm_payload(
                event_id="cr-confirm",
                chat_id=chat,
                case_id=case_id,
                diagnosis_id=diagnosis_id,
            )
        )
        first = _post(client, CARD_PATH, raw)
        sent_after_first = len(transport.sent)
        with app.state.feishu_store_factory.session() as store:
            audit_after_first = store.get_approval_audit("cr-confirm")

        second = _post(client, CARD_PATH, raw)
        with app.state.feishu_store_factory.session() as store:
            audit_after_second = store.get_approval_audit("cr-confirm")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["outcome"] == "CONFIRMED"
    assert len(transport.sent) == sent_after_first
    assert audit_after_first is not None
    assert audit_after_second == audit_after_first


def test_confirmation_id_with_different_verified_bytes_is_rejected(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    chat = "oc_confirmation_payload_conflict"
    with TestClient(app, raise_server_exceptions=False) as client:
        case_id, diagnosis_id = _drive_to_confirmable(client, chat, "cpc")
        first_raw = to_bytes(
            confirm_payload(
                event_id="cpc-confirm",
                chat_id=chat,
                case_id=case_id,
                diagnosis_id=diagnosis_id,
            )
        )
        second_raw = json.dumps(json.loads(first_raw), indent=2).encode()

        first = _post(client, CARD_PATH, first_raw)
        second = _post(client, CARD_PATH, second_raw)

    assert first.status_code == 200
    assert first.json()["outcome"] == "CONFIRMED"
    assert second.status_code == 409
    assert second.json() == {"code": 409, "msg": "conflict"}


def test_responses_and_database_never_leak_secrets(tmp_path):
    transport = RecordingTransport()
    app = make_app(tmp_path, transport)
    raw = to_bytes(message_payload(event_id="evt-leak", chat_id=CHAT_ID, text="x"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _post(client, EVENTS_PATH, raw)
        feishu_db = app.state.feishu_store_factory.db_path
    body = response.text
    for secret in (APP_SECRET, ENCRYPT_KEY, TOKEN, TENANT_TOKEN):
        assert secret not in body
    database_bytes = feishu_db.read_bytes()
    for secret in (APP_SECRET.encode(), ENCRYPT_KEY.encode(), TENANT_TOKEN.encode()):
        assert secret not in database_bytes
