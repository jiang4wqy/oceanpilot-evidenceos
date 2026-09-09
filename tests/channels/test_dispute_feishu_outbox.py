"""No real Feishu transport: immutable delivery, isolation, and signed shared callbacks."""

import copy
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.channels.feishu.outbox import FeishuDisputeOutbox, load_test_targets
from oceanpilot.adapters.channels.feishu.v2 import (
    FeishuV2Adapter,
    FeishuV2Error,
    FeishuV2Store,
    TrustedBindings,
    binding_key,
)
from oceanpilot.api.dispute_feishu import initialize_dispute_feishu
from oceanpilot.config import Settings
from oceanpilot.main import create_app

NOW = datetime(2026, 9, 9, 11, tzinfo=UTC).timestamp()
OP = {"role": "OPERATOR", "actor_id": "operator", "merchant_id": "merchant-a"}
MERCHANT = {"role": "MERCHANT", "actor_id": "merchant", "merchant_id": "merchant-a"}
TARGET = binding_key("chat", "synthetic-tenant", "oc_synthetic")
KEY = "synthetic-inbound-key"
TOKEN = "synthetic-inbound-token"


def config():
    return {
        "actors": {binding_key("actor", "synthetic-tenant", "ou_synthetic"): MERCHANT},
        "chats": {TARGET: "merchant-a"},
    }


def target_config(automatic=True):
    return {
        "targets": [
            {
                "tenant_key": "synthetic-tenant",
                "chat_id": "oc_synthetic",
                "merchant_id": "merchant-a",
                "authorized": True,
                "authorization_reference": "local-test-space-authorization",
                "allow_callback_replies": automatic,
            }
        ]
    }


class Cases:
    def __init__(self):
        self.revoked = False
        self.case = {
            "id": "synthetic-case",
            "merchant_id": "merchant-a",
            "revision": 3,
            "merchant_decision": "NONE",
            "work_status": "MERCHANT_ACTION_REQUIRED",
            "amount_minor": 10000,
            "currency": "USD",
            "source_type": "SYNTHETIC_DEMO",
            "rule_snapshot": {"conflict_status": "VERIFIED", "allowed_actions": ["CONTEST"]},
        }

    def get_case(self, case_id, identity):
        if (
            self.revoked
            or case_id != self.case["id"]
            or identity.get("merchant_id") not in {None, "merchant-a"}
        ):
            raise FeishuV2Error("CASE_NOT_ACCESSIBLE", 403)
        return copy.deepcopy(self.case)


class Transport:
    def __init__(self, *, lose_first=False, block=False):
        self.calls = []
        self.accepted = {}
        self.lose_first = lose_first
        self.started, self.release = threading.Event(), threading.Event()
        if not block:
            self.release.set()

    def _call(self, operation, **kwargs):
        self.calls.append((operation, copy.deepcopy(kwargs)))
        self.started.set()
        assert self.release.wait(3)
        key = kwargs["idempotency_key"]
        self.accepted.setdefault(key, "om_synthetic_" + str(len(self.accepted)))
        if self.lose_first and len(self.calls) == 1:
            raise TimeoutError("private provider diagnostics")
        return SimpleNamespace(message_id=self.accepted[key])

    def send_interactive_card(self, **kwargs):
        return self._call("SEND", **kwargs)

    def reply_interactive_card(self, **kwargs):
        return self._call("REPLY", **kwargs)

    def update_interactive_card(self, **kwargs):
        return self._call("UPDATE", **kwargs)


def outbox(tmp_path, *, client=None, automatic=True, now=None):
    bindings = TrustedBindings.from_json(json.dumps(config()))
    adapter = FeishuV2Adapter(
        Cases(),
        bindings,
        FeishuV2Store(tmp_path / "delivery.db"),
        base_url="http://localhost:8000",
        now=lambda: int(NOW),
        plan=lambda c: {
            "revision": c["revision"],
            "summary": "请补充收货记录。",
            "deadlines": {"internal": "private-internal-deadline"},
        },
    )
    box = FeishuDisputeOutbox(
        adapter,
        targets=load_test_targets(json.dumps(target_config(automatic)), bindings),
        client=client,
        now=now or (lambda: NOW),
    )
    adapter.outbox = box
    return box


