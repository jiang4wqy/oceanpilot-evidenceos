import asyncio
import base64
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from oceanpilot.adapters.persistence.dispute_agent import SQLiteDisputeAgentStore
from oceanpilot.adapters.persistence.dispute_collaboration import SQLiteDisputeCollaborationStore
from oceanpilot.adapters.persistence.dispute_updates import SQLiteDisputeUpdateReader
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_agent import DisputeAgentService
from oceanpilot.application.dispute_collaboration import DisputeCollaborationService
from oceanpilot.application.dispute_updates import DisputeUpdatesService
from oceanpilot.application.disputes import DisputeService
from oceanpilot.application.model_provider import ModelResult
from oceanpilot.domain.dispute import DisputeError

OP = {"role": "OPERATOR", "actor_id": "operator"}
MERCHANT = {"role": "MERCHANT", "actor_id": "merchant", "merchant_id": "merchant-a"}
OTHER = {"role": "MERCHANT", "actor_id": "other", "merchant_id": "merchant-b"}
NOW = datetime(2026, 9, 9, 8, tzinfo=UTC)


class Model:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def complete(self, task, messages, **kwargs):
        self.calls.append(json.loads(messages[0].content))
        if self.fail:
            raise RuntimeError("private provider detail")
        return ModelResult(
            text="请按本案已发布要求补充收货确认，OceanPayment 将继续审核。",
            model="scripted-shared-model",
        )


@pytest.fixture
def stack(tmp_path):
    clock = [NOW]
    path = tmp_path / "shared.db"
    disputes = DisputeService(SQLiteDisputeStore(path), clock=lambda: clock[0])
    model = Model()
    agent = DisputeAgentService(
        SQLiteDisputeAgentStore(path), disputes, model=model, clock=lambda: clock[0]
    )
    collab = DisputeCollaborationService(
        SQLiteDisputeCollaborationStore(path), disputes, agent, clock=lambda: clock[0]
    )
    agent.collaboration_provider = collab
    disputes.evidence_objects = collab
    case = disputes.execute(
        {
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "merchant_id": "merchant-a",
                "transaction_id": "synthetic-order-alpine",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 12500,
                "currency": "USD",
                "event_id": str(uuid4()),
            },
        },
        OP,
    )["case"]
    return disputes, agent, collab, case, model, clock


def command(disputes, case, action, data=None, identity=OP):
    return disputes.execute(
        {
            "command_id": str(uuid4()),
            "case_id": case["id"],
            "action": action,
            "expected_revision": case["revision"],
            "confirmed": True,
            "data": data or {},
        },
        identity,
    )["case"]


def collecting(stack):
    disputes, _, _, case, _, _ = stack
    case = command(disputes, case, "PUBLISH_TASK")
    return command(
        disputes,
        case,
        "MERCHANT_DECISION",
        {"decision": "CONTEST", "reason": "真实合成材料将支持抗辩"},
        MERCHANT,
    )


def file_payload(case, **overrides):
    data = {
        "transaction_id": case["transaction_id"],
        "currency": "USD",
        "amount_minor": 12500,
        "delivered_at": "2026-09-01T08:00:00Z",
        "recipient_confirmation": "synthetic signed receipt",
    }
    data.update(overrides)
    return {
        "command_id": str(uuid4()),
        "expected_revision": case["revision"],
        "code": "fulfillment.proof_of_delivery",
        "title": "合成收货确认",
        "filename": "delivery.json",
        "mime_type": "application/json",
        "content_base64": base64.b64encode(json.dumps(data).encode()).decode(),
    }


def test_shared_messages_cross_surfaces_with_distinct_sources_and_no_business_revision(stack):
    disputes, _, collab, case, _, _ = stack
    first = collab.post_message(case["id"], OP, str(uuid4()), "请补充收货签收确认。")
    collab.post_message(case["id"], MERCHANT, str(uuid4()), "我已经联系物流提供签收回执。")
    assert first["message"]["actor_type"] == "OCEANPAYMENT"
    seen = collab.activity(case["id"], MERCHANT)
    assert [m["actor_type"] for m in seen["messages"]] == ["OCEANPAYMENT", "MERCHANT"]
    assert disputes.get_case(case["id"], OP)["revision"] == case["revision"]
    assert all(m["delivery_status"] == "AVAILABLE_IN_PORTAL" for m in seen["messages"])


