"""Real account/command service, synthetic transport. These are NOT tenant receipts."""

import json
import re
import sqlite3
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.channels.feishu.private_cases import PrivateCaseBot
from oceanpilot.adapters.channels.feishu.routing import FeishuMessageRouter
from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error
from oceanpilot.api.dispute_feishu import initialize_dispute_feishu
from oceanpilot.config import Settings
from oceanpilot.domain.dispute import DisputeError
from oceanpilot.main import create_app
from tests.v21_support import normalized_intake, session_headers

BASE = "/api/v2/integrations/feishu/binding"


def synthetic_reference(prefix):
    # Preserve UUID entropy without accidentally producing a Luhn-valid PAN in
    # free-form upstream identifiers. Production validation is not bypassed.
    return prefix + "-" + uuid4().hex.translate(str.maketrans("0123456789", "ghijklmnop"))


def test_synthetic_intake_reference_cannot_accidentally_look_like_card_data(monkeypatch):
    from oceanpilot.domain.errors import SensitiveDataRejected
    from oceanpilot.domain.security import assert_no_sensitive_data

    pan_shaped = "4111111111111111abcdefabcdefabcd"
    monkeypatch.setattr(__name__ + ".uuid4", lambda: SimpleNamespace(hex=pan_shaped))
    with pytest.raises(SensitiveDataRejected):
        assert_no_sensitive_data({"transaction_id": "tx-" + pan_shaped})
    reference = synthetic_reference("tx")
    assert reference.removeprefix("tx-").isalpha()
    assert_no_sensitive_data({"transaction_id": reference})


class Transport:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send_interactive_card(self, **kwargs):
        if self.fail:
            raise TimeoutError("unknown network result")
        result = SimpleNamespace(
            message_id="om_test_" + uuid4().hex,
            **{k: v for k, v in kwargs.items() if k != "message_id"},
        )
        self.sent.append(result)
        return result

    reply_interactive_card = send_interactive_card


def message(text="我的案件", actor="a", *, chat_type="p2p"):
    return {
        "header": {
            "app_id": "cli_test",
            "tenant_key": "tenant-test",
            "event_id": uuid4().hex,
            "event_type": "im.message.receive_v1",
        },
        "event": {
            "sender": {"sender_type": "user", "sender_id": {"open_id": "ou_" + actor}},
            "message": {
                "message_id": "om_" + uuid4().hex,
                "chat_id": "oc_" + actor,
                "chat_type": chat_type,
                "message_type": "text",
                "content": json.dumps({"text": text}),
            },
        },
    }


def click(receipt, label, *, actor="a", message_id=None):
    value = next(
        b["value"]
        for e in receipt.card["elements"]
        for b in e.get("actions", [])
        if b["text"]["content"] == label
    )
    return {
        "header": {
            "app_id": "cli_test",
            "tenant_key": "tenant-test",
            "event_id": uuid4().hex,
            "event_type": "card.action.trigger",
        },
        "event": {
            "token": uuid4().hex,
            "operator": {"open_id": "ou_" + actor},
            "context": {
                "open_chat_id": "oc_" + actor,
                "open_message_id": message_id or receipt.message_id,
            },
            "action": {"value": value},
        },
    }


def body(receipt):
    return receipt.card["elements"][0]["text"]["content"]


def pairing_phrase(receipt):
    match = re.search(r"配对验证短语：([0-9a-f]{8})", body(receipt))
    assert match is not None, "Pairing must obtain its challenge from the private DM"
    return match.group(1)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    with TestClient(create_app(Settings(db_path=tmp_path / "business.db"))) as client:
        initialize_dispute_feishu(
            client.app,
            tmp_path / "business.db",
            environ={
                "FEISHU_APP_ID": "cli_test",
                "FEISHU_ENCRYPT_KEY": "test-secret",
                "FEISHU_VERIFICATION_TOKEN": "test-token",
                "OCEANPILOT_FEISHU_PRIVATE_CASES": "enabled",
            },
        )
        bot = client.app.state.feishu_private
        clock = [1800000000.0]
        bot.now = lambda: clock[0]
        bot.client = Transport()
        accounts = {}
        for name in ["a", "b"]:
            headers = session_headers(client, "MERCHANT", "synthetic-" + name)
            account = client.app.state.v21_auth.authenticate(headers["Cookie"].split("=", 1)[1])
            accounts[name] = account | {"headers": headers}
        yield SimpleNamespace(
            client=client,
            bot=bot,
            accounts=accounts,
            clock=clock,
            disputes=client.app.state.disputes,
        )


