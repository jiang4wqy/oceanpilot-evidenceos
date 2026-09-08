"""Event-driven model scheduling with explicit thread barriers and no sleeps."""

import json
from contextlib import contextmanager
from threading import Event, Lock
from uuid import uuid4

from oceanpilot.adapters.persistence.dispute_agent import SQLiteDisputeAgentStore
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_agent import DisputeAgentService
from oceanpilot.application.dispute_agent_events import DisputeAgentEvents
from oceanpilot.application.disputes import DisputeService
from oceanpilot.application.model_provider import ModelResult

OP = {"role": "OPERATOR", "actor_id": "event-test-op"}
MERCHANT = {"role": "MERCHANT", "actor_id": "event-test-merchant", "merchant_id": "merchant-1"}


class ControlledModel:
    def __init__(self, *, block_first=False):
        self.block_first = block_first
        self.entered = Event()
        self.release = Event()
        self.lock = Lock()
        self.requests = []

    def complete(self, task, messages, **kwargs):
        with self.lock:
            self.requests.append({"task": task, "messages": tuple(messages)})
            first = len(self.requests) == 1
        if first:
            self.entered.set()
            if self.block_first and not self.release.wait(timeout=5):
                raise RuntimeError("test did not release model barrier")
        return ModelResult(
            text="已核对当前案件版本；业务动作仍需授权人确认。", model="controlled-model"
        )


@contextmanager
def event_stack(tmp_path, *, enabled=True, block_first=False):
    db_path = tmp_path / "events.db"
    disputes = DisputeService(SQLiteDisputeStore(db_path))
    model = ControlledModel(block_first=block_first)
    agent = DisputeAgentService(SQLiteDisputeAgentStore(db_path), disputes, model=model)
    events = DisputeAgentEvents(agent, enabled=enabled)
    drained = Event()
    original_drain = events._drain

    def track_drain(case_id):
        try:
            original_drain(case_id)
        finally:
            drained.set()

    events._drain = track_drain
    disputes.on_change = events.changed
    try:
        yield disputes, agent, events, model, drained
    finally:
        model.release.set()
        events.close()
        # Bounded model barriers guarantee that no worker leaks to a later test.
        events._pool.shutdown(wait=True, cancel_futures=True)


def intake_command():
    return {
        "command_id": uuid4().hex,
        "action": "INTAKE",
        "confirmed": True,
        "data": {
            "merchant_id": "merchant-1",
            "transaction_id": "synthetic-event-transaction",
            "scheme": "VISA",
            "channel": "MOCK",
            "reason_code": "13.1",
            "amount_minor": 10000,
            "currency": "USD",
            "event_id": uuid4().hex,
        },
    }


def execute(disputes, case, action, data=None, identity=OP):
    return disputes.execute(
        {
            "command_id": uuid4().hex,
            "action": action,
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "confirmed": True,
            "data": data or {},
        },
        identity,
    )["case"]


def test_live_critical_event_records_tools_then_background_model_analysis(tmp_path):
    with event_stack(tmp_path, block_first=True) as (disputes, agent, events, model, drained):
        case = disputes.execute(intake_command(), OP)["case"]
        assert model.entered.wait(timeout=3)
        activity = agent.get_activity(case["id"], OP)
        assert activity["run"]["case_revision"] == case["revision"]
        assert len(activity["run"]["steps"]) == 6
        assert activity["conversations"] == []
        assert events.is_pending(case["id"]) is True
        assert disputes.get_case(case["id"], OP) == case
        model.release.set()
        assert drained.wait(timeout=3)
        activity = agent.get_activity(case["id"], OP)
        assert len(activity["conversations"]) == 1
        result = activity["conversations"][0]
        assert result["trigger"] == "AUTO_EVENT:INTAKE"
        assert result["case_revision"] == case["revision"]
        assert result["source"] == "MODEL"
        assert result["model"] == "controlled-model"
        merchant = agent.get_activity(case["id"], MERCHANT)["conversations"]
        assert len(merchant) == 1
        assert merchant[0]["audience"] == "MERCHANT"
        assert result["audience"] == "OPERATIONS"
        assert merchant[0]["id"] != result["id"]
        contexts = [json.loads(item["messages"][0].content) for item in model.requests]
        assert [item["requester_role"] for item in contexts] == ["OPERATOR", "MERCHANT"]
        assert events.is_pending(case["id"]) is False
        assert disputes.get_case(case["id"], OP) == case