def test_internal_scope_never_visible_to_merchant_or_shared_model(stack):
    _, _, collab, case, model, _ = stack
    collab.post_message(case["id"], OP, str(uuid4()), "internal-strategy-marker", "OP_INTERNAL")
    collab.post_message(case["id"], OP, str(uuid4()), "shared-receipt-marker")
    result = collab.post_message(
        case["id"], MERCHANT, str(uuid4()), "这份签收证据为何不足？", ask_agent=True
    )
    assert result["source"] == "MODEL"
    assert "shared-receipt-marker" in json.dumps(model.calls[-1])
    assert "internal-strategy-marker" not in json.dumps(model.calls[-1])
    assert "internal-strategy-marker" not in json.dumps(collab.activity(case["id"], MERCHANT))
    with pytest.raises(DisputeError):
        collab.activity(case["id"], MERCHANT, "OP_INTERNAL")


def test_old_private_history_stays_private_read_only_and_out_of_shared_context(stack):
    _, agent, collab, case, model, _ = stack
    for role, audience, marker in [
        ("MERCHANT", "MERCHANT", "legacy-merchant-private"),
        ("OPERATOR", "OPERATIONS", "legacy-op-private"),
    ]:
        agent.store.save_conversation(
            {
                "id": str(uuid4()),
                "case_id": case["id"],
                "case_revision": case["revision"],
                "actor_role": role,
                "audience": audience,
                "message": marker,
                "answer": marker,
                "created_at": NOW.isoformat(),
            }
        )
    collab.post_message(case["id"], MERCHANT, str(uuid4()), "现在由谁处理？", ask_agent=True)
    context = json.dumps(model.calls[-1])
    assert "legacy-merchant-private" not in context and "legacy-op-private" not in context
    assert (
        agent.get_activity(case["id"], MERCHANT)["legacy_conversations"][0]["message"]
        == "legacy-merchant-private"
    )
    with pytest.raises(DisputeError) as exc:
        agent.converse(case["id"], MERCHANT, "new private", case["revision"], audience="MERCHANT")
    assert exc.value.code == "LEGACY_THREAD_READ_ONLY"


def test_message_replay_is_bound_to_identity_payload_scope_and_calls_model_once(stack):
    _, _, collab, case, model, _ = stack
    key = str(uuid4())
    first = collab.post_message(case["id"], MERCHANT, key, "缺少什么？", ask_agent=True)
    second = collab.post_message(case["id"], MERCHANT, key, "缺少什么？", ask_agent=True)
    assert second["replayed"] and len(model.calls) == 1
    assert first["message"]["id"] == second["message"]["id"]
    for identity, text, scope in [(OP, "缺少什么？", "SHARED"), (MERCHANT, "different", "SHARED")]:
        with pytest.raises(DisputeError) as exc:
            collab.post_message(case["id"], identity, key, text, scope, True)
        assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_other_merchant_cannot_read_write_or_ask_model(stack):
    _, _, collab, case, model, _ = stack
    with pytest.raises(DisputeError):
        collab.post_message(case["id"], OTHER, str(uuid4()), "read other", ask_agent=True)
    assert not model.calls
    with pytest.raises(DisputeError):
        collab.activity(case["id"], OTHER)


def test_model_failure_keeps_user_message_and_has_explicit_fallback(stack):
    _, _, collab, case, model, _ = stack
    model.fail = True
    result = collab.post_message(case["id"], MERCHANT, str(uuid4()), "缺什么？", ask_agent=True)
    assert result["source"] == "FALLBACK"
    assert len(collab.activity(case["id"], MERCHANT)["messages"]) == 2
    assert "private provider detail" not in json.dumps(result)


def test_read_cursor_is_real_monotonic_and_business_read_only(stack):
    disputes, _, collab, case, _, _ = stack
    message = collab.post_message(case["id"], OP, str(uuid4()), "请查看任务")["message"]
    assert collab.activity(case["id"], MERCHANT)["read_cursor"] == 0
    assert collab.mark_read(case["id"], MERCHANT, "SHARED", message["cursor"])["read_cursor"] > 0
    assert collab.mark_read(case["id"], MERCHANT, "SHARED", 0)["read_cursor"] > 0
    with pytest.raises(DisputeError):
        collab.mark_read(case["id"], MERCHANT, "SHARED", 99999)
    assert disputes.get_case(case["id"], OP)["revision"] == case["revision"]


