from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sqlite3
import sys
from pathlib import Path
from time import time
from uuid import uuid4

from fastapi.testclient import TestClient

from oceanpilot.adapters.feishu.client import FeishuHttpRequest, FeishuHttpResponse
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.main import create_app

EVENTS_PATH = "/api/v1/integrations/feishu/events"
CARD_PATH = "/api/v1/integrations/feishu/card-actions"
FLOW_FACTS = (
    ("callback.delivery_status", "NOT_RECEIVED"),
    ("authentication.status", "REQUIRED"),
    ("transaction.reference", "txn_threeds_001"),
    ("transaction.occurred_at", "2026-08-05T04:00:00+00:00"),
    ("context.environment", "PROD"),
    ("symptom.status", "PENDING"),
    ("integration.type", "API"),
)

_LAST_SENSITIVE_VALUES: tuple[str, ...] = ()


class SyntheticFeishuTransport:
    def __init__(self, tenant_token: str) -> None:
        self.tenant_token = tenant_token
        self.requests: list[FeishuHttpRequest] = []
        self.cards: list[dict[str, object]] = []

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        self.requests.append(request)
        if request.url.endswith("/tenant_access_token/internal"):
            body: dict[str, object] = {
                "code": 0,
                "tenant_access_token": self.tenant_token,
                "expire": 7200,
            }
        elif "/im/v1/messages" in request.url:
            outbound = json.loads(request.body)
            self.cards.append(json.loads(outbound["content"]))
            body = {
                "code": 0,
                "data": {"message_id": f"om_synthetic_{len(self.cards)}"},
            }
        else:
            body = {"code": 0}
        return FeishuHttpResponse(
            status_code=200,
            body=json.dumps(body, separators=(",", ":")).encode(),
        )


def last_sensitive_values() -> tuple[str, ...]:
    return _LAST_SENSITIVE_VALUES


def _random_external(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _signed_headers(raw_body: bytes, *, encrypt_key: str) -> dict[str, str]:
    timestamp = str(int(time()))
    nonce = secrets.token_hex(12)
    signature = hashlib.sha256(f"{timestamp}{nonce}{encrypt_key}".encode() + raw_body).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def _raw(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _message_payload(
    *,
    event_id: str,
    chat_id: str,
    message_id: str,
    reporter_id: str,
    verification_token: str,
) -> dict[str, object]:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "token": verification_token,
        },
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": reporter_id},
            },
            "message": {
                "chat_id": chat_id,
                "message_id": message_id,
                "message_type": "text",
                "content": json.dumps(
                    {"text": "synthetic 3DS callback incident"},
                    separators=(",", ":"),
                ),
            },
        },
    }


def _action_payload(
    *,
    event_id: str,
    chat_id: str,
    actor_id: str,
    verification_token: str,
    value: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "card.action.trigger",
            "token": verification_token,
        },
        "event": {
            "operator": {"open_id": actor_id},
            "context": {"open_chat_id": chat_id},
            "action": {"tag": "button", "value": value},
        },
    }


def _post_signed(client: TestClient, path: str, body: bytes, *, encrypt_key: str):
    return client.post(
        path,
        content=body,
        headers=_signed_headers(body, encrypt_key=encrypt_key),
    )


