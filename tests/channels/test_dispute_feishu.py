import copy
import hashlib
import json
import re
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oceanpilot.adapters.channels.feishu.v2 import (
    FeishuV2Adapter,
    FeishuV2Error,
    FeishuV2Store,
    TrustedBindings,
    binding_key,
)
from oceanpilot.adapters.feishu.security import FeishuRequestVerifier
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.api.dispute_feishu import initialize_dispute_feishu, router
from oceanpilot.application.disputes import DisputeService
from oceanpilot.domain.dispute_rules import case_plan
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.security import assert_no_sensitive_data

NOW = 1809860400
ENCRYPT_KEY = "synthetic-feishu-v2-encrypt-key"
TOKEN = "synthetic-feishu-v2-token"
IDENTITY = {"role": "MERCHANT", "actor_id": "merchant-user", "merchant_id": "merchant-1"}
CARD_PATH = "/api/v2/integrations/feishu/card"
EVENTS_PATH = "/api/v2/integrations/feishu/events"


class CaseServiceDouble:
    """Isolates callback security from the separately tested Case Engine."""

    def __init__(self):
        self.cases = {
            "case-1": {
                "case_id": "case-1",
                "merchant_id": "merchant-1",
                "revision": 3,
                "merchant_decision": "NONE",
                "work_status": "MERCHANT_ACTION_REQUIRED",
                "source_type": "SYNTHETIC_DEMO",
                "amount": "100.00",
                "currency": "USD",
                "rule_snapshot": {
                    "conflict_status": "VERIFIED",
                    "allowed_actions": ["ACCEPT", "CONTEST"],
                },
            },
            "case-2": {"case_id": "case-2", "merchant_id": "merchant-2", "revision": 2},
        }
        self.commands, self.results = [], {}

    def get_case(self, case_id, identity):
        case = self.cases.get(case_id)
        if case is None or case["merchant_id"] != identity["merchant_id"]:
            raise FeishuV2Error("CASE_NOT_ACCESSIBLE", 403)
        return copy.deepcopy(case)

    def execute(self, command, identity):
        key = command["command_id"]
        if key in self.results:
            return copy.deepcopy(self.results[key])
        case = self.cases[command["case_id"]]
        if command["expected_revision"] != case["revision"]:
            raise FeishuV2Error("STALE_REVISION", 409)
        self.commands.append((copy.deepcopy(command), dict(identity)))
        if command["action"] == "MERCHANT_DECISION":
            case["merchant_decision"] = command["data"]["decision"]
        case["revision"] += 1
        self.results[key] = {"case": copy.deepcopy(case), "receipt": {}, "replayed": False}
        return copy.deepcopy(self.results[key])


def config():
    return {
        "actors": {binding_key("actor", "tenant-1", "ou-merchant"): IDENTITY},
        "chats": {
            binding_key("chat", "tenant-1", "oc-merchant"): "merchant-1",
            binding_key("chat", "tenant-1", "oc-other"): "merchant-2",
        },
    }


def make_adapter(tmp_path, service=None):
    return FeishuV2Adapter(
        service or CaseServiceDouble(),
        TrustedBindings.from_json(json.dumps(config())),
        FeishuV2Store(tmp_path / "feishu-v2.db"),
        base_url="http://localhost:8000",
        now=lambda: NOW,
        plan=lambda c: {"revision": c["revision"], "next_action": "OP_REVIEW"},
    )


@pytest.fixture
def stack(tmp_path):
    app = FastAPI()
    adapter = make_adapter(tmp_path)
    app.state.dispute_feishu = adapter
    app.state.dispute_feishu_verifier = FeishuRequestVerifier(
        encrypt_key=ENCRYPT_KEY,
        verification_token=TOKEN,
        now=lambda: NOW,
    )
    app.include_router(router)
    with TestClient(app) as client:
        yield client, adapter