def test_handoff_requires_claim_then_resolution_with_full_history_and_no_business_change(stack):
    disputes, _, collab, case, _, _ = stack
    h = collab.create_handoff(case["id"], MERCHANT, str(uuid4()), "请人工确认签收标准")["handoff"]
    assert h["status"] == "OPEN" and h["follow_up_at"]
    duplicate = collab.create_handoff(case["id"], MERCHANT, str(uuid4()), h["reason"])
    assert duplicate["handoff"]["id"] == h["id"]
    with pytest.raises(DisputeError):
        collab.update_handoff(case["id"], OP, h["id"], str(uuid4()), "RESOLVE", "done")
    collab.update_handoff(case["id"], OP, h["id"], str(uuid4()), "CLAIM", "已接手")
    result = collab.update_handoff(
        case["id"], OP, h["id"], str(uuid4()), "RESOLVE", "已解释所需材料"
    )
    assert result["handoff"]["claimed_at"] and result["handoff"]["resolved_at"]
    assert (
        len([e for e in collab.store.events(case["id"], "SHARED") if e["kind"] == "HANDOFF"]) == 3
    )
    assert disputes.get_case(case["id"], OP)["revision"] == case["revision"]


def test_merchant_cannot_claim_and_arbitrary_assignee_is_rejected(stack):
    _, _, collab, case, _, _ = stack
    with pytest.raises(DisputeError):
        collab.create_handoff(case["id"], MERCHANT, str(uuid4()), "help", assignee_id="untrusted")
    h = collab.create_handoff(case["id"], MERCHANT, str(uuid4()), "help")["handoff"]
    with pytest.raises(DisputeError):
        collab.update_handoff(case["id"], MERCHANT, h["id"], str(uuid4()), "CLAIM", "take")


def test_real_file_content_is_stored_cited_and_download_authorized(stack):
    _, _, collab, _, _, _ = stack
    case = collecting(stack)
    payload = file_payload(case)
    result = collab.upload_file(case["id"], MERCHANT, **payload)
    obj = result["file"]
    assert obj["content_check"]["status"] == "SUPPORTED" and obj["content_check"]["locators"]
    assert result["case"]["evidence"][-1]["object_id"] == obj["id"]
    assert collab.download_file(case["id"], obj["id"], OP)["content"] == base64.b64decode(
        payload["content_base64"]
    )
    assert result["case"]["revision"] == case["revision"] + 1
    with pytest.raises(DisputeError):
        collab.download_file(case["id"], obj["id"], OTHER)


def test_missing_content_facts_are_not_satisfied_by_evidence_code(stack):
    disputes, _, collab, _, _, _ = stack
    case = collecting(stack)
    result = collab.upload_file(
        case["id"], MERCHANT, **file_payload(case, recipient_confirmation="")
    )
    assert result["file"]["content_check"]["status"] == "INSUFFICIENT"
    assert "recipient_confirmation" in str(result["file"]["content_check"]["findings"])
    with pytest.raises(DisputeError) as exc:
        command(disputes, result["case"], "SUBMIT_EVIDENCE", identity=MERCHANT)
    assert exc.value.code == "CONTENT_CHECK_REQUIRED"


@pytest.mark.parametrize(
    "change",
    [
        {"transaction_id": "unrelated"},
        {"amount_minor": 777},
        {"currency": "EUR"},
        {"status": "not_delivered"},
    ],
)
def test_conflicting_files_are_saved_for_review_without_claiming_support(stack, change):
    _, _, collab, _, _, _ = stack
    case = collecting(stack)
    result = collab.upload_file(case["id"], MERCHANT, **file_payload(case, **change))
    assert result["file"]["content_check"]["status"] == "INSUFFICIENT"


def test_file_command_replay_preserves_single_object_and_business_revision(stack):
    disputes, _, collab, _, _, _ = stack
    case = collecting(stack)
    payload = file_payload(case)
    result = collab.upload_file(case["id"], MERCHANT, **payload)
    replay = collab.upload_file(case["id"], MERCHANT, **payload)
    assert replay["replayed"] and replay["file"]["id"] == result["file"]["id"]
    assert len(collab.store.objects(case["id"])) == 1
    assert disputes.get_case(case["id"], OP)["revision"] == result["case"]["revision"]