def bind(env, who="a"):
    bot = env.bot
    account = env.accounts[who]["actor_id"]
    pair = bot.create_pair(account)
    bot.handle(message("绑定 " + pair["code"], who), mode="events")
    bot.drain()
    phrase = pairing_phrase(bot.client.sent[-1])
    bot.confirm_pair(account, pair["pair_id"], phrase)
    return pair


def intake(env, who="a", *, publish=True):
    response = normalized_intake(
        env.client,
        {
            "confirmed": True,
            "data": {
                "merchant_id": "synthetic-" + who,
                "transaction_id": synthetic_reference("tx"),
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 12800,
                "currency": "USD",
                "event_id": synthetic_reference("bank"),
            },
        },
    )
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    if publish:
        headers = session_headers(env.client, "OPERATOR", "synthetic-" + who)
        operator = env.bot.directory.authenticate(headers["Cookie"].split("=", 1)[1])
        case = env.disputes.execute(
            {
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "action": "PUBLISH_TASK",
                "confirmed": True,
                "data": {},
            },
            operator,
        )["case"]
    return case


def decision(env, choice="CONTEST"):
    bind(env)
    case = intake(env)
    env.bot.handle(message(), mode="events")
    env.bot.drain()
    label = "发起抗辩" if choice == "CONTEST" else "接受拒付"
    assert label in json.dumps(env.bot.client.sent[-1].card, ensure_ascii=False), body(
        env.bot.client.sent[-1]
    )
    first = click(env.bot.client.sent[-1], label)
    env.bot.handle(first, mode="card")
    env.bot.drain()
    assert env.disputes.get_case(case["id"], env.accounts["a"])["merchant_decision"] == "NONE"
    second = click(env.bot.client.sent[-1], "确认" + label)
    return case, second


def test_pairing_api_requires_session_csrf_and_owner(env):
    c = env.client
    assert c.post(BASE + "/pairs").status_code == 401
    h = env.accounts["a"]["headers"]
    assert c.post(BASE + "/pairs", headers={"Cookie": h["Cookie"]}).status_code == 403
    p = c.post(BASE + "/pairs", headers=h)
    assert p.status_code == 200, p.text
    assert p.headers["Cache-Control"] == "no-store"
    ref = p.json()["pair_id"]
    assert c.get(BASE + "/pairs/" + ref, headers=env.accounts["b"]["headers"]).status_code == 404
    assert (
        c.post(
            BASE + "/pairs/" + ref + "/confirm", headers=h, json={"phrase": "12345678"}
        ).status_code
        == 409
    )
    assert c.get(BASE + "/page", headers=h).status_code == 200


def test_pair_once_encrypted_and_no_silent_overwrite(env):
    pair = bind(env)
    data = env.bot.path.read_bytes()
    assert pair["code"].encode() not in data and b"ou_a" not in data and b"oc_a" not in data
    with pytest.raises(FeishuV2Error, match="UNLINK_BEFORE_REBIND"):
        env.bot.create_pair(env.accounts["a"]["actor_id"])
    with pytest.raises(FeishuV2Error, match="PAIR_INVALID_OR_EXPIRED"):
        env.bot.handle(message("绑定 " + pair["code"], "b"), mode="events")


