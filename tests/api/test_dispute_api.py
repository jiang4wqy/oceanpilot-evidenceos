from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.application.dispute_demo import (
    close_demo,
    complete_contest,
    create_demo,
    demo_identity,
    issue,
    record_terminal_financial,
)
from oceanpilot.config import Settings
from oceanpilot.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path / "v2.db"))) as result:
        yield result


def headers(role="OPERATOR", merchant="synthetic-merchant-001"):
    return {
        "X-Demo-Role": role,
        "X-Demo-Actor": f"synthetic-{role.lower()}",
        "X-Demo-Merchant": merchant,
    }


def seed(client, scenario="A"):
    response = client.post("/api/v2/demo", headers=headers(), json={"scenario": scenario})
    assert response.status_code == 200, response.text
    return response.json()["case"]


def command(client, case, action, data, role="OPERATOR", **overrides):
    payload = {
        "command_id": str(uuid4()),
        "case_id": case["id"],
        "expected_revision": case["revision"],
        "confirmed": True,
        "action": action,
        "data": data,
    } | overrides
    return client.post("/api/v2/commands", headers=headers(role), json=payload)


@pytest.mark.parametrize(
    "scenario,status",
    [
        ("A", "MERCHANT_ACTION_REQUIRED"),
        ("B", "EVIDENCE_COLLECTING"),
        ("C", "MERCHANT_ACTION_REQUIRED"),
        ("D", "FINANCIAL_RECONCILIATION"),
    ],
)
def test_four_golden_cases_are_persisted_by_real_commands(client, scenario, status):
    case = seed(client, scenario)
    assert case["work_status"] == status
    assert case["owner"] == "OCEANPAYMENT"
    assert case["production_eligible"] is False
    assert len(case["audit"]) == case["revision"]
    if scenario == "C":
        assert any(t["type"] == "SLA_ESCALATION" for t in case["tasks"])
        assert case["merchant_decision"] == "NONE"
    if scenario == "D":
        assert case["business_outcome"] == "WON"
        assert case["financial_status"] == "DISCREPANCY"
        assert case["submissions"][0]["mode"] == "MOCK"


def test_merchant_sees_only_own_cases_and_cannot_seed_or_approve(client):
    case = seed(client)
    own = client.get("/api/v2/cases", headers=headers("MERCHANT")).json()
    assert len(own["cases"]) == 1
    other = headers("MERCHANT", "other-merchant")
    assert client.get("/api/v2/cases", headers=other).json() == {"cases": []}
    assert client.get(f"/api/v2/cases/{case['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v2/cases/{case['id']}/plan", headers=other).status_code == 404
    assert client.post("/api/v2/demo", headers=other, json={"scenario": "A"}).status_code == 403
    denied = command(client, case, "REVIEW", {"decision": "PASS", "reason": "试图自审"}, "MERCHANT")
    assert denied.status_code == 403
    assert command(client, case, "SUBMIT", {}, "AGENT").status_code == 403
    assert command(client, case, "CLOSE", {}, "ADMIN").status_code == 403


def test_strict_dto_stale_proposal_and_atomic_replay(client):
    case = seed(client)
    assert (
        command(client, case, "COMMENT", {"message": "hello", "role": "SUPERVISOR"}).status_code
        == 422
    )
    assert (
        command(client, case, "CLOSE", {}, "SUPERVISOR", expected_revision=True).status_code == 422
    )
    plan = client.get(f"/api/v2/cases/{case['id']}/plan", headers=headers()).json()
    assert plan["proposal"]["expected_revision"] == case["revision"]
    command_id = str(uuid4())
    first = command(client, case, "COMMENT", {"message": "共享案件上下文"}, command_id=command_id)
    replay = command(client, case, "COMMENT", {"message": "共享案件上下文"}, command_id=command_id)
    assert first.status_code == replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert first.json()["case"]["revision"] == replay.json()["case"]["revision"]
    stale = command(
        client,
        case,
        "MERCHANT_DECISION",
        {"decision": "CONTEST", "reason": "旧提案尝试执行"},
        "MERCHANT",
    )
    assert stale.status_code == 409
    changed = command(
        client, case, "COMMENT", {"message": "changed content"}, command_id=command_id
    )
    assert changed.status_code == 409


def test_contest_end_to_end_closes_only_after_financial_and_notification(client):
    service = client.app.state.disputes
    case = complete_contest(service, seed(client))
    assert command(client, case, "CLOSE", {}, "SUPERVISOR").status_code == 409
    case = record_terminal_financial(service, case)
    assert command(client, case, "CLOSE", {}, "SUPERVISOR").status_code == 409
    case = close_demo(service, case)
    assert case["work_status"] == "CLOSED"
    reread = client.get(f"/api/v2/cases/{case['id']}", headers=headers("MERCHANT")).json()
    assert reread["finality"] == "FINAL_CONFIRMED"
    assert reread["financial_status"] == "RECONCILED"
    assert reread["merchant_notification_completed"] is True


def test_financial_exception_reconciles_without_rewriting_ledger(client):
    case = seed(client, "D")
    assert command(client, case, "CLOSE", {}, "SUPERVISOR").status_code == 409
    before = case["financial_events"]
    response = command(
        client,
        case,
        "RECONCILE",
        {
            "status": "RECONCILED",
            "expected_net_minor": case["amount_minor"],
            "reason": "已人工核对差异并确认账本",
            "reference": "synthetic://reconciled",
        },
        "SUPERVISOR",
    )
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    assert case["financial_events"] == before
    assert close_demo(client.app.state.disputes, case)["work_status"] == "CLOSED"


def test_case_survives_restart_and_governance_does_not_grant_business_permissions(tmp_path):
    settings = Settings(db_path=tmp_path / "persistent.db")
    with TestClient(create_app(settings)) as first:
        case = seed(first)
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/api/v2/cases/{case['id']}", headers=headers()).json() == case
        assert second.get("/api/v2/governance", headers=headers("MERCHANT")).status_code == 403
        governance = second.get("/api/v2/governance", headers=headers("ADMIN"))
        assert governance.status_code == 200, governance.text
        assert "CLOSE" not in governance.json()["permissions"]["ADMIN"]
        assert Path(settings.db_path).exists()


def test_approved_redacted_knowledge_is_reused_only_after_human_review(client):
    service = client.app.state.disputes
    case = close_demo(
        service, record_terminal_financial(service, complete_contest(service, seed(client)))
    )
    case = issue(
        service,
        case,
        "KNOWLEDGE_CANDIDATE",
        {
            "summary": f"{case['merchant_id']} {case['id']} sample@example.com",
            "pattern": "同类争议需要完整签收和通信证据；人工确认规则来源。",
        },
        "OPERATOR",
    )["case"]
    fresh = create_demo(service, "A", demo_identity("OPERATOR"), str(uuid4()))["case"]
    url = f"/api/v2/cases/{fresh['id']}/plan"
    assert client.get(url, headers=headers()).json()["similar_cases"] == []
    candidate = case["knowledge_candidates"][0]
    assert "sample@example.com" not in candidate["summary"]
    issue(
        service,
        case,
        "APPROVE_KNOWLEDGE",
        {
            "candidate_id": candidate["id"],
            "decision": "APPROVE",
            "reason": "人工检查脱敏与复用范围",
        },
        "ADMIN",
    )
    similar = client.get(url, headers=headers()).json()["similar_cases"]
    assert len(similar) == 1
    assert case["merchant_id"] not in str(similar)
    assert client.get(url, headers=headers("MERCHANT")).json()["similar_cases"] == []