def test_duplicate_content_is_not_registered_twice(stack):
    _, _, collab, _, _, _ = stack
    case = collecting(stack)
    payload = file_payload(case)
    result = collab.upload_file(case["id"], MERCHANT, **payload)
    with pytest.raises(DisputeError) as exc:
        collab.upload_file(
            case["id"],
            MERCHANT,
            **(
                payload
                | {"command_id": str(uuid4()), "expected_revision": result["case"]["revision"]}
            ),
        )
    assert exc.value.code == "DUPLICATE_FILE"


@pytest.mark.parametrize(
    "filename,mime,data",
    [
        ("empty.txt", "text/plain", b"   "),
        ("script.html", "text/plain", b"<script>alert(1)</script>"),
        ("fake.json", "application/json", b"not json"),
        ("markup.txt", "text/plain", b"<html>executable</html>"),
        ("binary.txt", "text/plain", b"\xff\x00"),
    ],
)
def test_unusable_or_disguised_files_are_rejected(stack, filename, mime, data):
    _, _, collab, _, _, _ = stack
    case = collecting(stack)
    payload = file_payload(case) | {
        "filename": filename,
        "mime_type": mime,
        "content_base64": base64.b64encode(data).decode(),
    }
    with pytest.raises(DisputeError):
        collab.upload_file(case["id"], MERCHANT, **payload)
    assert not collab.store.objects(case["id"])


def test_only_clock_progress_produces_durable_deduplicated_reminders(stack):
    disputes, _, collab, _, _, clock = stack
    case = collecting(stack)
    assert not collab.tick()["emitted"]
    clock[0] += timedelta(hours=74)
    first = collab.tick()["emitted"]
    assert len(first) == 1 and first[0]["deadline_type"] == "merchant"
    assert not collab.tick()["emitted"]
    assert disputes.get_case(case["id"], OP)["revision"] == case["revision"]
    restarted = DisputeCollaborationService(
        SQLiteDisputeCollaborationStore(collab.store.db_path), disputes, clock=lambda: clock[0]
    )
    assert not restarted.tick()["emitted"]


def test_shared_events_wake_both_update_streams_without_changing_business_revision(stack):
    _, _, collab, case, _, _ = stack
    service = DisputeUpdatesService(SQLiteDisputeUpdateReader(collab.store.db_path))
    before = asyncio.run(service.poll(MERCHANT, case_id=case["id"], timeout=0))
    collab.post_message(case["id"], OP, str(uuid4()), "same case update")
    change = asyncio.run(
        service.poll(MERCHANT, case_id=case["id"], cursor=before["cursor"], timeout=0)
    )
    assert change["changes"][0]["collaboration_changed"]
    assert not change["changes"][0]["case_changed"]
    before = change
    collab.post_message(case["id"], OP, str(uuid4()), "internal update", "OP_INTERNAL")
    unchanged = asyncio.run(
        service.poll(MERCHANT, case_id=case["id"], cursor=before["cursor"], timeout=0)
    )
    assert not unchanged["changes"]


def test_approved_patterns_retrieved_only_with_approval_scope_stage_and_version(stack):
    disputes, agent, _, case, _, _ = stack
    other = dict(case)
    other["id"] = "approved-source-case"
    other["knowledge_candidates"] = [
        {
            "id": "approved-pattern",
            "status": "APPROVED",
            "redacted": True,
            "human_pii_review_confirmed": True,
            "summary": "签收证明需包含实际收件确认",
            "pattern": "发货记录不能代替签收确认",
            "rule_version": case["rule_snapshot"]["rule_version"],
            "reviewed_at": NOW.isoformat(),
        }
    ]
    with sqlite3.connect(disputes.store.db_path) as db:
        row = db.execute("SELECT * FROM v2_dispute_cases WHERE case_id=?", (case["id"],)).fetchone()
        columns = [r[1] for r in db.execute("PRAGMA table_info(v2_dispute_cases)")]
        values = dict(zip(columns, row, strict=True))
        values["case_id"], values["snapshot"] = other["id"], json.dumps(other)
        db.execute(
            "INSERT INTO v2_dispute_cases VALUES (" + ",".join("?" for _ in values) + ")",
            list(values.values()),
        )
    references = agent._retrieve_knowledge(case)["references"]
    assert references[0]["knowledge_id"] == "approved-pattern"
    assert references[0]["approval_version"] and not references[0]["production_eligible"]
    case = case | {"merchant_id": "merchant-b"}
    assert agent._approved_knowledge(case) == []


