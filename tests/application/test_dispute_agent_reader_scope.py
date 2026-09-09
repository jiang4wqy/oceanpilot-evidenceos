"""Reader access applies to persisted runs, historic messages, and actual model inputs."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from oceanpilot.adapters.persistence.dispute_agent import SQLiteDisputeAgentStore
from oceanpilot.adapters.persistence.dispute_collaboration import SQLiteDisputeCollaborationStore
from oceanpilot.adapters.persistence.dispute_identity import SQLiteDisputeIdentity
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_access import DisputeAccessPolicy
from oceanpilot.application.dispute_agent import DisputeAgentService
from oceanpilot.application.dispute_collaboration import DisputeCollaborationService
from oceanpilot.application.disputes import DisputeService
from oceanpilot.application.model_provider import ModelResult
from oceanpilot.domain.dispute import DisputeError

NOW = datetime(2026, 9, 9, 8, tzinfo=UTC)
OP = {"role": "OPERATOR", "actor_id": "operator"}
RISK = {"role": "RISK_OFFICER", "actor_id": "risk"}
MERCHANT = {"role": "MERCHANT", "actor_id": "late-merchant", "merchant_id": "merchant-a"}
LATE_OP = {"role": "OPERATOR", "actor_id": "late-operator"}
EXTERNAL = "2026-10-10T08:00:00+00:00"
INTERNAL = "2026-10-07T08:00:00+00:00"


class Model:
    def __init__(self):
        self.contexts = []

    def complete(self, task, messages, **kwargs):
        self.contexts.append(json.loads(messages[0].content))
        return ModelResult(
            text="请按本案商户任务补充材料，OceanPayment 跟进后续流程。", model="reader-scope-test"
        )


def add_user(directory, name, role):
    directory.create_user(
        username=name,
        password="Scope-regression-only!",
        display_name=name,
        user_id=name,
        role=role,
        merchant_ids=["merchant-a"],
        merchant_id="merchant-a" if role == "MERCHANT" else None,
    )


def intake(disputes):
    return disputes.execute(
        {
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "event_id": str(uuid4()),
                "merchant_id": "merchant-a",
                "transaction_id": str(uuid4()),
                "scheme": "VISA",
                "reason_code": "13.1",
                "channel": "MOCK",
                "amount_minor": 10000,
                "currency": "USD",
            },
        },
        OP,
    )["case"]


@pytest.fixture
def stack(tmp_path):
    path = tmp_path / "readers.db"
    directory = SQLiteDisputeIdentity(path)
    add_user(directory, "operator", "OPERATOR")
    add_user(directory, "risk", "RISK_OFFICER")
    disputes = DisputeService(
        SQLiteDisputeStore(path), clock=lambda: NOW, access_policy=DisputeAccessPolicy(directory)
    )
    old = intake(disputes)
    add_user(directory, "late-merchant", "MERCHANT")
    add_user(directory, "late-operator", "OPERATOR")
    case = intake(disputes)
    model = Model()
    agent = DisputeAgentService(
        SQLiteDisputeAgentStore(path), disputes, model=model, clock=lambda: NOW
    )
    collaboration = DisputeCollaborationService(
        SQLiteDisputeCollaborationStore(path), disputes, agent, clock=lambda: NOW
    )
    agent.collaboration_provider = collaboration
    agent.observe(case, "INTAKE")
    case = disputes.execute(
        {
            "command_id": str(uuid4()),
            "case_id": case["id"],
            "action": "CONFIRM_RULE",
            "expected_revision": case["revision"],
            "confirmed": True,
            "data": {
                "source_id": "SYNTHETIC_DEMO",
                "source_locator": "synthetic:reader-regression",
                "rule_version": "synthetic-reader-v1",
                "reason": "Reviewed the synthetic policy",
                "required_evidence": ["synthetic_order_record"],
                "allowed_actions": ["ACCEPT", "CONTEST"],
                "merchant_deadline": "2026-10-05T08:00:00+00:00",
                "internal_deadline": INTERNAL,
                "external_deadline": EXTERNAL,
            },
        },
        RISK,
    )["case"]
    agent.observe(case, "CONFIRM_RULE")
    return disputes, agent, case, old, model, directory


@pytest.mark.parametrize("reader", [MERCHANT, LATE_OP])
def test_all_run_copies_filter_cases_reader_cannot_open_and_preserve_internal_history(
    stack, reader
):
    disputes, agent, case, old, _, _ = stack
    with pytest.raises(DisputeError):
        disputes.get_case(old["id"], reader)
    persisted_before = deepcopy(agent.store.list_runs(case["id"]))
    assert old["id"] in json.dumps(persisted_before)
    activity = agent.get_activity(case["id"], reader)
    assert old["id"] not in json.dumps(activity)
    step = next(s for s in activity["run"]["steps"] if s["capability"] == "similar_case_retrieval")
    assert step["output"]["count"] == 0 and step["output"]["matches"] == []
    assert agent.store.list_runs(case["id"]) == persisted_before
    assert old["id"] in json.dumps(agent.get_activity(case["id"], OP)["run"])


def test_merchant_latest_and_historical_sla_steps_never_return_internal_dates(stack):
    _, agent, case, _, _, _ = stack
    activity = agent.get_activity(case["id"], MERCHANT)
    assert INTERNAL not in json.dumps(activity) and EXTERNAL not in json.dumps(activity)
    for run in agent.store.list_runs(case["id"]):
        projection = agent._reader_projection(case, MERCHANT, "MERCHANT", [run])
        projected = agent._run_for_reader(run, "MERCHANT", projection)
        sla = next(s for s in projected["steps"] if s["capability"] == "sla_monitor")
        assert set(sla["output"]["deadlines"]) <= {"merchant", "status"}
    raw = agent.get_activity(case["id"], OP)
    assert INTERNAL in json.dumps(raw) and EXTERNAL in json.dumps(raw)


def legacy_message(agent, case, old, audience):
    agent.store.save_conversation(
        {
            "id": str(uuid4()),
            "case_id": case["id"],
            "case_revision": case["revision"],
            "actor_id": "late-merchant",
            "actor_role": "MERCHANT",
            "audience": audience,
            "message": "请继续查看本案",
            "answer": f"旧返回内容 {old['id']} 内部目标 {INTERNAL} 外部目标 {EXTERNAL}",
            "model_analysis": f"旧分析 {EXTERNAL}",
            "created_at": NOW.isoformat(),
            "source": "MODEL",
            "provider": "legacy-model",
            "model": "legacy-model",
            "intent": "SLA",
            "trigger": "USER_MESSAGE",
        }
    )


def test_legacy_read_only_and_shared_history_are_projected_without_rewriting_source(stack):
    _, agent, case, old, _, _ = stack
    for scope in ("MERCHANT", "SHARED"):
        legacy_message(agent, case, old, scope)
    result = agent.get_activity(case["id"], MERCHANT)
    serialized = json.dumps(result)
    assert old["id"] not in serialized and INTERNAL not in serialized and EXTERNAL not in serialized
    assert result["legacy_read_only"] and result["legacy_conversations"]
    raw = agent.store.list_conversations(case["id"], audience="MERCHANT")
    assert old["id"] in json.dumps(raw) and EXTERNAL in json.dumps(raw)


@pytest.mark.parametrize(
    "identity,scope", [(MERCHANT, "SHARED"), (OP, "SHARED"), (LATE_OP, "OP_INTERNAL")]
)
def test_actual_model_context_and_returned_run_enforce_reader_and_thread_scope(
    stack, identity, scope
):
    _, agent, case, old, model, _ = stack
    legacy_message(agent, case, old, scope)
    response = agent.converse(
        case["id"], identity, "请解释本案期限和相似案件", case["revision"], audience=scope
    )
    assert response["source"] == "MODEL" and len(model.contexts) == 1
    context = model.contexts[0]
    assert old["id"] not in json.dumps(context) and old["id"] not in json.dumps(response)
    if scope == "SHARED":
        assert set(context["deadlines"]) == {"merchant"}
        assert INTERNAL not in json.dumps(context) and EXTERNAL not in json.dumps(context)
        assert INTERNAL not in json.dumps(response) and EXTERNAL not in json.dumps(response)
        assert "operations" not in context
    else:
        assert context["deadlines"]["internal"] == INTERNAL
        assert context["deadlines"]["external"] == EXTERNAL


def test_deterministic_merchant_sla_answer_does_not_bypass_context_filter(stack):
    _, agent, case, _, _, _ = stack
    agent.model = None
    response = agent.converse(case["id"], MERCHANT, "请问期限是什么时候", case["revision"])
    assert response["source"] == "DETERMINISTIC"
    assert INTERNAL not in json.dumps(response) and EXTERNAL not in json.dumps(response)
    assert case["deadlines"]["merchant"] in response["answer"]
