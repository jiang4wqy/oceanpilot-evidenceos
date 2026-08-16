from threading import RLock
from uuid import uuid4

from oceanpilot.adapters.clock import SystemClock
from oceanpilot.application.chargeback_ports import ChargebackAuditEvent
from oceanpilot.application.chargeback_supervisor import ChargebackCaseState
from oceanpilot.application.errors import (
    CaseNotFound,
    ConcurrentCaseWrite,
    NoEvidenceToWithdraw,
    PersistenceInvariantViolation,
)
from oceanpilot.application.scheduling import Clock
from oceanpilot.domain.chargeback import CardNetwork, ChargebackEvidenceCode


def _snapshot(state: ChargebackCaseState) -> ChargebackCaseState:
    """Copy mutable case state at the adapter boundary."""
    return ChargebackCaseState(
        reason_code=state.reason_code,
        collected=set(state.collected),
        created_at=state.created_at,
        reason_confident=state.reason_confident,
        reason_confirmed=state.reason_confirmed,
        collection_finalized=state.collection_finalized,
        card_network=state.card_network,
        revision=state.revision,
    )


class InMemoryChargebackCaseStore:
    """Process-local store with the same command semantics as SQLite.

    Snapshot reads prevent callers from mutating stored state before ``save``.
    An explicit evidence order supports deterministic latest-item withdrawal in
    demos that opt out of durable SQLite.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._cases: dict[str, ChargebackCaseState] = {}
        self._evidence_order: dict[str, list[ChargebackEvidenceCode]] = {}
        self._audit: dict[str, list[ChargebackAuditEvent]] = {}
        self._revision: dict[str, int] = {}
        self._clock = clock if clock is not None else SystemClock()
        self._lock = RLock()

    def create(self) -> str:
        with self._lock:
            case_id = str(uuid4())
            moment = self._clock.now()
            self._cases[case_id] = ChargebackCaseState(created_at=moment)
            self._evidence_order[case_id] = []
            self._revision[case_id] = 0
            self._audit[case_id] = [
                ChargebackAuditEvent(
                    seq=0,
                    event_type="CASE_OPENED",
                    detail=None,
                    case_revision=0,
                    occurred_at=moment,
                )
            ]
            return case_id

    def list_case_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(reversed(self._cases))

    def load(self, case_id: str) -> ChargebackCaseState | None:
        with self._lock:
            state = self._cases.get(case_id)
            return _snapshot(state) if state is not None else None

    def save(self, case_id: str, state: ChargebackCaseState) -> None:
        if not isinstance(state, ChargebackCaseState):
            raise PersistenceInvariantViolation()
        with self._lock:
            current = self._cases.get(case_id)
            if current is None:
                raise CaseNotFound()
            stored = set(current.collected)
            incoming = set(state.collected)
            if not stored.issubset(incoming):
                raise PersistenceInvariantViolation()
            if current.reason_confirmed and state.reason_code != current.reason_code:
                raise PersistenceInvariantViolation()
            if current.reason_confirmed and not state.reason_confirmed:
                raise PersistenceInvariantViolation()
            if current.collection_finalized and not state.collection_finalized:
                raise PersistenceInvariantViolation()

            new_codes = sorted(incoming - stored, key=lambda code: code.value)
            changed = state != current
            if changed:
                self._revision[case_id] += 1
            revision = self._revision[case_id]
            state.revision = revision
            self._cases[case_id] = _snapshot(state)
            for code in new_codes:
                self._evidence_order[case_id].append(code)
                self._append_audit(case_id, "EVIDENCE_ADDED", code.value, revision)

    def withdraw_latest_evidence(
        self,
        case_id: str,
        expected_evidence_code: ChargebackEvidenceCode,
    ) -> ChargebackCaseState:
        if not isinstance(expected_evidence_code, ChargebackEvidenceCode):
            raise PersistenceInvariantViolation()
        with self._lock:
            state = self._cases.get(case_id)
            if state is None:
                raise CaseNotFound()
            order = self._evidence_order[case_id]
            if not order:
                raise NoEvidenceToWithdraw()
            latest = order[-1]
            if latest != expected_evidence_code:
                raise ConcurrentCaseWrite()
            order.pop()
            state.collected.remove(latest)
            state.collection_finalized = False
            self._revision[case_id] += 1
            state.revision = self._revision[case_id]
            self._append_audit(
                case_id,
                "EVIDENCE_WITHDRAWN",
                latest.value,
                self._revision[case_id],
            )
            return _snapshot(state)

    def set_card_network(
        self,
        case_id: str,
        card_network: CardNetwork,
        expected_revision: int,
    ) -> ChargebackCaseState:
        if not isinstance(card_network, CardNetwork) or type(expected_revision) is not int:
            raise PersistenceInvariantViolation()
        with self._lock:
            state = self._cases.get(case_id)
            if state is None:
                raise CaseNotFound()
            if state.card_network is card_network:
                return _snapshot(state)
            if self._revision[case_id] != expected_revision:
                raise ConcurrentCaseWrite()
            self._revision[case_id] += 1
            state.card_network = card_network
            state.revision = self._revision[case_id]
            self._append_audit(
                case_id,
                "CARD_NETWORK_SELECTED",
                card_network.value,
                state.revision,
            )
            return _snapshot(state)

    def audit_trail(self, case_id: str) -> tuple[ChargebackAuditEvent, ...]:
        with self._lock:
            return tuple(self._audit.get(case_id, ()))

    def _append_audit(
        self,
        case_id: str,
        event_type: str,
        detail: str | None,
        revision: int,
    ) -> None:
        trail = self._audit[case_id]
        trail.append(
            ChargebackAuditEvent(
                seq=len(trail),
                event_type=event_type,
                detail=detail,
                case_revision=revision,
                occurred_at=self._clock.now(),
            )
        )
