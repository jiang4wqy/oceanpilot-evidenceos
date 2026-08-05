from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from oceanpilot.adapters.feishu.store import (
    FeishuCallbackStoreFactory,
    ReceiptConflict,
    ReceiptOutcome,
)

CREATED_AT = "2026-08-05T04:00:00Z"
COMPLETED_AT = "2026-08-05T04:00:01Z"
CASE_ID = "00000000-0000-4000-8000-000000000010"
OTHER_CASE_ID = "00000000-0000-4000-8000-000000000011"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
ACTOR_ID = "ou_synthetic_operator"


def test_event_claim_complete_and_replay_survive_reopen(tmp_path):
    db_path = tmp_path / "callbacks.db"
    factory = FeishuCallbackStoreFactory(db_path)
    response = {"card": {"type": "diagnosis"}, "ok": True}

    with factory.session() as store:
        claimed = store.claim_event("event-001", created_at=CREATED_AT)
        assert claimed.outcome is ReceiptOutcome.CLAIMED
        assert claimed.response is None

        completed = store.complete_event(
            "event-001",
            response=response,
            case_id=CASE_ID,
            completed_at=COMPLETED_AT,
        )
        assert completed.outcome is ReceiptOutcome.COMPLETED
        assert completed.response == response

    reopened = FeishuCallbackStoreFactory(db_path)
    with reopened.session() as store:
        replay = store.claim_event("event-001", created_at=CREATED_AT)
        assert replay.outcome is ReceiptOutcome.REPLAY
        assert replay.response == response


@pytest.mark.parametrize("receipt_kind", ("event", "action"))
def test_concurrent_claim_has_one_winner(tmp_path, receipt_kind):
    factory = FeishuCallbackStoreFactory(tmp_path / f"{receipt_kind}.db")
    barrier = Barrier(2)

    def claim():
        with factory.session() as store:
            barrier.wait()
            if receipt_kind == "event":
                return store.claim_event("shared-id", created_at=CREATED_AT).outcome
            return store.claim_action("shared-id", created_at=CREATED_AT).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = {future.result() for future in (executor.submit(claim), executor.submit(claim))}

    assert outcomes == {ReceiptOutcome.CLAIMED, ReceiptOutcome.IN_PROGRESS}


