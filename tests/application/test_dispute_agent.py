import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from oceanpilot.adapters.persistence.dispute_agent import SQLiteDisputeAgentStore
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_agent import DisputeAgentService
from oceanpilot.application.disputes import DisputeService
from oceanpilot.application.model_provider import ModelResult, ToolCall
from oceanpilot.domain.dispute import DisputeError

OP = {"role": "OPERATOR", "actor_id": "operator-a"}
MERCHANT = {"role": "MERCHANT", "actor_id": "merchant-user", "merchant_id": "merchant-private-a"}
OTHER = {"role": "MERCHANT", "actor_id": "other-user", "merchant_id": "merchant-private-b"}
NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


class RecordingModel:
    def __init__(self, text="模型实际调用 marker；当前仍需人工复核。", fail=False, callback=None):
        self.calls = []
        self.text = text
        self.fail = fail
        self.callback = callback

    def complete(self, task, messages, *, system=None, tools=()):
        self.calls.append((task, messages, system, tools))
        if self.callback:
            self.callback()
        if self.fail:
            raise RuntimeError("private-secret-provider-error")
        return ModelResult(text=self.text, model="synthetic-model-v2")


@pytest.fixture
def stack(tmp_path):
    path = tmp_path / "case.db"
    disputes = DisputeService(SQLiteDisputeStore(path), clock=lambda: NOW)
    agent = DisputeAgentService(SQLiteDisputeAgentStore(path), disputes, clock=lambda: NOW)
    return disputes, agent


def intake(disputes, **overrides):
    data = {
        "merchant_id": MERCHANT["merchant_id"],
        "transaction_id": "transaction-private-a",
        "scheme": "VISA",
        "channel": "MOCK",
        "reason_code": "13.1",
        "amount_minor": 12500,
        "currency": "USD",
        "event_id": uuid4().hex,
    }
    data.update(overrides)
    return disputes.execute(
        {"command_id": uuid4().hex, "action": "INTAKE", "confirmed": True, "data": data}, OP
    )["case"]


def execute(disputes, case, action, data=None, identity=OP):
    return disputes.execute(
        {
            "command_id": uuid4().hex,
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "action": action,
            "confirmed": True,
            "data": data or {},
        },
        identity,
    )["case"]


def test_observation_persists_six_real_results_and_specific_executable_proposal(stack):
    disputes, agent = stack
    case = intake(disputes)
    run = agent.observe(case, "COMMAND:INTAKE")
    assert run["status"] == "COMPLETED"
    assert [step["capability"] for step in run["steps"]] == [
        "rule_retrieval",
        "evidence_check",
        "sla_monitor",
        "similar_case_retrieval",
        "next_action_planning",
        "draft_preparation",
    ]
    assert run["steps"][0]["citations"][0]["source_id"] == case["rule_snapshot"]["source_id"]
    assert run["steps"][1]["output"]["missing_required"]
    proposal = run["proposals"][0]
    assert proposal["action"] == "PUBLISH_TASK"
    assert proposal["expected_revision"] == case["revision"]
    assert proposal["owner"] == "OPERATOR"
    assert proposal["requires_confirmation"] is True
    assert "13.1" in proposal["data"]["message"]
    changed = execute(disputes, case, proposal["action"], proposal["data"])
    assert changed["work_status"] == "MERCHANT_ACTION_REQUIRED"


def test_observe_is_idempotent_durable_and_does_not_call_model(stack):
    disputes, agent = stack
    model = RecordingModel()
    agent.model = model
    case = intake(disputes)
    first = agent.observe(case, "INTAKE")
    again = agent.observe(case, "RETRY")
    restarted = DisputeAgentService(
        SQLiteDisputeAgentStore(agent.store.db_path), disputes, clock=lambda: NOW
    )
    assert restarted.observe(case, "AFTER_RESTART") == first == again
    assert model.calls == []
    assert len(restarted.get_activity(case["id"], OP)["history"]) == 1