def _require_http(response, expected: int, step: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{step} failed with HTTP {response.status_code}")


def _card_has_confirmation(card: object) -> bool:
    if isinstance(card, dict):
        value = card.get("value")
        if isinstance(value, dict) and value.get("action") == "confirm_review":
            return True
        return any(_card_has_confirmation(child) for child in card.values())
    if isinstance(card, list):
        return any(_card_has_confirmation(child) for child in card)
    return False


def run(work_dir: Path) -> dict[str, object]:
    global _LAST_SENSITIVE_VALUES

    if work_dir.exists() and any(work_dir.iterdir()):
        raise ValueError("work directory must be empty")
    work_dir.mkdir(parents=True, exist_ok=True)

    core_db = work_dir / "core.db"
    feishu_db = work_dir / "feishu.db"
    chargeback_db = work_dir / "chargeback.db"
    app_id = _random_external("cli")
    app_secret = secrets.token_hex(24)
    verification_token = secrets.token_hex(24)
    encrypt_key = secrets.token_hex(24)
    tenant_token = secrets.token_hex(24)
    chat_id = _random_external("oc")
    reporter_id = _random_external("ou")
    reviewer_id = _random_external("ou")
    message_id = _random_external("om")
    message_event_id = _random_external("evt")
    confirmation_event_id = _random_external("evt")
    _LAST_SENSITIVE_VALUES = (
        app_secret,
        verification_token,
        encrypt_key,
        tenant_token,
        chat_id,
        reporter_id,
        reviewer_id,
        message_id,
    )

    transport = SyntheticFeishuTransport(tenant_token)
    feishu = FeishuSettings(
        app_id=app_id,
        app_secret=app_secret,
        verification_token=verification_token,
        encrypt_key=encrypt_key,
        db_path=feishu_db,
    )
    app = create_app(
        Settings(
            db_path=core_db,
            chargeback_db_path=chargeback_db,
            feishu=feishu,
        ),
        feishu_transport=transport,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        message_body = _raw(
            _message_payload(
                event_id=message_event_id,
                chat_id=chat_id,
                message_id=message_id,
                reporter_id=reporter_id,
                verification_token=verification_token,
            )
        )
        opened = _post_signed(client, EVENTS_PATH, message_body, encrypt_key=encrypt_key)
        _require_http(opened, 200, "message callback")
        if opened.json().get("outcome") != "NEED_INFO":
            raise RuntimeError("message callback did not request evidence")
        case_id = opened.json()["case_id"]
        cards_after_message = len(transport.cards)
        replayed_message = _post_signed(client, EVENTS_PATH, message_body, encrypt_key=encrypt_key)
        _require_http(replayed_message, 200, "message replay")
        message_replay = (
            replayed_message.json() == opened.json() and len(transport.cards) == cards_after_message
        )
        if not message_replay:
            raise RuntimeError("message replay created a side effect")

        diagnosis_id: str | None = None
        for index, (code, typed_value) in enumerate(FLOW_FACTS, start=1):
            action_body = _raw(
                _action_payload(
                    event_id=_random_external("evt"),
                    chat_id=chat_id,
                    actor_id=reporter_id,
                    verification_token=verification_token,
                    value={
                        "action": "submit_evidence",
                        "case_id": case_id,
                        "evidence_id": str(uuid4()),
                        "evidence_code": code,
                        "availability": "AVAILABLE",
                        "typed_value": typed_value,
                        "source_ref": f"fixture:{code}",
                    },
                )
            )
            submitted = _post_signed(client, CARD_PATH, action_body, encrypt_key=encrypt_key)
            _require_http(submitted, 200, f"evidence callback {index}")
            expected_outcome = "DIAGNOSED" if index == len(FLOW_FACTS) else "NEED_INFO"
            if submitted.json().get("outcome") != expected_outcome:
                raise RuntimeError(f"evidence callback {index} had an unexpected outcome")
            diagnosis_id = submitted.json().get("diagnosis_id", diagnosis_id)

        if (
            not diagnosis_id
            or not transport.cards
            or not _card_has_confirmation(transport.cards[-1])
        ):
            raise RuntimeError("diagnosis confirmation card was not emitted")

        before = client.get(f"/api/v1/cases/{case_id}")
        _require_http(before, 200, "pre-confirmation case")
        confirmation_body = _raw(
            _action_payload(
                event_id=confirmation_event_id,
                chat_id=chat_id,
                actor_id=reviewer_id,
                verification_token=verification_token,
                value={
                    "action": "confirm_review",
                    "case_id": case_id,
                    "diagnosis_id": diagnosis_id,
                },
            )
        )
        confirmed = _post_signed(client, CARD_PATH, confirmation_body, encrypt_key=encrypt_key)
        _require_http(confirmed, 200, "confirmation callback")
        cards_after_confirmation = len(transport.cards)
        replayed_confirmation = _post_signed(
            client, CARD_PATH, confirmation_body, encrypt_key=encrypt_key
        )
        _require_http(replayed_confirmation, 200, "confirmation replay")
        confirmation_replay = (
            replayed_confirmation.json() == confirmed.json()
            and len(transport.cards) == cards_after_confirmation
        )
        if not confirmation_replay:
            raise RuntimeError("confirmation replay created a side effect")
        after = client.get(f"/api/v1/cases/{case_id}")
        _require_http(after, 200, "post-confirmation case")

    detail = after.json()
    diagnosis = detail["current_diagnosis"]
    hypothesis = diagnosis["hypotheses"][0]
    route = diagnosis["routing_decision"]
    with sqlite3.connect(feishu_db) as connection:
        approval_count = connection.execute(
            "SELECT COUNT(*) FROM feishu_approval_audits"
        ).fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM feishu_event_receipts").fetchone()[0]
        action_count = connection.execute("SELECT COUNT(*) FROM feishu_action_receipts").fetchone()[
            0
        ]
    if approval_count != 1 or event_count != 8 or action_count != 1:
        raise RuntimeError("receipt or approval counts were not idempotent")

    return {
        "approval_audit_count": approval_count,
        "business_action_executed": False,
        "case_status": detail["case"]["status"],
        "case_unchanged_by_confirmation": before.json() == after.json(),
        "confirmation_replay": confirmation_replay,
        "confirmation_state": confirmed.json()["outcome"],
        "display_confidence": str(hypothesis["confidence_score"]),
        "evidence_steps": len(FLOW_FACTS),
        "matched_rule_id": hypothesis["rule_id"],
        "message_replay": message_replay,
        "mode": "SIGNED_FIXTURE",
        "outbound_cards": len(transport.cards),
        "priority": route["priority"],
        "responsible_team": route["responsible_team"],
        "synthetic": detail["case"]["synthetic"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the signed synthetic Feishu fallback")
    parser.add_argument("--work-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        summary = run(arguments.work_dir.resolve())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("SYNTHETIC SIGNED FEISHU FIXTURE -- no external Feishu or business action")
    print(json.dumps(summary, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