def sign(payload, *, timestamp=NOW):
    raw = json.dumps(payload).encode()
    nonce = "synthetic-nonce"
    return raw, {
        "Content-Type": "application/json",
        "X-Lark-Request-Timestamp": str(timestamp),
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": hashlib.sha256(
            f"{timestamp}{nonce}{ENCRYPT_KEY}".encode() + raw
        ).hexdigest(),
    }


def post(client, path, payload, **kwargs):
    raw, headers = sign(payload, **kwargs)
    return client.post(path, content=raw, headers=headers)


def action_value(adapter, **kwargs):
    card = adapter.render_case_card(
        "case-1",
        IDENTITY,
        tenant_key="tenant-1",
        chat_id="oc-merchant",
        **kwargs,
    )
    return card["elements"][-1]["actions"][0].get("value", {})


def card_payload(value, event_id="card-event-1"):
    return {
        "schema": "2.0",
        "header": {
            "event_type": "card.action.trigger",
            "event_id": event_id,
            "tenant_key": "tenant-1",
            "token": TOKEN,
        },
        "event": {
            "operator": {"open_id": "ou-merchant"},
            "context": {"open_chat_id": "oc-merchant"},
            "action": {"tag": "button", "value": value},
        },
    }


def message_payload(text="@OceanPilot case-1 还缺什么？", event_id="message-event-1"):
    return {
        "schema": "2.0",
        "header": {
            "event_type": "im.message.receive_v1",
            "event_id": event_id,
            "tenant_key": "tenant-1",
            "token": TOKEN,
        },
        "event": {
            "sender": {"sender_type": "user", "sender_id": {"open_id": "ou-merchant"}},
            "message": {
                "chat_id": "oc-merchant",
                "message_type": "text",
                "content": json.dumps({"text": text}),
            },
        },
    }


def test_verified_decision_uses_server_binding_and_one_auditable_command(stack):
    client, adapter = stack
    value = action_value(adapter)
    value["role"] = "ADMIN"  # An untrusted card field can never promote the actor.
    value["merchant_id"] = "merchant-2"
    response = post(client, CARD_PATH, card_payload(value))
    assert response.status_code == 200
    assert response.json()["outbound_delivery"] == "DISABLED"
    assert response.json()["case_plan"]["revision"] == 4
    command, identity = adapter.service.commands[0]
    assert identity == IDENTITY
    assert command["case_id"] == "case-1"
    assert command["expected_revision"] == 3 and command["confirmed"] is True
    assert command["action"] == "MERCHANT_DECISION"
    assert command["data"]["channel"] == "FEISHU"
    assert command["data"]["thread_id"] == binding_key("chat", "tenant-1", "oc-merchant")
    assert len(adapter.service.commands) == 1


def test_callback_replay_is_durable_and_does_not_repeat_mutation(stack, tmp_path):
    client, adapter = stack
    payload = card_payload(action_value(adapter))
    first = post(client, CARD_PATH, payload)
    client.app.state.dispute_feishu = make_adapter(tmp_path, adapter.service)
    second = post(client, CARD_PATH, payload)
    assert first.json() == second.json()
    assert len(adapter.service.commands) == 1
    assert adapter.service.cases["case-1"]["revision"] == 4


def test_retry_after_case_commit_uses_original_command(stack, monkeypatch):
    client, adapter = stack
    payload = card_payload(action_value(adapter))
    original = adapter.store.complete

    def failed_complete(*args):
        import sqlite3

        raise sqlite3.OperationalError("synthetic interruption")

    monkeypatch.setattr(adapter.store, "complete", failed_complete)
    assert post(client, CARD_PATH, payload).status_code == 503
    monkeypatch.setattr(adapter.store, "complete", original)
    assert post(client, CARD_PATH, payload).status_code == 200
    assert len(adapter.service.commands) == 1