def preview(box, **changes):
    return box.preview(
        **{
            "command_id": "preview-command",
            "case_id": "synthetic-case",
            "identity": OP,
            "target_ref": TARGET,
            **changes,
        }
    )


def test_preview_is_durable_private_target_and_network_disabled(tmp_path):
    box = outbox(tmp_path)
    row = preview(box)
    assert row["state"] == "PREVIEW" and row["message_id"] is None
    assert row["delivery_status"] == "NOT_SENT"
    assert "private-internal-deadline" not in json.dumps(row)
    assert "identity" not in row and "reply_to" not in row
    reopened = outbox(tmp_path)
    assert preview(reopened)["id"] == row["id"]
    assert preview(reopened)["replayed"] is True
    assert reopened.list_for_case("synthetic-case", OP)["items"][0]["id"] == row["id"]
    with pytest.raises(FeishuV2Error, match="FEISHU_OUTBOUND_DISABLED"):
        reopened.send(row["id"], OP, confirmed=True)
    assert b"oc_synthetic" not in box.store.path.read_bytes()
    assert b"synthetic-tenant" not in box.store.path.read_bytes()


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "SUMMARY"},
        {"identity": {**OP, "actor_id": "other-op"}},
    ],
)
def test_preview_idempotency_binds_payload_and_actor(tmp_path, changes):
    box = outbox(tmp_path)
    preview(box)
    with pytest.raises(FeishuV2Error, match="IDEMPOTENCY_CONFLICT"):
        preview(box, **changes)


def test_manual_send_needs_confirmation_and_never_auto_sends_preview(tmp_path):
    transport = Transport()
    box = outbox(tmp_path, client=transport)
    row = preview(box)
    assert box.drain() == []
    with pytest.raises(FeishuV2Error, match="CONFIRMATION_REQUIRED"):
        box.send(row["id"], OP)
    assert not transport.calls
    sent = box.send(row["id"], OP, confirmed=True)
    assert sent["state"] == "SENT" and sent["message_id"]
    assert sent["delivery_status"] == "DELIVERED_TO_FEISHU"
    assert box.send(row["id"], OP, confirmed=True)["replayed"] is True
    assert len(transport.calls) == 1


def test_timeout_retry_after_restart_reuses_same_provider_uuid_and_exact_card(tmp_path):
    transport = Transport(lose_first=True)
    box = outbox(tmp_path, client=transport)
    row = preview(box)
    failed = box.send(row["id"], OP, confirmed=True)
    assert failed["state"] == "UNCERTAIN" and failed["message_id"] is None
    assert "private provider" not in json.dumps(failed)
    reopened = outbox(tmp_path, client=transport)
    sent = reopened.send(row["id"], OP, confirmed=True)
    assert sent["state"] == "SENT" and sent["attempts"] == 2
    assert transport.calls[0] == transport.calls[1]
    assert len(transport.accepted) == 1


def test_concurrent_send_claim_prevents_second_inflight_request(tmp_path):
    transport = Transport(block=True)
    box = outbox(tmp_path, client=transport)
    row = preview(box)
    with ThreadPoolExecutor(2) as pool:
        future = pool.submit(box.send, row["id"], OP, confirmed=True)
        assert transport.started.wait(2)
        try:
            with pytest.raises(FeishuV2Error, match="IN_PROGRESS"):
                box.send(row["id"], OP, confirmed=True)
        finally:
            transport.release.set()
        assert future.result()["state"] == "SENT"
    assert len(transport.calls) == 1


@pytest.mark.parametrize("mutation", ["revoke", "merchant", "target"])
def test_current_case_and_target_access_revalidated_even_on_sent_replay(tmp_path, mutation):
    transport = Transport()
    box = outbox(tmp_path, client=transport)
    row = preview(box)
    box.send(row["id"], OP, confirmed=True)
    identity = OP
    if mutation == "revoke":
        box.adapter.service.revoked = True
    elif mutation == "merchant":
        identity = {**OP, "merchant_id": "merchant-b"}
    else:
        box.targets = {}
    with pytest.raises(FeishuV2Error):
        box.send(row["id"], identity, confirmed=True)
    assert len(transport.calls) == 1


