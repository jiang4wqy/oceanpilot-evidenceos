"""Local demonstration shortcuts retain real authentication and origin checks."""

import json

from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def test_demo_shortcuts_are_local_opt_in_and_keep_role_sessions(tmp_path, monkeypatch):
    monkeypatch.delenv("OCEANPILOT_DEMO_ACCOUNTS", raising=False)
    with TestClient(
        create_app(Settings(db_path=tmp_path / "demo.db")), base_url="http://127.0.0.1"
    ) as client:
        endpoint = "/api/v2/session/demo-login"
        assert client.post(endpoint, json={"surface": "merchant"}).status_code == 404
        records = []
        for name, role in [("merchant-a", "MERCHANT"), ("operator-a", "OPERATOR")]:
            user = client.app.state.v21_auth.create_user(
                username=name,
                password="private-demo-password",
                display_name=name,
                role=role,
                merchant_ids=["merchant-a"],
                merchant_id="merchant-a" if role == "MERCHANT" else None,
            )
            records.append({"user": user, "password": "private-demo-password"})
        account_file = tmp_path / "accounts.json"
        account_file.write_text(json.dumps({"accounts": records}))
        monkeypatch.setenv("OCEANPILOT_DEMO_ACCOUNTS", str(account_file))
        page = client.get("/v2/login").text
        assert "private-demo-password" not in page
        assert 'id="quickLogin" hidden' not in page
        for surface, role in [("merchant", "MERCHANT"), ("operations", "OPERATOR")]:
            reply = client.post(endpoint, json={"surface": surface})
            assert reply.status_code == 200
            assert reply.json()["user"]["role"] == role
            assert client.get("/api/v2/session").json()["user"]["role"] == role
        assert client.post(endpoint, json={"surface": "governance"}).status_code == 422
        assert (
            client.post(
                endpoint,
                json={"surface": "merchant"},
                headers={"origin": "https://elsewhere.example"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                endpoint, json={"surface": "merchant"}, headers={"host": "external.example"}
            ).status_code
            == 404
        )
