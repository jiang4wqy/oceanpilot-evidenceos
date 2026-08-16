import os

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.case_copilot import CaseCopilotAgent, CopilotActionKind
from oceanpilot.config import Settings
from oceanpilot.domain.chargeback import DisputeReasonCode, required_evidence_for
from oceanpilot.main import create_app


def test_case_copilot_fallback_prioritizes_reason_confirmation():
    outcome = CaseCopilotAgent(ScriptedModelProvider(default_text="not-json")).respond(
        "为什么这个案件还不能提交？",
        problem_type="未收到商品/服务",
        phase="REASON_PROPOSED",
        readiness="0/5 项",
        responsible_team="CUSTOMER_SUPPORT",
        human_gate=True,
        missing_codes=("TRANSACTION_RECEIPT",),
        missing_labels=("交易收据",),
    )

    assert "首要阻断" in outcome.assistant_message
    assert "人工确认" in outcome.assistant_message
    assert outcome.action_kind is CopilotActionKind.OPEN_CASE_DETAIL


def test_agent_turn_creates_a_case_and_returns_a_structured_judgment(tmp_path, monkeypatch):
    monkeypatch.delenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL", raising=False)
    app = create_app(Settings(db_path=tmp_path / "agent-api.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/agent/turns",
            json={"message": "客户下单后一直没收到货，请告诉我下一步", "locale": "zh-CN"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["synthetic"] is True
    assert body["case_id"]
    assert body["runtime"]["mode"] == "OFFLINE_FALLBACK"
    assert body["assistant_message"]
    assert "合成模型输出" not in body["assistant_message"]
    assert body["judgment"]["problem_type"] == "未收到商品/服务"
    assert body["judgment"]["next_action"]
    assert body["judgment"]["evidence_readiness"] == "0/5 项"
    actors = [item["actor"] for item in body["agent_trace"]]
    assert actors[:2] == ["AgentGateway", "CaseTool"]
    assert "EvidenceAgent" in actors


def test_agent_turn_rejects_sensitive_input_without_echoing_it(tmp_path, monkeypatch):
    monkeypatch.delenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL", raising=False)
    app = create_app(Settings(db_path=tmp_path / "agent-api-sensitive.db"))
    sensitive = "请查询卡号 4111 1111 1111 1111 的支付异常"

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/agent/turns",
            json={"message": sensitive, "locale": "zh-CN"},
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "SENSITIVE_DATA_REJECTED"
    assert sensitive not in response.text


def test_agent_turn_analyzes_bound_case_without_creating_a_duplicate(tmp_path, monkeypatch):
    monkeypatch.delenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL", raising=False)
    app = create_app(Settings(db_path=tmp_path / "agent-api-context.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/v1/agent/turns",
            json={"message": "客户下单后一直没收到货", "locale": "zh-CN"},
        ).json()
        response = client.post(
            "/api/v1/agent/turns",
            json={
                "message": "为什么这个案件还不能提交？",
                "locale": "zh-CN",
                "case_id": created["case_id"],
            },
        )
        cases = client.get("/api/v1/chargeback/cases").json()

    assert response.status_code == 201
    body = response.json()
    assert body["turn_kind"] == "CASE_ANALYZED"
    assert body["case_id"] == created["case_id"]
    assert body["intent"] == "EXPLAIN_EVIDENCE_GAP"
    assert body["recommended_action"]["kind"] == "OPEN_EVIDENCE_MODAL"
    assert body["recommended_action"]["evidence_code"]
    assert len(cases) == 1
    assert body["agent_trace"][1]["action"] == "读取当前案件确定性快照"


def test_agent_review_proposal_requires_confirmation_and_replays(tmp_path, monkeypatch):
    monkeypatch.delenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL", raising=False)
    app = create_app(Settings(db_path=tmp_path / "agent-review.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        case = client.post(
            "/api/v1/chargeback/cases",
            json={"description": "持卡人声称这笔无卡交易不是本人，属于非本人交易"},
        ).json()
        case = client.post(
            f"/api/v1/chargeback/cases/{case['case_id']}/confirm",
            json={"reason_code": "FRAUD_CARD_NOT_PRESENT"},
        ).json()
        for code in required_evidence_for(DisputeReasonCode.FRAUD_CARD_NOT_PRESENT):
            case = client.post(
                f"/api/v1/chargeback/cases/{case['case_id']}/evidence",
                json={"evidence_code": code.value},
            ).json()
        turn_response = client.post(
            "/api/v1/agent/turns",
            json={
                "message": "审核通过，已核对全部 Synthetic 材料内容一致。",
                "locale": "zh-CN",
                "case_id": case["case_id"],
                "card_network": "VISA",
                "trigger": "USER_MESSAGE",
            },
        )
        turn = turn_response.json()
        before_confirm = client.get(f"/api/v1/chargeback/cases/{case['case_id']}").json()
        created = client.post(
            f"/api/v1/agent/cases/{case['case_id']}/review-decisions",
            json={
                "source_turn_id": turn["source_turn_id"],
                "case_revision": turn["case_revision"],
                "confirmed_by": "judge_reviewer_01",
            },
        )
        replayed = client.post(
            f"/api/v1/agent/cases/{case['case_id']}/review-decisions",
            json={
                "source_turn_id": turn["source_turn_id"],
                "case_revision": turn["case_revision"],
                "confirmed_by": "judge_reviewer_01",
            },
        )
        restored = client.post(
            "/api/v1/agent/turns",
            json={
                "message": "重新打开案件并恢复当前审核状态",
                "case_id": case["case_id"],
                "trigger": "REVIEW_CONFIRMED",
            },
        )
        audit = client.get(f"/api/v1/chargeback/cases/{case['case_id']}/audit").json()
        latest_code = next(
            event["detail"]
            for event in reversed(audit["events"])
            if event["event_type"] == "EVIDENCE_ADDED"
        )
        withdrawn = client.post(
            f"/api/v1/chargeback/cases/{case['case_id']}/evidence/withdraw-latest",
            json={"evidence_code": latest_code},
        )
        after_withdrawal = client.post(
            "/api/v1/agent/turns",
            json={
                "message": "资料撤回后重新分析",
                "case_id": case["case_id"],
                "trigger": "EVIDENCE_WITHDRAWN",
            },
        )

    assert turn_response.status_code == 201
    assert turn["intent"] == "PROPOSE_REVIEW_DECISION"
    assert turn["review_proposal"]["status"] == "APPROVED"
    assert turn["review_proposal"]["requires_confirmation"] is True
    assert {item["reference_id"] for item in turn["citations"]} == {
        "visa-10-4-demo-v1",
        "oceanpayment-threeds-doc",
    }
    assert before_confirm["phase"] == "ASSESSED"
    assert created.status_code == 201
    assert created.json()["result"] == "CREATED"
    assert created.json()["review_status"] == "APPROVED"
    assert replayed.status_code == 200
    assert replayed.json()["result"] == "REPLAYED"
    assert replayed.json()["decision_id"] == created.json()["decision_id"]
    assert restored.status_code == 201
    assert restored.json()["card_network"] == "VISA"
    assert restored.json()["review_decision"]["audit_event_id"] == created.json()["audit_event_id"]
    assert withdrawn.status_code == 200
    assert after_withdrawal.status_code == 201
    assert after_withdrawal.json()["review_decision"] is None
    assert after_withdrawal.json()["review_status"] == "UNREVIEWED"


def test_agent_downgrades_approval_when_evidence_is_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL", raising=False)
    app = create_app(Settings(db_path=tmp_path / "agent-review-blocked.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        case = client.post(
            "/api/v1/chargeback/cases",
            json={"description": "持卡人声称这笔无卡交易不是本人，属于非本人交易"},
        ).json()
        case = client.post(
            f"/api/v1/chargeback/cases/{case['case_id']}/confirm",
            json={"reason_code": "FRAUD_CARD_NOT_PRESENT"},
        ).json()
        response = client.post(
            "/api/v1/agent/turns",
            json={
                "message": "审核通过",
                "case_id": case["case_id"],
                "card_network": "VISA",
            },
        )

    assert response.status_code == 201
    proposal = response.json()["review_proposal"]
    assert proposal["status"] == "NEEDS_MORE_INFO"
    assert proposal["conflicts"]
    assert "缺" in proposal["why"]


@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="DEEPSEEK_API_KEY not set; live agent turn skipped",
)
def test_live_agent_turn_uses_deepseek_and_keeps_structured_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL", "1")
    monkeypatch.setenv("OCEANPILOT_MODEL_PROVIDER", "deepseek")
    app = create_app(Settings(db_path=tmp_path / "agent-api-live.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/agent/turns",
            json={
                "message": "Synthetic 案件：客户下单后一直没收到货，请给出下一步",
                "locale": "zh-CN",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["runtime"]["mode"] == "DEEPSEEK_LIVE"
    assert body["runtime"]["provider"] == "DEEPSEEK"
    assert body["assistant_message"]
    assert body["judgment"]["problem_type"] == "未收到商品/服务"
    assert body["judgment"]["evidence_readiness"] == "0/5 项"
    assert all(item["output_summary"] for item in body["agent_trace"])
