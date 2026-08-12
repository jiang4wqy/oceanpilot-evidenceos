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
from oceanpilot.application.feishu_ports import FeishuBindingOutcome

CREATED_AT = "2026-08-05T04:00:00Z"
COMPLETED_AT = "2026-08-05T04:00:01Z"
ACTIVE_NOW = "2026-08-05T04:00:05Z"
LEASE_EXPIRES_AT = "2026-08-05T04:00:10Z"
TAKEOVER_NOW = "2026-08-05T04:00:11Z"
TAKEOVER_LEASE_EXPIRES_AT = "2026-08-05T04:00:21Z"
EVENT_HASH = "a" * 64
ACTION_HASH = "b" * 64
FIRST_CLAIM_TOKEN = "c" * 64
SECOND_CLAIM_TOKEN = "d" * 64
CASE_ID = "00000000-0000-4000-8000-000000000010"
OTHER_CASE_ID = "00000000-0000-4000-8000-000000000011"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
ACTOR_ID = "ou_synthetic_operator"
ACTOR_HASH = "1bb07ff40167a4833d0315808da6b25031e63c5d396bf04ea9569d61f8d27908"
REQUEST_ID = "00000000-0000-4000-8000-000000000060"
TRACE_ID = "00000000-0000-4000-8000-000000000070"
CREATED_AT_DT = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
COMPLETED_AT_DT = datetime(2026, 8, 5, 4, 0, 1, tzinfo=UTC)