def test_pair_expiry_and_website_confirmation(env):
    account = env.accounts["a"]["actor_id"]
    p = env.bot.create_pair(account)
    env.clock[0] += 601
    with pytest.raises(FeishuV2Error, match="PAIR_INVALID_OR_EXPIRED"):
        env.bot.handle(message("绑定 " + p["code"]), mode="events")
    p = env.bot.create_pair(account)
    env.bot.handle(message("绑定 " + p["code"]), mode="events")
    assert env.bot.binding_status(account)["bound"] is False
    h = env.accounts["a"]["headers"]
    env.bot.drain()
    phrase = pairing_phrase(env.bot.client.sent[-1])
    assert (
        env.client.post(
            BASE + "/pairs/" + p["pair_id"] + "/confirm", headers=h, json={"phrase": phrase}
        ).status_code
        == 200
    )
    assert env.client.delete(BASE, headers=h).json() == {"bound": False}


@pytest.mark.parametrize("choice", ["ACCEPT", "CONTEST"])
def test_real_command_two_steps_and_duplicate_receipt(env, choice):
    case, second = decision(env, choice)
    result = env.bot.handle(second, mode="card")
    assert result["outcome"] == "QUEUED"
    current = env.disputes.get_case(case["id"], env.accounts["a"])
    assert current["merchant_decision"] == choice
    assert current["revision"] == case["revision"] + 1
    assert env.bot.handle(second, mode="card")["outcome"] == "REPLAYED"
    duplicate = deepcopy(second)
    duplicate["event"]["token"] = uuid4().hex
    duplicate["header"]["event_id"] = uuid4().hex
    env.bot.handle(duplicate, mode="card")
    assert env.disputes.get_case(case["id"], env.accounts["a"])["revision"] == current["revision"]
    env.bot.drain()
    text = body(env.bot.client.sent[-1])
    assert "Mock" in text and "未调用语言模型" in text
    assert ("抗辩材料清单" in text) == (choice == "CONTEST")
    if choice == "CONTEST":
        assert "用途" in text and "来源" in text


@pytest.mark.parametrize(
    "attack", ["different_user", "forward", "extra_value", "expired", "disabled", "unlink"]
)
def test_confirmation_fail_closed(env, attack):
    case, second = decision(env)
    if attack == "different_user":
        bind(env, "b")
        second["event"]["operator"]["open_id"] = "ou_b"
        second["event"]["context"]["open_chat_id"] = "oc_b"
    elif attack == "forward":
        second["event"]["context"]["open_message_id"] = "om_forwarded"
    elif attack == "extra_value":
        second["event"]["action"]["value"]["confirmed"] = True
    elif attack == "expired":
        env.clock[0] += 301
    elif attack == "unlink":
        env.bot.unlink(env.accounts["a"]["actor_id"])
    else:
        env.bot.directory.set_disabled(env.accounts["a"]["actor_id"], True)
    with pytest.raises((FeishuV2Error, DisputeError)):
        env.bot.handle(second, mode="card")
    assert env.disputes.store.get_case(case["id"])["merchant_decision"] == "NONE"


def test_another_merchant_cannot_read_forged_case_id(env):
    case = intake(env, "a")
    bind(env, "b")
    with pytest.raises(DisputeError):
        env.bot.handle(message(case["id"], "b"), mode="events")
    assert all(case["id"] not in body(item) for item in env.bot.client.sent)


def test_bound_it_admin_cannot_read_runtime_cases(env):
    case = intake(env)
    headers = session_headers(env.client, "ADMIN", "synthetic-a")
    account = env.bot.directory.authenticate(headers["Cookie"].split("=", 1)[1])
    env.accounts["it"] = account | {"headers": headers}
    bind(env, "it")
    env.bot.handle(message(actor="it"), mode="events")
    env.bot.drain()
    assert case["id"] not in body(env.bot.client.sent[-1])
    with pytest.raises(DisputeError):
        env.bot.handle(message(case["id"], "it"), mode="events")


def test_role_change_to_it_revokes_pending_private_confirmation(env):
    case, second = decision(env)
    with sqlite3.connect(env.bot.directory.db_path) as db:
        db.execute(
            "UPDATE v21_users SET role='ADMIN' WHERE user_id=?", (env.accounts["a"]["actor_id"],)
        )
    with pytest.raises((FeishuV2Error, DisputeError)):
        env.bot.handle(second, mode="card")
    assert env.disputes.store.get_case(case["id"])["merchant_decision"] == "NONE"