def test_event_completion_does_not_overwrite_conflicting_response(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-conflict.db")
    original = {"ok": True, "result": "created"}

    with factory.session() as store:
        store.claim_event("event-conflict", created_at=CREATED_AT)
        store.complete_event(
            "event-conflict",
            response=original,
            case_id=CASE_ID,
            completed_at=COMPLETED_AT,
        )
        replay = store.complete_event(
            "event-conflict",
            response=original,
            case_id=CASE_ID,
            completed_at=COMPLETED_AT,
        )
        assert replay.outcome is ReceiptOutcome.REPLAY
        assert replay.response == original

        with pytest.raises(ReceiptConflict):
            store.complete_event(
                "event-conflict",
                response={"ok": False},
                case_id=OTHER_CASE_ID,
                completed_at=COMPLETED_AT,
            )

        persisted = store.claim_event("event-conflict", created_at=CREATED_AT)
        assert persisted.outcome is ReceiptOutcome.REPLAY
        assert persisted.response == original


def test_action_claim_complete_and_replay_are_idempotent(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "action.db")
    response = {"ok": True, "result": "confirmed"}

    with factory.session() as store:
        claimed = store.claim_action("action-001", created_at=CREATED_AT)
        assert claimed.outcome is ReceiptOutcome.CLAIMED

        completed = store.complete_action(
            "action-001",
            response=response,
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            completed_at=COMPLETED_AT,
        )
        assert completed.outcome is ReceiptOutcome.COMPLETED
        assert completed.response == response

        replay = store.claim_action("action-001", created_at=CREATED_AT)
        assert replay.outcome is ReceiptOutcome.REPLAY
        assert replay.response == response

        with pytest.raises(ReceiptConflict):
            store.complete_action(
                "action-001",
                response=response,
                case_id=OTHER_CASE_ID,
                diagnosis_id=DIAGNOSIS_ID,
                actor_id=ACTOR_ID,
                completed_at=COMPLETED_AT,
            )


def test_chat_case_binding_is_idempotent_and_never_overwritten(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "chat.db")

    with factory.session() as store:
        assert store.get_chat_case("chat-001") is None
        store.bind_chat_case("chat-001", CASE_ID, updated_at=CREATED_AT)
        store.bind_chat_case("chat-001", CASE_ID, updated_at=COMPLETED_AT)
        assert store.get_chat_case("chat-001") == CASE_ID

        with pytest.raises(ReceiptConflict):
            store.bind_chat_case("chat-001", OTHER_CASE_ID, updated_at=COMPLETED_AT)
        assert store.get_chat_case("chat-001") == CASE_ID


def test_confirmation_and_approval_audit_commit_atomically_and_replay(tmp_path):
    db_path = tmp_path / "approval.db"
    factory = FeishuCallbackStoreFactory(db_path)
    response = {"ok": True, "result": "approved"}

    with factory.session() as store:
        store.claim_action("action-confirm", created_at=CREATED_AT)
        completed = store.commit_confirmation(
            action_id="action-confirm",
            approval_id="approval-001",
            response=response,
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )
        assert completed.outcome is ReceiptOutcome.COMPLETED
        assert completed.response == response

        replay = store.commit_confirmation(
            action_id="action-confirm",
            approval_id="approval-001",
            response=response,
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )
        assert replay.outcome is ReceiptOutcome.REPLAY
        assert replay.response == response

    with FeishuCallbackStoreFactory(db_path).session() as store:
        audit = store.get_approval_audit("action-confirm")
        assert audit is not None
        assert audit.approval_id == "approval-001"
        assert audit.case_id == CASE_ID
        assert audit.diagnosis_id == DIAGNOSIS_ID
        assert audit.actor_id == ACTOR_ID
        assert audit.result == "APPROVED"
        assert audit.occurred_at == COMPLETED_AT
        assert audit.synthetic is True


def test_confirmation_rolls_back_receipt_when_audit_insert_conflicts(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "rollback.db")

    with factory.session() as store:
        for action_id in ("action-first", "action-second"):
            store.claim_action(action_id, created_at=CREATED_AT)

        store.commit_confirmation(
            action_id="action-first",
            approval_id="approval-shared",
            response={"ok": True, "action": "first"},
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )

        with pytest.raises(ReceiptConflict):
            store.commit_confirmation(
                action_id="action-second",
                approval_id="approval-shared",
                response={"ok": True, "action": "second"},
                case_id=OTHER_CASE_ID,
                diagnosis_id=DIAGNOSIS_ID,
                actor_id=ACTOR_ID,
                result="APPROVED",
                occurred_at=COMPLETED_AT,
            )

    with FeishuCallbackStoreFactory(factory.db_path).session() as store:
        still_claimed = store.claim_action("action-second", created_at=CREATED_AT)
        assert still_claimed.outcome is ReceiptOutcome.IN_PROGRESS
        assert store.get_approval_audit("action-second") is None

        completed = store.commit_confirmation(
            action_id="action-second",
            approval_id="approval-second",
            response={"ok": True, "action": "second"},
            case_id=OTHER_CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )
        assert completed.outcome is ReceiptOutcome.COMPLETED


def test_response_json_rejects_credentials_and_body_keys(tmp_path):
    db_path = tmp_path / "safe-json.db"
    factory = FeishuCallbackStoreFactory(db_path)

    with factory.session() as store:
        store.claim_event("event-sensitive", created_at=CREATED_AT)
        with pytest.raises(ValueError):
            store.complete_event(
                "event-sensitive",
                response={"credentials": "must-not-persist"},
                case_id=CASE_ID,
                completed_at=COMPLETED_AT,
            )
        with pytest.raises(ValueError):
            store.complete_event(
                "event-sensitive",
                response={"card": {"body": "raw-callback"}},
                case_id=CASE_ID,
                completed_at=COMPLETED_AT,
            )

        claimed = store.claim_event("event-sensitive", created_at=CREATED_AT)
        assert claimed.outcome is ReceiptOutcome.IN_PROGRESS

    database_bytes = db_path.read_bytes()
    assert b"must-not-persist" not in database_bytes
    assert b"raw-callback" not in database_bytes