def test_parallel_observations_save_one_run_and_one_proposal_set(stack):
    disputes, agent = stack
    case = intake(disputes)
    with ThreadPoolExecutor(max_workers=6) as pool:
        runs = list(pool.map(lambda _: agent.observe(case, "INTAKE"), range(6)))
    assert len({run["id"] for run in runs}) == 1
    assert len({run["proposals"][0]["id"] for run in runs}) == 1


def test_get_activity_is_read_only_and_reports_unobserved_revision(stack):
    disputes, agent = stack
    case = intake(disputes)
    for _ in range(3):
        activity = agent.get_activity(case["id"], OP)
        assert activity["run"] is None
        assert activity["stale"] is True
        assert activity["proposals"] == []
    with sqlite3.connect(agent.store.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM v2_dispute_agent_runs").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM v2_dispute_agent_conversations").fetchone()[0]
            == 0
        )


def test_case_revision_changes_invalidate_activity_but_preserve_old_proposal_for_replay(stack):
    disputes, agent = stack
    case = intake(disputes)
    run = agent.observe(case, "INTAKE")
    proposal = run["proposals"][0]
    changed = execute(disputes, case, "PUBLISH_TASK", proposal["data"])
    activity = agent.get_activity(case["id"], OP)
    assert activity["stale"] is True
    assert activity["proposals"] == []
    assert agent.get_proposal(case["id"], proposal["id"], OP) == proposal
    with pytest.raises(DisputeError) as error:
        agent.observe(case, "STALE")
    assert error.value.code == "REVISION_CONFLICT"
    agent.observe(changed, "PUBLISH_TASK")
    activity = agent.get_activity(case["id"], OP)
    assert [run["case_revision"] for run in activity["history"]] == [2, 1]


def test_merchant_decision_proposals_preserve_both_human_choices(stack):
    disputes, agent = stack
    case = execute(disputes, intake(disputes), "PUBLISH_TASK")
    run = agent.observe(case, "PUBLISH_TASK")
    assert {p["data"]["decision"] for p in run["proposals"]} == {"ACCEPT", "CONTEST"}
    assert all(p["owner"] == "MERCHANT" for p in run["proposals"])
    assert disputes.get_case(case["id"], OP)["merchant_decision"] == "NONE"


def test_unknown_rule_proposal_does_not_invent_source_deadline_or_permission(stack):
    disputes, agent = stack
    case = intake(disputes, channel="UNCONFIRMED")
    run = agent.observe(case, "INTAKE")
    proposal = run["proposals"][0]
    assert proposal["action"] == "CONFIRM_RULE"
    assert "external_deadline" not in proposal["data"]
    assert "source_id" in proposal["required_inputs"]
    assert "allowed_actions" in proposal["required_inputs"]
    assert any(finding["severity"] == "BLOCKER" for finding in run["findings"])
    answer = agent.converse(case["id"], OP, "还缺什么材料？", case["revision"])
    assert "仍待确认" in answer["answer"]


def test_similarity_retrieval_never_crosses_merchant_scope(stack):
    disputes, agent = stack
    same = intake(disputes)
    other = intake(disputes, merchant_id=OTHER["merchant_id"])
    case = intake(disputes)
    run = agent.observe(case, "INTAKE")
    assert [match["case_id"] for match in run["similar_cases"]] == [same["id"]]
    assert other["id"] not in json.dumps(run)
    for operation in (
        lambda: agent.get_activity(case["id"], OTHER),
        lambda: agent.get_proposal(case["id"], run["proposals"][0]["id"], OTHER),
        lambda: agent.converse(case["id"], OTHER, "下一步", case["revision"]),
    ):
        with pytest.raises(DisputeError) as error:
            operation()
        assert error.value.status == 404


