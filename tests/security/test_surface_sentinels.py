import hashlib
import json
import logging
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from time import time

from fastapi.testclient import TestClient

from examples import signed_fixture_demo
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.adapters.persistence.sqlite import SqliteCaseStoreFactory
from oceanpilot.config import FeishuSettings, Settings
from oceanpilot.main import create_app


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


def test_signed_fixture_material_is_absent_from_combined_runtime_surfaces(
    tmp_path,
    caplog,
    capsys,
    monkeypatch,
):
    work_dir = tmp_path / "combined-sentinel"
    monkeypatch.setattr(
        sys,
        "argv",
        ["signed_fixture_demo.py", "--work-dir", str(work_dir)],
    )

    with caplog.at_level(logging.DEBUG):
        assert signed_fixture_demo.main() == 0
    captured = capsys.readouterr()
    forbidden = signed_fixture_demo.last_sensitive_values()
    assert forbidden

    core_db = work_dir / "core.db"
    feishu_db = work_dir / "feishu.db"
    chargeback_db = work_dir / "chargeback.db"
    with sqlite3.connect(core_db) as connection:
        case_id = connection.execute("SELECT case_id FROM cases").fetchone()[0]
    with sqlite3.connect(feishu_db) as connection:
        action_id = connection.execute("SELECT action_id FROM feishu_approval_audits").fetchone()[0]

    with SqliteCaseStoreFactory(core_db)() as store:
        case_view = store.get_case_view(case_id)
    with FeishuCallbackStoreFactory(feishu_db).session() as store:
        approval = store.get_approval_audit(action_id)
    assert case_view is not None and case_view.current_diagnosis is not None
    assert approval is not None

    app = create_app(Settings(db_path=core_db, chargeback_db_path=chargeback_db))
    with TestClient(app, raise_server_exceptions=False) as client:
        payment_response = client.get(f"/api/v1/cases/{case_id}")
        problem_response = client.get("/api/v1/cases/00000000-0000-4000-8000-000000000999")
        chargeback_response = client.post(
            "/api/v1/chargeback/cases",
            json={"description": "synthetic product not received"},
        )
        chargeback_audit = client.get(
            f"/api/v1/chargeback/cases/{chargeback_response.json()['case_id']}/audit"
        )
        demo_html = client.get("/demo")
        payment_demo_html = client.get("/demo/payment-incident")

    assert payment_response.status_code == 200
    assert problem_response.status_code == 404
    assert chargeback_response.status_code == 201
    assert chargeback_audit.status_code == 200
    serialized_models = json.dumps(
        {
            "payment_case": case_view.model_dump(mode="json"),
            "approval": asdict(approval),
            "chargeback": chargeback_response.json(),
            "chargeback_audit": chargeback_audit.json(),
        },
        ensure_ascii=True,
        sort_keys=True,
    ).encode()
    surfaces = (
        captured.out.encode(),
        captured.err.encode(),
        caplog.text.encode(),
        payment_response.content,
        problem_response.content,
        chargeback_response.content,
        chargeback_audit.content,
        demo_html.content,
        payment_demo_html.content,
        serialized_models,
        _database_artifacts(core_db),
        _database_artifacts(feishu_db),
        _database_artifacts(chargeback_db),
    )
    for value in forbidden:
        assert value
        encoded = value.encode()
        assert all(encoded not in surface for surface in surfaces), value


def test_rejected_callback_body_canary_leaves_no_runtime_residue(
    tmp_path,
    caplog,
):
    canary = "Authorization: Bearer CALLBACK-BODY-CANARY"
    verification_token = "synthetic-verification-token"
    encrypt_key = "synthetic-encrypt-key"
    timestamp = str(int(time()))
    nonce = "synthetic-nonce"
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": "evt-sensitive-canary",
            "event_type": "im.message.receive_v1",
            "token": verification_token,
        },
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": "ou-sensitive-canary"},
            },
            "message": {
                "chat_id": "oc-sensitive-canary",
                "message_id": "om-sensitive-canary",
                "message_type": "text",
                "content": json.dumps({"text": canary}, separators=(",", ":")),
            },
        },
    }
    raw_body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = hashlib.sha256(f"{timestamp}{nonce}{encrypt_key}".encode() + raw_body).hexdigest()
    core_db = tmp_path / "core.db"
    feishu_db = tmp_path / "feishu.db"
    chargeback_db = tmp_path / "chargeback.db"
    app = create_app(
        Settings(
            db_path=core_db,
            chargeback_db_path=chargeback_db,
            feishu=FeishuSettings(
                app_id="cli-sensitive-canary",
                app_secret="synthetic-app-secret",
                verification_token=verification_token,
                encrypt_key=encrypt_key,
                db_path=feishu_db,
            ),
        )
    )

    with (
        caplog.at_level(logging.DEBUG),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post(
            "/api/v1/integrations/feishu/events",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Lark-Request-Timestamp": timestamp,
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": signature,
            },
        )

    assert response.status_code == 500
    surfaces = (
        response.content,
        caplog.text.encode(),
        _database_artifacts(core_db),
        _database_artifacts(feishu_db),
        _database_artifacts(chargeback_db),
    )
    assert all(canary.encode() not in surface for surface in surfaces)