def test_reusing_event_id_with_changed_payload_is_conflict(stack):
    client, adapter = stack
    payload = card_payload(action_value(adapter))
    assert post(client, CARD_PATH, payload).status_code == 200
    payload["event"]["action"]["value"]["decision"] = "CONTEST"
    assert post(client, CARD_PATH, payload).status_code == 409
    assert len(adapter.service.commands) == 1


@pytest.mark.parametrize("mutation", ["actor", "chat", "tenant", "case", "unknown_card"])
def test_forged_binding_cannot_change_a_case(stack, mutation):
    client, adapter = stack
    payload = card_payload(action_value(adapter))
    if mutation == "actor":
        payload["event"]["operator"]["open_id"] = "ou-stranger"
    elif mutation == "chat":
        payload["event"]["context"]["open_chat_id"] = "oc-other"
    elif mutation == "tenant":
        payload["header"]["tenant_key"] = "tenant-other"
    elif mutation == "case":
        payload["event"]["action"]["value"]["case_id"] = "case-2"
    else:
        payload["event"]["action"]["value"]["card_ref"] = "forged"
    assert post(client, CARD_PATH, payload).status_code == 403
    assert adapter.service.commands == []


@pytest.mark.parametrize("confirmed", [False, None, "true", 1])
def test_merchant_decision_requires_explicit_confirmation(stack, confirmed):
    client, adapter = stack
    value = action_value(adapter)
    value["confirmed"] = confirmed
    assert post(client, CARD_PATH, card_payload(value)).status_code == 409
    assert adapter.service.commands == []


def test_card_revision_cannot_be_refreshed_by_untrusted_input(stack):
    client, adapter = stack
    value = action_value(adapter)
    adapter.service.cases["case-1"]["revision"] = 4
    value["expected_revision"] = 4
    assert post(client, CARD_PATH, card_payload(value)).status_code == 409
    assert adapter.service.commands == []


def test_expired_card_is_rejected(stack):
    client, adapter = stack
    value = action_value(adapter)
    adapter.now = lambda: NOW + 3601
    assert post(client, CARD_PATH, card_payload(value)).status_code == 409


def test_summary_is_case_scoped_normalized_and_does_not_create_case(stack):
    client, adapter = stack
    response = post(client, EVENTS_PATH, message_payload())
    assert response.status_code == 200
    command, identity = adapter.service.commands[0]
    assert command["action"] == "COMMENT" and command["data"]["channel"] == "FEISHU"
    assert identity == IDENTITY and len(adapter.service.cases) == 2
    assert response.json()["case_plan"]["next_action"] == "OP_REVIEW"
    assert post(client, EVENTS_PATH, message_payload()).json() == response.json()
    assert len(adapter.service.commands) == 1


def test_summary_rejects_another_merchants_case(stack):
    client, adapter = stack
    assert post(client, EVENTS_PATH, message_payload("@OceanPilot case-2 总结")).status_code == 403
    assert adapter.service.commands == []


def test_unrelated_and_bot_messages_cause_no_commands(stack):
    client, adapter = stack
    assert post(client, EVENTS_PATH, message_payload("hello")).json()["outcome"] == "IGNORED"
    payload = message_payload()
    payload["event"]["sender"]["sender_type"] = "app"
    assert post(client, EVENTS_PATH, payload).json()["outcome"] == "IGNORED_BOT"
    assert adapter.service.commands == []


@pytest.mark.parametrize("kind", ["signature", "token", "past", "future"])
def test_request_authentication_precedes_all_mutations(stack, kind):
    client, adapter = stack
    payload = card_payload(action_value(adapter))
    if kind == "token":
        payload["header"]["token"] = "invalid"
    timestamp = NOW + (301 if kind == "future" else -301 if kind == "past" else 0)
    raw, headers = sign(payload, timestamp=timestamp)
    if kind == "signature":
        headers["X-Lark-Signature"] = "0" * 64
    assert client.post(CARD_PATH, content=raw, headers=headers).status_code == 401
    assert adapter.service.commands == []