def test_multiple_cases_require_selection(env):
    bind(env)
    a = intake(env)
    b = intake(env)
    env.bot.handle(message(), mode="events")
    env.bot.drain()
    receipt = env.bot.client.sent[-1]
    assert "请选择" in body(receipt)
    env.bot.handle(click(receipt, f"{b['id']} · {b['work_status']}"), mode="card")
    env.bot.drain()
    assert b["id"] in body(env.bot.client.sent[-1]) and a["id"] not in body(env.bot.client.sent[-1])


def test_bound_group_message_never_reaches_case_service(env):
    bind(env)
    case = intake(env)
    public = SimpleNamespace(handle=lambda *args, **kwargs: {"public": True})
    router = FeishuMessageRouter(public, env.bot)
    result = router.handle(message(case["id"], chat_type="group"), mode="events")
    assert result == {"public": True}
    with pytest.raises(FeishuV2Error, match="PRIVATE_CHAT_REQUIRED"):
        env.bot.handle(message(case["id"], chat_type="group"), mode="events")


def test_durable_outbox_uncertain_never_blindly_retried(env):
    bind(env)
    intake(env)
    env.bot.observe()
    env.bot.client.fail = True
    env.bot.drain()
    with env.bot.db() as db:
        assert (
            db.execute("SELECT count(*) FROM fp_records WHERE state='UNCERTAIN'").fetchone()[0] == 1
        )
    env.bot.client.fail = False
    restarted = PrivateCaseBot(
        env.bot.path,
        directory=env.bot.directory,
        disputes=env.disputes,
        app_id="cli_test",
        secret="test-secret",
        base_url="http://testserver",
        client=env.bot.client,
        now=env.bot.now,
    )
    before = len(restarted.client.sent)
    restarted.observe()
    restarted.drain()
    assert len(restarted.client.sent) == before


def test_unlink_blocks_waiting_notices(env):
    bind(env)
    intake(env)
    env.bot.observe()
    env.bot.unlink(env.accounts["a"]["actor_id"])
    before = len(env.bot.client.sent)
    env.bot.drain()
    assert len(env.bot.client.sent) == before


def test_role_change_to_it_blocks_waiting_notices(env):
    bind(env)
    intake(env)
    env.bot.observe()
    with sqlite3.connect(env.bot.directory.db_path) as db:
        db.execute(
            "UPDATE v21_users SET role='ADMIN' WHERE user_id=?",
            (env.accounts["a"]["actor_id"],),
        )
    before = len(env.bot.client.sent)
    env.bot.drain()
    env.bot.observe()
    env.bot.drain()
    assert len(env.bot.client.sent) == before
    with env.bot.db() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM fp_records WHERE kind='job' AND state='BLOCKED'"
            ).fetchone()[0]
            == 1
        )


def test_stale_confirmation_uses_business_revision_gate(env):
    case, second = decision(env)
    env.disputes.execute(
        {
            "command_id": str(uuid4()),
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "action": "MERCHANT_DECISION",
            "confirmed": True,
            "data": {"decision": "ACCEPT", "reason": "website choice"},
        },
        env.accounts["a"],
    )
    with pytest.raises(DisputeError):
        env.bot.handle(second, mode="card")
    assert env.disputes.store.get_case(case["id"])["merchant_decision"] == "ACCEPT"


def test_pending_intake_has_no_decision_buttons(env):
    bind(env)
    case = intake(env, publish=False)
    env.bot.handle(message(case["id"]), mode="events")
    env.bot.drain()
    receipt = env.bot.client.sent[-1]
    assert "待工作人员核实" in body(receipt)
    assert not any(b.get("value") for e in receipt.card["elements"] for b in e.get("actions", []))


