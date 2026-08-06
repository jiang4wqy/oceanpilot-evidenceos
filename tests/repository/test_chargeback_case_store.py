from datetime import UTC, datetime
from pathlib import Path

import pytest

from oceanpilot.adapters.persistence.chargeback_sqlite import (
    ChargebackAuditEventType,
    SqliteChargebackCaseStore,
    initialize_chargeback_schema,
)
from oceanpilot.application.chargeback_supervisor import ChargebackCaseState
from oceanpilot.application.errors import (
    CaseNotFound,
    ConcurrentCaseWrite,
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


def test_reason_is_immutable_once_set(store: SqliteChargebackCaseStore) -> None:
    case_id = store.create()
    _reason_state(store, case_id)
    reclassified = ChargebackCaseState(
        reason_code=DisputeReasonCode.FRAUD_CARD_NOT_PRESENT,
        collected=set(),
    )
    with pytest.raises(PersistenceInvariantViolation):
        store.save(case_id, reclassified)
    reloaded = store.load(case_id)
    assert reloaded is not None
    assert reloaded.reason_code is REASON


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