def test_duplicate_signature_headers_are_rejected(stack):
    client, adapter = stack
    raw, headers = sign(card_payload(action_value(adapter)))
    duplicated = [*headers.items(), ("X-Lark-Signature", headers["X-Lark-Signature"])]
    assert client.post(CARD_PATH, content=raw, headers=duplicated).status_code == 401
    assert adapter.service.commands == []


def test_trusted_op_identity_cannot_make_a_merchants_card_decision(stack):
    client, adapter = stack
    payload = card_payload(action_value(adapter))
    adapter.bindings.actors[binding_key("actor", "tenant-1", "ou-merchant")]["role"] = "OPERATOR"
    response = post(client, CARD_PATH, payload)
    assert response.status_code == 403
    assert adapter.service.commands == []


def test_challenge_requires_signed_token_and_integration_configuration(stack):
    client, adapter = stack
    payload = {"type": "url_verification", "token": TOKEN, "challenge": "synthetic-challenge"}
    assert post(client, EVENTS_PATH, payload).json() == {"challenge": "synthetic-challenge"}
    client.app.state.dispute_feishu = None
    assert post(client, EVENTS_PATH, payload).status_code == 503
    assert adapter.service.commands == []


def test_bad_media_type_and_large_body_are_rejected(stack):
    client, _ = stack
    raw, headers = sign(message_payload())
    headers["Content-Type"] = "text/plain"
    assert client.post(EVENTS_PATH, content=raw, headers=headers).status_code == 415
    raw, headers = sign({"padding": "x" * (65 * 1024)})
    assert client.post(EVENTS_PATH, content=raw, headers=headers).status_code == 413


def test_unconfigured_initialization_stays_disabled_without_creating_database(tmp_path):
    app = FastAPI()
    path = tmp_path / "never-created.db"
    assert initialize_dispute_feishu(app, path, environ={}) is False
    assert not path.exists() and app.state.dispute_feishu is None


@pytest.mark.parametrize("raw", ["{}", "invalid-json", '{"actors":{},"chats":{}}'])
def test_invalid_binding_configuration_fails_closed(raw):
    with pytest.raises(ValueError, match="trusted binding"):
        TrustedBindings.from_json(raw)


@pytest.mark.parametrize(
    "kind", ["NEW_DISPUTE", "MISSING_EVIDENCE", "SLA_REMINDER", "REVIEW_FEEDBACK"]
)
def test_card_kinds_render_locally_with_case_deep_link_and_explicit_boundaries(stack, kind):
    _, adapter = stack
    card = adapter.render_case_card(
        "case-1",
        IDENTITY,
        tenant_key="tenant-1",
        chat_id="oc-merchant",
        kind=kind,
    )
    serialized = json.dumps(card, ensure_ascii=False)
    assert "SYNTHETIC_DEMO" in serialized and "Mock" in serialized and "Disabled" in serialized
    actions = card["elements"][-1]["actions"]
    assert actions[-1]["url"].endswith("/v2/merchant?case_id=case-1")
    assert all("case_id" not in action.get("value", {}) for action in actions)
    if kind == "NEW_DISPUTE":
        assert len(actions) == 3 and "confirm" in actions[0]
    else:
        assert len(actions) == 1
    assert adapter.service.commands == []


def test_persisted_receipts_do_not_contain_callback_credentials_or_external_ids(stack):
    client, adapter = stack
    assert post(client, EVENTS_PATH, message_payload()).status_code == 200
    raw = adapter.store.path.read_bytes()
    for secret in (TOKEN, ENCRYPT_KEY, "ou-merchant", "oc-merchant", "tenant-1"):
        assert secret.encode() not in raw


