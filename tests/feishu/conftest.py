import hashlib
import json
import time
from pathlib import Path

from oceanpilot.adapters.feishu.client import FeishuHttpRequest, FeishuHttpResponse
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.main import create_app

TOKEN = "synthetic-verification-token"
ENCRYPT_KEY = "synthetic-encrypt-key"
APP_ID = "cli_synthetic_app"
APP_SECRET = "synthetic-app-secret"
TENANT_TOKEN = "t-synthetic-tenant-token"

EVENTS_PATH = "/api/v1/integrations/feishu/events"
CARD_PATH = "/api/v1/integrations/feishu/card-actions"

FIXTURES = Path(__file__).parent / "fixtures"


class RecordingTransport:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.fail_send = fail_send
        self.token_calls = 0
        self.sent: list[dict] = []

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        if request.url.endswith("/tenant_access_token/internal"):
            self.token_calls += 1
            return _json_response(
                {"code": 0, "tenant_access_token": TENANT_TOKEN, "expire": 7200}
            )
        if "/im/v1/messages" in request.url:
            if self.fail_send:
                raise RuntimeError("network down")
            body = json.loads(request.body)
            self.sent.append(body)
            return _json_response(
                {"code": 0, "data": {"message_id": f"om_sent_{len(self.sent)}"}}
            )
        return _json_response({"code": 0})


def _json_response(payload: object, status: int = 200) -> FeishuHttpResponse:
    return FeishuHttpResponse(
        status_code=status, body=json.dumps(payload).encode()
    )


def make_app(
    tmp_path: Path,
    transport: RecordingTransport,
    *,
    token: str = TOKEN,
    encrypt_key: str = ENCRYPT_KEY,
    with_feishu: bool = True,
):
    feishu = None
    if with_feishu:
        feishu = FeishuSettings(
            app_id=APP_ID,
            app_secret=APP_SECRET,
            verification_token=token,
            encrypt_key=encrypt_key,
            db_path=tmp_path / "feishu.db",
        )
    settings = Settings(db_path=tmp_path / "cases.db", feishu=feishu)
    return create_app(settings, feishu_transport=transport)


def sign(
    raw: bytes,
    *,
    timestamp: int | None = None,
    nonce: str = "nonce-synthetic",
    encrypt_key: str = ENCRYPT_KEY,
) -> dict[str, str]:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    signature = hashlib.sha256(
        f"{ts}{nonce}{encrypt_key}".encode() + raw
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Lark-Request-Timestamp": ts,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def to_bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def message_payload(
    *,
    event_id: str,
    chat_id: str,
    text: str,
    sender_type: str = "user",
    open_id: str = "ou_reporter_0001",
) -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "token": TOKEN,
        },
        "event": {
            "sender": {"sender_id": {"open_id": open_id}, "sender_type": sender_type},
            "message": {
                "chat_id": chat_id,
                "message_id": f"om_{event_id}",
                "message_type": "text",
                "content": json.dumps({"text": text}),
            },
        },
    }


def evidence_payload(
    *,
    event_id: str,
    chat_id: str,
    case_id: str,
    evidence_id: str,
    evidence_code: str,
    typed_value: object,
    availability: str = "AVAILABLE",
    open_id: str = "ou_reporter_0001",
) -> dict:
    value = {
        "action": "submit_evidence",
        "case_id": case_id,
        "evidence_id": evidence_id,
        "evidence_code": evidence_code,
        "availability": availability,
        "source_ref": f"feishu:{evidence_code}",
    }
    if typed_value is not None:
        value["typed_value"] = typed_value
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "card.action.trigger",
            "token": TOKEN,
        },
        "event": {
            "operator": {"open_id": open_id},
            "context": {"open_chat_id": chat_id},
            "action": {"tag": "button", "value": value},
        },
    }


def confirm_payload(
    *,
    event_id: str,
    chat_id: str,
    case_id: str,
    diagnosis_id: str,
    open_id: str = "ou_reviewer_0001",
) -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "card.action.trigger",
            "token": TOKEN,
        },
        "event": {
            "operator": {"open_id": open_id},
            "context": {"open_chat_id": chat_id},
            "action": {
                "tag": "button",
                "value": {
                    "action": "confirm_review",
                    "case_id": case_id,
                    "diagnosis_id": diagnosis_id,
                },
            },
        },
    }
