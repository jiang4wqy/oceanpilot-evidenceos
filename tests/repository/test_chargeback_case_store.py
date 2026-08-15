import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from oceanpilot.adapters.persistence.chargeback_schema import CHARGEBACK_SCHEMA_SQL
from oceanpilot.adapters.persistence.chargeback_sqlite import (
    ChargebackAuditEventType,
    SqliteChargebackCaseStore,
    initialize_chargeback_schema,
)
from oceanpilot.application.chargeback_supervisor import ChargebackCaseState
from oceanpilot.application.errors import (
    CaseNotFound,
    ConcurrentCaseWrite,
    NoEvidenceToWithdraw,
    PersistenceInvariantViolation,
)
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode

REASON = DisputeReasonCode.PRODUCT_NOT_RECEIVED
CODE_A = ChargebackEvidenceCode.TRANSACTION_RECEIPT
CODE_B = ChargebackEvidenceCode.DELIVERY_TRACKING
FIXED_MOMENT = datetime(2026, 8, 6, 4, 0, tzinfo=UTC)


class ScriptedClock:
    """Deterministic clock that can be told to fail on its Nth call."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment
        self.calls = 0
        self.raise_at: int | None = None

    def __call__(self) -> datetime:
        self.calls += 1
        if self.raise_at is not None and self.calls >= self.raise_at:
            raise RuntimeError("clock failure")
        return self._moment


@pytest.fixture
def cb_path(tmp_path: Path) -> Path:
    path = tmp_path / "chargeback.db"
    initialize_chargeback_schema(path)
    return path


@pytest.fixture
def store(cb_path: Path) -> SqliteChargebackCaseStore:
    return SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)


def _reason_state(store: SqliteChargebackCaseStore, case_id: str) -> ChargebackCaseState:
    state = store.load(case_id)
    assert state is not None
    state.reason_code = REASON
    store.save(case_id, state)
    return state


def test_create_persists_empty_case_at_revision_zero(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    loaded = store.load_with_revision(case_id)
    assert loaded is not None
    state, revision = loaded
    assert state.reason_code is None
    assert state.collected == set()
    assert revision == 0
    trail = store.audit_trail(case_id)
    assert [event.event_type for event in trail] == [ChargebackAuditEventType.CASE_OPENED]
    assert trail[0].case_revision == 0


def test_list_case_ids_returns_only_persisted_cases_newest_first(
    store: SqliteChargebackCaseStore,
) -> None:
    first = store.create()
    second = store.create()

    assert store.list_case_ids() == (second, first)


def test_reason_classification_bumps_revision_and_audits(
    store: SqliteChargebackCaseStore,
) -> None:
    case_id = store.create()
    _reason_state(store, case_id)
    loaded = store.load_with_revision(case_id)
    assert loaded is not None
    state, revision = loaded
    assert state.reason_code is REASON
    assert revision == 1
    trail = store.audit_trail(case_id)
    assert [event.event_type for event in trail] == [
        ChargebackAuditEventType.CASE_OPENED,
        ChargebackAuditEventType.REASON_CLASSIFIED,
    ]
    assert trail[1].detail == REASON.value
    assert trail[1].case_revision == 1


def test_state_survives_a_fresh_store_instance(cb_path: Path) -> None:
    writer = SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)
    case_id = writer.create()
    state = _reason_state(writer, case_id)
    state.collected.add(CODE_A)
    state.collected.add(CODE_B)
    writer.save(case_id, state)

    # A brand-new store object (new connections) sees the durable state.
    reader = SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)
    reloaded = reader.load(case_id)
    assert reloaded is not None
    assert reloaded.reason_code is REASON
    assert reloaded.collected == {CODE_A, CODE_B}


def test_replay_of_unchanged_state_is_a_noop(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collected.add(CODE_A)
    first = store.save_checked(case_id, state, expected_revision=1)
    assert first == 2
    audit_before = store.audit_trail(case_id)

    # Saving the identical state again changes nothing.
    replay = store.save_checked(case_id, state, expected_revision=2)
    assert replay == 2
    assert store.current_revision(case_id) == 2
    assert store.audit_trail(case_id) == audit_before


def test_save_checked_rejects_a_stale_revision(cb_path: Path) -> None:
    writer = SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)
    case_id = writer.create()
    _reason_state(writer, case_id)  # revision 1

    # Two actors both read revision 1, then both try to append different evidence.
    actor_one = SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)
    actor_two = SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)
    state_one = actor_one.load(case_id)
    state_two = actor_two.load(case_id)
    assert state_one is not None and state_two is not None
    state_one.collected.add(CODE_A)
    state_two.collected.add(CODE_B)

    assert actor_one.save_checked(case_id, state_one, expected_revision=1) == 2
    with pytest.raises(ConcurrentCaseWrite):
        actor_two.save_checked(case_id, state_two, expected_revision=1)

    # Only the winner's write is durable.
    final = writer.load(case_id)
    assert final is not None
    assert final.collected == {CODE_A}
    assert writer.current_revision(case_id) == 2


def test_evidence_is_append_only(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collected.add(CODE_A)
    store.save(case_id, state)

    shrunk = ChargebackCaseState(reason_code=REASON, collected=set())
    with pytest.raises(PersistenceInvariantViolation):
        store.save(case_id, shrunk)
    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.collected == {CODE_A}


def test_reason_is_immutable_once_confirmed(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = store.load(case_id)
    assert state is not None
    state.reason_code = REASON
    state.reason_confirmed = True
    store.save(case_id, state)  # reason set and confirmed

    reclassified = ChargebackCaseState(
        reason_code=DisputeReasonCode.FRAUD_CARD_NOT_PRESENT,
        collected=set(),
        reason_confirmed=True,
    )
    with pytest.raises(PersistenceInvariantViolation):
        store.save(case_id, reclassified)
    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.reason_code is REASON
    assert reloaded.reason_confirmed is True


def test_reason_can_be_corrected_before_confirmation(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    _reason_state(store, case_id)  # proposes REASON, not yet confirmed

    # A human corrects the proposed reason and confirms the corrected one.
    corrected = ChargebackCaseState(
        reason_code=DisputeReasonCode.FRAUD_CARD_NOT_PRESENT,
        collected=set(),
        reason_confirmed=True,
    )
    store.save(case_id, corrected)
    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.reason_code is DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    assert reloaded.reason_confirmed is True
    trail = [event.event_type for event in store.audit_trail(case_id)]
    assert ChargebackAuditEventType.REASON_CONFIRMED in trail


def test_confirmation_persists_and_is_audited(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    _reason_state(store, case_id)  # proposed, unconfirmed
    proposed = store.load(case_id)
    assert proposed is not None
    assert proposed.reason_confirmed is False

    proposed.reason_confirmed = True
    store.save(case_id, proposed)  # confirm-only change
    confirmed = store.load(case_id)
    assert confirmed is not None
    assert confirmed.reason_confirmed is True
    assert [event.event_type for event in store.audit_trail(case_id)] == [
        ChargebackAuditEventType.CASE_OPENED,
        ChargebackAuditEventType.REASON_CLASSIFIED,
        ChargebackAuditEventType.REASON_CONFIRMED,
    ]


def test_confirmation_cannot_be_revoked(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = store.load(case_id)
    assert state is not None
    state.reason_code = REASON
    state.reason_confirmed = True
    store.save(case_id, state)

    revoked = ChargebackCaseState(reason_code=REASON, collected=set(), reason_confirmed=False)
    with pytest.raises(PersistenceInvariantViolation):
        store.save(case_id, revoked)


def test_failed_write_rolls_back_atomically(cb_path: Path) -> None:
    clock = ScriptedClock(FIXED_MOMENT)
    store = SqliteChargebackCaseStore(cb_path, clock=clock)
    case_id = store.create()
    _reason_state(store, case_id)  # revision 1
    revision_before = store.current_revision(case_id)
    audit_before = store.audit_trail(case_id)

    # Fail on the audit-timestamp call that fires *after* the case UPDATE runs,
    # so a partial write exists inside the transaction and must be rolled back.
    clock.raise_at = clock.calls + 2
    state = store.load(case_id)
    assert state is not None
    state.collected.add(CODE_A)
    with pytest.raises(RuntimeError):
        store.save(case_id, state)

    assert store.current_revision(case_id) == revision_before
    assert store.audit_trail(case_id) == audit_before
    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.collected == set()


def test_unknown_case_is_reported_consistently(store: SqliteChargebackCaseStore) -> None:
    assert store.load("00000000-0000-4000-8000-000000000099") is None
    assert store.load_with_revision("missing") is None
    with pytest.raises(CaseNotFound):
        store.current_revision("missing")
    with pytest.raises(CaseNotFound):
        store.save("missing", ChargebackCaseState(reason_code=REASON))


def test_audit_trail_is_ordered_and_revision_tagged(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collected.add(CODE_A)
    state.collected.add(CODE_B)
    store.save(case_id, state)

    trail = store.audit_trail(case_id)
    assert [event.seq for event in trail] == [0, 1, 2, 3]
    assert [event.event_type for event in trail] == [
        ChargebackAuditEventType.CASE_OPENED,
        ChargebackAuditEventType.REASON_CLASSIFIED,
        ChargebackAuditEventType.EVIDENCE_ADDED,
        ChargebackAuditEventType.EVIDENCE_ADDED,
    ]
    # Both evidence rows share the single revision bump they were written under.
    assert {event.case_revision for event in trail[2:]} == {2}
    assert {event.detail for event in trail[2:]} == {CODE_A.value, CODE_B.value}


def test_finalization_persists_and_is_audited(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collection_finalized = True
    store.save(case_id, state)

    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.collection_finalized is True
    trail = [event.event_type for event in store.audit_trail(case_id)]
    assert ChargebackAuditEventType.COLLECTION_FINALIZED in trail


def test_finalization_cannot_be_revoked(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collection_finalized = True
    store.save(case_id, state)

    revoked = ChargebackCaseState(reason_code=REASON, collected=set(), collection_finalized=False)
    with pytest.raises(PersistenceInvariantViolation):
        store.save(case_id, revoked)


def test_created_at_is_loaded_for_deadline_tracking(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    state = store.load(case_id)
    assert state is not None
    assert state.created_at == FIXED_MOMENT


def test_withdraw_latest_evidence_is_atomic_and_audited(
    store: SqliteChargebackCaseStore,
) -> None:
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collected.add(CODE_A)
    store.save(case_id, state)
    state = store.load(case_id)
    assert state is not None
    state.collected.add(CODE_B)
    state.collection_finalized = True
    store.save(case_id, state)
    revision_before = store.current_revision(case_id)

    withdrawn = store.withdraw_latest_evidence(case_id, CODE_B)

    assert withdrawn.collected == {CODE_A}
    assert withdrawn.collection_finalized is False
    assert store.current_revision(case_id) == revision_before + 1
    event = store.audit_trail(case_id)[-1]
    assert event.event_type == ChargebackAuditEventType.EVIDENCE_WITHDRAWN
    assert event.detail == CODE_B.value
    assert event.case_revision == revision_before + 1


def test_withdrawal_survives_reopen(cb_path: Path) -> None:
    writer = SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)
    case_id = writer.create()
    state = _reason_state(writer, case_id)
    state.collected.update({CODE_A, CODE_B})
    writer.save(case_id, state)
    # New evidence rows in one save are inserted in sorted code order; CODE_A is
    # the deterministic latest item for these two enum values.
    latest = ChargebackEvidenceCode(writer.audit_trail(case_id)[-1].detail or "")
    writer.withdraw_latest_evidence(case_id, latest)

    reader = SqliteChargebackCaseStore(cb_path, clock=lambda: FIXED_MOMENT)
    reopened = reader.load(case_id)
    assert reopened is not None
    assert latest not in reopened.collected
    assert reader.audit_trail(case_id)[-1].event_type == "EVIDENCE_WITHDRAWN"


def test_duplicate_withdrawal_cannot_remove_the_next_item(
    store: SqliteChargebackCaseStore,
) -> None:
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collected.add(CODE_A)
    store.save(case_id, state)
    state = store.load(case_id)
    assert state is not None
    state.collected.add(CODE_B)
    store.save(case_id, state)

    store.withdraw_latest_evidence(case_id, CODE_B)
    with pytest.raises(ConcurrentCaseWrite):
        store.withdraw_latest_evidence(case_id, CODE_B)

    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.collected == {CODE_A}


def test_withdraw_without_evidence_is_a_conflict(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    with pytest.raises(NoEvidenceToWithdraw):
        store.withdraw_latest_evidence(case_id, CODE_A)


def test_failed_withdrawal_rolls_back_delete_revision_and_audit(cb_path: Path) -> None:
    clock = ScriptedClock(FIXED_MOMENT)
    store = SqliteChargebackCaseStore(cb_path, clock=clock)
    case_id = store.create()
    state = _reason_state(store, case_id)
    state.collected.add(CODE_A)
    store.save(case_id, state)
    revision_before = store.current_revision(case_id)
    audit_before = store.audit_trail(case_id)
    clock.raise_at = clock.calls + 2

    with pytest.raises(RuntimeError, match="clock failure"):
        store.withdraw_latest_evidence(case_id, CODE_A)

    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.collected == {CODE_A}
    assert store.current_revision(case_id) == revision_before
    assert store.audit_trail(case_id) == audit_before


def test_initialize_migrates_legacy_audit_constraint_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "legacy-chargeback.db"
    legacy_sql = CHARGEBACK_SCHEMA_SQL.replace(
        "'EVIDENCE_ADDED','EVIDENCE_WITHDRAWN','COLLECTION_FINALIZED'",
        "'EVIDENCE_ADDED','COLLECTION_FINALIZED'",
    )
    connection = sqlite3.connect(path)
    connection.executescript(legacy_sql)
    connection.close()
    legacy = SqliteChargebackCaseStore(path, clock=lambda: FIXED_MOMENT)
    case_id = legacy.create()
    state = _reason_state(legacy, case_id)
    state.collected.add(CODE_A)
    legacy.save(case_id, state)
    audit_before = legacy.audit_trail(case_id)

    initialize_chargeback_schema(path)

    migrated = SqliteChargebackCaseStore(path, clock=lambda: FIXED_MOMENT)
    assert migrated.audit_trail(case_id) == audit_before
    migrated.withdraw_latest_evidence(case_id, CODE_A)
    connection = sqlite3.connect(path)
    schema_sql = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name = 'chargeback_audit'"
    ).fetchone()[0]
    connection.close()
    assert "EVIDENCE_WITHDRAWN" in schema_sql