def test_event_claim_lease_allows_crash_takeover_and_fences_stale_worker(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-lease-takeover.db")

    with factory.session() as store:
        first = store.claim_event(
            "event-crashed-worker",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        active_retry = store.claim_event(
            "event-crashed-worker",
            payload_hash=EVENT_HASH,
            claim_token=SECOND_CLAIM_TOKEN,
            now=ACTIVE_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )
        takeover = store.claim_event(
            "event-crashed-worker",
            payload_hash=EVENT_HASH,
            claim_token=SECOND_CLAIM_TOKEN,
            now=TAKEOVER_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )

        with pytest.raises(ReceiptConflict):
            store.complete_event(
                "event-crashed-worker",
                claim_token=FIRST_CLAIM_TOKEN,
                response={"ok": True},
                case_id=CASE_ID,
                completed_at=TAKEOVER_NOW,
            )
        with pytest.raises(ReceiptConflict):
            store.release_event(
                "event-crashed-worker",
                payload_hash=EVENT_HASH,
                claim_token=FIRST_CLAIM_TOKEN,
            )
        completed = store.complete_event(
            "event-crashed-worker",
            claim_token=SECOND_CLAIM_TOKEN,
            response={"ok": True},
            case_id=CASE_ID,
            completed_at=TAKEOVER_NOW,
        )

    assert first.outcome is ReceiptOutcome.CLAIMED
    assert active_retry.outcome is ReceiptOutcome.IN_PROGRESS
    assert takeover.outcome is ReceiptOutcome.CLAIMED
    assert completed.outcome is ReceiptOutcome.COMPLETED
    connection = sqlite3.connect(factory.db_path)
    try:
        attempt = connection.execute(
            "SELECT attempt FROM feishu_event_receipts WHERE event_id = ?",
            ("event-crashed-worker",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert attempt == 2


def test_event_claim_complete_and_replay_survive_reopen(tmp_path):
    db_path = tmp_path / "callbacks.db"
    factory = FeishuCallbackStoreFactory(db_path)
    response = {"card": {"type": "diagnosis"}, "ok": True}

    with factory.session() as store:
        claimed = store.claim_event(
            "event-001",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        assert claimed.outcome is ReceiptOutcome.CLAIMED
        assert claimed.response is None

        completed = store.complete_event(
            "event-001",
            claim_token=FIRST_CLAIM_TOKEN,
            response=response,
            case_id=CASE_ID,
            completed_at=COMPLETED_AT,
        )
        assert completed.outcome is ReceiptOutcome.COMPLETED
        assert completed.response == response

    reopened = FeishuCallbackStoreFactory(db_path)
    with reopened.session() as store:
        replay = store.claim_event(
            "event-001",
            payload_hash=EVENT_HASH,
            claim_token=SECOND_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        assert replay.outcome is ReceiptOutcome.REPLAY
        assert replay.response == response


def test_event_claim_rejects_callback_id_reused_with_different_payload(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-payload.db")

    with factory.session() as store:
        first = store.claim_event(
            "event-payload-001",
            payload_hash="a" * 64,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        same_payload = store.claim_event(
            "event-payload-001",
            payload_hash="a" * 64,
            claim_token=SECOND_CLAIM_TOKEN,
            now=ACTIVE_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )
        with pytest.raises(ReceiptConflict):
            store.claim_event(
                "event-payload-001",
                payload_hash="b" * 64,
                claim_token=SECOND_CLAIM_TOKEN,
                now=ACTIVE_NOW,
                lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
            )

    assert first.outcome is ReceiptOutcome.CLAIMED
    assert same_payload.outcome is ReceiptOutcome.IN_PROGRESS


def test_action_claim_rejects_completed_id_reused_with_different_payload(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "action-payload.db")
    response = {"ok": True}

    with factory.session() as store:
        store.claim_action(
            "action-payload-001",
            payload_hash=ACTION_HASH,
            created_at=CREATED_AT,
        )
        store.complete_action(
            "action-payload-001",
            response=response,
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id=ACTOR_ID,
            completed_at=COMPLETED_AT,
        )
        replay = store.claim_action(
            "action-payload-001",
            payload_hash=ACTION_HASH,
            created_at=CREATED_AT,
        )
        with pytest.raises(ReceiptConflict):
            store.claim_action(
                "action-payload-001",
                payload_hash=EVENT_HASH,
                created_at=CREATED_AT,
            )

    assert replay.outcome is ReceiptOutcome.REPLAY
    assert replay.response == response


@pytest.mark.parametrize("receipt_kind", ("event", "action"))
@pytest.mark.parametrize("status", ("CLAIMED", "COMPLETED"))
def test_legacy_receipt_without_payload_hash_is_pinned_on_first_claim(
    tmp_path, receipt_kind, status
):
    db_path = tmp_path / f"legacy-{receipt_kind}-{status}.db"
    table = f"feishu_{receipt_kind}_receipts"
    key_column = f"{receipt_kind}_id"
    extra_columns = (
        ""
        if receipt_kind == "event"
        else ", diagnosis_id TEXT, actor_id TEXT"
    )
    completion_columns = (
        "response_json, case_id, completed_at"
        if receipt_kind == "event"
        else "response_json, case_id, diagnosis_id, actor_id, completed_at"
    )
    completion_values = (
        ('{"ok":true}', CASE_ID, COMPLETED_AT)
        if receipt_kind == "event"
        else ('{"ok":true}', CASE_ID, DIAGNOSIS_ID, ACTOR_HASH, COMPLETED_AT)
    )
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            f"""
            CREATE TABLE {table} (
                {key_column} TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                response_json TEXT,
                case_id TEXT{extra_columns},
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        if status == "CLAIMED":
            connection.execute(
                f"INSERT INTO {table} ({key_column}, status, created_at) "
                "VALUES (?, 'CLAIMED', ?)",
                ("legacy-id", CREATED_AT),
            )
        else:
            placeholders = ", ".join("?" for _ in completion_values)
            connection.execute(
                f"INSERT INTO {table} ({key_column}, status, created_at, "
                f"{completion_columns}) VALUES (?, 'COMPLETED', ?, {placeholders})",
                ("legacy-id", CREATED_AT, *completion_values),
            )
        connection.commit()
    finally:
        connection.close()

    factory = FeishuCallbackStoreFactory(db_path)
    with factory.session() as store:
        claim = (
            store.claim_event(
                "legacy-id",
                payload_hash=EVENT_HASH,
                claim_token=FIRST_CLAIM_TOKEN,
                now=CREATED_AT,
                lease_expires_at=LEASE_EXPIRES_AT,
            )
            if receipt_kind == "event"
            else store.claim_action(
                "legacy-id", payload_hash=EVENT_HASH, created_at=CREATED_AT
            )
        )
        with pytest.raises(ReceiptConflict):
            if receipt_kind == "event":
                store.claim_event(
                    "legacy-id",
                    payload_hash=ACTION_HASH,
                    claim_token=SECOND_CLAIM_TOKEN,
                    now=ACTIVE_NOW,
                    lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
                )
            else:
                store.claim_action(
                    "legacy-id", payload_hash=ACTION_HASH, created_at=CREATED_AT
                )

    expected = (
        ReceiptOutcome.CLAIMED
        if receipt_kind == "event" and status == "CLAIMED"
        else ReceiptOutcome.IN_PROGRESS
        if status == "CLAIMED"
        else ReceiptOutcome.REPLAY
    )
    assert claim.outcome is expected


def test_releasing_claimed_event_allows_retry_with_same_payload(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-release.db")

    with factory.session() as store:
        store.claim_event(
            "retry-event",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        store.release_event(
            "retry-event",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
        )
        retried = store.claim_event(
            "retry-event",
            payload_hash=EVENT_HASH,
            claim_token=SECOND_CLAIM_TOKEN,
            now=COMPLETED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )

    assert retried.outcome is ReceiptOutcome.CLAIMED


def test_releasing_claimed_event_preserves_payload_identity(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-release-identity.db")

    with factory.session() as store:
        store.claim_event(
            "retry-event",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        store.release_event(
            "retry-event",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
        )
        with pytest.raises(ReceiptConflict):
            store.claim_event(
                "retry-event",
                payload_hash=ACTION_HASH,
                claim_token=SECOND_CLAIM_TOKEN,
                now=COMPLETED_AT,
                lease_expires_at=LEASE_EXPIRES_AT,
            )


def test_release_event_never_deletes_mismatched_or_completed_receipt(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-release-conflict.db")

    with factory.session() as store:
        store.claim_event(
            "release-conflict",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        with pytest.raises(ReceiptConflict):
            store.release_event(
                "release-conflict",
                payload_hash=ACTION_HASH,
                claim_token=FIRST_CLAIM_TOKEN,
            )
        assert (
            store.claim_event(
                "release-conflict",
                payload_hash=EVENT_HASH,
                claim_token=SECOND_CLAIM_TOKEN,
                now=ACTIVE_NOW,
                lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
            ).outcome
            is ReceiptOutcome.IN_PROGRESS
        )
        store.complete_event(
            "release-conflict",
            claim_token=FIRST_CLAIM_TOKEN,
            response={"ok": True},
            case_id=CASE_ID,
            completed_at=COMPLETED_AT,
        )
        with pytest.raises(ReceiptConflict):
            store.release_event(
                "release-conflict",
                payload_hash=EVENT_HASH,
                claim_token=FIRST_CLAIM_TOKEN,
            )
        assert (
            store.claim_event(
                "release-conflict",
                payload_hash=EVENT_HASH,
                claim_token=SECOND_CLAIM_TOKEN,
                now=ACTIVE_NOW,
                lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
            ).outcome
            is ReceiptOutcome.REPLAY
        )


def test_new_receipt_tables_require_payload_hash_at_database_boundary(tmp_path):
    db_path = tmp_path / "new-schema.db"
    FeishuCallbackStoreFactory(db_path)

    connection = sqlite3.connect(db_path)
    try:
        for table in ("feishu_event_receipts", "feishu_action_receipts"):
            columns = {
                row[1]: row for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert columns["payload_hash"][3] == 1
    finally:
        connection.close()


def test_case_binding_lease_takeover_reuses_reserved_id_and_fences_stale_worker(
    tmp_path,
):
    factory = FeishuCallbackStoreFactory(tmp_path / "binding.db")

    with factory.session() as store:
        claimed = store.claim_case_binding(
            "binding-001",
            "event-owner",
            CASE_ID,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        in_progress = store.claim_case_binding(
            "binding-001",
            "event-other",
            OTHER_CASE_ID,
            claim_token=SECOND_CLAIM_TOKEN,
            now=ACTIVE_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )
        takeover = store.claim_case_binding(
            "binding-001",
            "event-other",
            OTHER_CASE_ID,
            claim_token=SECOND_CLAIM_TOKEN,
            now=TAKEOVER_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )
        with pytest.raises(ReceiptConflict):
            store.complete_case_binding(
                "binding-001",
                "event-owner",
                CASE_ID,
                claim_token=FIRST_CLAIM_TOKEN,
                updated_at=COMPLETED_AT,
            )
        with pytest.raises(ReceiptConflict):
            store.release_case_binding(
                "binding-001",
                "event-owner",
                claim_token=FIRST_CLAIM_TOKEN,
            )
        assert store.get_case_id("binding-001") is None

        bound = store.complete_case_binding(
            "binding-001",
            "event-other",
            CASE_ID,
            claim_token=SECOND_CLAIM_TOKEN,
            updated_at=COMPLETED_AT,
        )
        with pytest.raises(ReceiptConflict):
            store.complete_case_binding(
                "binding-001",
                "event-owner",
                CASE_ID,
                claim_token=FIRST_CLAIM_TOKEN,
                updated_at=COMPLETED_AT,
            )
        replay = store.complete_case_binding(
            "binding-001",
            "event-other",
            CASE_ID,
            claim_token=SECOND_CLAIM_TOKEN,
            updated_at=COMPLETED_AT,
        )
        observed = store.claim_case_binding(
            "binding-001",
            "event-later",
            OTHER_CASE_ID,
            claim_token=FIRST_CLAIM_TOKEN,
            now=TAKEOVER_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )

    assert claimed.outcome is FeishuBindingOutcome.CLAIMED
    assert claimed.case_id == CASE_ID
    assert in_progress.outcome is FeishuBindingOutcome.IN_PROGRESS
    assert in_progress.case_id == CASE_ID
    assert takeover.outcome is FeishuBindingOutcome.CLAIMED
    assert takeover.case_id == CASE_ID
    assert bound.outcome is FeishuBindingOutcome.BOUND
    assert bound.case_id == CASE_ID
    assert replay == bound
    assert observed == bound


def test_active_case_binding_lease_keeps_stable_reserved_case_id(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "binding-resume.db")

    first = factory.claim_case_binding(
        "binding-resume",
        "event-owner",
        CASE_ID,
        claim_token=FIRST_CLAIM_TOKEN,
        now=CREATED_AT_DT,
        lease_expires_at=datetime(2026, 8, 5, 4, 0, 10, tzinfo=UTC),
    )
    resumed = factory.claim_case_binding(
        "binding-resume",
        "event-owner",
        OTHER_CASE_ID,
        claim_token=SECOND_CLAIM_TOKEN,
        now=COMPLETED_AT_DT,
        lease_expires_at=datetime(2026, 8, 5, 4, 0, 11, tzinfo=UTC),
    )

    assert first.outcome is FeishuBindingOutcome.CLAIMED
    assert first.case_id == CASE_ID
    assert resumed.outcome is FeishuBindingOutcome.IN_PROGRESS
    assert resumed.case_id == CASE_ID


def test_case_binding_claim_reads_legacy_chat_mapping(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "legacy-binding.db")
    factory.bind_case("legacy-binding", CASE_ID, updated_at=CREATED_AT_DT)

    claim = factory.claim_case_binding(
        "legacy-binding",
        "event-after-upgrade",
        OTHER_CASE_ID,
        claim_token=FIRST_CLAIM_TOKEN,
        now=COMPLETED_AT_DT,
        lease_expires_at=datetime(2026, 8, 5, 4, 0, 11, tzinfo=UTC),
    )

    assert claim.outcome is FeishuBindingOutcome.BOUND
    assert claim.case_id == CASE_ID


@pytest.mark.parametrize("status", ("CLAIMED", "BOUND"))
def test_legacy_case_binding_claims_migrate_without_losing_reserved_case_id(
    tmp_path,
    status,
):
    db_path = tmp_path / f"legacy-binding-claim-{status.lower()}.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE feishu_binding_claims (
                binding_key TEXT PRIMARY KEY,
                owner_event_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('CLAIMED', 'BOUND')),
                case_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO feishu_binding_claims (
                binding_key, owner_event_id, status, case_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-binding-claim",
                "legacy-event",
                status,
                CASE_ID,
                CREATED_AT,
                COMPLETED_AT if status == "BOUND" else None,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    factory = FeishuCallbackStoreFactory(db_path)
    claim = factory.claim_case_binding(
        "legacy-binding-claim",
        "event-after-upgrade",
        OTHER_CASE_ID,
        claim_token=FIRST_CLAIM_TOKEN,
        now=COMPLETED_AT_DT,
        lease_expires_at=datetime(2026, 8, 5, 4, 0, 11, tzinfo=UTC),
    )

    expected = (
        FeishuBindingOutcome.CLAIMED
        if status == "CLAIMED"
        else FeishuBindingOutcome.BOUND
    )
    assert claim.outcome is expected
    assert claim.case_id == CASE_ID
    assert factory.get_case_id("legacy-binding-claim") == (
        CASE_ID if status == "BOUND" else None
    )


def test_concurrent_case_binding_claim_has_one_owner(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "binding-concurrent.db")
    barrier = Barrier(2)

    def claim(event_id):
        barrier.wait()
        return factory.claim_case_binding(
            "shared-binding",
            event_id,
            CASE_ID,
            claim_token=f"token-{event_id}",
            now=CREATED_AT_DT,
            lease_expires_at=datetime(2026, 8, 5, 4, 0, 10, tzinfo=UTC),
        ).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = {
            future.result()
            for future in (
                executor.submit(claim, "event-a"),
                executor.submit(claim, "event-b"),
            )
        }

    assert outcomes == {
        FeishuBindingOutcome.CLAIMED,
        FeishuBindingOutcome.IN_PROGRESS,
    }


def test_releasing_owned_case_binding_claim_allows_recovery(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "binding-release.db")
    claimed = factory.claim_case_binding(
        "recoverable-binding",
        "event-owner",
        CASE_ID,
        claim_token=FIRST_CLAIM_TOKEN,
        now=CREATED_AT_DT,
        lease_expires_at=datetime(2026, 8, 5, 4, 0, 10, tzinfo=UTC),
    )

    with pytest.raises(ReceiptConflict):
        factory.release_case_binding(
            "recoverable-binding",
            "event-owner",
            claim_token=SECOND_CLAIM_TOKEN,
        )
    factory.release_case_binding(
        "recoverable-binding",
        "event-owner",
        claim_token=FIRST_CLAIM_TOKEN,
    )
    retried = factory.claim_case_binding(
        "recoverable-binding",
        "event-retry",
        OTHER_CASE_ID,
        claim_token=SECOND_CLAIM_TOKEN,
        now=COMPLETED_AT_DT,
        lease_expires_at=datetime(2026, 8, 5, 4, 0, 11, tzinfo=UTC),
    )

    assert claimed.outcome is FeishuBindingOutcome.CLAIMED
    assert retried.outcome is FeishuBindingOutcome.CLAIMED


def test_release_case_binding_never_deletes_bound_mapping(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "binding-release-bound.db")
    factory.claim_case_binding(
        "bound-binding",
        "event-owner",
        CASE_ID,
        claim_token=FIRST_CLAIM_TOKEN,
        now=CREATED_AT_DT,
        lease_expires_at=datetime(2026, 8, 5, 4, 0, 10, tzinfo=UTC),
    )
    factory.complete_case_binding(
        "bound-binding",
        "event-owner",
        CASE_ID,
        claim_token=FIRST_CLAIM_TOKEN,
        updated_at=COMPLETED_AT_DT,
    )

    with pytest.raises(ReceiptConflict):
        factory.release_case_binding(
            "bound-binding",
            "event-owner",
            claim_token=FIRST_CLAIM_TOKEN,
        )

    assert factory.get_case_id("bound-binding") == CASE_ID


@pytest.mark.parametrize("receipt_kind", ("event", "action"))
@pytest.mark.parametrize("payload_hash", (None, "A" * 64, "a" * 63, "g" * 64))
def test_receipt_claim_requires_lowercase_sha256(tmp_path, receipt_kind, payload_hash):
    factory = FeishuCallbackStoreFactory(tmp_path / f"invalid-{receipt_kind}.db")

    with factory.session() as store, pytest.raises(ValueError):
        if receipt_kind == "event":
            store.claim_event(
                "invalid-event",
                payload_hash=payload_hash,
                claim_token=FIRST_CLAIM_TOKEN,
                now=CREATED_AT,
                lease_expires_at=LEASE_EXPIRES_AT,
            )
        else:
            store.claim_action(
                "invalid-action",
                payload_hash=payload_hash,
                created_at=CREATED_AT,
            )


@pytest.mark.parametrize("receipt_kind", ("event", "action"))
def test_concurrent_claim_has_one_winner(tmp_path, receipt_kind):
    factory = FeishuCallbackStoreFactory(tmp_path / f"{receipt_kind}.db")
    barrier = Barrier(2)

    def claim():
        with factory.session() as store:
            barrier.wait()
            if receipt_kind == "event":
                return store.claim_event(
                    "shared-id",
                    payload_hash=EVENT_HASH,
                    claim_token=FIRST_CLAIM_TOKEN,
                    now=CREATED_AT,
                    lease_expires_at=LEASE_EXPIRES_AT,
                ).outcome
            return store.claim_action(
                "shared-id", payload_hash=ACTION_HASH, created_at=CREATED_AT
            ).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = {future.result() for future in (executor.submit(claim), executor.submit(claim))}

    assert outcomes == {ReceiptOutcome.CLAIMED, ReceiptOutcome.IN_PROGRESS}


@pytest.mark.parametrize("receipt_kind", ("event", "action"))
def test_concurrent_receipt_id_reuse_with_different_hash_has_one_conflict(
    tmp_path, receipt_kind
):
    factory = FeishuCallbackStoreFactory(tmp_path / f"{receipt_kind}-hash-race.db")
    barrier = Barrier(2)

    def claim(payload_hash):
        with factory.session() as store:
            barrier.wait()
            try:
                result = (
                    store.claim_event(
                        "shared-id",
                        payload_hash=payload_hash,
                        claim_token=(
                            FIRST_CLAIM_TOKEN
                            if payload_hash == EVENT_HASH
                            else SECOND_CLAIM_TOKEN
                        ),
                        now=CREATED_AT,
                        lease_expires_at=LEASE_EXPIRES_AT,
                    )
                    if receipt_kind == "event"
                    else store.claim_action(
                        "shared-id", payload_hash=payload_hash, created_at=CREATED_AT
                    )
                )
                return result.outcome
            except ReceiptConflict:
                return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = {
            future.result()
            for future in (
                executor.submit(claim, EVENT_HASH),
                executor.submit(claim, ACTION_HASH),
            )
        }

    assert outcomes == {ReceiptOutcome.CLAIMED, "CONFLICT"}


def test_event_completion_does_not_overwrite_conflicting_response(tmp_path):
    factory = FeishuCallbackStoreFactory(tmp_path / "event-conflict.db")
    original = {"ok": True, "result": "created"}

    with factory.session() as store:
        store.claim_event(
            "event-conflict",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        store.complete_event(
            "event-conflict",
            claim_token=FIRST_CLAIM_TOKEN,
            response=original,
            case_id=CASE_ID,
            completed_at=COMPLETED_AT,
        )
        replay = store.complete_event(
            "event-conflict",
            claim_token=FIRST_CLAIM_TOKEN,
            response=original,
            case_id=CASE_ID,
            completed_at=COMPLETED_AT,
        )
        assert replay.outcome is ReceiptOutcome.REPLAY
        assert replay.response == original

        with pytest.raises(ReceiptConflict):
            store.complete_event(
                "event-conflict",
                claim_token=FIRST_CLAIM_TOKEN,
                response={"ok": False},
                case_id=OTHER_CASE_ID,
                completed_at=COMPLETED_AT,
            )

        persisted = store.claim_event(
            "event-conflict",
            payload_hash=EVENT_HASH,
            claim_token=SECOND_CLAIM_TOKEN,
            now=ACTIVE_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )
        assert persisted.outcome is ReceiptOutcome.REPLAY
        assert persisted.response == original


def test_action_claim_complete_and_replay_are_idempotent(tmp_path):
    db_path = tmp_path / "action.db"
    factory = FeishuCallbackStoreFactory(db_path)
    response = {"ok": True, "result": "confirmed"}

    with factory.session() as store:
        claimed = store.claim_action(
            "action-001", payload_hash=ACTION_HASH, created_at=CREATED_AT
        )
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

        replay = store.claim_action(
            "action-001", payload_hash=ACTION_HASH, created_at=CREATED_AT
        )
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
        store.claim_action(
            "action-port", payload_hash=ACTION_HASH, created_at=CREATED_AT
        )

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
        store.claim_action(
            "action-port-retry", payload_hash=ACTION_HASH, created_at=CREATED_AT
        )
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
        store.claim_action(
            "action-confirm", payload_hash=ACTION_HASH, created_at=CREATED_AT
        )
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
        store.claim_action(
            "action-first", payload_hash=ACTION_HASH, created_at=CREATED_AT
        )
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

        store.claim_action(
            "action-second", payload_hash=EVENT_HASH, created_at=CREATED_AT
        )
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

        store.claim_action(
            "action-after-migration", payload_hash=ACTION_HASH, created_at=CREATED_AT
        )

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
            store.claim_action(
                action_id, payload_hash=ACTION_HASH, created_at=CREATED_AT
            )

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
        still_claimed = store.claim_action(
            "action-second", payload_hash=ACTION_HASH, created_at=CREATED_AT
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
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
            occurred_at=COMPLETED_AT,
        )
        assert completed.outcome is ReceiptOutcome.COMPLETED


def test_response_json_rejects_credentials_and_body_keys(tmp_path):
    db_path = tmp_path / "safe-json.db"
    factory = FeishuCallbackStoreFactory(db_path)

    with factory.session() as store:
        store.claim_event(
            "event-sensitive",
            payload_hash=EVENT_HASH,
            claim_token=FIRST_CLAIM_TOKEN,
            now=CREATED_AT,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
        with pytest.raises(ValueError):
            store.complete_event(
                "event-sensitive",
                claim_token=FIRST_CLAIM_TOKEN,
                response={"credentials": "must-not-persist"},
                case_id=CASE_ID,
                completed_at=COMPLETED_AT,
            )
        with pytest.raises(ValueError):
            store.complete_event(
                "event-sensitive",
                claim_token=FIRST_CLAIM_TOKEN,
                response={"card": {"body": "raw-callback"}},
                case_id=CASE_ID,
                completed_at=COMPLETED_AT,
            )

        claimed = store.claim_event(
            "event-sensitive",
            payload_hash=EVENT_HASH,
            claim_token=SECOND_CLAIM_TOKEN,
            now=ACTIVE_NOW,
            lease_expires_at=TAKEOVER_LEASE_EXPIRES_AT,
        )
        assert claimed.outcome is ReceiptOutcome.IN_PROGRESS

    database_bytes = db_path.read_bytes()
    assert b"must-not-persist" not in database_bytes
    assert b"raw-callback" not in database_bytes