def test_stale_unpublished_preview_cannot_send_until_user_previews_again(tmp_path):
    transport = Transport()
    box = outbox(tmp_path, client=transport)
    row = preview(box)
    box.adapter.service.case["revision"] += 1
    with pytest.raises(FeishuV2Error, match="PREVIEW_STALE"):
        box.send(row["id"], OP, confirmed=True)
    assert not transport.calls


@pytest.mark.parametrize("automatic", [False, True])
def test_callback_reply_requires_extra_local_authorization_and_drains_once(tmp_path, automatic):
    transport = Transport()
    box = outbox(tmp_path, client=transport, automatic=automatic)
    kwargs = dict(
        event_ref="verified-event",
        case_id="synthetic-case",
        identity=MERCHANT,
        target_ref=TARGET,
        message_id="om_inbound",
    )
    first = box.callback(**kwargs)
    assert first["state"] == ("PENDING" if automatic else "PREVIEW")
    assert box.callback(**kwargs)["id"] == first["id"]
    box.drain()
    box.drain()
    assert len(transport.calls) == int(automatic)
    if automatic:
        assert transport.calls[0][0] == "REPLY"
        assert transport.calls[0][1]["message_id"] == "om_inbound"


def test_callback_update_requires_a_previously_delivered_same_case_card(tmp_path):
    transport = Transport()
    box = outbox(tmp_path, client=transport)
    kwargs = dict(
        event_ref="update-event",
        case_id="synthetic-case",
        identity=MERCHANT,
        target_ref=TARGET,
        update=True,
    )
    assert box.callback(message_id="om_unrelated", **kwargs)["state"] == "NOT_QUEUED"
    sent = box.send(preview(box)["id"], OP, confirmed=True)
    box.callback(message_id=sent["message_id"], **kwargs)
    box.drain()
    assert [call[0] for call in transport.calls] == ["SEND", "UPDATE"]


def test_revoked_callback_identity_is_blocked_without_network(tmp_path):
    transport = Transport()
    box = outbox(tmp_path, client=transport)
    row = box.callback(
        event_ref="revoke-event",
        case_id="synthetic-case",
        identity=MERCHANT,
        target_ref=TARGET,
        message_id="om_inbound",
    )
    box.adapter.service.revoked = True
    assert box.drain() == []
    assert not transport.calls
    assert box._read(row["id"])["state"] == "BLOCKED"


@pytest.mark.parametrize(
    "change",
    [
        {"authorized": False},
        {"authorization_reference": ""},
        {"merchant_id": "merchant-b"},
        {"allow_callback_replies": "true"},
    ],
)
def test_allowlist_is_strict_and_must_match_trusted_binding(change):
    data = target_config()
    data["targets"][0].update(change)
    with pytest.raises(ValueError):
        load_test_targets(json.dumps(data), TrustedBindings.from_json(json.dumps(config())))


def test_external_actor_cannot_be_configured_as_reserved_system_agent():
    data = config()
    data["actors"][binding_key("actor", "synthetic-tenant", "ou_synthetic")] = {
        "role": "AGENT",
        "actor_id": "oceanpilot-workflow-agent",
        "merchant_id": "merchant-a",
    }
    with pytest.raises(ValueError):
        TrustedBindings.from_json(json.dumps(data))