def test_reading_receipt_itself_does_not_cause_infinite_update_writes(stack):
    _, _, collab, case, _, _ = stack
    message = collab.post_message(case["id"], OP, str(uuid4()), "请阅读")["message"]
    collab.mark_read(case["id"], MERCHANT, "SHARED", message["cursor"])
    position = collab.store.cursor(case["id"], "SHARED")
    for _ in range(4):
        collab.mark_read(case["id"], MERCHANT, "SHARED", position)
    assert collab.store.cursor(case["id"], "SHARED") == position


def test_overdue_handoff_escalates_once_and_resolved_handoff_stops(stack):
    _, _, collab, case, _, clock = stack
    handoff = collab.create_handoff(case["id"], MERCHANT, str(uuid4()), "请人工确认")
    clock[0] += timedelta(hours=5)
    collab.tick()
    escalated = collab.activity(case["id"], MERCHANT)["handoffs"][0]
    assert escalated["escalation_level"] == 1
    count = len(collab.store.events(case["id"], "SHARED"))
    collab.tick()
    assert len(collab.store.events(case["id"], "SHARED")) == count
    identifier = handoff["handoff"]["id"]
    collab.update_handoff(case["id"], OP, identifier, str(uuid4()), "CLAIM", "已接手")
    collab.update_handoff(case["id"], OP, identifier, str(uuid4()), "RESOLVE", "已解决")
    collab.tick()
    assert collab.activity(case["id"], MERCHANT)["handoffs"][0]["status"] == "RESOLVED"


def test_late_model_result_does_not_lose_shared_question_or_publish_stale_answer(stack):
    disputes, agent, collab, case, _, _ = stack

    class ChangingModel:
        def complete(self, task, messages, **kwargs):
            command(disputes, case, "PUBLISH_TASK")
            return ModelResult(text="stale answer", model="scripted")

    agent.model = ChangingModel()
    result = collab.post_message(case["id"], MERCHANT, str(uuid4()), "请解释进度", ask_agent=True)
    assert result["agent_status"] == "CASE_CHANGED" and result["message_preserved"]
    assert collab.activity(case["id"], MERCHANT)["messages"][0]["message"] == "请解释进度"
    assert all(
        m.get("message") != "stale answer"
        for m in collab.activity(case["id"], MERCHANT)["messages"]
    )


def test_edited_proposal_keeps_server_verified_origin_and_replays_after_revision_change(stack):
    disputes, agent, _, case, _, _ = stack
    disputes.proposal_validator = agent.validate_proposal_edit
    run = agent.observe(case, "INTAKE")
    proposal = run["proposals"][0]
    payload = {
        "command_id": str(uuid4()),
        "case_id": case["id"],
        "action": proposal["action"],
        "expected_revision": case["revision"],
        "confirmed": True,
        "data": {"message": "请按共享线程中的清单补充签收材料。"},
        "proposal_origin": {
            "run_id": run["id"],
            "proposal_id": proposal["id"],
            "scope": proposal["scope"],
            "original_revision": case["revision"],
        },
    }
    result = disputes.execute(payload, OP)
    origin = result["case"]["audit"][-1]["proposal_origin"]
    assert origin["edited"] and origin["original_data"] == proposal["data"]
    assert origin["actual_data"] == payload["data"] and origin["confirmed_by"] == OP["actor_id"]
    assert disputes.execute(payload, OP)["replayed"]


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "different"},
        {"scope": "OP_INTERNAL"},
        {"action": "RECORD_FINANCIAL"},
        {"original_revision": 99},
    ],
)
def test_proposal_origin_tampering_is_rejected(stack, change):
    _, agent, _, case, _, _ = stack
    run = agent.observe(case, "INTAKE")
    proposal = run["proposals"][0]
    args = {
        "run_id": run["id"],
        "proposal_id": proposal["id"],
        "scope": proposal["scope"],
        "original_revision": case["revision"],
        "expected_revision": case["revision"],
        "action": proposal["action"],
        "actual_data": proposal["data"],
    } | change
    with pytest.raises(DisputeError):
        agent.validate_proposal_edit(case["id"], OP, **args)