@pytest.mark.parametrize("allowed", [["ACCEPT"], ["CONTEST"], None])
def test_new_dispute_card_only_offers_confirmed_rule_actions(stack, allowed):
    _, adapter = stack
    adapter.service.cases["case-1"]["rule_snapshot"] = {
        "conflict_status": "VERIFIED" if allowed else "NEEDS_CONFIRMATION",
        "allowed_actions": allowed,
    }
    card = adapter.render_case_card(
        "case-1",
        IDENTITY,
        tenant_key="tenant-1",
        chat_id="oc-merchant",
    )
    actions = card["elements"][-1]["actions"]
    assert [a["value"]["decision"] for a in actions if "value" in a] == (allowed or [])
    assert actions[-1]["text"]["content"] == "查看案件"
    assert actions[-1]["url"].endswith("/v2/merchant?case_id=case-1")
    assert adapter.service.commands == []


def test_sensitive_message_is_rejected_before_receipt_persistence(stack):
    client, adapter = stack
    secret = "4111111111111111"
    response = post(client, EVENTS_PATH, message_payload(f"@OceanPilot case-1 card {secret}"))
    assert response.status_code == 422
    assert secret.encode() not in adapter.store.path.read_bytes()
    assert adapter.service.commands == []


def real_service(tmp_path):
    service = DisputeService(
        SQLiteDisputeStore(tmp_path / "real-cases.db"),
        clock=lambda: datetime.fromtimestamp(NOW, UTC),
    )
    operator = {"role": "OPERATOR", "actor_id": "op-demo", "merchant_id": "merchant-1"}
    risk = {**operator, "role": "RISK_OFFICER", "actor_id": "risk-demo"}
    case = service.execute(
        {
            "command_id": "seed-intake",
            "action": "INTAKE",
            "case_id": "case-1",
            "confirmed": True,
            "data": {
                "event_id": "synthetic-upstream-event",
                "merchant_id": "merchant-1",
                "transaction_id": "synthetic-transaction",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 10000,
                "currency": "USD",
            },
        },
        operator,
    )["case"]
    case = service.execute(
        {
            "command_id": "seed-rule",
            "action": "CONFIRM_RULE",
            "case_id": "case-1",
            "expected_revision": case["revision"],
            "confirmed": True,
            "data": {
                "source_id": "SYNTHETIC_DEMO",
                "source_locator": "synthetic:test/feishu",
                "rule_version": "synthetic-v1",
                "reason": "Synthetic callback integration test",
                "external_deadline": "2026-10-01T00:00:00+00:00",
                "required_evidence": ["synthetic_order_record"],
                "allowed_actions": ["ACCEPT", "CONTEST"],
            },
        },
        risk,
    )["case"]
    service.execute(
        {
            "command_id": "seed-task",
            "action": "PUBLISH_TASK",
            "case_id": "case-1",
            "expected_revision": case["revision"],
            "confirmed": True,
            "data": {},
        },
        operator,
    )
    return service


def test_signed_callback_executes_real_case_engine_with_atomic_collaboration_audit(stack, tmp_path):
    client, adapter = stack
    adapter.service = real_service(tmp_path)
    adapter.plan = case_plan
    value = action_value(adapter)
    value["decision"] = "CONTEST"
    before = adapter.service.get_case("case-1", IDENTITY)
    payload = card_payload(value)
    response = post(client, CARD_PATH, payload)
    assert response.status_code == 200, response.text
    case = adapter.service.get_case("case-1", IDENTITY)
    assert case["revision"] == before["revision"] + 1
    assert case["merchant_decision"] == "CONTEST"
    assert case["work_status"] == "EVIDENCE_COLLECTING"
    assert len(case["audit"]) == len(before["audit"]) + 1
    assert case["audit"][-1]["action"] == "MERCHANT_DECISION"
    assert case["audit"][-1]["role"] == "MERCHANT"
    assert case["audit"][-1]["actor_id"] == IDENTITY["actor_id"]
    assert case["audit"][-1]["confirmed"] is True
    event = case["collaboration"][-1]
    assert event["case_id"] == "case-1" and event["channel"] == "FEISHU"
    assert event["role"] == "MERCHANT" and event["actor_id"] == IDENTITY["actor_id"]
    assert event["external_event_id"] == binding_key("event", "tenant-1", "card-event-1")
    assert response.json()["case_plan"]["missing_critical"] == ["synthetic_order_record"]
    assert post(client, CARD_PATH, payload).json() == response.json()
    assert adapter.service.get_case("case-1", IDENTITY) == case


