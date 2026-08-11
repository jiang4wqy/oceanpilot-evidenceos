import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest

from oceanpilot.adapters.feishu.store import (
    FeishuCallbackStoreFactory,
    ReceiptConflict,
    ReceiptOutcome,
)
from oceanpilot.application.feishu_models import FeishuApprovalRecord

CREATED_AT = "2026-08-05T04:00:00Z"
COMPLETED_AT = "2026-08-05T04:00:01Z"
CASE_ID = "00000000-0000-4000-8000-000000000010"
OTHER_CASE_ID = "00000000-0000-4000-8000-000000000011"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
ACTOR_ID = "ou_synthetic_operator"
ACTOR_HASH = "1bb07ff40167a4833d0315808da6b25031e63c5d396bf04ea9569d61f8d27908"
REQUEST_ID = "00000000-0000-4000-8000-000000000060"
TRACE_ID = "00000000-0000-4000-8000-000000000070"
CREATED_AT_DT = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
COMPLETED_AT_DT = datetime(2026, 8, 5, 4, 0, 1, tzinfo=UTC)


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
    db_path = tmp_path / "action.db"
    factory = FeishuCallbackStoreFactory(db_path)
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

    database_bytes = db_path.read_bytes()
    assert ACTOR_ID.encode() not in database_bytes
    assert ACTOR_HASH.encode() in database_bytes

    with FeishuCallbackStoreFactory(db_path).session() as store:
        replay_after_reopen = store.complete_action(
            "action-001",
            response=response,
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            completed_at=COMPLETED_AT,
        )
    assert replay_after_reopen.outcome is ReceiptOutcome.REPLAY


def test_chat_case_binding_is_idempotent_and_never_overwritten(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "chat.db")

    assert factory.get_case_id("tenant:chat:thread-001") is None
    factory.bind_case("tenant:chat:thread-001", CASE_ID, updated_at=CREATED_AT_DT)
    factory.bind_case("tenant:chat:thread-001", CASE_ID, updated_at=COMPLETED_AT_DT)
    assert factory.get_case_id("tenant:chat:thread-001") == CASE_ID

    with pytest.raises(ReceiptConflict):
        factory.bind_case(
            "tenant:chat:thread-001",
            OTHER_CASE_ID,
            updated_at=COMPLETED_AT_DT,
        )
    assert factory.get_case_id("tenant:chat:thread-001") == CASE_ID


def test_factory_implements_confirmation_port_with_correlated_audit(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "approval-port.db")
    with factory.session() as store:
        store.claim_action("action-port", created_at=CREATED_AT)

    receipt = factory.record_confirmation(
        FeishuApprovalRecord(
            action_id="action-port",
            approval_id="approval-port",
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_hash=ACTOR_HASH,
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
            occurred_at=COMPLETED_AT_DT,
            result="CONFIRMED",
            synthetic=True,
        )
    )

    assert receipt.replayed is False
    with factory.session() as store:
        audit = store.get_approval_audit("action-port")
    assert audit is not None
    assert audit.actor_hash == ACTOR_HASH
    assert audit.request_id == REQUEST_ID
    assert audit.trace_id == TRACE_ID

    with factory.session() as store:
        store.claim_action("action-port-retry", created_at=CREATED_AT)
    replay = factory.record_confirmation(
        FeishuApprovalRecord(
            action_id="action-port-retry",
            approval_id="approval-port-retry",
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_hash=ACTOR_HASH,
            request_id="00000000-0000-4000-8000-000000000061",
            trace_id="00000000-0000-4000-8000-000000000071",
            occurred_at=COMPLETED_AT_DT,
            result="CONFIRMED",
            synthetic=True,
        )
    )
    assert replay.replayed is True
    assert replay.action_id == "action-port"
    assert replay.approval_id == "approval-port"


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
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
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
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
            occurred_at=COMPLETED_AT,
        )
        assert replay.outcome is ReceiptOutcome.REPLAY
        assert replay.response == response

    assert ACTOR_ID.encode() not in db_path.read_bytes()

    with FeishuCallbackStoreFactory(db_path).session() as store:
        audit = store.get_approval_audit("action-confirm")
        assert audit is not None
        assert audit.approval_id == "approval-001"
        assert audit.case_id == CASE_ID
        assert audit.diagnosis_id == DIAGNOSIS_ID
        assert audit.actor_hash == ACTOR_HASH
        assert audit.result == "APPROVED"
        assert audit.request_id == REQUEST_ID
        assert audit.trace_id == TRACE_ID
        assert audit.occurred_at == COMPLETED_AT
        assert audit.synthetic is True