def test_demo_batch_reset_preserves_cases_and_invalidates_cards(env):
    from oceanpilot.adapters.channels.feishu.demo import FeishuDemoBatches

    bind(env)
    admin_headers = session_headers(env.client, "ADMIN", "synthetic-a")
    admin = env.bot.directory.authenticate(admin_headers["Cookie"].split("=", 1)[1])
    operators = []
    for name in ["a", "b"]:
        h = session_headers(env.client, "OPERATOR", "synthetic-" + name)
        operators.append(env.bot.directory.authenticate(h["Cookie"].split("=", 1)[1])["actor_id"])
    batches = FeishuDemoBatches(env.bot, env.client.app.state.dispute_intake)
    spec = dict(
        administrator=admin["actor_id"],
        operators=operators,
        merchants=["synthetic-a", "synthetic-b"],
        confirmed=True,
    )
    batch_id = str(uuid4())
    first = batches.begin(batch_id, **spec)
    assert batches.begin(batch_id, **spec) == first
    assert len(env.disputes.list_cases(env.accounts["a"])) == 1
    old = env.disputes.store.get_case(first["cases"][0])
    assert old["merchant_decision"] == "NONE" and old["work_status"] == "MERCHANT_ACTION_REQUIRED"
    assert old["rule_snapshot"]["reason_code"] == "13.1"
    env.bot.observe()
    env.bot.drain()
    old_click = click(env.bot.client.sent[-1], "发起抗辩")
    second = batches.begin(str(uuid4()), **spec)
    assert set(first["cases"]).isdisjoint(second["cases"])
    assert env.disputes.store.get_case(old["id"])["audit"] == old["audit"]
    with pytest.raises(FeishuV2Error):
        env.bot.handle(old_click, mode="card")
    env.bot.handle(message(), mode="events")
    env.bot.drain()
    assert second["cases"][0] in body(env.bot.client.sent[-1])
    assert old["id"] not in body(env.bot.client.sent[-1])


def test_crash_after_business_commit_replays_without_second_decision(env, monkeypatch):
    case, second = decision(env)
    original = env.bot.put
    crashed = [False]

    def crash(db, kind, ref, owner, state, data):
        if kind == "card" and state == "DONE" and not crashed[0]:
            crashed[0] = True
            raise RuntimeError("simulated crash after business commit")
        return original(db, kind, ref, owner, state, data)

    monkeypatch.setattr(env.bot, "put", crash)
    with pytest.raises(RuntimeError):
        env.bot.handle(second, mode="card")
    assert env.disputes.store.get_case(case["id"])["merchant_decision"] == "CONTEST"
    env.bot.handle(second, mode="card")
    assert env.disputes.store.get_case(case["id"])["revision"] == case["revision"] + 1


def test_material_upload_and_return_match_website(env):
    import base64

    case, second = decision(env)
    env.bot.handle(second, mode="card")
    merchant = env.accounts["a"]["headers"]
    current = env.disputes.store.get_case(case["id"])
    root = f"/api/v2/cases/{case['id']}/collaboration"
    for code in current["rule_snapshot"]["required_evidence"]:
        sample = env.client.get(root + f"/samples/{code}?variant=sufficient", headers=merchant)
        assert sample.status_code == 200, sample.text
        upload = env.client.post(
            root + "/files",
            headers=merchant,
            json={
                "command_id": str(uuid4()),
                "expected_revision": current["revision"],
                "code": code,
                "title": "Synthetic sample",
                "filename": "sample.json",
                "mime_type": "application/json",
                "content_base64": base64.b64encode(sample.content).decode(),
            },
        )
        assert upload.status_code == 200, upload.text
        current = upload.json()["case"]
    submit = env.client.post(
        "/api/v2/commands",
        headers=merchant,
        json={
            "command_id": str(uuid4()),
            "case_id": case["id"],
            "expected_revision": current["revision"],
            "action": "SUBMIT_EVIDENCE",
            "confirmed": True,
            "data": {},
        },
    )
    assert submit.status_code == 200, submit.text
    current = submit.json()["case"]
    operator = session_headers(env.client, "OPERATOR", "synthetic-a")
    returned = env.client.post(
        "/api/v2/commands",
        headers=operator,
        json={
            "command_id": str(uuid4()),
            "case_id": case["id"],
            "expected_revision": current["revision"],
            "action": "REVIEW",
            "confirmed": True,
            "data": {"decision": "REVISION", "reason": "请补充清晰的签收页（合成演示反馈）"},
        },
    )
    assert returned.status_code == 200, returned.text
    current = returned.json()["case"]
    env.bot.observe()
    env.bot.handle(message("为什么退回 " + case["id"]), mode="events")
    env.bot.drain()
    text = body(env.bot.client.sent[-1])
    assert "清晰的签收页" in text and f"版本 {current['revision']}" in text
    assert "内容检查就绪" in text and "MERCHANT_REVISION_REQUIRED" in text
    assert text.index("审核反馈：") < text.index("抗辩材料清单")
    assert "清晰的签收页" in text[:500]
    assert "下一步：先按审核反馈补充或更正材料，再提交人工复核。" in text
    assert "当前规则清单全部就绪" not in text
    assert "登记清单齐全，提交 OP 人工复核" not in text
    assert "材料已核验，可以提交" not in text
    assert any(e["source_channel"] == "PORTAL" for e in current["evidence"])


