from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sqlite3
import sys
from pathlib import Path
from time import time

from fastapi.testclient import TestClient

from oceanpilot.adapters.feishu.client import FeishuHttpRequest, FeishuHttpResponse
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.main import create_app

APP_ID = "fixture-app-id"
CHAT_ID = "oc_fixture_demo"
MERCHANT_REF = "merchant_fixture_demo"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "feishu" / "fixtures"


class SyntheticFeishuTransport:
    def __init__(self) -> None:
        self.requests: list[FeishuHttpRequest] = []

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        self.requests.append(request)
        if request.url.endswith("/tenant_access_token/internal"):
            body = {"code": 0, "tenant_access_token": "synthetic-access-token"}
        else:
            body = {
                "code": 0,
                "data": {"message_id": f"om_fixture_outbound_{len(self.requests)}"},
            }
        return FeishuHttpResponse(
            status_code=200,
            body=json.dumps(body, separators=(",", ":")).encode(),
        )


def _signed_headers(raw_body: bytes, *, encrypt_key: str) -> dict[str, str]:
    timestamp = str(int(time()))
    nonce = f"fixture-{timestamp}"
    signature = hashlib.sha256(f"{timestamp}{nonce}{encrypt_key}".encode() + raw_body).hexdigest()
    return {
        "content-type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def _message_body(*, verification_token: str) -> bytes:
    now_ms = str(int(time() * 1000))
    payload = json.loads((FIXTURE_ROOT / "message_received.json").read_text(encoding="utf-8"))
    payload["header"].update(
        {
            "event_id": "evt_fixture_message_001",
            "token": verification_token,
            "create_time": now_ms,
            "tenant_key": "tenant_fixture",
            "app_id": APP_ID,
        }
    )
    payload["event"]["sender"]["tenant_key"] = "tenant_fixture"
    payload["event"]["message"].update(
        {
            "message_id": "om_fixture_message_001",
            "root_id": "om_fixture_thread_001",
            "create_time": now_ms,
            "chat_id": CHAT_ID,
        }
    )
    return json.dumps(payload, separators=(",", ":")).encode()


def _action_body(
    *,
    event_id: str,
    actor_id: str,
    open_message_id: str,
    value: dict[str, object],
    verification_token: str,
) -> bytes:
    fixture_name = (
        "confirmation_action.json"
        if value.get("action_kind") == "confirm_review"
        else "evidence_action.json"
    )
    payload = json.loads((FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8"))
    payload["header"].update(
        {
            "event_id": event_id,
            "token": verification_token,
            "create_time": str(int(time() * 1000)),
            "tenant_key": "tenant_fixture",
            "app_id": APP_ID,
        }
    )
    payload["event"]["operator"]["open_id"] = actor_id
    payload["event"]["context"].update(
        {
            "open_message_id": open_message_id,
            "open_chat_id": CHAT_ID,
        }
    )
    payload["event"]["action"] = {"tag": "button", "value": value}
    return json.dumps(payload, separators=(",", ":")).encode()


def _last_card(transport: SyntheticFeishuTransport) -> dict[str, object]:
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


def _require_button_value(
    transport: SyntheticFeishuTransport,
    predicate,
    step: str,
) -> dict[str, object]:
    selected = next(
        (value for value in _button_values(_last_card(transport)) if predicate(value)),
        None,
    )
    if selected is None:
        raise RuntimeError(f"{step} card action was not available")
    return selected


def _require_http(response, expected: int, step: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{step} failed with HTTP {response.status_code}")


def run(work_dir: Path) -> dict[str, object]:
    if work_dir.exists() and any(work_dir.iterdir()):
        raise ValueError("work directory must be empty")
    work_dir.mkdir(parents=True, exist_ok=True)
    core_db = work_dir / "core.db"
    feishu_db = work_dir / "feishu.db"
    app_secret = secrets.token_hex(24)
    verification_token = secrets.token_hex(24)
    encrypt_key = secrets.token_hex(24)
    feishu = FeishuSettings(
        app_id=APP_ID,
        app_secret=app_secret,
        verification_token=verification_token,
        encrypt_key=encrypt_key,
        callback_db_path=feishu_db,
        demo_chat_id=CHAT_ID,
        demo_merchant_ref=MERCHANT_REF,
    )
    transport = SyntheticFeishuTransport()
    app = create_app(
        Settings(db_path=core_db, feishu=feishu),
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
        message_body = _message_body(verification_token=verification_token)
        opened = client.post(
            "/api/v1/feishu/events",
            content=message_body,
            headers=_signed_headers(message_body, encrypt_key=encrypt_key),
        )
        _require_http(opened, 200, "message callback")

        for index, expected_code in enumerate(expected_codes, start=1):
            selected = _require_button_value(
                transport,
                lambda value, code=expected_code: (
                    value.get("evidence_code") == code and value.get("typed_value") != "DECLINED"
                ),
                f"evidence {expected_code}",
            )
            action_body = _action_body(
                event_id=f"evt_fixture_evidence_{index:02d}",
                actor_id="ou_fixture_merchant",
                open_message_id=f"om_fixture_question_{index:02d}",
                value=selected,
                verification_token=verification_token,
            )
            submitted = client.post(
                "/api/v1/feishu/card-actions",
                content=action_body,
                headers=_signed_headers(action_body, encrypt_key=encrypt_key),
            )
            _require_http(submitted, 200, f"evidence callback {index}")

        confirmation_value = _require_button_value(
            transport,
            lambda value: value.get("action_kind") == "confirm_review",
            "confirmation",
        )
        before_confirmation = client.get(f"/api/v1/cases/{confirmation_value['case_id']}")
        _require_http(before_confirmation, 200, "pre-confirmation case")
        confirmation_body = _action_body(
            event_id="evt_fixture_confirmation_001",
            actor_id="ou_fixture_reviewer",
            open_message_id="om_fixture_diagnosis_001",
            value=confirmation_value,
            verification_token=verification_token,
        )
        confirmed = client.post(
            "/api/v1/feishu/card-actions",
            content=confirmation_body,
            headers=_signed_headers(confirmation_body, encrypt_key=encrypt_key),
        )
        _require_http(confirmed, 200, "confirmation callback")
        cockpit = client.get(f"/api/v1/demo/cases/{confirmation_value['case_id']}")
        _require_http(cockpit, 200, "cockpit")
        detail = cockpit.json()
        after_confirmation = client.get(f"/api/v1/cases/{confirmation_value['case_id']}")
        _require_http(after_confirmation, 200, "post-confirmation case")

    with sqlite3.connect(feishu_db) as connection:
        approval_count = connection.execute(
            "SELECT COUNT(*) FROM feishu_approval_audits"
        ).fetchone()[0]
    hypothesis = detail["diagnosis"]["hypotheses"][0]
    route = detail["diagnosis"]["routing"]
    return {
        "mode": "SIGNED_FIXTURE",
        "synthetic": detail["synthetic"],
        "message_http": opened.status_code,
        "evidence_steps": len(expected_codes),
        "cockpit_http": cockpit.status_code,
        "case_status": detail["case"]["status"],
        "matched_rule_id": hypothesis["rule_id"],
        "display_confidence": hypothesis["confidence_score"],
        "responsible_team": route["responsible_team"],
        "priority": route["priority"],
        "confirmation_state": detail["confirmation"]["state"],
        "case_unchanged_by_confirmation": (
            before_confirmation.json()["case"] == after_confirmation.json()["case"]
        ),
        "approval_audit_count": approval_count,
        "business_action_executed": False,
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