def test_confirmation_context_survives_reopen_and_semantic_duplicate_replays(tmp_path):
    db_path = tmp_path / "approval-context.db"
    factory = FeishuCallbackStoreFactory(db_path)
    response = {"ok": True, "result": "confirmed"}

    with factory.session() as store:
        store.claim_action("action-first", created_at=CREATED_AT)
        created = store.commit_confirmation(
            action_id="action-first",
            approval_id="approval-first",
            response=response,
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="CONFIRMED",
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
            occurred_at=COMPLETED_AT,
        )
        assert created.outcome is ReceiptOutcome.COMPLETED

        store.claim_action("action-second", created_at=CREATED_AT)
        replay = store.commit_confirmation(
            action_id="action-second",
            approval_id="approval-second",
            response=response,
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="CONFIRMED",
            request_id="00000000-0000-4000-8000-000000000061",
            trace_id="00000000-0000-4000-8000-000000000071",
            occurred_at=COMPLETED_AT,
        )
        assert replay.outcome is ReceiptOutcome.REPLAY

    with FeishuCallbackStoreFactory(db_path).session() as store:
        audit = store.get_approval_audit("action-first")
        assert audit is not None
        assert audit.actor_hash == ACTOR_HASH
        assert audit.request_id == REQUEST_ID
        assert audit.trace_id == TRACE_ID


def test_existing_approval_database_migrates_without_losing_rows(tmp_path):
    db_path = tmp_path / "legacy-approval.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE feishu_approval_audits (
                approval_id TEXT PRIMARY KEY,
                action_id TEXT NOT NULL UNIQUE,
                case_id TEXT NOT NULL,
                diagnosis_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                result TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO feishu_approval_audits (
                approval_id, action_id, case_id, diagnosis_id, actor_id,
                result, occurred_at, synthetic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                "approval-legacy",
                "action-legacy",
                CASE_ID,
                DIAGNOSIS_ID,
                ACTOR_ID,
                "APPROVED",
                COMPLETED_AT,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with FeishuCallbackStoreFactory(db_path).session() as store:
        audit = store.get_approval_audit("action-legacy")
        assert audit is not None
        assert audit.approval_id == "approval-legacy"
        assert audit.actor_hash == ACTOR_HASH
        assert audit.action_kind == "CONFIRM_REVIEW"
        assert audit.request_id is None
        assert audit.trace_id is None

        store.claim_action("action-after-migration", created_at=CREATED_AT)

    replay = FeishuCallbackStoreFactory(db_path).record_confirmation(
        FeishuApprovalRecord(
            action_id="action-after-migration",
            approval_id="approval-after-migration",
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_hash=ACTOR_HASH,
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
            occurred_at=COMPLETED_AT_DT,
            result="CONFIRMED",
            synthetic=True,
        )
    )
    assert replay.replayed is True
    assert replay.action_id == "action-legacy"
    assert replay.approval_id == "approval-legacy"


def test_existing_duplicate_approval_rows_survive_additive_migration(tmp_path):
    db_path = tmp_path / "legacy-duplicate-approval.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE feishu_approval_audits (
                approval_id TEXT PRIMARY KEY,
                action_id TEXT NOT NULL UNIQUE,
                case_id TEXT NOT NULL,
                diagnosis_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                result TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO feishu_approval_audits (
                approval_id, action_id, case_id, diagnosis_id, actor_id,
                result, occurred_at, synthetic
            ) VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, 1)
            """,
            (
                (
                    "approval-legacy-a",
                    "action-legacy-a",
                    CASE_ID,
                    DIAGNOSIS_ID,
                    ACTOR_ID,
                    COMPLETED_AT,
                ),
                (
                    "approval-legacy-b",
                    "action-legacy-b",
                    CASE_ID,
                    DIAGNOSIS_ID,
                    ACTOR_ID,
                    COMPLETED_AT,
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with FeishuCallbackStoreFactory(db_path).session() as store:
        first = store.get_approval_audit("action-legacy-a")
        second = store.get_approval_audit("action-legacy-b")

    assert first is not None
    assert second is not None
    assert first.actor_hash == ACTOR_HASH
    assert second.actor_hash == ACTOR_HASH


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
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
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
                request_id=REQUEST_ID,
                trace_id=TRACE_ID,
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
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
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