def test_lease_recovery_does_not_assume_delivery(env):
    bind(env)
    intake(env)
    env.bot.observe()
    with env.bot.db() as db:
        db.execute(
            "UPDATE fp_records SET state='SENDING',updated=? WHERE kind='job' AND state='PENDING'",
            (env.clock[0] - 121,),
        )
    before = len(env.bot.client.sent)
    env.bot.drain()
    assert len(env.bot.client.sent) == before
    with env.bot.db() as db:
        assert (
            db.execute("SELECT count(*) FROM fp_records WHERE state='UNCERTAIN'").fetchone()[0] == 1
        )


def test_signed_callback_and_challenge_without_legacy_adapter(env):
    import hashlib
    import time

    from tests.feishu.crypto_helpers import encrypted_body

    def post(payload, path="/events", good=True):
        payload = deepcopy(payload)
        payload.setdefault("header", {})["token"] = "test-token"
        body = encrypted_body(payload, "test-secret")
        timestamp = str(int(time.time()))
        nonce = "private-test-nonce"
        signature = hashlib.sha256((timestamp + nonce + "test-secret").encode() + body).hexdigest()
        return env.client.post(
            "/api/v2/integrations/feishu" + path,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Lark-Request-Timestamp": timestamp,
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": signature if good else "bad",
            },
        )

    assert post(message(), good=False).status_code == 401
    assert post(message()).status_code == 200
    challenge = post(
        {"type": "url_verification", "token": "test-token", "challenge": "synthetic-challenge"}
    )
    assert challenge.json() == {"challenge": "synthetic-challenge"}


def test_signed_live_format_card_timestamp_runs_two_steps_only_on_card_route(env):
    import hashlib
    from datetime import UTC, datetime

    from tests.feishu.crypto_helpers import encrypted_body

    bind(env)
    case = intake(env)
    env.bot.handle(message(case["id"]), mode="events")
    env.bot.drain()

    def post(label):
        payload = click(env.bot.client.sent[-1], label)
        payload["schema"] = "2.0"
        payload["header"]["token"] = "test-token"
        raw = encrypted_body(payload, "test-secret")
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S +0000 UTC m=+123.123456789")
        signature = hashlib.sha256((stamp + "nonce" + "test-secret").encode() + raw).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": stamp,
            "X-Lark-Request-Nonce": "nonce",
            "X-Lark-Signature": signature,
        }
        root = "/api/v2/integrations/feishu"
        assert env.client.post(root + "/events", content=raw, headers=headers).status_code == 401
        result = env.client.post(root + "/card", content=raw, headers=headers)
        assert result.status_code == 200 and result.json()["outcome"] == "QUEUED"
        env.bot.drain()

    post("发起抗辩")
    assert env.disputes.store.get_case(case["id"])["merchant_decision"] == "NONE"
    post("确认发起抗辩")
    assert env.disputes.store.get_case(case["id"])["merchant_decision"] == "CONTEST"