def test_real_engine_rejects_stale_card_after_audited_summary(stack, tmp_path):
    client, adapter = stack
    adapter.service = real_service(tmp_path)
    adapter.plan = case_plan
    value = action_value(adapter)
    summary = post(client, EVENTS_PATH, message_payload())
    assert summary.status_code == 200, summary.text
    case = adapter.service.get_case("case-1", IDENTITY)
    assert case["audit"][-1]["action"] == "COMMENT"
    assert case["collaboration"][-1]["channel"] == "FEISHU"
    rejected = post(client, CARD_PATH, card_payload(value))
    assert rejected.status_code == 409, rejected.text
    assert rejected.headers["content-type"] == "application/problem+json"
    assert adapter.service.get_case("case-1", IDENTITY) == case


def test_real_engine_recovers_receipt_after_interrupted_callback(stack, tmp_path, monkeypatch):
    import sqlite3

    client, adapter = stack
    adapter.service = real_service(tmp_path)
    adapter.plan = case_plan
    payload = card_payload(action_value(adapter))
    complete = adapter.store.complete

    def interrupt(*args):
        raise sqlite3.OperationalError("synthetic post-commit failure")

    monkeypatch.setattr(adapter.store, "complete", interrupt)
    assert post(client, CARD_PATH, payload).status_code == 503
    case = adapter.service.get_case("case-1", IDENTITY)
    monkeypatch.setattr(adapter.store, "complete", complete)
    response = post(client, CARD_PATH, payload)
    assert response.status_code == 200, response.text
    assert adapter.service.get_case("case-1", IDENTITY) == case


def test_configured_initializer_runs_with_real_service_without_outbound_client(tmp_path):
    app = FastAPI()
    app.state.disputes = real_service(tmp_path)
    assert (
        initialize_dispute_feishu(
            app,
            tmp_path / "configured-callbacks.db",
            environ={
                "OCEANPILOT_V2_FEISHU_BINDINGS_JSON": json.dumps(config()),
                "FEISHU_ENCRYPT_KEY": ENCRYPT_KEY,
                "FEISHU_VERIFICATION_TOKEN": TOKEN,
            },
        )
        is True
    )
    assert isinstance(app.state.dispute_feishu, FeishuV2Adapter)
    assert not hasattr(app.state, "feishu_client")