def test_changes_to_busy_case_coalesce_and_old_model_result_cannot_override_new_revision(tmp_path):
    with event_stack(tmp_path, block_first=True) as (disputes, agent, events, model, drained):
        first = disputes.execute(intake_command(), OP)["case"]
        assert model.entered.wait(timeout=3)
        second = execute(disputes, first, "PUBLISH_TASK")
        latest = execute(
            disputes,
            second,
            "MERCHANT_DECISION",
            {
                "decision": "CONTEST",
                "reason": "Merchant explicitly confirmed Contest",
            },
            MERCHANT,
        )
        assert latest["revision"] == first["revision"] + 2
        assert agent.get_activity(latest["id"], OP)["run"]["case_revision"] == latest["revision"]
        model.release.set()
        assert drained.wait(timeout=3)
        # One in-flight attempt and two audience-specific latest-version attempts; the intermediate
        # publish event is coalesced, and the old result is rejected by converse.
        assert len(model.requests) == 3
        conversations = agent.get_activity(latest["id"], OP)["conversations"]
        assert len(conversations) == 1
        assert conversations[0]["case_revision"] == latest["revision"]
        assert conversations[0]["trigger"] == "AUTO_EVENT:MERCHANT_DECISION"
        merchant = agent.get_activity(latest["id"], MERCHANT)["conversations"]
        assert len(merchant) == 1
        assert merchant[0]["case_revision"] == latest["revision"]
        final_context = json.loads(model.requests[-1]["messages"][0].content)
        assert final_context["case_state"]["merchant_decision"] == "CONTEST"
        assert final_context["case_state"]["work_status"] == "EVIDENCE_COLLECTING"
        assert disputes.get_case(latest["id"], OP) == latest
        assert events.is_pending(latest["id"]) is False


def test_business_command_replay_does_not_repeat_background_model_request(tmp_path):
    with event_stack(tmp_path) as (disputes, agent, events, model, drained):
        command = intake_command()
        case = disputes.execute(command, OP)["case"]
        assert drained.wait(timeout=3)
        before = agent.get_activity(case["id"], OP)
        assert len(model.requests) == 2
        replay = disputes.execute(command, OP)
        assert replay["replayed"] is True
        assert len(model.requests) == 2
        assert events.is_pending(case["id"]) is False
        assert agent.get_activity(case["id"], OP) == before
        assert disputes.get_case(case["id"], OP) == case


def test_completed_background_analysis_is_not_repeated_by_new_queue_after_restart(tmp_path):
    with event_stack(tmp_path) as (disputes, agent, events, model, drained):
        case = disputes.execute(intake_command(), OP)["case"]
        assert drained.wait(timeout=3)
        assert len(model.requests) == 2
    with event_stack(tmp_path) as (disputes, agent, events, model, drained):
        events.changed(disputes.get_case(case["id"], OP), "INTAKE")
        assert drained.wait(timeout=3)
        assert model.requests == []
        assert len(agent.get_activity(case["id"], OP)["conversations"]) == 1


def test_disabled_background_mode_still_records_immediate_tool_run(tmp_path):
    with event_stack(tmp_path, enabled=False) as (disputes, agent, events, model, _):
        case = disputes.execute(intake_command(), OP)["case"]
        activity = agent.get_activity(case["id"], OP)
        assert activity["run"]["case_revision"] == case["revision"]
        assert len(activity["run"]["steps"]) == 6
        assert activity["conversations"] == []
        assert events.is_pending(case["id"]) is False
        assert model.requests == []