@pytest.mark.parametrize(
    "response", ['{"fact_ids":["fact-0"]}', '{"fact_ids":["invented"]}', "invalid"]
)
def test_model_only_selects_authorized_facts_or_degrades(env, response):
    from oceanpilot.application.model_provider import ModelResult

    calls = []

    def complete(task, messages, **kwargs):
        calls.append((task, messages, kwargs))
        return ModelResult(text=response)

    env.bot.model = SimpleNamespace(complete=complete)
    bind(env)
    case = intake(env)
    env.bot.handle(message("当前进度 " + case["id"]), mode="events")
    env.bot.drain()
    assert len(calls) == 1
    prompt = calls[0][1][0].content
    assert case["id"] not in prompt and "ou_a" not in prompt and "synthetic-a" not in prompt
    assert calls[0][2]["tools"] == ()
    text = body(env.bot.client.sent[-1])
    if response.startswith('{"fact_ids":["fact-0"'):
        assert "模型辅助定位实际事实" in text and "[fact-0]" in text
    else:
        assert "结构化降级" in text and "invented" not in text


def test_revoke_during_model_latency_prevents_send(env):
    from oceanpilot.application.model_provider import ModelResult

    bind(env)
    case = intake(env)
    env.bot.handle(message(case["id"]), mode="events")

    def complete(*args, **kwargs):
        env.bot.unlink(env.accounts["a"]["actor_id"])
        return ModelResult(text='{"fact_ids":["fact-0"]}')

    env.bot.model = SimpleNamespace(complete=complete)
    before = len(env.bot.client.sent)
    env.bot.drain()
    assert len(env.bot.client.sent) == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["event"].update(sender=[]),
        lambda p: p["event"]["message"].update(content="[]"),
        lambda p: p["event"]["message"].update(content='{"text":0}'),
        lambda p: p["event"]["sender"].update(tenant_key="another-tenant"),
    ],
)
def test_malformed_private_envelopes_fail_closed(env, mutate):
    payload = message()
    mutate(payload)
    with pytest.raises(FeishuV2Error):
        env.bot.handle(payload, mode="events")


def test_pairing_cross_origin_and_no_session_cannot_unlink(env):
    bind(env)
    headers = env.accounts["a"]["headers"] | {"Origin": "https://attacker.invalid"}
    assert env.client.delete(BASE, headers=headers).status_code == 403
    assert env.client.delete(BASE).status_code == 401
    assert env.bot.binding_status(env.accounts["a"]["actor_id"])["bound"]


def test_missing_provider_receipt_is_uncertain_not_sent(env):
    bind(env)
    intake(env)
    env.bot.observe()
    env.bot.client = SimpleNamespace(
        send_interactive_card=lambda **kwargs: SimpleNamespace(message_id="")
    )
    env.bot.drain()
    with env.bot.db() as db:
        assert (
            db.execute("SELECT count(*) FROM fp_records WHERE state='UNCERTAIN'").fetchone()[0] == 1
        )


def test_vault_key_or_application_mismatch_fails_at_startup(env):
    for secret, app in [("wrong-key", "cli_test"), ("test-secret", "different-app")]:
        with pytest.raises(ValueError):
            PrivateCaseBot(
                env.bot.path,
                directory=env.bot.directory,
                disputes=env.disputes,
                app_id=app,
                secret=secret,
                base_url="http://testserver",
            )


def test_selection_card_rechecks_each_case_before_send(env, monkeypatch):
    bind(env)
    intake(env)
    other = intake(env)
    env.bot.handle(message(), mode="events")
    original = env.disputes.get_case

    def deny(case_id, identity):
        if case_id == other["id"]:
            raise DisputeError("NOT_FOUND", "No longer authorized", 404)
        return original(case_id, identity)

    monkeypatch.setattr(env.disputes, "get_case", deny)
    before = len(env.bot.client.sent)
    env.bot.drain()
    assert len(env.bot.client.sent) == before


