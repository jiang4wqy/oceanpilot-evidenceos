"""Four-role authority, team visibility, immutable history and upgrade regressions."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.persistence.dispute_agent import SQLiteDisputeAgentStore
from oceanpilot.adapters.persistence.dispute_identity import SQLiteDisputeIdentity
from oceanpilot.adapters.persistence.dispute_queue import DisputeQueueReader
from oceanpilot.adapters.persistence.dispute_updates import SQLiteDisputeUpdateReader
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
    for identity in (manager,):
        page = reader.read(identity, limit=1, assigned_to="officer-a", now=NOW)
        assert page["total"] == 1
        assert sum(p["total"] for p in page["assignee_progress"]) == 2
        assert service.get_case(second["id"], identity)["id"] == second["id"]
    admin = {"role": "ADMIN", "actor_id": "admin"}
    assert reader.read(admin, now=NOW)["total"] == 0
    assert service.list_cases(admin) == []
    with pytest.raises(DisputeError):
        service.get_case(first["id"], admin)
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


@pytest.mark.parametrize("role", ["SUPERVISOR"])
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
        {"role": "SUPERVISOR", "actor_id": "independent-manager"},
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
        for path in ("/v2/admin", "/v2/governance"):
            assert client.get(path).status_code == 200
        assert client.get("/v2/operations").status_code == 403
        assert client.get("/v2/merchant").status_code == 403
        assert client.get("/v2/director", follow_redirects=False).headers["location"] == "/v2/admin"
        assert client.get("/api/v2/director/accounts").status_code == 410
        permissions = client.get("/api/v2/governance").json()["permissions"]
        assert set(permissions) == ACCOUNT_ROLES
        assert client.get("/api/v2/capabilities").json()["actions"] == []
        assert client.get("/api/v2/capabilities").json()["intake_events"] is False
        assert client.get("/api/v2/command-schemas").json() == {"commands": {}}
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
        user(auth, "case-officer", "OPERATOR", ["merchant-a"])
        case = service.execute(intake_command(), {"role": "OPERATOR", "actor_id": "case-officer"})[
            "case"
        ]
        updates = client.get("/api/v2/updates", params={"case_id": case["id"], "timeout": 0})
        assert updates.status_code == 404, updates.text
        assert client.get(f"/api/v2/cases/{case['id']}/collaboration").status_code == 404
        assert client.get(f"/api/v2/cases/{case['id']}").status_code == 404
        assert client.get("/api/v2/cases").json()["total"] == 0
        assert client.get("/api/v2/governance").json()["knowledge"] == []
        assert client.get("/api/v2/governance").json()["metrics"] == {}
        assert client.get("/api/v2/updates", params={"timeout": 0}).json()["changes"] == []


def test_manager_cannot_reconcile_own_ledger_events(tmp_path):
    service = DisputeService(SQLiteDisputeStore(tmp_path / "ledger.db"), clock=lambda: NOW)
    case = reconciled(service)
    admin = {"role": "SUPERVISOR", "actor_id": "ledger-manager"}
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


@pytest.mark.parametrize("action", sorted(ACTION_ROLES))
def test_it_admin_has_no_business_command_authority(tmp_path, action):
    service = DisputeService(SQLiteDisputeStore(tmp_path / "business.db"), clock=lambda: NOW)
    assert "ADMIN" not in ACTION_ROLES[action]
    with pytest.raises(DisputeError) as error:
        service.execute({"action": action}, {"role": "ADMIN", "actor_id": "it-admin"})
    assert error.value.code == "FORBIDDEN"


@pytest.mark.parametrize("action", ["CONFIRM_RULE", "ASSIGN_CASE", "APPROVE_KNOWLEDGE"])
def test_manager_only_controls_reject_officer(tmp_path, action):
    service = DisputeService(SQLiteDisputeStore(tmp_path / "business.db"), clock=lambda: NOW)
    assert ACTION_ROLES[action] == {"SUPERVISOR"}
    with pytest.raises(DisputeError) as error:
        service.execute({"action": action}, {"role": "OPERATOR", "actor_id": "officer"})
    assert error.value.code == "FORBIDDEN"


def test_pending_rule_tasks_move_to_manager_once_without_rewriting_history(tmp_path):
    path = tmp_path / "pending-rules.db"
    service = DisputeService(SQLiteDisputeStore(path), clock=lambda: NOW)
    identity = {"role": "OPERATOR", "actor_id": "officer"}
    case = service.execute(intake_command(channel="UNKNOWN"), identity)["case"]
    case = run(service, case, "MONITOR_SLA", identity=identity)
    task = next(t for t in case["tasks"] if t["type"] == "RULE_CONFIRMATION")
    assert task["owner"] == "SUPERVISOR"
    task.update(
        owner="OPERATOR", assignee="officer", assignee_id="officer", assignee_role="OPERATOR"
    )
    completed = dict(task, id="historical", status="COMPLETED")
    case["tasks"].append(completed)
    with sqlite3.connect(path) as db:
        receipts = db.execute("SELECT * FROM v2_dispute_commands").fetchall()
        db.execute("UPDATE v2_dispute_cases SET snapshot=?", (json.dumps(case),))
    store = SQLiteDisputeStore(path)
    upgraded = store.get_case(case["id"])
    active = next(t for t in upgraded["tasks"] if t["id"] == task["id"])
    assert active["owner"] == active["assignee_role"] == "SUPERVISOR"
    assert active["assignee"] is None
    assert active["assignee_id"] is None
    assert upgraded["tasks"][-1] == completed
    assert upgraded["revision"] == case["revision"] + 1
    assert upgraded["audit"][:-1] == case["audit"]
    assert upgraded["audit"][-1]["action"] == "MANAGER_AUTHORITY_MIGRATION"
    assert upgraded["audit"][-1]["previous_tasks"][0]["assignee"] == "officer"
    assert SQLiteDisputeStore(path).get_case(case["id"]) == upgraded
    manager = {"role": "SUPERVISOR", "actor_id": "manager"}
    assert (
        DisputeQueueReader(store, None).read(manager, now=NOW)["cases"][0]["task_summary"]["for_me"]
        == 1
    )
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM v2_dispute_commands").fetchall() == receipts


@pytest.mark.parametrize("with_policy", [False, True])
def test_admin_sql_readers_ignore_old_grants_and_update_positions(tmp_path, with_policy):
    path = tmp_path / "reader-scopes.db"
    auth = SQLiteDisputeIdentity(path)
    user(auth, "it-admin", "ADMIN", ["merchant-a"])
    user(auth, "officer", "OPERATOR", ["merchant-a"])
    policy = DisputeAccessPolicy(auth) if with_policy else None
    service = DisputeService(SQLiteDisputeStore(path), clock=lambda: NOW, access_policy=policy)
    identity = {"role": "OPERATOR", "actor_id": "officer"}
    case = service.execute(intake_command(), identity)["case"]
    case.setdefault("participants", []).append({"user_id": "it-admin", "role": "ADMIN"})
    with sqlite3.connect(path) as db:
        db.execute("UPDATE v2_dispute_cases SET snapshot=?", (json.dumps(case),))
    SQLiteDisputeAgentStore(path)
    reader = SQLiteDisputeUpdateReader(path, policy)
    old = reader.read(identity, None, None)
    admin = {"role": "ADMIN", "actor_id": "it-admin"}
    assert reader.read(admin, None, old)["changes"] == []
    with pytest.raises(DisputeError) as error:
        reader.read(admin, case["id"], old)
    assert error.value.code == "NOT_FOUND"
    assert DisputeQueueReader(service.store, policy).read(admin, now=NOW)["total"] == 0


def test_legacy_admin_case_grants_cannot_restore_access(tmp_path):
    path = tmp_path / "scopes.db"
    auth = SQLiteDisputeIdentity(path)
    user(auth, "it-admin", "ADMIN", ["merchant-a"])
    user(auth, "officer", "OPERATOR", ["merchant-a"])
    policy = DisputeAccessPolicy(auth)
    identity = {"role": "ADMIN", "actor_id": "it-admin"}
    case = {"merchant_id": "merchant-a", "participants": [{"user_id": "it-admin"}]}
    assert not policy.can_access(case, identity)
    assert policy.case_participants(case) == []
    assert all(p["role"] != "ADMIN" for p in policy.assignment_candidates(case))
    with pytest.raises(DisputeError):
        policy.require_intake("merchant-a", identity)