def test_noncritical_idle_event_does_not_start_another_model_call(tmp_path):
    with event_stack(tmp_path) as (disputes, agent, events, model, drained):
        case = disputes.execute(intake_command(), OP)["case"]
        assert drained.wait(timeout=3)
        case = execute(disputes, case, "COMMENT", {"message": "OP updated local collaboration."})
        assert agent.get_activity(case["id"], OP)["run"]["case_revision"] == case["revision"]
        assert events.is_pending(case["id"]) is False
        assert len(model.requests) == 2


def test_merchant_evidence_changes_start_fresh_analysis_even_when_agent_was_idle(tmp_path):
    with event_stack(tmp_path, enabled=False) as (disputes, agent, events, model, drained):
        case = disputes.execute(intake_command(), OP)["case"]
        case = execute(disputes, case, "PUBLISH_TASK")
        case = execute(
            disputes,
            case,
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "Merchant confirmed contest"},
            MERCHANT,
        )
        events.enabled = True
        case = execute(
            disputes,
            case,
            "REGISTER_EVIDENCE",
            {
                "code": "fulfillment.tracking",
                "title": "Synthetic tracking",
                "reference": "synthetic-tracking-object",
                "source_channel": "PORTAL",
            },
            MERCHANT,
        )
        assert drained.wait(timeout=3)
        conversation = agent.get_activity(case["id"], MERCHANT)["conversations"][-1]
        assert conversation["trigger"] == "AUTO_EVENT:REGISTER_EVIDENCE"
        assert conversation["case_revision"] == case["revision"]
        assert len(model.requests) == 2
        drained.clear()
        case = execute(
            disputes,
            case,
            "WITHDRAW_EVIDENCE",
            {
                "evidence_id": case["evidence"][-1]["id"],
                "reason": "Merchant replaces document",
            },
            MERCHANT,
        )
        assert drained.wait(timeout=3)
        conversation = agent.get_activity(case["id"], MERCHANT)["conversations"][-1]
        assert conversation["trigger"] == "AUTO_EVENT:WITHDRAW_EVIDENCE"
        assert conversation["case_revision"] == case["revision"]
        assert len(model.requests) == 4


def test_restart_backfills_missing_merchant_analysis_without_repeating_internal_analysis(tmp_path):
    with event_stack(tmp_path, enabled=False) as (disputes, agent, events, model, drained):
        case = disputes.execute(intake_command(), OP)["case"]
        agent.converse(
            case["id"],
            {"role": "AGENT", "actor_id": "old-agent"},
            "旧版仅为运营团队分析",
            1,
            trigger="AUTO_EVENT:INTAKE",
        )
        prior = agent.get_activity(case["id"], OP)["conversations"]
        assert agent.get_activity(case["id"], MERCHANT)["conversations"] == []
        model.requests.clear()
        events.enabled = True
        events.schedule(case, "INTAKE")
        assert drained.wait(timeout=3)
        assert len(model.requests) == 1
        context = json.loads(model.requests[0]["messages"][0].content)
        assert context["audience"] == "MERCHANT"
        assert context["conversation_history"] == []
        assert agent.get_activity(case["id"], OP)["conversations"] == prior
        assert len(agent.get_activity(case["id"], MERCHANT)["conversations"]) == 1


def test_background_analysis_uses_only_same_audience_private_history(tmp_path):
    with event_stack(tmp_path, enabled=False) as (disputes, agent, events, model, drained):
        case = disputes.execute(intake_command(), OP)["case"]
        agent.converse(case["id"], OP, "INTERNAL-PRIVATE-DISCUSSION", 1)
        agent.converse(case["id"], MERCHANT, "MERCHANT-PRIVATE-DISCUSSION", 1)
        model.requests.clear()
        events.enabled = True
        events.schedule(case, "INTAKE")
        assert drained.wait(timeout=3)
        assert len(model.requests) == 2
        op_context = model.requests[0]["messages"][0].content
        merchant_context = model.requests[1]["messages"][0].content
        assert "INTERNAL-PRIVATE-DISCUSSION" in op_context
        assert "MERCHANT-PRIVATE-DISCUSSION" not in op_context
        assert "MERCHANT-PRIVATE-DISCUSSION" in merchant_context
        assert "INTERNAL-PRIVATE-DISCUSSION" not in merchant_context