@pytest.mark.parametrize(
    "question,intent,expected",
    [
        ("还缺什么材料", "EVIDENCE_GAPS", "尚缺"),
        ("为什么不能关", "CLOSE_BLOCKERS", "不能结案"),
        ("起草一条商户通知", "MERCHANT_MESSAGE", "OceanPayment"),
        ("起草答复", "RESPONSE_DRAFT", "答复草稿"),
        ("依据是什么", "RULE_EXPLANATION", "来源"),
        ("下一步", "NEXT_ACTION", "下一步"),
    ],
)
def test_deterministic_conversation_answers_from_persisted_case_sources(
    stack, question, intent, expected
):
    disputes, agent = stack
    case = intake(disputes)
    result = agent.converse(case["id"], MERCHANT, question, case["revision"])
    assert result["intent"] == intent
    assert expected in result["answer"]
    assert result["source"] == "DETERMINISTIC"
    assert result["source_citations"]
    assert (
        agent.get_activity(case["id"], MERCHANT)["conversations"][0]["answer"] == result["answer"]
    )
    assert disputes.get_case(case["id"], OP)["revision"] == 1


def test_conversation_actually_calls_model_and_reports_true_provider_and_model(stack):
    disputes, agent = stack
    agent.model = RecordingModel()
    agent.model_runtime = {"provider": "INJECTED", "model": "configured-other-model"}
    case = intake(disputes)
    result = agent.converse(
        case["id"], OP, "这个原因码为什么需要物流签收证明？", 1, trigger="AUTO_EVENT:INTAKE"
    )
    assert len(agent.model.calls) == 1
    assert "marker" in result["answer"]
    assert result["source"] == "MODEL"
    assert result["provider"] == "INJECTED"
    assert result["model"] == "synthetic-model-v2"
    assert result["trigger"] == "AUTO_EVENT:INTAKE"
    task, messages, system, tools = agent.model.calls[0]
    assert task.max_output_tokens == 1000
    assert "为什么需要物流签收证明" in messages[0].content
    assert "不能审批" in system
    assert tools == ()


def test_model_context_preserves_question_but_removes_private_identifiers_and_references(stack):
    disputes, agent = stack
    agent.model = RecordingModel()
    case = intake(disputes)
    question = (
        f"{case['id']} {case['merchant_id']} {case['transaction_id']} "
        "jane@example.com https://private.example/evidence 为什么需要签收材料？"
    )
    agent.converse(case["id"], OP, question, 1)
    sent = agent.model.calls[0][1][0].content
    for value in (
        case["id"],
        case["merchant_id"],
        case["transaction_id"],
        "jane@example.com",
        "https://private.example/evidence",
    ):
        assert value not in sent
    assert "为什么需要签收材料" in sent
    assert "prepared_draft" in sent
    assert "next_action" in sent


@pytest.mark.parametrize(
    "text,fail", [("", False), ("card 4111 1111 1111 1111", False), ("unused", True)]
)
def test_model_failure_or_unsafe_output_falls_back_without_leaking_details(stack, text, fail):
    disputes, agent = stack
    agent.model = RecordingModel(text=text, fail=fail)
    case = intake(disputes)
    result = agent.converse(case["id"], OP, "下一步", 1)
    assert result["source"] == "FALLBACK"
    assert result["provider"] == "DETERMINISTIC"
    assert "private-secret" not in json.dumps(result)
    assert "4111" not in result["answer"]
    assert result["provider_fallback"]


def test_model_tool_calls_cannot_execute_business_commands(stack):
    disputes, agent = stack

    class UnsafeModel:
        def complete(self, *args, **kwargs):
            return ModelResult(
                text="approved", tool_calls=(ToolCall(call_id="bad", name="SUBMIT", arguments={}),)
            )

    agent.model = UnsafeModel()
    case = intake(disputes)
    result = agent.converse(case["id"], OP, "直接提交", 1)
    assert result["source"] == "FALLBACK"
    assert disputes.get_case(case["id"], OP)["revision"] == 1


def test_stale_conversation_rejected_before_model_and_after_concurrent_business_change(stack):
    disputes, agent = stack
    case = intake(disputes)
    agent.model = RecordingModel()
    with pytest.raises(DisputeError):
        agent.converse(case["id"], OP, "下一步", 0)
    assert agent.model.calls == []
    agent.model.callback = lambda: execute(disputes, case, "COMMENT", {"message": "new facts"})
    with pytest.raises(DisputeError) as error:
        agent.converse(case["id"], OP, "下一步", 1)
    assert error.value.code == "REVISION_CONFLICT"
    assert agent.get_activity(case["id"], OP)["conversations"] == []


