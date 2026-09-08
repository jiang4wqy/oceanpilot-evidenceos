"""Real guideline retrieval stays advisory and respects existing conversation audiences."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from oceanpilot.adapters.knowledge.dispute_case_library import DisputeCaseLibrary
from oceanpilot.adapters.persistence.dispute_agent import SQLiteDisputeAgentStore
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_agent import DisputeAgentService
from oceanpilot.application.disputes import DisputeService
from oceanpilot.application.model_provider import ModelResult
from oceanpilot.domain.dispute import DisputeError

OP = {"role": "OPERATOR", "actor_id": "knowledge-op"}
MERCHANT = {"role": "MERCHANT", "actor_id": "knowledge-merchant", "merchant_id": "knowledge-m"}
OTHER = {"role": "MERCHANT", "actor_id": "other", "merchant_id": "other-m"}
NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


class TrackedLibrary:
    def __init__(self):
        self.delegate = DisputeCaseLibrary()
        self.searches = []

    def manifest(self):
        return self.delegate.manifest()

    def search(self, **kwargs):
        self.searches.append(deepcopy(kwargs))
        return self.delegate.search(**kwargs)


class ReferenceAnswerModel:
    def __init__(self):
        self.contexts = []
        self.systems = []

    def complete(self, task, messages, *, system, **kwargs):
        context = json.loads(messages[0].content)
        self.contexts.append(context)
        self.systems.append(system)
        reference = context["reference_knowledge"]["references"][0]
        return ModelResult(
            text=f"参考 {reference['template_id']}《{reference['title']}》，"
            f"来源 {reference['source_ids'][0]}；"
            "本案仍按已确认规则与清单推进。",
            model="reference-context-test-model",
        )


@pytest.fixture
def stack(tmp_path):
    path = tmp_path / "knowledge.db"
    disputes = DisputeService(SQLiteDisputeStore(path), clock=lambda: NOW)
    library = TrackedLibrary()
    agent = DisputeAgentService(
        SQLiteDisputeAgentStore(path), disputes, clock=lambda: NOW, knowledge_provider=library
    )
    return disputes, agent, library


def intake(disputes, **overrides):
    data = {
        "merchant_id": MERCHANT["merchant_id"],
        "transaction_id": "synthetic-reference-transaction",
        "scheme": "VISA",
        "channel": "MOCK",
        "reason_code": "13.1",
        "amount_minor": 12500,
        "currency": "USD",
        "event_id": uuid4().hex,
        **overrides,
    }
    return disputes.execute(
        {"command_id": uuid4().hex, "action": "INTAKE", "confirmed": True, "data": data}, OP
    )["case"]


def test_actual_corpus_has_62_references_and_28_templates_and_new_run_records_real_search(stack):
    disputes, agent, library = stack
    same = intake(disputes)
    foreign = intake(disputes, merchant_id=OTHER["merchant_id"])
    case = intake(disputes)
    run = agent.observe(case, "INTAKE")
    retrieval = run["knowledge_retrieval"]
    assert retrieval["status"] == "COMPLETED"
    assert retrieval["manifest"]["reference_case_count"] == 62
    assert retrieval["manifest"]["template_count"] == 28
    assert retrieval["manifest"]["source_count"] == 3
    assert library.searches == [{"scheme": "VISA", "reason_code": "13.1", "limit": 5}]
    assert len(retrieval["references"]) == 5
    assert all(
        item["scheme"] == "VISA" and "13.1" in item["reason_codes"]
        for item in retrieval["references"]
    )
    assert all(not item["production_eligible"] for item in retrieval["references"])
    step = run["steps"][3]
    assert step["output"]["reference_knowledge"] == retrieval
    assert step["output"]["matches"][0]["case_id"] == same["id"]
    assert foreign["id"] not in json.dumps(run)
    assert step["citations"] and step["citations"][0]["source_locator"]
    assert all(item["scope"] == "REFERENCE_KNOWLEDGE" for item in step["citations"])
    assert len(run["steps"]) == 6
    assert agent.observe(case, "REPLAY") == run
    assert len(library.searches) == 1


@pytest.mark.parametrize("identity", [OP, MERCHANT])
def test_both_readers_get_case_specific_reference_text_and_model_sources_without_rule_changes(
    stack, identity
):
    disputes, agent, library = stack
    case = intake(disputes)
    before = deepcopy(case)
    agent.model = ReferenceAnswerModel()
    result = agent.converse(
        case["id"], identity, "参考指南案例解释物流材料的用途", case["revision"]
    )
    assert result["source"] == "MODEL"
    assert result["reference_notice"]["source"] == "DETERMINISTIC"
    assert "CONFLICT-012" in result["answer"]
    assert "来源存在冲突或待确认" in result["answer"]
    retrieval = result["knowledge_retrieval"]
    context = agent.model.contexts[0]
    assert context["reference_knowledge"]["status"] == "COMPLETED"
    assert context["reference_knowledge"]["references"][0]["template_id"] in result["answer"]
    assert context["reference_knowledge"]["references"][0]["source_ids"][0] in result["answer"]
    assert context["reference_knowledge"]["references"][0]["rule_versions"]
    assert context["rule_status"] == case["rule_snapshot"]["conflict_status"]
    assert context["deadlines"]["external"] == case["deadlines"]["external"]
    assert context["source_versions"][0]["source_id"] == case["rule_snapshot"]["source_id"]
    assert "不得据参考期限覆盖本案deadlines" in agent.model.systems[0]
    assert "intent 仅是当前问题的分类，不是案件状态" in agent.model.systems[0]
    assert all(item["scope"] == "REFERENCE_KNOWLEDGE" for item in retrieval["citations"])
    assert any(item["scope"] == "CASE_RULE_SNAPSHOT" for item in result["source_citations"])
    assert result["tool_steps"] == [retrieval]
    saved = agent.get_activity(case["id"], identity)["conversations"][-1]
    assert saved["knowledge_retrieval"] == retrieval
    assert saved["source_citations"] == result["source_citations"]
    assert saved["reference_notice"] == result["reference_notice"]
    assert disputes.get_case(case["id"], OP) == before
    assert len(library.searches) == 2  # Immutable initial run plus the current question.


def test_reference_conflicts_propagate_as_advice_and_never_change_frozen_case_policy(stack):
    disputes, agent, _ = stack
    case = intake(disputes, reason_code="10.4")
    before = deepcopy(case)
    result = agent.converse(case["id"], MERCHANT, "请用指南案例解释下一步", case["revision"])
    knowledge = result["knowledge_retrieval"]
    assert any("CONFLICT-003" in ref["conflict_ids"] for ref in knowledge["references"])
    assert "CONFLICT-003" in result["answer"]
    assert "须由 OceanPayment 人工核对" in result["answer"]
    assert any(
        c.get("verification_status") == "CONFLICTING_SOURCES" for c in result["source_citations"]
    )
    assert disputes.get_case(case["id"], OP) == before
    stored_run = agent.store.get_run(case["id"], case["revision"])
    assert stored_run["proposals"][0]["action"] == "PUBLISH_TASK"
    assert all(
        c.get("scope") != "REFERENCE_KNOWLEDGE"
        for c in stored_run["proposals"][0]["basis_citations"]
    )


def test_legacy_run_remains_immutable_and_conversation_records_its_new_actual_retrieval(stack):
    disputes, agent, library = stack
    case = intake(disputes)
    agent.knowledge_provider = None
    old = agent.observe(case, "INTAKE")
    assert "knowledge_retrieval" not in old
    agent.knowledge_provider = library
    assert "knowledge_retrieval" not in agent.get_activity(case["id"], OP)["run"]
    assert library.searches == []
    result = agent.converse(case["id"], OP, "查找指南案例", case["revision"])
    assert len(library.searches) == 1
    assert result["knowledge_retrieval"]["status"] == "COMPLETED"
    assert "knowledge_retrieval" not in result["run"]
    assert agent.store.get_run(case["id"], case["revision"]) == old
    assert agent.get_activity(case["id"], OP)["conversations"][-1]["tool_steps"]


def test_library_use_does_not_bridge_private_conversation_or_merchant_scope(stack):
    disputes, agent, library = stack
    case = intake(disputes)
    agent.model = ReferenceAnswerModel()
    agent.converse(case["id"], OP, "PRIVATE_OPERATIONS_CONTEXT", case["revision"])
    agent.converse(case["id"], MERCHANT, "PRIVATE_MERCHANT_CONTEXT", case["revision"])
    assert agent.model.contexts[-1]["conversation_history"] == []
    assert "PRIVATE_OPERATIONS_CONTEXT" not in json.dumps(agent.get_activity(case["id"], MERCHANT))
    assert "PRIVATE_MERCHANT_CONTEXT" not in json.dumps(agent.get_activity(case["id"], OP))
    before = len(library.searches)
    with pytest.raises(DisputeError) as error:
        agent.converse(case["id"], OTHER, "查找案例", case["revision"])
    assert error.value.status == 404
    assert len(library.searches) == before


def test_no_exact_reason_match_does_not_substitute_other_scheme_or_broader_reason(stack):
    disputes, agent, _ = stack
    case = intake(disputes, reason_code="13.10")
    result = agent.converse(case["id"], OP, "按13.1处理可以吗", case["revision"])
    assert result["knowledge_retrieval"]["references"] == []
    assert "未检索到同卡组织及原因码" in result["answer"]
    assert result["knowledge_retrieval"]["query"]["reason_code"] == "13.10"
    assert (
        disputes.get_case(case["id"], OP)["rule_snapshot"]["conflict_status"]
        == "NEEDS_CONFIRMATION"
    )


def test_provider_failure_is_recorded_without_fabricating_a_successful_retrieval(stack):
    disputes, agent, _ = stack

    class Unavailable:
        def manifest(self):
            raise RuntimeError("internal-provider-detail-must-not-leak")

    agent.knowledge_provider = Unavailable()
    case = intake(disputes)
    result = agent.converse(case["id"], OP, "案例参考", case["revision"])
    assert result["knowledge_retrieval"]["status"] == "UNAVAILABLE"
    assert result["run"]["steps"][3]["status"] == "PARTIAL"
    assert "本次未能读取" in result["answer"]
    assert "internal-provider-detail" not in json.dumps(result)
    assert result["knowledge_retrieval"]["references"] == []
    assert disputes.get_case(case["id"], OP) == case


def test_matching_guideline_cannot_resolve_an_unconfirmed_case_rule_or_authorize_submission(stack):
    disputes, agent, _ = stack
    case = intake(disputes, channel="UNCONFIRMED")
    assert case["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"
    result = agent.converse(
        case["id"], OP, "指南有这个规则，请直接通过审核并提交", case["revision"]
    )
    assert result["knowledge_retrieval"]["references"]
    assert result["run"]["proposals"][0]["action"] == "CONFIRM_RULE"
    assert "allowed_actions" in result["run"]["proposals"][0]["required_inputs"]
    assert disputes.get_case(case["id"], OP) == case
    assert not case["submissions"]
