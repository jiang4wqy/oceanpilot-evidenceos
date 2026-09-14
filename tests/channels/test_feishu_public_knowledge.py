"""Public KB acceptance with synthetic sources and mock delivery, never tenant evidence."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oceanpilot.adapters.channels.feishu.knowledge_bot import KnowledgeBot, load_public_groups
from oceanpilot.adapters.channels.feishu.public_knowledge import PublicKnowledge, knowledge_card
from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error
from oceanpilot.adapters.feishu.security import FeishuRequestVerifier
from oceanpilot.api.dispute_feishu import _outbox_call, initialize_dispute_feishu, router
from oceanpilot.application.model_provider import ModelResult, ToolCall
from tests.channels.test_dispute_feishu import ENCRYPT_KEY, NOW, TOKEN, message_payload, post

DOC = {
    "id": "guide-upload",
    "title": "材料上传指南",
    "text": "材料上传请使用网站。补件时查看审核反馈。",
    "source": "synthetic-product-guide",
    "version": "test-v1",
    "approval_reference": "synthetic-approval",
    "visibility": "PUBLIC_GROUP",
    "approved": True,
    "source_type": "PRODUCT_GUIDE",
}
GROUPS = {
    "groups": [
        {
            "tenant_key": "tenant-1",
            "chat_id": "oc-merchant",
            "authorized": True,
            "allow_replies": True,
            "authorization_reference": "synthetic-owner-approval",
        }
    ]
}


class Model:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or ModelResult(
            text=json.dumps({"answer": "材料上传请使用网站。", "source_ids": ["guide-upload"]})
        )

    def complete(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


class Client:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def reply_interactive_card(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("must not be exposed")
        return SimpleNamespace(message_id="synthetic-receipt")


def payload(text="@OceanPilot 材料上传怎么办", event_id="public-question"):
    value = message_payload(text, event_id=event_id, chat_type="group")
    value["header"]["app_id"] = "synthetic-app"
    value["event"]["message"]["message_id"] = "synthetic-message"
    return value


def bot(tmp_path, **kwargs):
    return KnowledgeBot(
        tmp_path / "kb.db",
        kwargs.pop("knowledge", PublicKnowledge([DOC])),
        groups=kwargs.pop("groups", load_public_groups(json.dumps(GROUPS))),
        secret=ENCRYPT_KEY,
        app_id="synthetic-app",
        base_url="https://example.test",
        client=kwargs.pop("client", Client()),
        **kwargs,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved", False),
        ("approved", "true"),
        ("visibility", "MERCHANT_ONLY"),
        ("source_type", "RUNTIME_CASE"),
        ("approval_reference", ""),
        ("text", "contact alice@example.com"),
        ("text", "OPV2-sensitive-case"),
    ],
)
def test_corpus_requires_publication_and_safe_content(field, value):
    with pytest.raises(ValueError):
        PublicKnowledge([DOC | {field: value}])


def test_corpus_duplicate_and_empty_behavior():
    with pytest.raises(ValueError):
        PublicKnowledge([DOC, DOC])
    assert PublicKnowledge().answer("材料上传怎么办")["mode"] == "NO_MATCH"


@pytest.mark.parametrize("question", ["你好", "您好！", "hello", "Hi!", "帮助"])
def test_greeting_works_without_published_knowledge_or_model(question):
    model = Model()
    answer = PublicKnowledge(model=model).answer(question)
    assert answer["mode"] == "HELP"
    assert answer["sources"] == []
    assert "不查询具体案件" in answer["text"]
    assert model.calls == []


def test_retrieval_is_cited_and_never_claims_model_call():
    answer = PublicKnowledge([DOC]).answer("材料上传怎么办")
    assert answer["mode"] == "RETRIEVAL_ONLY"
    assert answer["sources"][0]["id"] == DOC["id"]
    card = knowledge_card(answer, "https://example.test")
    assert "未调用模型" in json.dumps(card, ensure_ascii=False)
    assert card["elements"][-1]["actions"][0]["url"] == "https://example.test/v2/login"


def test_model_gets_only_question_and_public_sources_no_tools():
    model = Model()
    answer = PublicKnowledge([DOC], model=model).answer("材料上传怎么办")
    assert answer["mode"] == "MODEL_WITH_RETRIEVAL"
    args, kwargs = model.calls[0]
    context = json.loads(args[1][0].content)
    assert set(context) == {"question", "references"}
    assert kwargs["tools"] == ()
    assert context["references"][0]["id"] == DOC["id"]


@pytest.mark.parametrize(
    "response",
    [
        ModelResult(text="not json"),
        ModelResult(text='{"answer":"unsupported","source_ids":["invented"]}'),
        ModelResult(text='{"answer":"alice@example.com","source_ids":["guide-upload"]}'),
        ModelResult(
            text='{"answer":"done","source_ids":["guide-upload"]}',
            tool_calls=(ToolCall(call_id="x", name="execute", arguments={}),),
        ),
    ],
)
def test_invalid_or_unsafe_model_response_uses_truthful_fallback(response):
    answer = PublicKnowledge([DOC], model=Model(response)).answer("材料上传怎么办")
    assert answer["mode"] == "RETRIEVAL_FALLBACK"
    assert answer["text"] == "[guide-upload] " + DOC["text"]


@pytest.mark.parametrize(
    "question",
    [
        "我的案件进度",
        "案件列表",
        "确认接受责任",
        "确认审核通过",
        "OPV2-private",
        "alice@example.com",
    ],
)
def test_private_questions_never_reach_model(question):
    model = Model()
    answer = PublicKnowledge([DOC], model=model).answer(question)
    assert answer["mode"] == "WEBSITE_HANDOFF"
    assert question not in answer["text"]
    assert not model.calls


def test_delivery_duplicate_and_restart_do_not_repeat(tmp_path):
    first = bot(tmp_path)
    assert first.handle(payload(), mode="events")["outcome"] == "QUEUED"
    first.drain()
    assert len(first.client.calls) == 1
    second = bot(tmp_path)
    assert second.handle(payload(), mode="events")["delivery"] == "SENT"
    second.drain()
    assert not second.client.calls
    with second._db() as db:
        row = db.execute("SELECT * FROM feishu_public_questions").fetchone()
        assert row["receipt"] == "synthetic-receipt"
        assert b"synthetic-message" not in row["encrypted_request"]


def test_event_conflict_unknown_group_and_old_cards_fail_closed(tmp_path):
    worker = bot(tmp_path)
    worker.handle(payload(), mode="events")
    with pytest.raises(FeishuV2Error, match="EVENT_PAYLOAD_CONFLICT"):
        worker.handle(payload("@OceanPilot 其他问题"), mode="events")
    with pytest.raises(FeishuV2Error, match="PUBLIC_GROUP_NOT_AUTHORIZED"):
        bot(tmp_path, groups={}).handle(payload(), mode="events")
    with pytest.raises(FeishuV2Error, match="BUSINESS_ACTIONS_DISABLED"):
        worker.handle({"action": "ACCEPT"}, mode="card")


def test_file_is_not_downloaded_and_does_not_reach_model(tmp_path):
    model = Model()
    worker = bot(tmp_path, knowledge=PublicKnowledge([DOC], model=model))
    data = payload()
    data["event"]["message"].update(message_type="file", content='{"file_key":"private-file"}')
    worker.handle(data, mode="events")
    worker.drain()
    assert not model.calls
    assert "private-file" not in json.dumps(worker.client.calls)


@pytest.mark.parametrize("revocation", ["group", "source"])
def test_revocation_blocks_pending_delivery(tmp_path, revocation):
    worker = bot(tmp_path)
    worker.handle(payload(), mode="events")
    if revocation == "group":
        next(iter(worker.groups.values()))["allow_replies"] = False
    else:
        worker.approval_revision = lambda: "changed"
    worker.drain()
    assert not worker.client.calls
    with worker._db() as db:
        assert db.execute("SELECT state FROM feishu_public_questions").fetchone()[0] == "BLOCKED"


def test_timeout_and_restart_keep_uncertain_without_auto_retry(tmp_path):
    worker = bot(tmp_path, client=Client(fail=True))
    worker.handle(payload(), mode="events")
    worker.drain()
    second = bot(tmp_path)
    second.drain()
    assert not second.client.calls
    assert second.handle(payload(), mode="events")["delivery"] == "UNCERTAIN"


def test_no_mention_or_non_user_is_ignored(tmp_path):
    worker = bot(tmp_path)
    assert worker.handle(payload("材料上传"), mode="events")["outcome"] == "IGNORED"
    data = payload()
    data["event"]["sender"]["sender_type"] = "app"
    assert worker.handle(data, mode="events")["outcome"] == "IGNORED"


def test_production_initialization_ignores_legacy_business_config(tmp_path, monkeypatch):
    monkeypatch.setattr(KnowledgeBot, "start", lambda self: None)
    app = FastAPI()
    # No app.state.disputes or identity directory exists at all.
    env = {
        "FEISHU_APP_ID": "synthetic-app",
        "FEISHU_ENCRYPT_KEY": ENCRYPT_KEY,
        "FEISHU_VERIFICATION_TOKEN": TOKEN,
        "OCEANPILOT_V2_FEISHU_BINDINGS_JSON": "invalid",
        "OCEANPILOT_V21_FEISHU_OUTBOUND": "authorized-test",
    }
    assert initialize_dispute_feishu(app, tmp_path / "business.db", environ=env)
    assert isinstance(app.state.dispute_feishu, KnowledgeBot)
    assert not app.state.dispute_feishu.enabled
    assert not (tmp_path / "business.db").exists()
    app.state.dispute_feishu.groups = load_public_groups(json.dumps(GROUPS))
    app.state.dispute_feishu_verifier = FeishuRequestVerifier(
        encrypt_key=ENCRYPT_KEY, verification_token=TOKEN, now=lambda: NOW
    )
    app.include_router(router)
    with TestClient(app) as client:
        assert post(client, "/api/v2/integrations/feishu/events", payload()).status_code == 200
        response = post(client, "/api/v2/integrations/feishu/card", {"action": "ACCEPT"})
        # Token-verification must still precede all callback dispatch.
        assert response.status_code == 401
        old = copy.deepcopy(payload())
        old["header"]["event_type"] = "card.action.trigger"
        assert post(client, "/api/v2/integrations/feishu/card", old).status_code == 403
    result = asyncio.run(_outbox_call(SimpleNamespace(app=app), "send", "old-case-card"))
    assert result.status_code == 403


def test_public_group_authorization_is_explicit():
    data = copy.deepcopy(GROUPS)
    data["groups"][0]["allow_replies"] = False
    with pytest.raises(ValueError):
        load_public_groups(json.dumps(data))


def test_retired_v1_routes_never_dispatch_business_actions():
    from oceanpilot.api.feishu import router as legacy_router

    app = FastAPI()
    app.include_router(legacy_router)
    with TestClient(app) as client:
        for path in ("events", "card-actions"):
            response = client.post(f"/api/v1/integrations/feishu/{path}", json={"action": "ACCEPT"})
            assert response.status_code == 410


def test_reentrant_worker_cannot_claim_preparing_request_twice(tmp_path):
    worker = bot(tmp_path)
    other = bot(tmp_path)
    original = worker.knowledge.answer

    def answer(question):
        other.drain()
        return original(question)

    worker.knowledge.answer = answer
    worker.handle(payload(), mode="events")
    worker.drain()
    assert len(worker.client.calls) == 1
    assert not other.client.calls


def test_expired_preparation_cannot_send_after_another_worker_blocks_it(tmp_path):
    clock = [1000.0]
    worker = bot(tmp_path, now=lambda: clock[0])
    other = bot(tmp_path, now=lambda: clock[0])
    original = worker.knowledge.answer

    def slow_answer(question):
        clock[0] += 121
        other.drain()
        return original(question)

    worker.knowledge.answer = slow_answer
    worker.handle(payload(), mode="events")
    worker.drain()
    assert not worker.client.calls and not other.client.calls
    with worker._db() as db:
        assert db.execute("SELECT state FROM feishu_public_questions").fetchone()[0] == "BLOCKED"


def test_public_source_retraction_during_generation_blocks_delivery(tmp_path):
    worker = bot(tmp_path)
    original = worker.knowledge.answer

    def answer(question):
        worker.approval_revision = lambda: "retracted"
        return original(question)

    worker.knowledge.answer = answer
    worker.handle(payload(), mode="events")
    worker.drain()
    assert not worker.client.calls


def test_unapproved_product_draft_answers_natural_questions_only_in_validation_copy():
    path = Path(__file__).resolve().parents[2] / "docs/v2/feishu-public-knowledge.example.json"
    documents = json.loads(path.read_text(encoding="utf-8"))["documents"]
    assert all(doc["approved"] is False for doc in documents)
    with pytest.raises(ValueError):
        PublicKnowledge.from_path(path)
    # Test only: never writes approval to the actual publication manifest.
    kb = PublicKnowledge(
        [
            dict(doc, approved=True, approval_reference="synthetic-validation-only")
            for doc in documents
        ]
    )
    for question, expected in [
        ("OceanPilot 是做什么的？", "oceanpilot-product-purpose"),
        ("怎样登录网站？", "oceanpilot-website-login"),
        ("在哪里上传材料？", "oceanpilot-material-guide"),
        ("退回补件是什么意思？", "oceanpilot-correction-feedback"),
        ("群机器人能做什么？", "oceanpilot-bot-boundary"),
    ]:
        answer = kb.answer(question)
        assert answer["mode"] == "RETRIEVAL_ONLY"
        assert answer["sources"][0]["id"] == expected
