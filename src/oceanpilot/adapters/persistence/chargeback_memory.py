from uuid import uuid4

from oceanpilot.application.chargeback_supervisor import ChargebackCaseState


class InMemoryChargebackCaseStore:
    """Process-local chargeback case store (demo/HTTP entry).

    Not durable across restarts; T9 replaces it with a SQLite-backed store that
    adds audit and CAS behind the same ChargebackCaseStore protocol.
    """

    def __init__(self) -> None:
        self._cases: dict[str, ChargebackCaseState] = {}

    def create(self) -> str:
        case_id = str(uuid4())
        self._cases[case_id] = ChargebackCaseState()
        return case_id

    def load(self, case_id: str) -> ChargebackCaseState | None:
        return self._cases.get(case_id)

    def save(self, case_id: str, state: ChargebackCaseState) -> None:
        self._cases[case_id] = state