def test_sensitive_user_message_is_rejected_before_observation_and_model(stack):
    disputes, agent = stack
    agent.model = RecordingModel()
    case = intake(disputes)
    with pytest.raises(DisputeError) as error:
        agent.converse(case["id"], OP, "cvv: 123", 1)
    assert error.value.code == "SENSITIVE_DATA_REJECTED"
    assert agent.model.calls == []
    assert agent.get_activity(case["id"], OP)["run"] is None


def test_observation_uses_authoritative_repository_snapshot_not_supplied_case_fields(stack):
    disputes, agent = stack
    case = intake(disputes)
    tampered = deepcopy(case)
    tampered["amount_minor"] = 99999
    tampered["finality"] = "FINAL_CONFIRMED"
    run = agent.observe(tampered, "INTAKE")
    assert "99999" not in run["prepared"]["merchant_message"]
    assert "12500" in run["prepared"]["merchant_message"]


def test_model_prompt_separates_parties_and_does_not_reask_an_existing_contest_decision(stack):
    disputes, agent = stack
    case = execute(disputes, intake(disputes), "PUBLISH_TASK")
    case = execute(
        disputes,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "CONTEST",
            "reason": "商户确认继续抗辩",
        },
        MERCHANT,
    )
    agent.model = RecordingModel()
    agent.converse(case["id"], MERCHANT, "下一步谁提供材料？", case["revision"])
    _, messages, system, _ = agent.model.calls[0]
    context = json.loads(messages[0].content)
    assert context["requester_role"] == "MERCHANT"
    assert context["case_state"]["merchant_decision"] == "CONTEST"
    assert context["next_action"]["owner_label"] == "商户本人"
    assert "不重复要求确认 Accept/Contest" in system
    assert "不得把商户与 Agent 合并" in system
    assert "真实材料由商户提供" in context["prepared_draft"]["merchant_message"]
    assert "前确认 ACCEPT" not in context["prepared_draft"]["merchant_message"]


def test_redaction_preserves_rule_versions_and_dates_while_removing_phone_numbers(stack):
    disputes, agent = stack
    case = intake(disputes)
    agent.model = RecordingModel(text="根据 synthetic-v2-2026-09-08，期限是 2026-09-11。")
    result = agent.converse(case["id"], OP, "请解释2026-09-11的期限，联系13812345678", 1)
    context = json.loads(agent.model.calls[0][1][0].content)
    assert context["source_versions"][0]["rule_version"] == case["rule_snapshot"]["rule_version"]
    assert "2026-09-11" in context["user_question"]
    assert "13812345678" not in context["user_question"]
    assert "synthetic-v2-2026-09-08" in result["answer"]
    assert "2026-09-11" in result["answer"]


def test_request_to_draft_evidence_response_is_not_misclassified_as_missing_materials(stack):
    disputes, agent = stack
    case = intake(disputes)
    result = agent.converse(case["id"], OP, "帮我起草抗辩材料", 1)
    assert result["intent"] == "RESPONSE_DRAFT"
    assert "答复草稿" in result["answer"]