@pytest.fixture
def api(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "base.db", chargeback_db_path=tmp_path / "v2.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.dispute_agent_events.enabled = False
        app.state.dispute_agent.model = None
        app.state.dispute_collaboration_scheduler.close()
        directory = app.state.v21_auth
        headers, identities = {}, {}
        for name, role, merchant in [
            ("operator", "OPERATOR", "merchant-a"),
            ("risk", "RISK_OFFICER", "merchant-a"),
            ("merchant", "MERCHANT", "merchant-a"),
            ("outsider", "MERCHANT", "merchant-b"),
        ]:
            directory.create_user(
                username=name,
                password="Synthetic-pass-only!",
                display_name=name,
                role=role,
                merchant_id=merchant if role == "MERCHANT" else None,
                merchant_ids=[merchant],
                user_id=name,
            )
            token, _ = directory.login(name, "Synthetic-pass-only!")
            headers[name] = {
                "Cookie": "oceanpilot_session=" + token,
                "X-CSRF-Token": directory.csrf_token(token),
            }
            identities[name] = {
                "role": role,
                "actor_id": name,
                "merchant_id": merchant if role == "MERCHANT" else None,
            }
        case = app.state.disputes.execute(
            {
                "command_id": str(uuid4()),
                "action": "INTAKE",
                "confirmed": True,
                "data": {
                    "merchant_id": "merchant-a",
                    "transaction_id": str(uuid4()),
                    "scheme": "VISA",
                    "channel": "MOCK",
                    "reason_code": "13.1",
                    "amount_minor": 10000,
                    "currency": "USD",
                    "event_id": str(uuid4()),
                },
            },
            identities["operator"],
        )["case"]
        assert initialize_dispute_feishu(
            app,
            tmp_path / "v2.db",
            environ={
                "OCEANPILOT_V2_FEISHU_BINDINGS_JSON": json.dumps(config()),
                "FEISHU_ENCRYPT_KEY": KEY,
                "FEISHU_VERIFICATION_TOKEN": TOKEN,
                "OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON": json.dumps(target_config()),
            },
        )
        box = app.state.dispute_feishu_outbox
        transport = Transport()
        box.client = transport  # Explicit local test seam; no real network or auto thread.
        yield client, app, headers, identities, case, box, transport


def signed_post(client, case_id, *, event_id="shared-event", text=None, root_id=None):
    payload = {
        "schema": "2.0",
        "header": {
            "event_type": "im.message.receive_v1",
            "event_id": event_id,
            "tenant_key": "synthetic-tenant",
            "token": TOKEN,
        },
        "event": {
            "sender": {"sender_type": "user", "sender_id": {"open_id": "ou_synthetic"}},
            "message": {
                "chat_id": "oc_synthetic",
                "message_id": "om_inbound",
                "message_type": "text",
                "content": json.dumps({"text": text or f"@OceanPilot {case_id} 还缺什么？"}),
                "root_id": root_id,
            },
        },
    }
    raw = json.dumps(payload).encode()
    stamp = str(int(datetime.now(UTC).timestamp()))
    nonce = "synthetic-nonce"
    signature = hashlib.sha256((stamp + nonce + KEY).encode() + raw).hexdigest()
    return client.post(
        "/api/v2/integrations/feishu/events",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": stamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature,
        },
    )