def test_pair_status_does_not_disclose_dm_challenge_or_address(env):
    h = env.accounts["a"]["headers"]
    pair = env.client.post(BASE + "/pairs", headers=h).json()
    env.bot.handle(message("绑定 " + pair["code"]), mode="events")
    env.bot.drain()
    phrase = pairing_phrase(env.bot.client.sent[-1])
    response = env.client.get(BASE + "/pairs/" + pair["pair_id"], headers=h)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"pair_id": pair["pair_id"], "state": "CLAIMED"}
    for secret in (pair["code"], phrase, "ou_a", "oc_a", "tenant-test"):
        assert secret not in response.text
    wrong = "ffffffff" if phrase != "ffffffff" else "00000000"
    rejected = env.client.post(
        BASE + "/pairs/" + pair["pair_id"] + "/confirm", headers=h, json={"phrase": wrong}
    )
    assert rejected.status_code == 403
    assert env.client.get(BASE, headers=h).json()["bound"] is False


@pytest.mark.parametrize("change", ["access", "revision", "expiry"])
def test_selection_card_revalidates_dependencies_immediately_before_send(env, monkeypatch, change):
    bind(env)
    intake(env)
    target = intake(env)
    env.bot.handle(message(), mode="events")
    original = env.disputes.get_case

    def changed_case(case_id, identity):
        case = original(case_id, identity)
        if case_id == target["id"]:
            if change == "access":
                raise DisputeError("NOT_FOUND", "Grant revoked during preparation", 404)
            if change == "revision":
                return case | {"revision": case["revision"] + 1}
        return case

    def prepare(card, intent, model):
        # Another request can revoke a grant or revise a case after the first
        # validation transaction. No selected case_id exists on a list-card job.
        monkeypatch.setattr(env.disputes, "get_case", changed_case)
        if change == "expiry":
            later = env.bot.now() + 1900
            monkeypatch.setattr(env.bot, "now", lambda: later)
        return card

    monkeypatch.setattr("oceanpilot.adapters.channels.feishu.private_cases.focused_card", prepare)
    before = len(env.bot.client.sent)
    env.bot.drain()
    assert len(env.bot.client.sent) == before
    with env.bot.db() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM fp_records WHERE kind='job' AND state='BLOCKED'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("mutation", ["expired", "regenerated", "disabled", "unlinked"])
def test_claimed_pair_rechecks_account_expiry_and_revocation(env, mutation):
    account = env.accounts["a"]["actor_id"]
    pair = env.bot.create_pair(account)
    env.bot.handle(message("绑定 " + pair["code"]), mode="events")
    env.bot.drain()
    phrase = pairing_phrase(env.bot.client.sent[-1])
    if mutation == "expired":
        env.clock[0] += 601
    elif mutation == "regenerated":
        env.bot.create_pair(account)
    elif mutation == "disabled":
        env.bot.directory.set_disabled(account, True)
    else:
        env.bot.unlink(account)
    with pytest.raises(FeishuV2Error):
        env.bot.confirm_pair(account, pair["pair_id"], phrase)
    with env.bot.db() as db:
        assert env.bot.link(db, account=account) is None


def test_pair_confirmation_cannot_be_reused(env):
    account = env.accounts["a"]["actor_id"]
    pair = bind(env)
    phrase = pairing_phrase(env.bot.client.sent[-1])
    version = env.bot.binding_status(account)["version"]
    with pytest.raises(FeishuV2Error, match="PAIR_INVALID_OR_EXPIRED"):
        env.bot.confirm_pair(account, pair["pair_id"], phrase)
    assert env.bot.binding_status(account)["version"] == version


def test_same_open_id_in_another_tenant_cannot_reuse_binding(env):
    bind(env)
    case = intake(env)
    payload = message(case["id"])
    payload["header"]["tenant_key"] = "different-tenant"
    env.bot.handle(payload, mode="events")
    env.bot.drain()
    text = body(env.bot.client.sent[-1])
    assert "配对码" in text and case["id"] not in text
