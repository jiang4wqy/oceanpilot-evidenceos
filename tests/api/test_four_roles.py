"""Four-role authority, team visibility, immutable history and upgrade regressions."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.persistence.dispute_identity import SQLiteDisputeIdentity
from oceanpilot.adapters.persistence.dispute_queue import DisputeQueueReader
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_access import DisputeAccessPolicy
from oceanpilot.application.disputes import DisputeService
from oceanpilot.config import Settings
from oceanpilot.domain.dispute import ACCOUNT_ROLES, ACTION_ROLES, DisputeError
from oceanpilot.main import create_app
from tests.workflow.test_dispute_engine import NOW, intake_command, reconciled, reviewed, run

PASSWORD = "four-role-regression-password"


def user(auth, name, role, merchants=()):
    return auth.create_user(
        username=name,
        password=PASSWORD,
        display_name=name,
        role=role,
        user_id=name,
        merchant_ids=list(merchants),
        merchant_id=merchants[0] if role == "MERCHANT" else None,
    )


@pytest.mark.parametrize("old,new", [("RISK_OFFICER", "OPERATOR"), ("DIRECTOR", "ADMIN")])
def test_account_upgrade_preserves_credentials_and_revokes_only_legacy_sessions(tmp_path, old, new):
    path = tmp_path / "accounts.db"
    auth = SQLiteDisputeIdentity(path)
    user(auth, "migrated", new, ["merchant-a"])
    user(auth, "unchanged", "MERCHANT", ["merchant-a"])
    legacy_token, _ = auth.login("migrated", PASSWORD)
    merchant_token, _ = auth.login("unchanged", PASSWORD)
    with sqlite3.connect(path) as db:
        before = db.execute(
            "SELECT password_hash,merchant_ids FROM v21_users WHERE user_id='migrated'"
        ).fetchone()
        db.execute("UPDATE v21_users SET role=? WHERE user_id='migrated'", (old,))
    migrated = SQLiteDisputeIdentity(path)
    with pytest.raises(DisputeError):
        migrated.resolve(legacy_token)
    assert migrated.resolve(merchant_token)["role"] == "MERCHANT"
    token, account = migrated.login("migrated", PASSWORD)
    assert account["role"] == new and account["merchant_ids"] == ["merchant-a"]
    assert SQLiteDisputeIdentity(path).resolve(token)["role"] == new
    with sqlite3.connect(path) as db:
        assert (
            db.execute(
                "SELECT password_hash,merchant_ids FROM v21_users WHERE user_id='migrated'"
            ).fetchone()
            == before
        )
    with pytest.raises(DisputeError, match="不支持"):
        user(migrated, "forbidden", old, ["merchant-a"])


def test_case_migration_keeps_historical_roles_and_receipts(tmp_path):
    path = tmp_path / "case.db"
    store = SQLiteDisputeStore(path)
    service = DisputeService(store, clock=lambda: NOW)
    case = service.execute(intake_command(), {"role": "OPERATOR", "actor_id": "handler"})["case"]
    case["participants"] = [{"user_id": "legacy", "role": "RISK_OFFICER"}]
    case["tasks"] = [
        {"id": "active", "owner": "RISK_OFFICER", "status": "OPEN", "assignee": "legacy"},
        {"id": "done", "owner": "RISK_OFFICER", "status": "COMPLETED"},
    ]
    case["reviews"] = [{"role": "RISK_OFFICER", "reviewer": "legacy"}]
    with sqlite3.connect(path) as db:
        receipts = db.execute("SELECT * FROM v2_dispute_commands").fetchall()
        db.execute("UPDATE v2_dispute_cases SET snapshot=?", (json.dumps(case),))
    upgraded = SQLiteDisputeStore(path).get_case(case["id"])
    assert upgraded["revision"] == case["revision"] + 1
    assert upgraded["tasks"][0]["owner"] == "OPERATOR"
    assert upgraded["tasks"][0]["assignee"] == "legacy"
    assert upgraded["tasks"][1]["owner"] == "RISK_OFFICER"
    assert upgraded["reviews"] == case["reviews"]
    assert upgraded["audit"][:-1] == case["audit"]
    assert SQLiteDisputeStore(path).get_case(case["id"]) == upgraded
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM v2_dispute_commands").fetchall() == receipts


def test_team_visibility_assignment_and_full_dataset_totals(tmp_path):
    path = tmp_path / "team.db"
    auth = SQLiteDisputeIdentity(path)
    for name, role, scopes in [
        ("officer-a", "OPERATOR", ["merchant-a"]),
        ("officer-b", "OPERATOR", ["merchant-b"]),
        ("manager", "SUPERVISOR", []),
        ("admin", "ADMIN", []),
        ("merchant", "MERCHANT", ["merchant-a"]),
    ]:
        user(auth, name, role, scopes)
    policy = DisputeAccessPolicy(auth)
    service = DisputeService(SQLiteDisputeStore(path), access_policy=policy, clock=lambda: NOW)
    officer_a = {"role": "OPERATOR", "actor_id": "officer-a"}
    officer_b = {"role": "OPERATOR", "actor_id": "officer-b"}
    first = service.execute(intake_command(), officer_a)["case"]
    second = service.execute(
        intake_command(merchant_id="merchant-b", transaction_id="other"), officer_b
    )["case"]
    # Managers created after allocation still see every case.
    user(auth, "late-manager", "SUPERVISOR")
    manager = {"role": "SUPERVISOR", "actor_id": "late-manager"}
    reader = DisputeQueueReader(service.store, policy)
    for identity in (manager, {"role": "ADMIN", "actor_id": "admin"}):
        page = reader.read(identity, limit=1, assigned_to="officer-a", now=NOW)
        assert page["total"] == 1
        assert sum(p["total"] for p in page["assignee_progress"]) == 2
        assert service.get_case(second["id"], identity)["id"] == second["id"]
    assert "assignee_progress" not in reader.read(officer_a, now=NOW)
    with pytest.raises(DisputeError):
        service.get_case(second["id"], officer_a)
    user(auth, "new-officer", "OPERATOR", ["merchant-a"])
    reassigned = run(
        service,
        first,
        "ASSIGN_CASE",
        {"user_id": "new-officer", "reason": "Team assignment"},
        manager,
    )
    assert reassigned["assigned_op_user_id"] == "new-officer"
    assert service.get_case(first["id"], {"role": "OPERATOR", "actor_id": "new-officer"})


@pytest.mark.parametrize("role", ["SUPERVISOR", "ADMIN"])
def test_privileged_package_author_cannot_self_approve(tmp_path, role):
    service = DisputeService(SQLiteDisputeStore(tmp_path / "workflow.db"), clock=lambda: NOW)
    case = reviewed(service)
    author = {"role": role, "actor_id": "privileged-author"}
    case = run(service, case, "BUILD_PACKAGE", identity=author)
    for action, data in [
        ("APPROVE_PACKAGE", {"reason": "checked", "pii_checked": True}),
        ("FINAL_REVIEW", {"decision": "APPROVE", "reason": "checked", "pii_checked": True}),
    ]:
        with pytest.raises(DisputeError) as error:
            run(service, case, action, data, author)
        assert error.value.code == "REVIEWER_SEPARATION_REQUIRED"
    case = run(
        service,
        case,
        "APPROVE_PACKAGE",
        {"reason": "Independent review", "pii_checked": True},
        {"role": "ADMIN", "actor_id": "independent-admin"},
    )
    submitted = run(service, case, "SUBMIT", identity=author)
    assert submitted["audit"][-1]["role"] == role


def test_admin_http_pages_account_controls_and_retired_routes(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path / "http.db"))) as client:
        auth = client.app.state.v21_auth
        user(auth, "administrator", "ADMIN")
        login = client.post(
            "/api/v2/session/login", json={"username": "administrator", "password": PASSWORD}
        )
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        for path in ("/v2/admin", "/v2/operations", "/v2/governance"):
            assert client.get(path).status_code == 200
        assert client.get("/v2/merchant").status_code == 403
        assert client.get("/v2/director", follow_redirects=False).headers["location"] == "/v2/admin"
        assert client.get("/api/v2/director/accounts").status_code == 410
        permissions = client.get("/api/v2/governance").json()["permissions"]
        assert set(permissions) == ACCOUNT_ROLES
        assert set(client.get("/api/v2/capabilities").json()["actions"]) == set(ACTION_ROLES) - {
            "INTAKE"
        }
        result = client.post(
            "/api/v2/admin/accounts",
            json={
                "username": "new-user",
                "password": PASSWORD,
                "display_name": "Test officer",
                "role": "OPERATOR",
                "merchant_ids": ["merchant-a"],
            },
        )
        assert result.status_code == 200, result.text
        identifier = result.json()["id"]
        assert (
            client.post(
                f"/api/v2/admin/accounts/{identifier}/status", json={"disabled": True}
            ).status_code
            == 200
        )
        with sqlite3.connect(auth.db_path) as db:
            audits = db.execute(
                "SELECT actor_id,action FROM v21_account_audit WHERE target_id=?", (identifier,)
            ).fetchall()
        assert audits == [("administrator", "CREATE_ACCOUNT"), ("administrator", "ACCOUNT_STATUS")]
        service = client.app.state.disputes
        case = service.execute(intake_command(), {"role": "ADMIN", "actor_id": "administrator"})[
            "case"
        ]
        updates = client.get("/api/v2/updates", params={"case_id": case["id"], "timeout": 0})
        assert updates.status_code == 200, updates.text
        assert client.get(f"/api/v2/cases/{case['id']}/collaboration").status_code == 200


def test_administrator_cannot_reconcile_own_ledger_events(tmp_path):
    service = DisputeService(SQLiteDisputeStore(tmp_path / "ledger.db"), clock=lambda: NOW)
    case = reconciled(service)
    admin = {"role": "ADMIN", "actor_id": "ledger-admin"}
    case = run(
        service,
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": "admin-fee",
            "kind": "FEE",
            "amount_minor": 100,
            "currency": "USD",
            "source": "MOCK",
            "reference": "synthetic-fee-record",
        },
        admin,
    )
    data = {
        "status": "RECONCILED",
        "expected_net_minor": sum(e["net_minor"] for e in case["financial_events"]),
        "reason": "Verify the ledger",
        "reference": "synthetic-statement",
    }
    with pytest.raises(DisputeError) as error:
        run(service, case, "RECONCILE", data, admin)
    assert error.value.code == "REVIEWER_SEPARATION_REQUIRED"
    checked = run(
        service, case, "RECONCILE", data, {"role": "SUPERVISOR", "actor_id": "second-manager"}
    )
    assert checked["financial_status"] == "RECONCILED"
