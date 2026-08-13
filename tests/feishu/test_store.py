import sqlite3
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
PAYLOAD_HASH = "a" * 64
OTHER_PAYLOAD_HASH = "b" * 64
CHAT_DIGEST = "sha256:chat:0762b1fd9deeec5d39a675ed0c73d9b0e8565f6c8814796cafdb1ead989e2a9b"
ACTOR_DIGEST = "sha256:actor:75c55c996beff88c692d8ab4d77feee7b09fdd0b13c7caa772b75b730c3576af"


@pytest.mark.parametrize("receipt_kind", ("event", "action"))
def test_receipt_id_replay_rejects_different_verified_payload(receipt_kind, tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / f"{receipt_kind}-payload.db")

    with factory.session() as store:
        claim = store.claim_event if receipt_kind == "event" else store.claim_action
        assert (
            claim("same-id", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT).outcome
            is ReceiptOutcome.CLAIMED
        )
        with pytest.raises(ReceiptConflict):
            claim("same-id", payload_hash=OTHER_PAYLOAD_HASH, created_at=CREATED_AT)


@pytest.mark.parametrize(
    ("table", "key_column"),
    (
        ("feishu_event_receipts", "event_id"),
        ("feishu_action_receipts", "action_id"),
    ),
)
def test_new_receipt_schema_requires_payload_hash(table, key_column, tmp_path):
    db_path = tmp_path / f"new-{key_column}.db"
    FeishuCallbackStoreFactory(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {row[1]: row for row in connection.execute(f"PRAGMA table_info({table})")}

    assert columns["payload_hash"][3] == 1


@pytest.mark.parametrize(
    ("table", "key_column", "claim_name"),
    (
        ("feishu_event_receipts", "event_id", "claim_event"),
        ("feishu_action_receipts", "action_id", "claim_action"),
    ),
)
def test_legacy_receipt_adopts_first_payload_hash_and_replays_after_reopen(
    table, key_column, claim_name, tmp_path
):
    db_path = tmp_path / f"legacy-{key_column}.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f"CREATE TABLE {table} ("
            f"{key_column} TEXT PRIMARY KEY, "
            "status TEXT NOT NULL, response_json TEXT, case_id TEXT, "
            "diagnosis_id TEXT, actor_id TEXT, created_at TEXT NOT NULL, "
            "completed_at TEXT)"
        )
        connection.execute(
            f"INSERT INTO {table} ({key_column}, status, created_at) VALUES (?, 'CLAIMED', ?)",
            ("legacy-receipt", CREATED_AT),
        )

    factory = FeishuCallbackStoreFactory(db_path)
    with sqlite3.connect(db_path) as connection:
        columns = {row[1]: row for row in connection.execute(f"PRAGMA table_info({table})")}
    assert columns["payload_hash"][3] == 0

    with factory.session() as store:
        claim = getattr(store, claim_name)
        assert (
            claim("legacy-receipt", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT).outcome
            is ReceiptOutcome.IN_PROGRESS
        )

    with FeishuCallbackStoreFactory(db_path).session() as store:
        claim = getattr(store, claim_name)
        assert (
            claim("legacy-receipt", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT).outcome
            is ReceiptOutcome.IN_PROGRESS
        )
        with pytest.raises(ReceiptConflict):
            claim(
                "legacy-receipt",
                payload_hash=OTHER_PAYLOAD_HASH,
                created_at=CREATED_AT,
            )


@pytest.mark.parametrize("receipt_kind", ("event", "action"))
@pytest.mark.parametrize("payload_hash", ("A" * 64, "a" * 63, "g" * 64, ""))
def test_invalid_payload_hash_is_rejected_without_claiming(receipt_kind, payload_hash, tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / f"invalid-{receipt_kind}.db")

    with factory.session() as store:
        claim = store.claim_event if receipt_kind == "event" else store.claim_action
        with pytest.raises(ValueError):
            claim("receipt", payload_hash=payload_hash, created_at=CREATED_AT)
        assert (
            claim("receipt", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT).outcome
            is ReceiptOutcome.CLAIMED
        )


def test_event_claim_complete_and_replay_survive_reopen(tmp_path):
    db_path = tmp_path / "callbacks.db"
    factory = FeishuCallbackStoreFactory(db_path)
    response = {"card": {"type": "diagnosis"}, "ok": True}

    with factory.session() as store:
        claimed = store.claim_event("event-001", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
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
        replay = store.claim_event("event-001", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
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
                return store.claim_event(
                    "shared-id", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT
                ).outcome
            return store.claim_action(
                "shared-id", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT
            ).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = {future.result() for future in (executor.submit(claim), executor.submit(claim))}

    assert outcomes == {ReceiptOutcome.CLAIMED, ReceiptOutcome.IN_PROGRESS}


def test_event_completion_does_not_overwrite_conflicting_response(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-conflict.db")
    original = {"ok": True, "result": "created"}

    with factory.session() as store:
        store.claim_event("event-conflict", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
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

        persisted = store.claim_event(
            "event-conflict", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT
        )
        assert persisted.outcome is ReceiptOutcome.REPLAY
        assert persisted.response == original


def test_action_claim_complete_and_replay_are_idempotent(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "action.db")
    response = {"ok": True, "result": "confirmed"}

    with factory.session() as store:
        claimed = store.claim_action("action-001", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
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

        replay = store.claim_action("action-001", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
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
    db_path = tmp_path / "chat.db"
    factory = FeishuCallbackStoreFactory(db_path)

    with factory.session() as store:
        assert store.get_chat_case("chat-001") is None
        store.bind_chat_case("chat-001", CASE_ID, updated_at=CREATED_AT)
        store.bind_chat_case("chat-001", CASE_ID, updated_at=COMPLETED_AT)
        assert store.get_chat_case("chat-001") == CASE_ID

        with pytest.raises(ReceiptConflict):
            store.bind_chat_case("chat-001", OTHER_CASE_ID, updated_at=COMPLETED_AT)
        assert store.get_chat_case("chat-001") == CASE_ID

    database_bytes = db_path.read_bytes()
    assert b"chat-001" not in database_bytes
    assert CHAT_DIGEST.encode() in database_bytes


def test_external_id_digests_are_accepted_without_hashing_again(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "digests.db")

    with factory.session() as store:
        store.bind_chat_case(CHAT_DIGEST, CASE_ID, updated_at=CREATED_AT)
        assert store.get_chat_case("chat-001") == CASE_ID
        assert store.get_chat_case(CHAT_DIGEST) == CASE_ID

        store.claim_action("digest-action", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
        store.commit_confirmation(
            action_id="digest-action",
            approval_id="digest-approval",
            response={"ok": True},
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_DIGEST,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )
        audit = store.get_approval_audit("digest-action")

    assert audit is not None
    assert audit.actor_id == ACTOR_DIGEST


def test_malformed_digest_prefixes_are_treated_as_raw_external_ids(tmp_path):
    db_path = tmp_path / "malformed-digests.db"
    malformed_chat = "sha256:chat:not-a-real-digest"
    malformed_actor = "sha256:actor:not-a-real-digest"
    factory = FeishuCallbackStoreFactory(db_path)

    with factory.session() as store:
        store.bind_chat_case(malformed_chat, CASE_ID, updated_at=CREATED_AT)
        store.claim_action("malformed-action", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
        store.commit_confirmation(
            action_id="malformed-action",
            approval_id="malformed-approval",
            response={"ok": True},
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=malformed_actor,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )
        audit = store.get_approval_audit("malformed-action")

    assert audit is not None
    assert audit.actor_id.startswith("sha256:actor:")
    assert audit.actor_id != malformed_actor
    database_bytes = db_path.read_bytes()
    assert malformed_chat.encode() not in database_bytes
    assert malformed_actor.encode() not in database_bytes


def test_reopen_normalizes_malformed_legacy_digest_prefixes(tmp_path):
    db_path = tmp_path / "legacy-malformed-digests.db"
    malformed_chat = "sha256:chat:not-a-real-digest"
    malformed_actor = "sha256:actor:not-a-real-digest"
    factory = FeishuCallbackStoreFactory(db_path)
    with factory.session() as store:
        store.claim_action(
            "legacy-malformed-action",
            payload_hash=PAYLOAD_HASH,
            created_at=CREATED_AT,
        )
        store.commit_confirmation(
            action_id="legacy-malformed-action",
            approval_id="legacy-malformed-approval",
            response={"ok": True},
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO feishu_chat_cases (chat_id, case_id, updated_at) VALUES (?, ?, ?)",
            (malformed_chat, CASE_ID, CREATED_AT),
        )
        connection.execute(
            "UPDATE feishu_action_receipts SET actor_id = ? WHERE action_id = ?",
            (malformed_actor, "legacy-malformed-action"),
        )
        connection.execute(
            "UPDATE feishu_approval_audits SET actor_id = ? WHERE action_id = ?",
            (malformed_actor, "legacy-malformed-action"),
        )

    with FeishuCallbackStoreFactory(db_path).session() as store:
        assert store.get_chat_case(malformed_chat) == CASE_ID
        audit = store.get_approval_audit("legacy-malformed-action")
        assert audit is not None
        assert audit.actor_id.startswith("sha256:actor:")
        assert audit.actor_id != malformed_actor

    database_bytes = db_path.read_bytes()
    assert malformed_chat.encode() not in database_bytes
    assert malformed_actor.encode() not in database_bytes


def test_reopen_migrates_legacy_raw_chat_binding_once(tmp_path):
    db_path = tmp_path / "legacy-chat.db"
    FeishuCallbackStoreFactory(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO feishu_chat_cases (chat_id, case_id, updated_at) VALUES (?, ?, ?)",
            ("legacy-chat", CASE_ID, CREATED_AT),
        )

    for _ in range(2):
        with FeishuCallbackStoreFactory(db_path).session() as store:
            assert store.get_chat_case("legacy-chat") == CASE_ID

    database_bytes = db_path.read_bytes()
    assert b"legacy-chat" not in database_bytes


def test_reopen_merges_raw_and_digest_chat_binding_for_same_case(tmp_path):
    db_path = tmp_path / "legacy-chat-duplicate.db"
    FeishuCallbackStoreFactory(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO feishu_chat_cases (chat_id, case_id, updated_at) VALUES (?, ?, ?)",
            (
                ("chat-001", CASE_ID, CREATED_AT),
                (CHAT_DIGEST, CASE_ID, COMPLETED_AT),
            ),
        )

    with FeishuCallbackStoreFactory(db_path).session() as store:
        assert store.get_chat_case("chat-001") == CASE_ID
        assert store.get_chat_case(CHAT_DIGEST) == CASE_ID

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT chat_id, case_id FROM feishu_chat_cases").fetchall()
    assert rows == [(CHAT_DIGEST, CASE_ID)]


def test_reopen_rejects_conflicting_raw_and_digest_chat_bindings(tmp_path):
    db_path = tmp_path / "legacy-chat-conflict.db"
    FeishuCallbackStoreFactory(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO feishu_chat_cases (chat_id, case_id, updated_at) VALUES (?, ?, ?)",
            (
                ("chat-001", CASE_ID, CREATED_AT),
                (CHAT_DIGEST, OTHER_CASE_ID, COMPLETED_AT),
            ),
        )

    with pytest.raises(ReceiptConflict):
        FeishuCallbackStoreFactory(db_path)

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT chat_id, case_id FROM feishu_chat_cases ORDER BY chat_id"
        ).fetchall()
    assert rows == [("chat-001", CASE_ID), (CHAT_DIGEST, OTHER_CASE_ID)]


def test_reopen_migrates_legacy_raw_actor_ids_once(tmp_path):
    db_path = tmp_path / "legacy-actor.db"
    factory = FeishuCallbackStoreFactory(db_path)
    with factory.session() as store:
        store.claim_action("legacy-action", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
        store.commit_confirmation(
            action_id="legacy-action",
            approval_id="legacy-approval",
            response={"ok": True},
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            result="APPROVED",
            occurred_at=COMPLETED_AT,
        )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE feishu_action_receipts SET actor_id = ? WHERE action_id = ?",
            ("legacy-actor", "legacy-action"),
        )
        connection.execute(
            "UPDATE feishu_approval_audits SET actor_id = ? WHERE action_id = ?",
            ("legacy-actor", "legacy-action"),
        )

    for _ in range(2):
        with FeishuCallbackStoreFactory(db_path).session() as store:
            audit = store.get_approval_audit("legacy-action")
            assert audit is not None
            assert audit.actor_id.startswith("sha256:actor:")

    assert b"legacy-actor" not in db_path.read_bytes()


def test_confirmation_and_approval_audit_commit_atomically_and_replay(tmp_path):
    db_path = tmp_path / "approval.db"
    factory = FeishuCallbackStoreFactory(db_path)
    response = {"ok": True, "result": "approved"}

    with factory.session() as store:
        store.claim_action("action-confirm", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
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
        assert audit.actor_id == ACTOR_DIGEST
        assert audit.result == "APPROVED"
        assert audit.occurred_at == COMPLETED_AT
        assert audit.synthetic is True

    database_bytes = db_path.read_bytes()
    assert ACTOR_ID.encode() not in database_bytes


def test_confirmation_rolls_back_receipt_when_audit_insert_conflicts(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "rollback.db")

    with factory.session() as store:
        for action_id in ("action-first", "action-second"):
            store.claim_action(action_id, payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)

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
        still_claimed = store.claim_action(
            "action-second", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT
        )
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
        store.claim_event("event-sensitive", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT)
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

        claimed = store.claim_event(
            "event-sensitive", payload_hash=PAYLOAD_HASH, created_at=CREATED_AT
        )
        assert claimed.outcome is ReceiptOutcome.IN_PROGRESS

    database_bytes = db_path.read_bytes()
    assert b"must-not-persist" not in database_bytes
    assert b"raw-callback" not in database_bytes