@pytest.mark.parametrize("mode", ["card", "event"])
def test_new_callback_derived_ids_do_not_trigger_sensitive_data_guard(stack, tmp_path, mode):
    client, adapter = stack
    adapter.service = real_service(tmp_path)
    adapter.plan = case_plan
    tenant, event_id = "synthetic-review-tenant", "synthetic-review-event-46"
    event_ref = binding_key("event", tenant, event_id)
    with pytest.raises(SensitiveDataRejected):
        assert_no_sensitive_data("feishu:" + event_ref)
    adapter.bindings = TrustedBindings(
        {binding_key("actor", tenant, "ou-merchant"): IDENTITY},
        {binding_key("chat", tenant, "oc-merchant"): "merchant-1"},
    )
    if mode == "card":
        card = adapter.render_case_card(
            "case-1", IDENTITY, tenant_key=tenant, chat_id="oc-merchant"
        )
        payload = card_payload(card["elements"][-1]["actions"][0]["value"], event_id)
        path = CARD_PATH
    else:
        payload = message_payload(event_id=event_id)
        path = EVENTS_PATH
    payload["header"]["tenant_key"] = tenant
    before = adapter.service.get_case("case-1", IDENTITY)
    response = post(client, path, payload)
    assert response.status_code == 200, response.text
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    remembered = adapter.store.receipt(event_ref, digest)
    command = remembered["command"]
    assert command["command_id"] != "feishu:" + event_ref
    assert command["command_id"].startswith("feishu:")
    assert all(len(m.group()) < 13 for m in re.finditer(r"[\d\s-]+", command["command_id"]))
    assert_no_sensitive_data(command["command_id"])
    assert command["data"]["external_event_id"] == event_ref
    assert command["data"]["thread_id"] == binding_key("chat", tenant, "oc-merchant")
    if mode == "card":
        assert command["data"]["authorization_reference"] == command["command_id"]
        assert_no_sensitive_data(command["data"]["authorization_reference"])
    case = adapter.service.get_case("case-1", IDENTITY)
    assert case["revision"] == before["revision"] + 1
    assert post(client, path, payload).json() == response.json()
    assert adapter.service.get_case("case-1", IDENTITY) == case


@pytest.mark.parametrize("mode", ["card", "event"])
@pytest.mark.parametrize("prior_state", ["remembered", "committed", "completed"])
def test_valid_legacy_commands_keep_original_identifiers_and_authorization_on_replay(
    stack, tmp_path, monkeypatch, mode, prior_state
):
    client, adapter = stack
    adapter.service = real_service(tmp_path)
    adapter.plan = case_plan
    payload = card_payload(action_value(adapter)) if mode == "card" else message_payload()
    event_ref = binding_key("event", "tenant-1", payload["header"]["event_id"])
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    command = adapter._command(
        payload["event"], mode, IDENTITY, binding_key("chat", "tenant-1", "oc-merchant"), event_ref
    )
    # Pre-upgrade remembered commands are used verbatim, including proof of
    # authorization. Their successful execution must remain replayable after a crash.
    command["command_id"] = "feishu:" + event_ref
    assert_no_sensitive_data(command["command_id"])
    if mode == "card":
        command["data"]["authorization_reference"] = "feishu:" + event_ref
    adapter.store.remember(event_ref, digest, command)
    before = adapter.service.get_case("case-1", IDENTITY)
    if prior_state == "committed":
        adapter.service.execute(command, IDENTITY)
    elif prior_state == "completed":
        adapter.handle(payload, mode=mode)

    restarted = make_adapter(tmp_path, adapter.service)
    restarted.plan = case_plan
    client.app.state.dispute_feishu = restarted

    def must_not_regenerate(*_args):
        raise AssertionError("A remembered callback command must remain immutable")

    monkeypatch.setattr(restarted, "_command", must_not_regenerate)
    path = CARD_PATH if mode == "card" else EVENTS_PATH
    response = post(client, path, payload)
    assert response.status_code == 200, response.text
    assert restarted.store.receipt(event_ref, digest)["command"] == command
    case = restarted.service.get_case("case-1", IDENTITY)
    assert case["revision"] == before["revision"] + 1
    assert case["audit"][-1]["command_id"] == command["command_id"]
    if mode == "card":
        assert case["merchant_authorization"]["reference"] == "feishu:" + event_ref
    assert post(client, path, payload).json() == response.json()
    assert restarted.service.get_case("case-1", IDENTITY) == case

    changed = copy.deepcopy(payload)
    if mode == "card":
        decision = changed["event"]["action"]["value"]["decision"]
        changed["event"]["action"]["value"]["decision"] = (
            "CONTEST" if decision == "ACCEPT" else "ACCEPT"
        )
    else:
        changed["event"]["message"]["content"] = json.dumps({"text": "@OceanPilot case-1 changed"})
    assert post(client, path, changed).status_code == 409
    assert restarted.service.get_case("case-1", IDENTITY) == case