def test_approved_closed_case_pattern_is_used_by_next_case_and_pending_is_excluded(stack):
    disputes, agent, collab, case, model, clock = stack
    supervisor = {"role": "SUPERVISOR", "actor_id": "supervisor"}
    admin = {"role": "ADMIN", "actor_id": "knowledge-reviewer"}
    source = command(
        disputes,
        case,
        "RECORD_OUTCOME",
        {
            "event_id": str(uuid4()),
            "source": "MOCK",
            "outcome": "WITHDRAWN",
            "final": True,
            "reason": "已核验合成撤回事件",
        },
    )
    source = command(
        disputes,
        source,
        "VERIFY_OUTCOME",
        {
            "event_id": source["upstream_events"][-1]["event_id"],
            "decision": "CONFIRM",
            "reason": "已核对合成上游来源和当前阶段",
            "authorization_reference": "mock-review-confirmed",
        },
        {"role": "RISK_OFFICER", "actor_id": "risk-reviewer"},
    )
    source = command(
        disputes,
        source,
        "RECONCILE",
        {
            "status": "NOT_APPLICABLE",
            "expected_net_minor": 0,
            "reason": "合成撤回无需资金事项",
            "reference": "mock-withdrawal",
        },
        supervisor,
    )
    source = command(disputes, source, "NOTIFY_MERCHANT", {"message": "该合成争议已正式撤回。"})
    source = command(disputes, source, "CLOSE", identity=supervisor)
    source = command(
        disputes,
        source,
        "KNOWLEDGE_CANDIDATE",
        {
            "summary": "本模式要求对收货确认逐项核查。",
            "pattern": "tracking is distinct from recipient confirmation",
        },
    )
    candidate = source["knowledge_candidates"][-1]
    other = disputes.execute(
        {
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "merchant_id": "merchant-a",
                "transaction_id": "synthetic-next-case",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 12500,
                "currency": "USD",
                "event_id": str(uuid4()),
            },
        },
        OP,
    )["case"]
    assert agent._approved_knowledge(other) == []
    command(
        disputes,
        source,
        "APPROVE_KNOWLEDGE",
        {
            "candidate_id": candidate["id"],
            "decision": "APPROVE",
            "reason": "已人工核对脱敏、范围和来源",
        },
        admin,
    )
    result = collab.post_message(
        other["id"], MERCHANT, str(uuid4()), "如何准备签收材料？", ask_agent=True
    )
    assert result["source"] == "MODEL"
    assert any(
        r.get("knowledge_id") == candidate["id"]
        for r in model.calls[-1]["reference_knowledge"]["references"]
    )
    clock[0] += timedelta(days=10)
    assert not [e for e in collab.tick()["emitted"] if e["case_id"] == case["id"]]


@pytest.mark.parametrize(
    "changes",
    [
        {"transaction_id": "wrong-order"},
        {"currency": "EUR"},
        {"amount_minor": 12500.9},
        {"amount_minor": True},
        {"status": "not_delivered"},
    ],
)
def test_unknown_file_type_cannot_bypass_common_case_fact_checks(stack, changes):
    _, _, collaboration, case, _, _ = stack
    facts = {
        "transaction_id": case["transaction_id"],
        "currency": case["currency"],
        "amount_minor": case["amount_minor"],
    } | changes
    assessment = collaboration._assess(case, "unknown.claim_document", json.dumps(facts), facts)
    assert assessment["status"] == "INSUFFICIENT" and assessment["findings"]


def test_unknown_document_with_matching_transaction_retains_facts_for_independent_review(stack):
    _, _, collaboration, case, _, _ = stack
    facts = {
        "transaction_id": case["transaction_id"],
        "currency": case["currency"],
        "amount_minor": case["amount_minor"],
    }
    assessment = collaboration._assess(case, "unknown.claim_document", json.dumps(facts), facts)
    assert assessment["status"] == "NEEDS_MANUAL"
    assert assessment["facts"] == facts
