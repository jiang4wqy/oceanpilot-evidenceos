from uuid import uuid4

from oceanpilot.adapters.clock import SystemClock
from oceanpilot.application.chargeback_supervisor import ChargebackCaseState
from oceanpilot.application.scheduling import Clock


class InMemoryChargebackCaseStore:
    """Process-local chargeback case store (demo/HTTP entry).

    Not durable across restarts; T9 replaces it with a SQLite-backed store that
    adds audit and CAS behind the same ChargebackCaseStore protocol. Stamps
    ``created_at`` at creation (clock injectable) so the SLA deadline can be
    computed just like the durable store.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._cases: dict[str, ChargebackCaseState] = {}
        self._clock = clock if clock is not None else SystemClock()

    def create(self) -> str:
        case_id = str(uuid4())
        self._cases[case_id] = ChargebackCaseState(created_at=self._clock.now())
        return case_id

    def load(self, case_id: str) -> ChargebackCaseState | None:
        return self._cases.get(case_id)

    def save(self, case_id: str, state: ChargebackCaseState) -> None:
        self._cases[case_id] = state