def test_http_long_custom_rule_publishes_saved_proposal_without_losing_checklist(tmp_path):
    from fastapi.testclient import TestClient

    from oceanpilot.config import Settings
    from oceanpilot.main import create_app

    app = create_app(Settings(db_path=tmp_path / "long-rule.db"), chargeback_model=RecordingModel())

    def headers(role):
        return {
            "X-Demo-Role": role,
            "X-Demo-Actor": f"long-rule-{role}",
            "X-Demo-Merchant": "merchant-long",
        }

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v2/commands",
            headers=headers("OPERATOR"),
            json={
                "command_id": str(uuid4()),
                "action": "INTAKE",
                "confirmed": True,
                "data": {
                    "merchant_id": "merchant-long",
                    "transaction_id": "tx-long",
                    "scheme": "CUSTOM",
                    "channel": "CUSTOM",
                    "reason_code": "CUSTOM",
                    "amount_minor": 12500,
                    "currency": "USD",
                    "event_id": str(uuid4()),
                },
            },
        )
        assert response.status_code == 200, response.text
        case = response.json()["case"]
        evidence_codes = [f"custom.requirement.{index:02d}." + "a" * 18 for index in range(30)]
        assert all(len(code) == 40 for code in evidence_codes)
        response = client.post(
            "/api/v2/commands",
            headers=headers("RISK_OFFICER"),
            json={
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "action": "CONFIRM_RULE",
                "confirmed": True,
                "data": {
                    "source_id": "source-" + "s" * 153,
                    "source_locator": "manual:requirements",
                    "rule_version": "version-" + "v" * 92,
                    "required_evidence": evidence_codes,
                    "allowed_actions": ["CONTEST"],
                    "external_deadline": "2026-12-15T12:00:00Z",
                    "reason": "已人工核对该演示规则的全部证据清单及操作权限。",
                },
            },
        )
        assert response.status_code == 200, response.text
        case = response.json()["case"]
        response = client.get(f"/api/v2/cases/{case['id']}/agent", headers=headers("OPERATOR"))
        assert response.status_code == 200, response.text
        activity = response.json()
        proposal = next(p for p in activity["proposals"] if p["action"] == "PUBLISH_TASK")
        assert proposal["required_inputs"] == []
        assert len(proposal["data"]["message"]) <= 1000
        assert "完整清单" in proposal["data"]["message"]
        checklist = activity["run"]["steps"][1]["output"]["checklist"]
        assert {item["code"] for item in checklist} == set(evidence_codes)
        assert len(activity["run"]["prepared"]["review_brief"]) <= 1000
        response = client.post(
            f"/api/v2/cases/{case['id']}/agent/proposals/{proposal['id']}/execute",
            headers=headers("OPERATOR"),
            json={
                "command_id": str(uuid4()),
                "expected_revision": case["revision"],
                "confirmed": True,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["case"]["work_status"] == "MERCHANT_ACTION_REQUIRED"
        assert set(response.json()["case"]["rule_snapshot"]["required_evidence"]) == set(
            evidence_codes
        )


def test_long_evidence_draft_fits_http_contract_and_package_retains_every_item(stack):
    from oceanpilot.api.disputes import ApprovalData, DraftData, ReviewData

    disputes, agent = stack
    case = execute(disputes, intake(disputes), "PUBLISH_TASK")
    case = execute(
        disputes,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "CONTEST",
            "reason": "商户确认抗辩并提供全部材料。",
        },
        MERCHANT,
    )
    codes = case["rule_snapshot"]["required_evidence"] + [
        f"custom.evidence.{index:02d}." + "p" * 81 for index in range(40)
    ]
    for code in codes:
        case = execute(
            disputes,
            case,
            "REGISTER_EVIDENCE",
            {
                "code": code,
                "title": "合规登记的完整材料说明" * 15,
                "reference": "synthetic://registered-material",
            },
            MERCHANT,
        )
    case = execute(disputes, case, "SUBMIT_EVIDENCE", identity=MERCHANT)
    run = agent.observe(case, "SUBMIT_EVIDENCE")
    review = ReviewData.model_validate(
        {"decision": "PASS", "reason": run["prepared"]["review_brief"]}
    )
    case = execute(
        disputes,
        case,
        "REVIEW",
        review.model_dump(),
        {"role": "RISK_OFFICER", "actor_id": "independent-risk"},
    )
    run = agent.observe(case, "REVIEW")
    proposal = next(p for p in run["proposals"] if p["action"] == "BUILD_PACKAGE")
    draft = DraftData.model_validate(proposal["data"])
    assert len(draft.draft) <= 10000
    assert "另 " in draft.draft
    assert "完整材料索引随证据包保留" in draft.draft
    case = execute(disputes, case, "BUILD_PACKAGE", draft.model_dump())
    assert len(case["packages"][-1]["evidence_index"]) == len(codes)
    assert {item["code"] for item in case["packages"][-1]["evidence_index"]} == set(codes)
    approval = agent.observe(case, "BUILD_PACKAGE")["proposals"][0]
    ApprovalData.model_validate({**approval["data"], "pii_checked": True})