def test_real_trusted_callback_joins_shared_thread_without_business_revision(api):
    client, app, headers, identities, case, box, transport = api
    response = signed_post(client, case["id"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["revision"] == case["revision"]
    assert result["outbound_delivery"] == "PENDING"
    path = f"/api/v2/cases/{case['id']}/collaboration"
    shared = client.get(path, headers=headers["operator"]).json()
    message = next(m for m in shared["messages"] if m.get("channel") == "FEISHU")
    assert message["actor_id"] == "merchant" and message["scope"] == "SHARED"
    assert any(m.get("model") == "case-plan" for m in shared["messages"])
    assert client.get(path, headers=headers["merchant"]).json()["messages"] == shared["messages"]
    assert signed_post(client, case["id"]).json() == result
    assert len(client.get(path, headers=headers["operator"]).json()["messages"]) == len(
        shared["messages"]
    )
    assert not transport.calls
    box.drain()
    assert len(transport.calls) == 1 and transport.calls[0][0] == "REPLY"
    assert (
        app.state.disputes.get_case(case["id"], identities["operator"])["revision"]
        == case["revision"]
    )


def test_outbox_http_uses_trusted_session_csrf_confirmation_and_actual_receipt(api):
    client, _, headers, _, case, _, transport = api
    path = "/api/v2/integrations/feishu/outbox"
    payload = {"command_id": str(uuid4()), "case_id": case["id"], "target_ref": TARGET}
    assert client.post(path, json=payload).status_code == 401
    assert (
        client.post(
            path, headers={"Cookie": headers["operator"]["Cookie"]}, json=payload
        ).status_code
        == 403
    )
    assert client.post(path, headers=headers["merchant"], json=payload).status_code == 403
    assert (
        client.get(path, params={"case_id": case["id"]}, headers=headers["outsider"]).status_code
        == 404
    )
    preview_response = client.post(path, headers=headers["operator"], json=payload)
    assert preview_response.status_code == 200, preview_response.text
    row = preview_response.json()
    assert not transport.calls
    sent = client.post(
        path + "/" + row["id"] + "/send", headers=headers["operator"], json={"confirmed": True}
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["message_id"] == "om_synthetic_0"
    assert len(transport.calls) == 1


def test_real_callback_rechecks_revoked_account_on_replay(api):
    client, app, _, _, case, _, transport = api
    assert signed_post(client, case["id"]).status_code == 200
    # Directory is authoritative even when an immutable Feishu response already exists.
    with closing(app.state.v21_auth._connect()) as db:
        db.execute("UPDATE v21_users SET disabled=1 WHERE user_id='merchant'")
        db.commit()
    response = signed_post(client, case["id"])
    assert response.status_code in {403, 404}, response.text
    assert not transport.calls


def test_model_or_internal_notes_do_not_leak_into_feishu_shared_summary(api):
    client, app, _, identities, case, _, _ = api
    app.state.dispute_collaboration.post_message(
        case["id"],
        identities["operator"],
        str(uuid4()),
        "private-internal-only-marker",
        "OP_INTERNAL",
    )
    response = signed_post(client, case["id"])
    assert response.status_code == 200, response.text
    assert "private-internal-only-marker" not in response.text
    merchant = app.state.dispute_collaboration.activity(case["id"], identities["merchant"])
    assert "private-internal-only-marker" not in json.dumps(merchant)


def test_same_chat_cannot_reply_to_another_cases_delivered_root(api):
    client, _, _, _, case, box, _ = api
    with box.store._connection() as db:
        db.execute(
            "INSERT INTO v21_feishu_outbox VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "fout-other",
                "other-command",
                "hash",
                "other-case",
                TARGET,
                "SENT",
                0,
                "om_other_root",
                NOW,
                "{}",
            ),
        )
    response = signed_post(client, case["id"], root_id="om_other_root")
    assert response.status_code == 403 and response.json()["code"] == "CASE_BINDING_MISMATCH"


def test_signed_decision_keeps_atomic_business_audit_and_updates_delivered_card(api):
    from datetime import timedelta

    client, app, _, identities, case, box, transport = api
    for action, role, data in [
        (
            "CONFIRM_RULE",
            "risk",
            {
                "source_id": "SYNTHETIC_DEMO",
                "source_locator": "synthetic:feishu-test",
                "rule_version": "synthetic-v21",
                "reason": "Explicit synthetic rule confirmation",
                "external_deadline": (app.state.disputes.clock() + timedelta(days=14)).isoformat(),
                "required_evidence": ["synthetic_order_record"],
                "allowed_actions": ["ACCEPT", "CONTEST"],
            },
        ),
        ("PUBLISH_TASK", "operator", {}),
    ]:
        case = app.state.disputes.execute(
            {
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "action": action,
                "expected_revision": case["revision"],
                "confirmed": True,
                "data": data,
            },
            identities[role],
        )["case"]
    row = box.preview(
        command_id=str(uuid4()),
        case_id=case["id"],
        identity=identities["operator"],
        target_ref=TARGET,
    )
    sent = box.send(row["id"], identities["operator"], confirmed=True)
    value = next(
        button["value"]
        for button in row["card"]["elements"][-1]["actions"]
        if button.get("value", {}).get("decision") == "CONTEST"
    )
    payload = {
        "schema": "2.0",
        "header": {
            "event_type": "card.action.trigger",
            "event_id": "trusted-decision",
            "tenant_key": "synthetic-tenant",
            "token": TOKEN,
        },
        "event": {
            "operator": {"open_id": "ou_synthetic"},
            "context": {"open_chat_id": "oc_synthetic", "open_message_id": sent["message_id"]},
            "action": {"tag": "button", "value": value},
        },
    }
    raw = json.dumps(payload).encode()
    timestamp = str(int(datetime.now(UTC).timestamp()))
    signed = {
        "Content-Type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": "nonce",
        "X-Lark-Signature": hashlib.sha256((timestamp + "nonce" + KEY).encode() + raw).hexdigest(),
    }
    response = client.post("/api/v2/integrations/feishu/card", content=raw, headers=signed)
    assert response.status_code == 200, response.text
    after = app.state.disputes.get_case(case["id"], identities["operator"])
    assert after["revision"] == case["revision"] + 1
    assert after["merchant_decision"] == "CONTEST"
    assert after["audit"][-1]["action"] == "MERCHANT_DECISION"
    assert after["audit"][-1]["actor_id"] == "merchant"
    shared = app.state.dispute_collaboration.activity(case["id"], identities["merchant"])
    assert any(
        message.get("source_event_type") == "MERCHANT_DECISION" for message in shared["messages"]
    )
    box.drain()
    assert [call[0] for call in transport.calls] == ["SEND", "UPDATE"]
    assert (
        client.post("/api/v2/integrations/feishu/card", content=raw, headers=signed).json()
        == response.json()
    )
    assert len(transport.calls) == 2


def test_shared_callback_receipt_crash_replays_same_answer_after_business_change(api, monkeypatch):
    import sqlite3

    client, app, _, identities, case, box, _ = api
    original = box.adapter.store.complete
    monkeypatch.setattr(
        box.adapter.store,
        "complete",
        lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("simulated local interruption")),
    )
    assert signed_post(client, case["id"]).status_code == 503
    before = app.state.dispute_collaboration.activity(case["id"], identities["merchant"])
    app.state.disputes.execute(
        {
            "command_id": str(uuid4()),
            "case_id": case["id"],
            "action": "COMMENT",
            "expected_revision": case["revision"],
            "confirmed": False,
            "data": {"message": "Business aggregate revision changed during receipt interruption"},
        },
        identities["operator"],
    )
    monkeypatch.setattr(box.adapter.store, "complete", original)
    response = signed_post(client, case["id"])
    assert response.status_code == 200, response.text
    after = app.state.dispute_collaboration.activity(case["id"], identities["merchant"])
    original_feishu = [
        m
        for m in before["messages"]
        if m.get("channel") == "FEISHU" or m.get("model") == "case-plan"
    ]
    replay_feishu = [
        m
        for m in after["messages"]
        if m.get("channel") == "FEISHU" or m.get("model") == "case-plan"
    ]
    assert original_feishu == replay_feishu


@pytest.mark.parametrize(
    "enabled_flag,credentials,targets,expected",
    [
        (False, True, True, False),
        (True, False, True, False),
        (True, True, False, False),
        (True, True, True, True),
    ],
)
def test_initializer_requires_all_local_authorization_conditions(
    tmp_path, monkeypatch, enabled_flag, credentials, targets, expected
):
    from oceanpilot.adapters.feishu import client as client_module

    constructed = []
    monkeypatch.setattr(
        client_module,
        "FeishuOutboundClient",
        lambda **kwargs: constructed.append(True) or Transport(),
    )
    monkeypatch.setattr(FeishuDisputeOutbox, "start", lambda self: None)
    env = {
        "OCEANPILOT_V2_FEISHU_BINDINGS_JSON": json.dumps(config()),
        "FEISHU_ENCRYPT_KEY": KEY,
        "FEISHU_VERIFICATION_TOKEN": TOKEN,
    }
    if enabled_flag:
        env["OCEANPILOT_V21_FEISHU_OUTBOUND"] = "authorized-test"
    if credentials:
        env.update(FEISHU_APP_ID="synthetic-app", FEISHU_APP_SECRET="synthetic-secret")
    if targets:
        env["OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON"] = json.dumps(target_config())
    app = SimpleNamespace(state=SimpleNamespace(disputes=Cases()))
    assert initialize_dispute_feishu(app, tmp_path / "init.db", environ=env)
    assert bool(constructed) is expected
    assert app.state.dispute_feishu_outbox.enabled is expected


def test_old_uncertain_update_cannot_overwrite_new_case_revision(tmp_path):
    transport = Transport()
    box = outbox(tmp_path, client=transport)
    sent = box.send(preview(box)["id"], OP, confirmed=True)
    row = box.callback(
        event_ref="old-patch",
        case_id="synthetic-case",
        identity=MERCHANT,
        target_ref=TARGET,
        message_id=sent["message_id"],
        update=True,
    )
    transport.lose_first = True
    transport.calls.clear()
    assert box.send(row["id"], OP, confirmed=True)["state"] == "UNCERTAIN"
    box.adapter.service.case["revision"] += 1
    with pytest.raises(FeishuV2Error, match="PREVIEW_STALE"):
        box.send(row["id"], OP, confirmed=True)
    assert len(transport.calls) == 1
